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
import re
import sys
from pathlib import Path

# Make `backend.*` importable when run as `python scripts/read_kit_revision.py`
# from the repo root (or anywhere -- resolve relative to this file).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# A disambiguated sibling is always "<marker>--<fingerprint>" where the suffix
# is an ENCODED `sha256:<12 hex>` marker -- i.e. exactly "sha256-" + 12 hex
# chars after encode_marker turns the colon into a dash. Matching that exact
# shape (rather than any "--" run) is what keeps two UNRELATED markers apart:
# `encode_marker` collapses any run of unsafe characters to a single "-", so an
# ordinary raw marker like "12/2024//rev2" also encodes with a "--" in it and
# would otherwise look like a sibling of "12/2024", producing a FALSE ambiguity
# (fresh-eyes round 3, reproduced live).
_SIBLING_SUFFIX_RE = re.compile(r"^sha256-[0-9a-f]{12}$")

# The digest `sibling_marker` appends to a TRIMMED base so the trim stays
# verifiable (8 hex chars of sha256 over the full encoded base).
_BASE_TAG_RE = re.compile(r"^[0-9a-f]{8}$")


def _sibling_match(segment: str, base: str) -> str:
    """Whether `segment` MIGHT be, or PROVABLY IS, a disambiguated sibling of
    `base`. Returns "no", "loose", or "exact" (bd polyglot-pdf-amojb).

    Deliberately a loose "might" for the non-exact case, not a verified "is"
    -- and that asymmetry is the whole design:

    A sibling segment is only ever WRITTEN when the plain-base segment already
    exists holding different bytes (see `_archive_published_revision`). So
    whenever a sibling exists at all, the plain base exists too, retrieval
    collects >= 2 distinct candidates, and `_resolve` raises AmbiguousRevision.
    A "loose" match can therefore NEVER cause a schema to be returned on its
    own -- it only ever ADDS a candidate, pushing toward the honest "cannot
    tell" answer and the operator's --segment read.

    That means over-matching "loose" is SAFE and under-matching is not: a
    missed sibling silently drops the candidate count to 1 and hands back a
    single revision as if it were unambiguous, which on a legal surface is the
    one outcome that must never happen (verified in review by stubbing this to
    "no" -- retrieval then resolved to the first revision alone).

    Earlier versions tried to VERIFY the relationship exactly -- exact base,
    then prefix, then prefix-at-trim-budget, then a digest of the raw marker.
    Every one admitted a wrong-schema case or hid a real sibling, because the
    writer's trim is lossy and the reader cannot invert it in the general
    case. ONE case CAN be verified, but not from shape alone: when
    `seg_base == base` exactly, no lossy trim was involved in the SEGMENT'S
    TEXT -- but that alone does not prove this segment was actually WRITTEN
    by `sibling_marker` for THIS marker (an unrelated kit's raw edition_date
    could coincidentally contain the same "<base>--sha256-<12hex>" shape).
    This function returns "exact" for that shape match, but `_resolve` does
    NOT trust it on shape alone -- it re-derives the archived schema's own
    content fingerprint and recomputes `sibling_marker(marker, fingerprint)`,
    demoting to "loose" (bd polyglot-pdf-amojb round 2, Opus cross-surface
    review) unless the recomputed segment matches byte-for-byte. That closes
    the provenance gap the SHAPE-only "exact" left open. Every other
    relationship (trimmed-base prefix match either direction) stays "loose"
    unconditionally: those genuinely cannot be verified even with the
    archived content in hand, since the trim is lossy in both directions.

    The one hard requirement for either match is the fingerprint suffix,
    which keeps an ordinary marker that merely encodes with a "--" run from
    matching every base.
    """
    marker_pos = segment.rfind("--")
    if marker_pos <= 0:
        return "no"
    seg_base, suffix = segment[:marker_pos], segment[marker_pos + 2:]
    if not _SIBLING_SUFFIX_RE.fullmatch(suffix):
        return "no"
    if seg_base == base:
        return "exact"
    # Strip the writer's optional "-<8hex>" trim tag before comparing: a
    # trimmed base is NOT a prefix of the plain base while that tag is on it.
    head, sep, tag = seg_base.rpartition("-")
    if sep and _BASE_TAG_RE.fullmatch(tag):
        seg_base = head
    # Compare BOTH ways: encode_marker truncates both sides at the cap, so
    # either can be the shorter one.
    if base.startswith(seg_base) or seg_base.startswith(base):
        return "loose"
    return "no"


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
        form_meta = form_meta if isinstance(form_meta, dict) else {}
        # ALL THREE ranks, exactly as the confirmation record resolved them
        # (bd polyglot-pdf-xzw5). Omitting author_version here computed a
        # sha256: fingerprint for a kit whose records name "2026-08-07", so a
        # LIVE author-versioned revision was unfindable -- the audit trail
        # naming a revision this tool could not produce, which is the precise
        # failure the archive exists to prevent. The archive WRITER was fixed
        # in this bead; this reader was the other half.
        live_marker = resolve_edition_marker(
            form_meta.get("edition_date"),
            current,
            form_meta.get("author_version"),
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
    # Archived revisions filed under this marker. THREE kinds of match, and
    # the difference decides what may be returned:
    #   EXACT   -- the segment IS our encoded marker (the plain base), OR an
    #              UNTRIMMED sibling whose seg_base is byte-identical to it
    #              AND whose archived content re-derives that exact segment
    #              via sibling_marker (bd polyglot-pdf-amojb: shape alone is
    #              not enough -- an unrelated kit's marker could coincidentally
    #              LOOK like a sibling of ours; the content-fingerprint
    #              re-derivation below proves this segment was actually
    #              WRITTEN as our sibling, not merely shaped like one).
    #              Authoritative either way.
    #   LOOSE   -- a "<base>--<fingerprint>" sibling whose base was TRIMMED,
    #              so it only MIGHT be ours. The writer's trim is lossy for
    #              this case, so it cannot be verified (three designs tried
    #              and each admitted a wrong answer). It is only ever
    #              CORROBORATING: enough to prove ambiguity, never enough to
    #              be the answer on its own.
    from backend.services.form_kits import sibling_marker

    exact_count = 0
    for segment in await store.list_archived_markers(kit_id):
        is_exact = segment == base
        if not is_exact:
            match = _sibling_match(segment, base)
            if match == "no":
                continue
            is_exact = match == "exact"
        archived = await store.load_archived_revision_or_none(kit_id, segment)
        if archived is None:
            continue
        if is_exact and not (segment == base):
            # PROVENANCE, not just shape (bd polyglot-pdf-amojb round 2, Opus
            # cross-surface review): `seg_base == base` only proves the
            # CANDIDATE SEGMENT'S TEXT matches the shape sibling_marker would
            # produce for an untrimmed base -- it does NOT prove THIS segment
            # was actually WRITTEN by sibling_marker for THIS marker. An
            # unrelated kit's edition_date that happens to literally contain
            # "<base>--sha256-<12hex>" (a pasted-in string, a coincidental
            # collision) would pass the shape check and silently return that
            # kit's own schema -- exactly the "confident wrong schema" this
            # tool's whole design exists to prevent. Recomputing the sibling
            # segment FROM the archived schema's own content-derived
            # fingerprint (the same value the WRITER used to build it) closes
            # the loop: only a segment that a real write of THIS schema under
            # THIS marker could have produced counts as exact. A segment that
            # merely LOOKS like one, but was not, demotes to loose --
            # corroborating an ambiguity, never returned on its own.
            fingerprint = resolve_edition_marker(None, archived) or "revision"
            is_exact = sibling_marker(marker, fingerprint) == segment
        candidates.append((f"archive:{segment}", archived))
        if is_exact:
            exact_count += 1
    if current is not None and any(s == "current" for s, _ in candidates):
        exact_count += 1  # the live schema matched the marker exactly

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
    if exact_count == 0:
        # The single candidate came ONLY from a loose sibling match, so it may
        # belong to a different marker entirely -- e.g. a revision published
        # under "12/20" when the record names "12/2024". Returning it would be
        # the confident-wrong-answer failure this tool exists to avoid.
        raise FormKitNotFound(
            f"No revision found for {kit_id} at marker {marker} "
            f"(a stored revision resembles it but cannot be confirmed as the "
            f"same marker; use --list/--segment to inspect)"
        )
    return distinct[0]


async def _archived_published_at(store, kit_id: str, segment: str):
    """The archived revision's publish date, or None when unavailable.

    Best-effort: this only enriches an error message, so a missing or
    unreadable metadata.json degrades to None rather than turning an honest
    AMBIGUOUS report into a crash.
    """
    try:
        meta = await store.load_archived_metadata_or_none(kit_id, segment)
    except Exception:
        return None
    if isinstance(meta, dict):
        value = meta.get("published_at")
        return value if isinstance(value, str) else None
    return None


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

    # structlog's default factory prints to STDOUT, and creating the store logs
    # (form_kits.local_store / .gcs_store). stdout here is the schema JSON an
    # operator redirects to a file and diffs -- a log line in front of it makes
    # the file invalid JSON while the script still exits 0. Bind logs to stderr
    # BEFORE anything backend-side is imported or constructed.
    import structlog

    structlog.configure(
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr)
    )

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
        # Print each candidate WITH its publish date: the message used to tell
        # the operator to compare "each revision's archived metadata" while
        # giving them no way to read it (fresh-eyes finding). published_at is
        # what makes the confirmation event's timestamp actionable.
        lines = []
        for candidate in exc.candidates:
            when = ""
            if candidate.startswith("archive:"):
                published = asyncio.run(
                    _archived_published_at(store, args.kit_id, candidate[len("archive:"):])
                )
                when = f"  published_at: {published}" if published else "  published_at: (unrecorded)"
            else:
                when = "  (the kit's CURRENT schema)"
            lines.append(f"  --segment {candidate.removeprefix('archive:')}{when}")
        print(f"AMBIGUOUS for {args.kit_id}/{args.marker}: "
              f"{len(exc.candidates)} distinct revisions answer to this marker. "
              "The record's marker alone cannot say which one it was confirmed "
              "against, so this refuses to guess. Compare the confirmation "
              "event's timestamp against these, then read the one you want:\n"
              + "\n".join(lines), file=sys.stderr)
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
