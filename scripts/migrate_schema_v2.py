#!/usr/bin/env python3
"""Deterministic, idempotent v1 -> schema-v2 migration (bd polyglot-pdf-4lqi, P6.1a).

Migrates a hand-curated v1 form schema (the i-90 kit is the target) to the strict
v2 wire format the epic standardizes. PURE TOOLING: this script produces a
migrated schema + a report; APPLYING it to a shipped kit is a separate bead
(P6.1b). Deterministic and idempotent -- migrate(migrate(x)) == migrate(x).

Transforms (plan P6.1):
1. classify: a v1 `checkbox` WITH options[] becomes `checkbox_group` (a multi-box
   question); its field-level pdf_field_name moves off the field (v2 forbids it
   on a group -- per-box identity lives on options[].pdf_field_name). A standalone
   checkbox (no options) stays `checkbox`.
2. mint option slugs: each option.value is re-minted to a semantic slug from its
   label (conditional_vocabulary.mint_unique_slugs), recording an old->new map
   per field. Every show_if / require_if / controls_fields value that referenced
   an OLD option value is rewritten to the new slug.
3. rewrite operators on a (now) checkbox_group trigger: equals -> includes,
   not_equals -> not_includes. is_checked DUAL FATE: on a STANDALONE checkbox
   trigger it is kept (bool sugar); on a checkbox_group trigger it is INVALID in
   v2 and rewritten to is_not_empty. (The dual fate is pinned by the SHARED
   fixture backend/tests/fixtures/is_checked_dual_fate.json, consumed by both the
   P1.1 validator tests and the migration tests, so the two agree by construction.)
4. fold conditional_logic INTO conditional_behavior: keep unlock_method +
   pdf_field_flag_change; DROP show_method (spike-confirmed: no reader -- the
   consumers are pdf_fill_routes.py + FieldRenderer.tsx, which read unlock_method
   and pdf_field_flag_change only). conditional_logic is then removed.
5. controls_fields: each edge is a trigger-side action (shows/unlocks/... target
   ids). v2 evaluates target-side show_if/require_if, so a controls_fields edge is
   dropped ONLY when its target already carries a mirroring show_if/require_if
   naming this trigger; an UNMIRRORED edge is REPORTED (never silently dropped)
   for human conversion.
6. drop conditional_fields (legacy; v2 rejects it).
7. stamp schema_version '2'.

ASCII only.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

# Reach the backend package (the registry lives there). Mirrors extract_form.py.
_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from backend.models import conditional_vocabulary as vocab  # noqa: E402

# The controls_fields action keys (trigger-side).
_ACTION_KEYS = ("shows", "hides", "unlocks", "locks",
                "makes_required", "makes_optional")

# conditional_behavior / conditional_logic sub-keys with a live reader
# (spike, plan P6.1): unlock_method (pdf_fill_routes + FieldRenderer) and
# pdf_field_flag_change (pdf_fill_routes, dual-read). show_method has NO reader
# and is dropped on the fold.
_BEHAVIOR_KEEP = ("unlock_method", "pdf_field_flag_change")


def _is_group_checkbox(f: Dict[str, Any]) -> bool:
    """A v1 checkbox with >= 2 options -> a v2 checkbox_group (a multi-box
    question). A checkbox with exactly ONE option is a STANDALONE checkbox
    (a single yes/no box modeled with a one-element options[]); it becomes a
    plain v2 checkbox (see _unwrap_single_option_checkbox), not a group."""
    return f.get("type") == "checkbox" and isinstance(f.get("options"), list) \
        and len(f.get("options")) >= 2


def _unwrap_single_option_checkbox(f: Dict[str, Any]) -> bool:
    """A v1 checkbox with EXACTLY ONE option is a standalone boolean box, which
    v2 models as a plain `checkbox` with NO options (its identity is the
    field-level pdf_field_name). Lift the single option's pdf_field_name onto the
    field if the field lacks one, then drop options[]. Returns True if changed."""
    if f.get("type") != "checkbox":
        return False
    opts = f.get("options")
    if not isinstance(opts, list) or len(opts) != 1:
        return False
    opt = opts[0]
    if isinstance(opt, dict) and not f.get("pdf_field_name") and opt.get("pdf_field_name"):
        f["pdf_field_name"] = opt["pdf_field_name"]
    f.pop("options", None)
    return True


def _mint_field_slugs(f: Dict[str, Any]) -> Tuple[Dict[str, str], List[str]]:
    """Re-mint a choice field's option values to slugs; return (old->new map,
    colliding_old_values).

    Minted from labels (unique per field). An option with no label falls back to
    its existing value as the mint input, so a label-less option still gets a
    stable slug. Options are mutated in place.

    A v1 field with TWO options sharing one `value` is ambiguous: a condition
    referencing that old value cannot be rewritten to a single new slug without
    guessing. Such colliding old values are REPORTED (not silently collapsed to
    the last option's slug -- fresh-eyes) and left OUT of the rewrite map, so the
    referencing condition is preserved verbatim for a human to resolve rather
    than corrupted.
    """
    options = f.get("options")
    if not isinstance(options, list):
        return {}, []
    labels = [
        (o.get("label") if isinstance(o, dict) and o.get("label")
         else str(o.get("value")) if isinstance(o, dict) else str(o))
        for o in options
    ]
    slugs = vocab.mint_unique_slugs([str(x) for x in labels])
    # First pass: count how many options each old value appears on.
    old_counts: Dict[str, int] = {}
    for o in options:
        if isinstance(o, dict) and o.get("value") is not None:
            old_counts[str(o["value"])] = old_counts.get(str(o["value"]), 0) + 1
    colliding = sorted(v for v, n in old_counts.items() if n > 1)
    old_to_new: Dict[str, str] = {}
    for o, slug in zip(options, slugs):
        if not isinstance(o, dict):
            continue
        old = o.get("value")
        # Only map an UNAMBIGUOUS old value (appears on exactly one option).
        if old is not None and old_counts.get(str(old), 0) == 1:
            old_to_new[str(old)] = slug
        o["value"] = slug
    return old_to_new, colliding


def _rewrite_atom_value(atom: Dict[str, Any], old_to_new: Dict[str, str],
                        trigger_type: Optional[str]) -> None:
    """Rewrite one atomic condition's value + operator in place.

    value: an old option value referenced by the condition -> its new slug (both
    scalar and list values).

    operator rewrites keyed on the (post-migration) TRIGGER TYPE:
    - is_checked DUAL FATE: kept ONLY on a standalone `checkbox` trigger (bool
      sugar). On ANY OTHER option-bearing trigger (checkbox_group / radio /
      select) it means "a selection exists" -> is_not_empty (the shared fixture
      pins the checkbox vs checkbox_group ends; radio/select extend the same
      "option-bearing -> is_not_empty" principle -- CLAUDE.md scar #5 idiom).
    - on a checkbox_group trigger only: equals -> includes, not_equals ->
      not_includes (membership).
    """
    op = atom.get("operator")
    is_group = trigger_type == "checkbox_group"
    is_option_bearing = trigger_type in vocab.CHOICE_FIELD_TYPES

    # v1 emptiness idiom: equals/not_equals "" means "field is (not) empty". v2
    # spells that is_empty/is_not_empty (which take NO value). Rewrite BEFORE the
    # membership rewrite so an equals "" on a group trigger becomes is_empty.
    if op in ("equals", "not_equals") and str(atom.get("value", "")) == "":
        atom["operator"] = "is_empty" if op == "equals" else "is_not_empty"
        atom.pop("value", None)
        return
    # is_checked on an OPTION-BEARING trigger (not a standalone checkbox) -> a
    # "selection exists" test. Do this before slug rewriting (it drops the value).
    if op == "is_checked" and is_option_bearing:
        atom["operator"] = "is_not_empty"
        atom.pop("value", None)
        return
    # Strip a vestigial value on a no-value operator (v1 is_not_empty value="").
    if op in ("is_empty", "is_not_empty"):
        atom.pop("value", None)

    val = atom.get("value")
    if isinstance(val, list):
        atom["value"] = [old_to_new.get(str(v), v) for v in val]
    elif val is not None:
        atom["value"] = old_to_new.get(str(val), val)

    if is_group:
        if op == "equals":
            atom["operator"] = "includes"
        elif op == "not_equals":
            atom["operator"] = "not_includes"


def _walk_condition_atoms(cond: Any) -> List[Dict[str, Any]]:
    """Every atomic {field, operator, value} dict in a show_if/require_if.

    Handles a legacy single atom and a composite group (all_of/any_of/none_of
    buckets of atoms). Depth <= 1 by the v2 contract.
    """
    if not isinstance(cond, dict):
        return []
    buckets = vocab.CONDITION_GROUP_BUCKETS & cond.keys()
    if not buckets:
        return [cond]
    atoms: List[Dict[str, Any]] = []
    for bucket in buckets:
        members = cond.get(bucket)
        if isinstance(members, list):
            atoms.extend(m for m in members if isinstance(m, dict))
    return atoms


def _fold_behavior(f: Dict[str, Any]) -> bool:
    """Fold conditional_logic INTO conditional_behavior; drop conditional_logic.

    Keeps unlock_method + pdf_field_flag_change (the read sub-keys); drops any
    other sub-key (e.g. show_method, no reader). Returns True if anything changed.
    conditional_LOGIC wins on a key conflict (the merge iterates (cl, cb) with
    first-writer-wins). This is moot on the i-90 gold -- the two containers never
    disagree on a kept key there (verified: 0 value conflicts across the 16 fields
    carrying both) -- and it is the right precedence anyway: the full descriptor
    (pdf_field_flag_change) lives only on conditional_logic in the gold, so the
    fold is what makes the unlock actually fillable.
    """
    cl = f.get("conditional_logic")
    cb = f.get("conditional_behavior")
    if not isinstance(cl, dict) and not isinstance(cb, dict):
        return False
    merged: Dict[str, Any] = {}
    for src in (cl if isinstance(cl, dict) else {},
                cb if isinstance(cb, dict) else {}):
        for k in _BEHAVIOR_KEEP:
            if k in src and k not in merged:
                merged[k] = src[k]
    changed = False
    if merged:
        if f.get("conditional_behavior") != merged:
            f["conditional_behavior"] = merged
            changed = True
    if "conditional_logic" in f:
        del f["conditional_logic"]
        changed = True
    return changed


def _dump_entry_for(pdf_field_name: Any, dump: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The dump field entry whose name matches pdf_field_name (exact, else
    dot-suffix -- the linter/filler convention)."""
    if not isinstance(pdf_field_name, str) or not pdf_field_name or not isinstance(dump, dict):
        return None
    entries = dump.get("fields")
    if not isinstance(entries, list):
        return None
    exact = [e for e in entries if isinstance(e, dict) and e.get("name") == pdf_field_name]
    if exact:
        return exact[0]
    suffix = [e for e in entries if isinstance(e, dict)
              and isinstance(e.get("name"), str) and e["name"].endswith("." + pdf_field_name)]
    return suffix[0] if suffix else None


def _recover_options_from_dump(f: Dict[str, Any], dump: Optional[Dict[str, Any]],
                               report: Dict[str, Any]) -> bool:
    """A v1 choice field with < 2 options is invalid in v2. If it is really a PDF
    combobox (the dump has choices), retype to `select` and build options from
    the choices; else report needs_options. Returns True if changed."""
    if f.get("type") not in ("radio", "select", "checkbox_group"):
        return False
    opts = f.get("options")
    if isinstance(opts, list) and len(opts) >= 2:
        return False  # already valid
    fid = f.get("id")
    entry = _dump_entry_for(f.get("pdf_field_name"), dump)
    choices = None
    if entry:
        widgets = entry.get("widgets")
        w0 = widgets[0] if isinstance(widgets, list) and widgets else {}
        choices = w0.get("choices") if isinstance(w0, dict) else None
    if not isinstance(choices, list) or len(choices) < 2:
        if isinstance(fid, str):
            report["needs_options"].append(fid)
        return False
    # Build select options from the combobox choices. The display becomes the
    # label; the option value is a slug minted from the display; the raw combobox
    # value rides on pdf_on_value so fill selects the right list entry. Drop the
    # blank placeholder choice (display "" / " ").
    labels, on_values = [], []
    for c in choices:
        if not isinstance(c, dict):
            continue
        disp = str(c.get("display", "")).strip()
        raw = c.get("value")
        if not disp:
            continue
        labels.append(disp)
        on_values.append(raw)
    if len(labels) < 2:
        if isinstance(fid, str):
            report["needs_options"].append(fid)
        return False
    slugs = vocab.mint_unique_slugs(labels)
    f["type"] = "select"
    f["options"] = [
        {"value": slug, "label": label, "pdf_on_value": on}
        for slug, label, on in zip(slugs, labels, on_values)
    ]
    if isinstance(fid, str):
        report["options_from_dump"].append(fid)
    return True


def migrate(schema: Dict[str, Any],
            dump: Optional[Dict[str, Any]] = None
            ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Migrate a v1 schema to v2. Returns (migrated_copy, report).

    Idempotent: a schema already stamped v2 is returned unchanged (with an empty
    report) -- so migrate(migrate(x)) == migrate(x).

    dump: the optional AcroForm dump (acroform_dump.py). When given, a choice
    field that lint would reject for having < 2 options (a v1 combobox mis-typed
    as an option-less radio/select -- the i-90 height dropdowns) is retyped to
    `select` and its options are recovered from the widget's PDF choices. Without
    a dump such a field is left as-is and REPORTED (needs_options) -- the caller
    that has the PDF (P6.1b) supplies the dump.
    """
    migrated = copy.deepcopy(schema)
    report: Dict[str, Any] = {
        "checkbox_groups": [], "standalone_unwrapped": [], "slug_maps": {},
        "operators_rewritten": 0, "behaviors_folded": 0,
        "controls_fields_dropped": 0, "unmirrored_controls": [],
        "conditional_fields_dropped": 0, "options_from_dump": [],
        "needs_options": [], "duplicate_option_values": [],
    }

    if str(migrated.get("schema_version")) == vocab.SCHEMA_VERSION_V2:
        return migrated, report  # already v2 -> no-op (idempotent)

    raw_fields = migrated.get("fields")
    fields = [f for f in raw_fields if isinstance(f, dict)] \
        if isinstance(raw_fields, list) else []
    fields_by_id = {f["id"]: f for f in fields if isinstance(f.get("id"), str)}

    # Pass 1: classify checkbox -> checkbox_group / standalone; recover
    # combobox options from the dump; mint slugs; record group ids.
    slug_maps: Dict[str, Dict[str, str]] = {}
    group_ids: set = set()
    for f in fields:
        fid = f.get("id")
        if _is_group_checkbox(f):
            f["type"] = "checkbox_group"
            # A checkbox_group carries NO field-level pdf_field_name (per-box
            # identity is on options[].pdf_field_name).
            f.pop("pdf_field_name", None)
            if isinstance(fid, str):
                group_ids.add(fid)
                report["checkbox_groups"].append(fid)
        elif _unwrap_single_option_checkbox(f):
            if isinstance(fid, str):
                report["standalone_unwrapped"].append(fid)
        # A choice field with < 2 options is invalid in v2. Recover options from
        # the PDF dump when available (the i-90 height comboboxes mis-typed as
        # option-less radios); else report it for the dump-bearing caller.
        if _recover_options_from_dump(f, dump, report):
            pass
        if isinstance(f.get("options"), list) and f.get("type") in vocab.CHOICE_FIELD_TYPES:
            m, colliding = _mint_field_slugs(f)
            if m and isinstance(fid, str):
                slug_maps[fid] = m
            if colliding and isinstance(fid, str):
                # A duplicate v1 option value is ambiguous to rewrite -- reported,
                # not silently collapsed (fresh-eyes). i-90 has none; a future
                # kit (P6.1c) with duplicates surfaces here instead of corrupting.
                report["duplicate_option_values"].append(
                    {"field": fid, "values": colliding})
    report["slug_maps"] = slug_maps

    def _trigger_type(trigger_id: Any) -> Optional[str]:
        # fields_by_id reflects POST-pass-1 types (checkbox->checkbox_group,
        # combobox->select), so the operator rewrite keys on the final type.
        t = fields_by_id.get(trigger_id) if isinstance(trigger_id, str) else None
        return t.get("type") if isinstance(t, dict) else None

    def _slug_map_for(trigger_id: Any) -> Dict[str, str]:
        return slug_maps.get(trigger_id, {}) if isinstance(trigger_id, str) else {}

    # Pass 2: rewrite show_if / require_if atoms (value slugs + operators keyed on
    # the trigger's post-migration type).
    for f in fields:
        for kind in ("show_if", "require_if"):
            cond = f.get(kind)
            for atom in _walk_condition_atoms(cond):
                trig = atom.get("field")
                # An atom naming a trigger that does not resolve to a field is
                # REPORTED (fresh-eyes): its type-keyed operator rewrite (e.g.
                # is_checked -> is_not_empty on a group) is skipped, so a would-be
                # invalid operator must not slip through silently. i-90 has none.
                if isinstance(trig, str) and trig not in fields_by_id:
                    report.setdefault("unresolved_trigger_refs", []).append(
                        {"in": f.get("id"), "kind": kind, "trigger": trig})
                before = (atom.get("operator"), copy.deepcopy(atom.get("value")))
                _rewrite_atom_value(atom, _slug_map_for(trig),
                                    _trigger_type(trig))
                if (atom.get("operator"), atom.get("value")) != before:
                    report["operators_rewritten"] += 1

    # Pass 3: fold conditional_logic into conditional_behavior; drop legacy
    # conditional_fields.
    for f in fields:
        if _fold_behavior(f):
            report["behaviors_folded"] += 1
        if "conditional_fields" in f:
            del f["conditional_fields"]
            report["conditional_fields_dropped"] += 1

    # Pass 4: controls_fields -- drop an edge only when its targets carry a
    # mirroring show_if/require_if naming this trigger; report unmirrored edges.
    for f in fields:
        controls = f.get("controls_fields")
        if not isinstance(controls, list):
            continue
        trigger_id = f.get("id")
        trig_type = f.get("type")  # post-pass-1 type (checkbox_group/select/...)
        trig_slug_map = slug_maps.get(trigger_id, {}) if isinstance(trigger_id, str) else {}
        surviving: List[dict] = []
        for control in controls:
            if not isinstance(control, dict):
                continue
            unmirrored = _unmirrored_targets(control, trigger_id, trig_type,
                                             trig_slug_map, fields_by_id)
            if unmirrored:
                # Keep the unmirrored edge for the human -- but MIGRATE its
                # operator+value to v2 (slug + group operator) like a show_if
                # atom, so the surviving control is v2-valid (lint-clean), not a
                # stale widget-leaf value that would ref-option-value error.
                migrated_atom = {"operator": control.get("operator", "equals"),
                                 "value": control.get("value")}
                _rewrite_atom_value(migrated_atom, trig_slug_map, trig_type)
                control["operator"] = migrated_atom["operator"]
                if "value" in migrated_atom:
                    control["value"] = migrated_atom["value"]
                else:
                    control.pop("value", None)
                report["unmirrored_controls"].append({
                    "trigger": trigger_id,
                    "operator": control["operator"],
                    "targets": unmirrored,
                })
                surviving.append(control)
            else:
                report["controls_fields_dropped"] += 1
        if surviving:
            f["controls_fields"] = surviving
        else:
            f.pop("controls_fields", None)

    migrated["schema_version"] = vocab.SCHEMA_VERSION_V2
    return migrated, report


def _control_condition(control: Dict[str, Any], trigger_id: Any,
                       trigger_type: Optional[str],
                       slug_map: Dict[str, str]) -> Dict[str, Any]:
    """The equivalent show_if atom a controls_fields edge implies, NORMALIZED to
    v2 (same operator/value rewrites the target-side atoms got). This is what a
    mirroring target-side condition must MATCH."""
    atom = {"field": trigger_id, "operator": control.get("operator", "equals"),
            "value": control.get("value")}
    _rewrite_atom_value(atom, slug_map, trigger_type)
    return atom


def _target_mirrors(target: Dict[str, Any], want: Dict[str, Any]) -> bool:
    """True if the target's show_if/require_if carries an atom that MATCHES the
    control's implied condition on (field, operator, value) -- a TRUE mirror, not
    merely naming the same trigger (fresh-eyes: a value/polarity-blind match
    silently drops a live, distinct edge -- e.g. the i-90 p2_checkbox2[5] edge
    gating on option [0] while the target's show_if gates on option [11])."""
    for kind in ("show_if", "require_if"):
        for atom in _walk_condition_atoms(target.get(kind)):
            if (atom.get("field") == want.get("field")
                    and atom.get("operator") == want.get("operator")
                    and atom.get("value") == want.get("value")):
                return True
    return False


def _unmirrored_targets(control: Dict[str, Any], trigger_id: Any,
                        trigger_type: Optional[str], slug_map: Dict[str, str],
                        fields_by_id: Dict[str, dict]) -> List[str]:
    """Target ids of a controls_fields edge whose target does NOT carry a
    condition MATCHING the edge's implied condition (field+operator+value). An
    empty list means every target truly mirrors the edge (safe to drop it)."""
    want = _control_condition(control, trigger_id, trigger_type, slug_map)
    targets: List[str] = []
    for key in _ACTION_KEYS:
        vals = control.get(key)
        if isinstance(vals, list):
            targets.extend(t for t in vals if isinstance(t, str))
    unmirrored: List[str] = []
    for tid in targets:
        target = fields_by_id.get(tid)
        if not isinstance(target, dict) or not _target_mirrors(target, want):
            unmirrored.append(tid)
    return unmirrored


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Migrate a v1 form schema to v2.")
    ap.add_argument("--in", dest="inp", required=True, help="input v1 schema.json")
    ap.add_argument("--out", required=True, help="output migrated v2 schema.json")
    ap.add_argument("--archive", default=None,
                    help="write the pre-migration schema here "
                         "(schema_archived.json backup convention)")
    args = ap.parse_args(argv)

    with open(args.inp, encoding="utf-8") as fh:
        schema = json.load(fh)

    if args.archive:
        with open(args.archive, "w", encoding="utf-8") as fh:
            json.dump(schema, fh, indent=2)

    migrated, report = migrate(schema)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(migrated, fh, indent=2)

    print(f"[migrated] {args.inp} -> {args.out}")
    print(f"  checkbox_groups: {len(report['checkbox_groups'])}; "
          f"operators rewritten: {report['operators_rewritten']}; "
          f"behaviors folded: {report['behaviors_folded']}; "
          f"controls_fields dropped: {report['controls_fields_dropped']}; "
          f"conditional_fields dropped: {report['conditional_fields_dropped']}")
    if report["unmirrored_controls"]:
        print(f"  WARNING: {len(report['unmirrored_controls'])} UNMIRRORED "
              f"controls_fields edge(s) KEPT for human conversion:", file=sys.stderr)
        for u in report["unmirrored_controls"][:10]:
            print(f"    trigger={u['trigger']} -> {u['targets']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
