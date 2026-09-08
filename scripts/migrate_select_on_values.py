"""Migrate a form kit's SELECT options to the v2 shape (bd polyglot-pdf-g2fpr,
PR 3a / bead ub7om).

A dropdown authored before the epic keeps the PDF's export code in
``option.value`` (``'AL'``). Every other choice type keeps a semantic slug in
``value`` and the widget identity in ``pdf_on_value``; the filler (PR 1) and
the writers (PR 2) now treat selects the same way. This tool brings an
EXISTING kit across:

  for every select option WITHOUT a ``pdf_on_value``:
      pdf_on_value = value                      (the code moves, verbatim)
      value        = mint_select_slugs(...)     (kept if already a slug, e.g. '5')
  every show_if / require_if atom on that field is retargeted old -> new,
  on fields AND sections, scalar and list values alike.

Idempotent: an option that already carries ``pdf_on_value`` is never touched,
so a second run is a no-op and the report is empty. Options already in v2
shape reserve their slugs, so a newly minted legacy sibling cannot collide.

Deliberately NOT done here:
  * metadata.json is never opened. The schema's SHA changes, so a readiness
    stamp goes stale by design -- a human re-verify in the editor mints a
    fresh one. That is the audit trail, not a bug.
  * Radio / checkbox_group values are untouched (they already carry
    pdf_on_value; migrate_schema_v2.py owns their v1 -> v2 path).
  * Duplicate codes inside one field are reported, not resolved: the
    conditions that name them cannot be retargeted unambiguously, and
    /resume-form drops such a field rather than guess (bd polyglot-pdf-7dvpp).

Usage (the maintainer runs this on a COPY first, then on the kit):

    python scripts/migrate_select_on_values.py --kit form-kits/i-90_v2
        # rewrites <kit>/schema.json in place, archives the pre-migration
        # schema to <kit>/schema_pre_select_migration.json and writes
        # <kit>/select_migration_report.json

    python scripts/migrate_select_on_values.py --in a.json --out b.json \
        --archive a.bak.json --report report.json

ASCII only (CLAUDE.md scar #6).
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from backend.models import conditional_vocabulary as vocab  # noqa: E402

# The v2 condition walker is the migration precedent's; one definition.
from scripts.migrate_schema_v2 import _walk_condition_atoms  # noqa: E402


def _is_v2_option(o: Any) -> bool:
    """An option already in the v2 shape: a dict carrying a non-empty string
    pdf_on_value. Legacy = the key is ABSENT (or not a usable string) -- the
    editor's convert-on-touch uses the same test (PR 2)."""
    return (isinstance(o, dict)
            and isinstance(o.get("pdf_on_value"), str)
            and o.get("pdf_on_value") != "")


def _migrate_field(field: Dict[str, Any]) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """Migrate ONE select field's options in place.

    Returns (old_to_new value map for the options that changed, per-field
    report entry). Options already in v2 shape are untouched and their values
    reserved; string options (not dicts) are left alone and reported.
    """
    options = field.get("options")
    entry: Dict[str, Any] = {
        "field": field.get("id"),
        "migrated": 0,
        "already_v2": 0,
        "kept_as_slug": 0,
        "non_dict_options": 0,
        "slug_map": {},
        "duplicate_codes": [],
    }
    if not isinstance(options, list):
        return {}, entry

    legacy_idx: List[int] = []
    reserved: List[str] = []
    for i, o in enumerate(options):
        if not isinstance(o, dict):
            entry["non_dict_options"] += 1
            continue
        if _is_v2_option(o):
            entry["already_v2"] += 1
            if isinstance(o.get("value"), str):
                reserved.append(o["value"])
            continue
        legacy_idx.append(i)

    if not legacy_idx:
        return {}, entry

    codes = [str(options[i].get("value", "")) for i in legacy_idx]
    labels = [str(options[i].get("label") or codes[k])
              for k, i in enumerate(legacy_idx)]
    # A code two legacy options share cannot be retargeted unambiguously.
    seen: Dict[str, int] = {}
    for c in codes:
        seen[c] = seen.get(c, 0) + 1
    entry["duplicate_codes"] = sorted(c for c, n in seen.items() if n > 1)

    slugs = vocab.mint_select_slugs(labels, codes, reserved=reserved)
    old_to_new: Dict[str, str] = {}
    for k, i in enumerate(legacy_idx):
        o = options[i]
        code, slug = codes[k], slugs[k]
        o["pdf_on_value"] = code
        o["value"] = slug
        entry["migrated"] += 1
        if slug == code:
            entry["kept_as_slug"] += 1
        else:
            entry["slug_map"][code] = slug
            # Only an UNAMBIGUOUS code is retargeted.
            if seen[code] == 1:
                old_to_new[code] = slug
    return old_to_new, entry


