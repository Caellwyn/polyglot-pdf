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

Quarantined fields (``_ignored_fields[].field``) are migrated too: the
editor's un-ignore restores such a field verbatim, so a legacy select left
there would fail the v2 gate the moment it came back (PR 3b). They are
reported with ``quarantined: true``.

Idempotent: an option that already carries ``pdf_on_value`` is never touched,
so a second run migrates nothing and retargets nothing -- and writes NO
artifacts: the archive is the rollback and the report the audit trail, and a
second run must not clobber either (the cross-surface pass caught the first
cut doing exactly that while printing "nothing to do"). An existing archive is
never overwritten, even by a later run that does migrate something. What a
second run DOES still report is the outstanding human work -- every kind in
``_HUMAN_WORK``: ``no_code`` (a cleared code the tool cannot supply),
``duplicate_codes`` (a code more than one option claims) and
``non_dict_options`` (plain-string options it cannot migrate) -- and the CLI
warns on each every time, so "nothing to do" is printed only when there truly
is nothing. Options already in v2 shape reserve their slugs, so a newly minted
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
        # schema to <kit>/_schema_pre_select_migration.json and writes
        # <kit>/_select_migration_report.json -- the "_" prefix keeps both
        # out of the kit upload (deploy-form-kit.sh publishes everything
        # NOT so prefixed; bd polyglot-pdf-mtbdq)

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


# THE kinds of outstanding human work, ENUMERATED in one place (scar #8:
# rounds 4-7 each surfaced one kind and forgot a sibling). Every per-field
# report key that is not a migration OUTCOME must appear here -- the pin in
# tests/test_migrate_select_on_values.py asserts exactly that -- and this
# tuple drives BOTH gates: whether a field entry reaches the report at all,
# and how it prints. Each row: (report key, header noun phrase, count of one
# field's entry, render of one field's entry).
_HUMAN_WORK = (
    ("no_code",
     "option(s) have a CLEARED export code and were left alone -- supply the /Opt entry by hand",
     len, lambda v: ", ".join(v)),
    ("duplicate_codes",
     "export code(s) are claimed by more than one option -- their conditions were NOT "
     "retargeted; resolve by hand",
     len, lambda v: ", ".join(v)),
    ("non_dict_options",
     "field(s) carry plain-string options the tool cannot migrate -- rewrite them as "
     "{value, label} objects first",
     lambda v: 1, lambda v: f"{v} string option(s)"),
)
_HUMAN_WORK_KEYS = tuple(k for k, _, _, _ in _HUMAN_WORK)
# Per-field report keys that describe what the tool DID, not what a human
# still must do. The pin asserts entry keys == these + _HUMAN_WORK_KEYS. What
# the pin cannot judge is CLASSIFICATION: a fact that really needs a human,
# filed here as an "outcome", would never warn. Ask, before adding a key
# here: can the maintainer act on it? If yes, it belongs in _HUMAN_WORK.
_OUTCOME_KEYS = ("field", "quarantined", "migrated", "already_v2", "kept_as_slug",
                 "kept_codes", "slug_map")
ARCHIVE_NAME = "_schema_pre_select_migration.json"
REPORT_NAME = "_select_migration_report.json"
_WARN_CAP = 10


def _has_human_work(entry: Dict[str, Any]) -> bool:
    return any(entry[k] for k in _HUMAN_WORK_KEYS)


def _migrate_field(field: Dict[str, Any]) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """Migrate ONE select field's options in place.

    Returns (old_to_new value map for the options that changed, per-field
    report entry). Options already in v2 shape are untouched and their values
    reserved; string options (not dicts) are left alone and reported.
    """
    options = field.get("options")
    entry: Dict[str, Any] = {
        "field": field.get("id"),
        "quarantined": False,
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
                v = o.get("value")
                entry["no_code"].append(v if isinstance(v, str) else "<no value>")
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
    # Quarantined fields ride along: (field dict, quarantined?) in one pass.
    quarantined = [e.get("field") for e in (migrated.get("_ignored_fields") or [])
                   if isinstance(e, dict)]
    candidates = [(f, False) for f in fields] + [(f, True) for f in quarantined]
    maps: Dict[str, Dict[str, str]] = {}
    for f, is_q in candidates:
        if not isinstance(f, dict) or f.get("type") != "select":
            continue
        old_to_new, entry = _migrate_field(f)
        entry["quarantined"] = is_q
        # A field reaches the report when the tool did something OR a human
        # still must -- the second half derived from _HUMAN_WORK, not restated.
        if entry["migrated"] or _has_human_work(entry):
            report["fields"].append(entry)
        report["options_migrated"] += entry["migrated"]
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
    # A top-level index for report readers, DERIVED from the per-field entries
    # (one source; a second accumulator drifted -- fresh-eyes round 7).
    report["fields_with_duplicate_codes"] = [
        e["field"] for e in report["fields"] if e["duplicate_codes"]]
    return migrated, report


def _warn_outstanding_work(report: Dict[str, Any]) -> bool:
    """Print every kind of outstanding human work to stderr, one line per
    field, capped like migrate_schema_v2's warnings. Returns True when there
    was any -- the caller must then NOT print "nothing to do"."""
    any_work = False
    for key, header, count_one, render in _HUMAN_WORK:
        rows = [(e["field"] if isinstance(e["field"], str) else "<no id>", e[key])
                for e in report["fields"] if e[key]]
        if not rows:
            continue
        any_work = True
        count = sum(count_one(v) for _, v in rows)   # explicit per kind, not by type
        print(f"  WARNING: {count} {header}:", file=sys.stderr)
        for fid, v in rows[:_WARN_CAP]:
            print(f"    {fid}: {render(v)}", file=sys.stderr)
        if len(rows) > _WARN_CAP:
            print(f"    ... and {len(rows) - _WARN_CAP} more field(s); see the report",
                  file=sys.stderr)
    return any_work


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
        archive = args.archive or os.path.join(args.kit, ARCHIVE_NAME)
        report_path = args.report or os.path.join(args.kit, REPORT_NAME)
    else:
        if not (args.inp and args.out):
            ap.error("give --kit DIR, or both --in and --out")
        inp, out, archive, report_path = args.inp, args.out, args.archive, args.report

    with open(inp, encoding="utf-8") as fh:
        schema = json.load(fh)
    migrated, report = migrate_selects(schema)
    if report["options_migrated"] == 0:
        # A no-op run writes NOTHING: the archive is the rollback and the
        # report the audit trail of the run that did the work.
        print(f"[select-migration] {inp}: nothing migrated; existing archive/report kept")
    else:
        if archive and os.path.exists(archive):
            print(f"  archive already exists, kept: {archive}")
        elif archive:
            _write_json(archive, schema)
        _write_json(out, migrated)
        if report_path:
            _write_json(report_path, report)

    print(f"[select-migration] {inp} -> {out}")
    print(f"  options migrated: {report['options_migrated']}; "
          f"conditions retargeted: {report['conditions_retargeted']}; "
          f"fields touched: {len(report['fields'])}")
    # EVERY kind of outstanding human work is surfaced on stderr, every run,
    # through one helper (rounds 4, 5 and 6 each surfaced one kind and forgot
    # a sibling); "nothing to do" only when there is none and nothing moved.
    any_work = _warn_outstanding_work(report)
    if report["options_migrated"] == 0 and not any_work:
        print("  nothing to do (already migrated)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
