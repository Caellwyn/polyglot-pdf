"""Retrieve the EXACT schema a confirmation record was confirmed against
(bd polyglot-pdf-w3zw).

The confirmation trail records `kit_id` + a revision marker (`edition_date`, or
a `sha256:<12hex>` shape fingerprint for a form with no government edition --
see docs/standards/confirmation-and-audit.md). A marker is not a storage
address, and kit storage is ONE slot per kit, so before the revision archive a
republish destroyed the schema an old record pointed at. This script is the
operational read that closes that loop: given a record's kit_id + marker, it
returns the schema of THAT revision -- the current one when the marker still
matches it, else the archived copy.

Why it matters: answering "what did field p1_line3a actually ask?" months later
is the whole point of pinning the trail to a revision. Without retrieval the
pin names a revision nobody can produce.

Usage (from the repo root, with the backend venv):

    # Take kit_id + edition_date/marker straight from a confirmation event:
    backend/.venv/Scripts/python.exe scripts/read_kit_revision.py \
        w7 --marker "12/2024"

    # A fingerprint-era record (custom/firm form with no government edition):
    backend/.venv/Scripts/python.exe scripts/read_kit_revision.py \
        acme-intake --marker "sha256:1a2b3c4d5e6f"

    # What revisions does this kit have archived?
    backend/.venv/Scripts/python.exe scripts/read_kit_revision.py w7 --list

Reads the SAME store the backend uses (FORM_KITS_MODE / FORM_KITS_LOCAL_ROOT /
FORM_KITS_GCS_BUCKET), so a deployed lookup needs those env vars set and your
own credentials to have read access on the bucket.

Prints the schema JSON on stdout. Exit codes: 0 = schema printed (or markers
listed); 1 = the store was READABLE but has no such revision; 2 = RETRIEVAL
FAILED (the store could not be read -- NOT evidence the revision is absent).
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

# Make `backend.*` importable when run as `python scripts/read_kit_revision.py`
# from the repo root (or anywhere -- resolve relative to this file).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


async def _resolve(store, kit_id: str, marker: str) -> tuple[str, dict]:
    """(source, schema) for `marker`: the live schema when it still matches,
    else the archived copy. Raises FormKitNotFound when neither has it."""
    from backend.services.form_kits import FormKitNotFound, encode_marker
    from backend.utils.confirmation_logger import resolve_edition_marker

    # Try the CURRENT schema first: the common case is a kit that has not been
    # revised since the record was written, and it costs one read.
    try:
        current = await store.load_schema(kit_id, _schema_file(await store.load_metadata(kit_id)))
    except FormKitNotFound:
        current = None
    if isinstance(current, dict):
        form_meta = current.get("form_metadata")
        live_marker = resolve_edition_marker(
            form_meta.get("edition_date") if isinstance(form_meta, dict) else None,
            current,
        )
        # Compare ENCODED: the archive keys on the encoded segment, so an
        # edition_date and its archived directory name must compare the same way.
        if live_marker and encode_marker(live_marker) == encode_marker(marker):
            return "current", current

    return "archive", await store.load_archived_revision(kit_id, marker)


def _schema_file(meta) -> str:
    from backend.services.form_kits import safe_filename

    meta = meta if isinstance(meta, dict) else {}
    return safe_filename(meta.get("schema") or "schema.json", "schema.json")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Retrieve the schema a confirmation record was confirmed "
                    "against, by kit id + revision marker."
    )
    parser.add_argument("kit_id", help="the kit_id from the confirmation event")
    parser.add_argument(
        "--marker",
        help="the event's edition_date (e.g. '12/2024') or fingerprint "
             "(e.g. 'sha256:1a2b3c4d5e6f')",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list the archived revision markers for this kit instead of "
             "retrieving one",
    )
    args = parser.parse_args()

    if not args.list and not args.marker:
        parser.error("either --marker or --list is required")

    from backend.services.form_kits import (
        FormKitNotFound,
        FormKitStoreError,
        get_form_kit_store,
    )

    try:
        store = get_form_kit_store()
    except Exception as exc:  # misconfigured store env -- a FAILURE, not absence
        print(f"RETRIEVAL FAILED: could not open the form-kit store ({exc}).",
              file=sys.stderr)
        return 2

    if args.list:
        try:
            markers = asyncio.run(store.list_archived_markers(args.kit_id))
        except FormKitStoreError as exc:
            print(f"RETRIEVAL FAILED for {args.kit_id}: could not list archived "
                  f"revisions ({exc}). This is NOT evidence there are none.",
                  file=sys.stderr)
            return 2
        if not markers:
            print(f"No archived revisions for {args.kit_id} (the kit may never "
                  "have been revised -- its CURRENT schema is still the only "
                  "one).", file=sys.stderr)
            return 1
        for m in markers:
            print(m)
        return 0

    try:
        source, schema = asyncio.run(_resolve(store, args.kit_id, args.marker))
    except FormKitNotFound:
        print(f"No revision found for {args.kit_id} at marker {args.marker}. "
              "The kit's current schema does not match this marker and no "
              "archived copy carries it (a revision superseded BEFORE the "
              "archive shipped is not recoverable).", file=sys.stderr)
        return 1
    except FormKitStoreError as exc:
        # A store failure and an absent revision are OPPOSITE answers for a
        # legal-retrieval tool -- never conflate them (the read_confirmations
        # lesson, bd z2is).
        print(f"RETRIEVAL FAILED for {args.kit_id}/{args.marker}: the store "
              f"could not be read ({exc}). This is NOT evidence the revision "
              "is absent.", file=sys.stderr)
        return 2

    print(f"# source: {source}", file=sys.stderr)
    print(json.dumps(schema, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