def _retarget(cond: Any, trigger: str, old_to_new: Dict[str, str]) -> int:
    """Rewrite every atom on `trigger` inside one show_if/require_if.
    Returns the number of atoms changed."""
    n = 0
    for atom in _walk_condition_atoms(cond):
        if atom.get("field") != trigger:
            continue
        val = atom.get("value")
        if isinstance(val, list):
            new = [old_to_new.get(str(v), v) for v in val]
            if new != val:
                atom["value"] = new
                n += 1
        elif val is not None and str(val) in old_to_new:
            atom["value"] = old_to_new[str(val)]
            n += 1
    return n


def migrate_selects(schema: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Pure: returns (migrated deep copy, report). Idempotent."""
    migrated = copy.deepcopy(schema)
    report: Dict[str, Any] = {
        "fields": [],
        "options_migrated": 0,
        "conditions_retargeted": 0,
        "fields_with_duplicate_codes": [],
    }
    fields = migrated.get("fields") or []
    maps: Dict[str, Dict[str, str]] = {}
    for f in fields:
        if not isinstance(f, dict) or f.get("type") != "select":
            continue
        old_to_new, entry = _migrate_field(f)
        if entry["migrated"] or entry["duplicate_codes"]:
            report["fields"].append(entry)
        report["options_migrated"] += entry["migrated"]
        if entry["duplicate_codes"]:
            report["fields_with_duplicate_codes"].append(entry["field"])
        if old_to_new:
            maps[str(f.get("id"))] = old_to_new
    if maps:
        holders: List[Dict[str, Any]] = [f for f in fields if isinstance(f, dict)]
        holders += [s for s in (migrated.get("sections") or []) if isinstance(s, dict)]
        for holder in holders:
            for kind in ("show_if", "require_if"):
                cond = holder.get(kind)
                if cond is None:
                    continue
                for trigger, old_to_new in maps.items():
                    report["conditions_retargeted"] += _retarget(cond, trigger, old_to_new)
    return migrated, report


def _write_json(path: str, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Move a select option's export code into pdf_on_value and mint a slug value.")
    ap.add_argument("--kit", default=None,
                    help="a form-kit directory: rewrites <kit>/schema.json in place with "
                         "an archive + report beside it (never touches metadata.json)")
    ap.add_argument("--in", dest="inp", default=None, help="input schema.json")
    ap.add_argument("--out", default=None, help="output schema.json")
    ap.add_argument("--archive", default=None, help="write the pre-migration schema here")
    ap.add_argument("--report", default=None, help="write the full report JSON here")
    args = ap.parse_args(argv)

    if args.kit:
        if args.inp or args.out:
            ap.error("--kit and --in/--out are alternatives")
        inp = os.path.join(args.kit, "schema.json")
        out = inp
        archive = args.archive or os.path.join(args.kit, "schema_pre_select_migration.json")
        report_path = args.report or os.path.join(args.kit, "select_migration_report.json")
    else:
        if not (args.inp and args.out):
            ap.error("give --kit DIR, or both --in and --out")
        inp, out, archive, report_path = args.inp, args.out, args.archive, args.report

    with open(inp, encoding="utf-8") as fh:
        schema = json.load(fh)
    migrated, report = migrate_selects(schema)
    if archive:
        _write_json(archive, schema)
    _write_json(out, migrated)
    if report_path:
        _write_json(report_path, report)

    print(f"[select-migration] {inp} -> {out}")
    print(f"  options migrated: {report['options_migrated']}; "
          f"conditions retargeted: {report['conditions_retargeted']}; "
          f"fields touched: {len(report['fields'])}")
    if report["fields_with_duplicate_codes"]:
        print(f"  WARNING: duplicate export codes inside "
              f"{report['fields_with_duplicate_codes']} -- their conditions were NOT "
              f"retargeted; resolve by hand", file=sys.stderr)
    if report["options_migrated"] == 0:
        print("  nothing to do (already migrated)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
