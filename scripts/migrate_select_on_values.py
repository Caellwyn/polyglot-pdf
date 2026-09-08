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
so a second run migrates nothing and retargets nothing. What a second run
DOES still report is the outstanding human work -- ``no_code`` (a cleared
code the tool cannot supply) and ``duplicate_codes`` -- and the CLI warns on
both every time, so "nothing to do" is printed only when there truly is
nothing. Options already in v2 shape reserve their slugs, so a newly minted
legacy sibling cannot collide.

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
    """An option already in the v2 shape: a dict carrying a string pdf_on_value
    -- INCLUDING the empty string. Legacy means the key is ABSENT (or not a
    string), exactly the editor's convert-on-touch test (PR 2). An empty code
    is a v2 option whose author cleared it (lint: select-on-value-missing);
    treating it as legacy fabricated a code from a slug-shaped value
    ({value: 'alabama', pdf_on_value: ''} -> pdf_on_value 'alabama', not in
    /Opt) -- fresh-eyes round 3. Such options are left alone and REPORTED."""
    return isinstance(o, dict) and isinstance(o.get("pdf_on_value"), str)


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
        "kept_codes": [],
        "non_dict_options": 0,
        "slug_map": {},
        "duplicate_codes": [],
        "no_code": [],
    }
    if not isinstance(options, list):
        return {}, entry

    legacy_idx: List[int] = []
    reserved: List[str] = []
    v2_codes: List[str] = []
    for i, o in enumerate(options):
        if not isinstance(o, dict):
            entry["non_dict_options"] += 1
            continue
        if _is_v2_option(o):
            entry["already_v2"] += 1
            if isinstance(o.get("value"), str):
                reserved.append(o["value"])
            if o.get("pdf_on_value") == "":
                # A cleared code: left alone, named for the human who must
                # supply it (the tool cannot know the /Opt entry).
                entry["no_code"].append(str(o.get("value")))
            else:
                v2_codes.append(o["pdf_on_value"])
            continue
        legacy_idx.append(i)

    if not legacy_idx:
        return {}, entry

    codes = [str(options[i].get("value", "")) for i in legacy_idx]
    labels = [str(options[i].get("label") or codes[k])
              for k, i in enumerate(legacy_idx)]
    # A code claimed by more than one option cannot be retargeted
    # unambiguously: two legacy options sharing it, OR a legacy code that is
    # also an already-v2 sibling's VALUE (a condition naming '5' may mean the
    # v2 option, not the legacy one -- fresh-eyes round 2), OR a legacy code
    # an already-v2 sibling carries as ITS pdf_on_value (two options would
    # write one widget state -- round 3). All are reported and left for a
    # human; none is guessed.
    seen: Dict[str, int] = {}
    for c in codes:
        seen[c] = seen.get(c, 0) + 1
    reserved_set = set(reserved) | set(v2_codes)
    entry["duplicate_codes"] = sorted(
        c for c, n in seen.items() if n > 1 or c in reserved_set)

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
            entry["kept_codes"].append(code)     # named, so the report audits every option
        else:
            entry["slug_map"][code] = slug
            # Only an UNAMBIGUOUS code is retargeted.
            if seen[code] == 1 and code not in reserved_set:
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
        # Every kind of outstanding human work reaches the report: a string
        # option (not a dict) is one the tool cannot migrate at all.
        if (entry["migrated"] or entry["duplicate_codes"] or entry["no_code"]
                or entry["non_dict_options"]):
            report["fields"].append(entry)
        report["options_migrated"] += entry["migrated"]
        if entry["duplicate_codes"]:
            report["fields_with_duplicate_codes"].append(entry["field"])
        fid = f.get("id")
        if old_to_new and isinstance(fid, str) and fid:
            # An id-less field cannot be a condition trigger; keying it as the
            # string "None" would merge two such fields' maps (fresh-eyes).
            maps[fid] = old_to_new
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
    # BOTH kinds of outstanding human work are surfaced on stderr, every run
    # (fresh-eyes round 4: no_code had no CLI signal, so a kit with cleared
    # codes printed "nothing to do" while a field still needed a human).
    if report["fields_with_duplicate_codes"]:
        print(f"  WARNING: duplicate export codes inside "
              f"{report['fields_with_duplicate_codes']} -- their conditions were NOT "
              f"retargeted; resolve by hand", file=sys.stderr)
    # One line per field, capped like migrate_schema_v2's warnings, so a run
    # on a real kit stays readable.
    no_code = [(e["field"], e["no_code"]) for e in report["fields"] if e["no_code"]]
    if no_code:
        print(f"  WARNING: {sum(len(v) for _, v in no_code)} option(s) have a CLEARED "
              f"export code and were left alone -- supply the /Opt entry by hand:",
              file=sys.stderr)
        for fid, values in no_code[:10]:
            print(f"    {fid}: {', '.join(values)}", file=sys.stderr)
        if len(no_code) > 10:
            print(f"    ... and {len(no_code) - 10} more field(s); see the report",
                  file=sys.stderr)
    non_dict = [(e["field"], e["non_dict_options"]) for e in report["fields"]
                if e["non_dict_options"]]
    if non_dict:
        print(f"  WARNING: {len(non_dict)} field(s) carry plain-string options the tool "
              f"cannot migrate -- rewrite them as {{value, label}} objects first:",
              file=sys.stderr)
        for fid, n in non_dict[:10]:
            print(f"    {fid}: {n} string option(s)", file=sys.stderr)
    if (report["options_migrated"] == 0 and not no_code and not non_dict
            and not report["fields_with_duplicate_codes"]):
        print("  nothing to do (already migrated)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
