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

    # Disambiguate when --marker reports AMBIGUOUS (segment names from --list):
    backend/.venv/Scripts/python.exe scripts/read_kit_revision.py \
        w7 --segment "12-2024--sha256-1a2b3c4d5e6f"

Reads the SAME store the backend uses (FORM_KITS_MODE / FORM_KITS_LOCAL_ROOT /
FORM_KITS_GCS_BUCKET), so a deployed lookup needs those env vars set and your
own credentials to have read access on the bucket.

Prints the schema JSON on stdout. Exit codes: 0 = schema printed (or markers
listed); 1 = the store was READABLE but has no such revision; 2 = RETRIEVAL
FAILED (the store could not be read -- NOT evidence the revision is absent);
3 = AMBIGUOUS, several distinct revisions answer to this marker and the record
alone cannot say which (never guesses -- see --segment).

An edition_date is NOT unique: an author can revise fields without bumping it,
so one marker can name several stored revisions. Exit 3 exists so that case is
reported honestly instead of returning a confident wrong schema.
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


class AmbiguousRevision(Exception):
    """More than one stored revision answers to this marker.

    A confirmation record carries the PLAIN marker, but an edition_date is not
    unique -- an author can revise fields without bumping it, so several stored
    revisions may share one. When that happens the record alone cannot say WHICH
    one it meant, and guessing would hand an operator a confident wrong schema.
    For a legal record that is strictly worse than an honest "cannot tell", so
    this is raised instead, carrying the candidates for a human to disambiguate.
    """

    def __init__(self, candidates: list[str]):
        self.candidates = candidates
        super().__init__(f"{len(candidates)} revisions match this marker")


async def _resolve(store, kit_id: str, marker: str) -> tuple[str, dict]:
    """(source, schema) for `marker` -- the live schema when it still matches,
    else the archived copy.

    Raises FormKitNotFound when nothing carries the marker, and
    AmbiguousRevision when SEVERAL stored revisions do (never picks one).
    """
    from backend.services.form_kits import FormKitNotFound, encode_marker
    from backend.utils.confirmation_logger import resolve_edition_marker

    base = encode_marker(marker)
    candidates: list[tuple[str, dict]] = []

    # The CURRENT schema is a candidate when it still answers to this marker --
    # the common case is a kit that was never revised after the record was
    # written.
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
        # edition_date and its archived directory name compare the same way.
        if live_marker and encode_marker(live_marker) == base:
            candidates.append(("current", current))

    # Every ARCHIVED revision filed under this marker: the plain segment, plus
    # any "<marker>--<fingerprint>" sibling written when a later revision
    # collided on the same marker. A record naming the second revision carries
    # the same plain marker as the first, so the siblings MUST be searched --
    # looking up only the plain segment silently returns the first revision's
    # schema for a record that meant the second.
    for segment in await store.list_archived_markers(kit_id):
        if segment == base or segment.startswith(f"{base}--"):
            archived = await store.load_archived_revision_or_none(kit_id, segment)
            if archived is not None:
                candidates.append((f"archive:{segment}", archived))

    if not candidates:
        raise FormKitNotFound(
            f"No revision found for {kit_id} at marker {marker}"
        )
    # Identical bytes under several segments are one revision, not an ambiguity.
    distinct = []
    for source, schema in candidates:
        if not any(schema == seen for _s, seen in distinct):
            distinct.append((source, schema))
    if len(distinct) > 1:
        raise AmbiguousRevision([source for source, _ in distinct])
    return distinct[0]


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
    parser.add_argument(
        "--segment",
        help="read ONE exact archived segment as printed by --list (e.g. "
             "'12-2024--sha256-1a2b3c4d5e6f'). Use this to disambiguate when "
             "--marker reports AMBIGUOUS.",
    )
    args = parser.parse_args()

    if not args.list and not args.marker and not args.segment:
        parser.error("one of --marker, --segment or --list is required")

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

    if args.segment:
        # Exact-segment read: no marker matching, no ambiguity -- the operator
        # has already chosen which sibling they want from --list.
        try:
            schema = asyncio.run(
                store.load_archived_revision(args.kit_id, args.segment)
            )
        except FormKitNotFound:
            print(f"No archived segment '{args.segment}' for {args.kit_id} "
                  "(run --list to see what is stored).", file=sys.stderr)
            return 1
        except FormKitStoreError as exc:
            print(f"RETRIEVAL FAILED for {args.kit_id}/{args.segment}: the store "
                  f"could not be read ({exc}). This is NOT evidence the "
                  "revision is absent.", file=sys.stderr)
            return 2
        print(f"# source: archive:{args.segment}", file=sys.stderr)
        print(json.dumps(schema, indent=2, ensure_ascii=False))
        return 0

    try:
        source, schema = asyncio.run(_resolve(store, args.kit_id, args.marker))
    except AmbiguousRevision as exc:
        # NEVER pick one. The marker on a confirmation record is not unique when
        # an author revised fields without bumping the edition date, and handing
        # over a confident wrong schema is the worst outcome for a legal record.
        print(f"AMBIGUOUS for {args.kit_id}/{args.marker}: "
              f"{len(exc.candidates)} distinct revisions answer to this marker "
              f"({', '.join(exc.candidates)}). The record's marker alone cannot "
              "say which one it was confirmed against -- inspect each with "
              "--segment <name> and use the confirmation event's timestamp "
              "against each revision's archived metadata to choose.",
              file=sys.stderr)
        return 3
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
