#!/usr/bin/env python3
"""Backfill per-option (and field) pdf_position into an EXISTING form-kit schema
(bd polyglot-pdf-5f41, sprint 9 editable-Preview epic).

Preview mode paints radio/checkbox selections at their own printed boxes; that
needs each FieldOption to carry its widget's rect. The AcroForm dump already
records every widget's rect AND on_value, so this is a purely mechanical,
deterministic patch -- no LLM anywhere. The mapping itself lives in
extract_form.py::_backfill_positions (ONE shared implementation for this CLI
and the extraction pipeline): option pdf_field_name -> widget group
(suffix-aware), disambiguated by pdf_on_value for multi-widget groups, plus the
shared-field-name radio/combo shape; anything unresolvable is REPORTED, never
guessed.

Idempotent IN EFFECT, not by skipping: since bd polyglot-pdf-icyi the
deterministic widget rect OWNS pdf_position, so every resolvable field/option is
RE-DERIVED on every run -- but the dump is deterministic PyMuPDF output, so a
second run computes byte-identical values and writes nothing. "Would this change
the file?" is therefore answered by COMPARING positions before/after, never by
counting derivations (counting made --check exit 1 forever, even on a fully
positioned kit, and made exit 0 unreachable). The dump is regenerated in memory
from the kit's form.pdf on every run; no dump files are committed.

ASCII only (cp1252 safe); writes json with ensure_ascii (same convention as
extract_form.py, matching the committed schema files).

Usage:
    python scripts/authoring/backfill_option_positions.py --kit form-kits/i-90
    python scripts/authoring/backfill_option_positions.py \
        --schema path/schema.json --pdf path/form.pdf
    ... --check   # report only, write nothing

Exit codes:
    0  nothing to patch and nothing unmatched (kit fully positioned)
    1  --check found patchable positions (a write run would change the file)
    2  unmatched options remain (a name/on_value that resolves to no widget)
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import tempfile

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO, "scripts", "bakeoff"))
import acroform_dump  # noqa: E402

# Import extract_form by file path (repo precedent: tests/test_extract_form_backfill.py)
# for the shared _backfill_positions implementation.
_EXTRACT_FORM = os.path.join(_REPO, "scripts", "authoring", "extract_form.py")
_spec = importlib.util.spec_from_file_location("extract_form", _EXTRACT_FORM)
_ef = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("extract_form", _ef)
_spec.loader.exec_module(_ef)


def _position_map(schema: dict) -> dict:
    """Every pdf_position in the schema, keyed by POSITIONAL INDEX.

    The change-detector's input (bd polyglot-pdf-icyi). Keyed by
    (field_index, option_index-or-None), which is collision-free by
    construction. Keying by (field_id, option_value) -- the first version --
    collided whenever an option carried no `value`: its key became
    (field_id, None), the SAME key as the field's own entry, so the field's
    position was silently discarded from the comparison and a genuinely wrong
    field rect compared EQUAL. That made `--check` report exit 0 and, worse,
    made a PATCH run skip the write (`if changed and not check`) and throw away
    the corrected positions it had just computed. Duplicate field ids collided
    the same way (fresh-eyes Opus round 2).

    Index keys mean a REORDER also reads as a change, which is correct here: the
    field-level rect of an options-bearing field is defined as its FIRST
    option's widget, so moving options can legitimately move that rect."""
    out: dict = {}
    for i, field in enumerate(schema.get("fields") or []):
        if not isinstance(field, dict):
            continue
        out[(i, None)] = field.get("pdf_position")
        for j, opt in enumerate(field.get("options") or []):
            if isinstance(opt, dict):
                out[(i, j)] = opt.get("pdf_position")
    return out


def _positions_differ(before: dict, after: dict) -> bool:
    """Did any pdf_position actually change (added, removed, or moved)?

    Replaces the old `fields_filled + options_filled > 0` test, which counted
    DERIVATIONS -- and since the deterministic rect now always re-derives, that
    was permanently true (bd polyglot-pdf-icyi, fresh-eyes Opus round)."""
    return _position_map(before) != _position_map(after)


def backfill_kit(schema_path: str, pdf_path: str, check: bool) -> int:
    """Run the shared backfill against one schema+pdf pair. Returns the exit code."""
    with open(schema_path, encoding="utf-8") as fh:
        schema = json.load(fh)

    dump = acroform_dump.dump_pdf(pdf_path)
    # Snapshot BEFORE the pass so "changed" can mean "the file would actually
    # differ" rather than "a derivation ran" (bd polyglot-pdf-icyi): since the
    # deterministic rect now wins unconditionally, every resolvable field and
    # option is re-derived on EVERY run, so counting derivations made `changed`
    # permanently true -- which pegged `--check` at exit 1 ("needs patching")
    # for every kit, including a fully-positioned one, and made the documented
    # exit 0 unreachable. Deep-copied via json round-trip: the pass mutates the
    # position dicts in place.
    before = json.loads(json.dumps(schema))

    # _backfill_positions takes a dump PATH (the extraction pipeline hands it a
    # temp file); mirror that instead of forking the signature.
    fd, dump_path = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(dump, fh)
        result = _ef._backfill_positions(schema, dump_path)
    finally:
        os.remove(dump_path)

    fields_filled = result["fields_filled"]
    options_filled = result["options_filled"]
    unmatched = result["unmatched"]
    changed = _positions_differ(before, schema)

    mode = "CHECK" if check else "PATCH"
    print(f"[{mode}] {schema_path}: fields_filled={fields_filled} "
          f"options_filled={options_filled} unmatched={len(unmatched)}")
    for u in unmatched:
        print(f"  UNMATCHED field={u['field_id']} option={u['option_value']}: "
              f"{u['reason']}")

    if changed and not check:
        with open(schema_path, "w", encoding="utf-8") as fh:
            json.dump(schema, fh, indent=2)
        print(f"  wrote {schema_path}")

    if unmatched:
        return 2
    if changed and check:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Deterministically backfill options[].pdf_position (and any "
                    "missing field pdf_position) into a form-kit schema.json "
                    "from the kit PDF's AcroForm widgets.")
    ap.add_argument("--kit", help="Kit directory holding schema.json + form.pdf "
                                  "(e.g. form-kits/i-90)")
    ap.add_argument("--schema", help="Explicit schema.json path (with --pdf)")
    ap.add_argument("--pdf", help="Explicit form PDF path (with --schema)")
    ap.add_argument("--check", action="store_true",
                    help="Report only; write nothing. Exit 1 if a write run "
                         "would patch anything, 2 if unmatched options remain.")
    args = ap.parse_args(argv)

    if args.kit:
        if args.schema or args.pdf:
            ap.error("pass EITHER --kit OR --schema/--pdf, not both")
        schema_path = os.path.join(args.kit, "schema.json")
        pdf_path = os.path.join(args.kit, "form.pdf")
    elif args.schema and args.pdf:
        schema_path, pdf_path = args.schema, args.pdf
    else:
        ap.error("pass --kit DIR, or --schema FILE --pdf FILE")

    for p in (schema_path, pdf_path):
        if not os.path.exists(p):
            print(f"ERROR: {p} not found")
            return 2

    return backfill_kit(schema_path, pdf_path, args.check)


if __name__ == "__main__":
    sys.exit(main())
