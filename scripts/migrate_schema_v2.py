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
5. controls_fields: each edge is a trigger-side action (shows/makes_required/
   unlocks/... target ids). v2 has NO trigger-side logic (only target-side
   show_if/require_if), so every edge is MIRRORED into the target: `shows` ->
   the target's show_if, `makes_required` -> require_if (merged via any_of when
   several triggers gate one target). An action already mirrored by an existing
   target condition is a no-op drop. Actions with no clean target-side v2
   equivalent (unlocks/locks/hides/makes_optional -- read-only/negation logic)
   are REPORTED as unconverted, never silently lost (in the shipped kits these
   are all `unlocks`, redundant with the target's conditional_behavior.
   unlock_method=flip_readonly_bit). controls_fields is then always removed.
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
    field if the field lacks one, then drop options[].

    Returns the OLD single-option value (or None) so pass 2 can rewrite any
    condition that referenced it to the standalone-checkbox idiom is_checked --
    otherwise `equals <that leaf>` becomes a dangling ref against the now-boolean
    trigger (never fires), silently breaking the dependent's visibility
    (evaluator-equivalence catch, bd c5r8)."""
    if f.get("type") != "checkbox":
        return None
    opts = f.get("options")
    if not isinstance(opts, list) or len(opts) != 1:
        return None
    opt = opts[0]
    old_value = str(opt.get("value")) if isinstance(opt, dict) and opt.get("value") is not None else None
    if isinstance(opt, dict) and not f.get("pdf_field_name") and opt.get("pdf_field_name"):
        f["pdf_field_name"] = opt["pdf_field_name"]
    f.pop("options", None)
    return old_value


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
        "controls_fields_dropped": 0, "controls_mirrored": 0,
        "unmirrored_controls": [],
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
    # trigger id -> its old single-option value, for standalone-unwrapped
    # checkboxes: a condition `equals <that value>` on it must become is_checked
    # (the value vanished with the unwrap; a bare equals would dangle -- bd c5r8).
    standalone_old_value: Dict[str, str] = {}
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
        else:
            unwrapped_old = _unwrap_single_option_checkbox(f)
            if unwrapped_old is not None and isinstance(fid, str):
                report["standalone_unwrapped"].append(fid)
                standalone_old_value[fid] = unwrapped_old
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
                # Standalone-unwrap ref fixup (bd c5r8): an atom `equals <old
                # single-option value>` on a trigger that was unwrapped to a
                # standalone checkbox loses its referent (the option is gone, the
                # trigger is now boolean), so a bare equals would dangle. Rewrite
                # `equals <that value>` to the standalone-checkbox idiom
                # is_checked. A `not_equals` on such a trigger has NO clean v2
                # idiom ("checkbox unchecked" is neither is_empty -- which is
                # false on a boolean false -- nor a negated is_checked), so it is
                # REPORTED for human conversion rather than mis-rewritten. i-90
                # has only equals cases.
                is_standalone_ref = (
                    isinstance(trig, str) and trig in standalone_old_value
                    and str(atom.get("value")) == standalone_old_value[trig])
                if is_standalone_ref and atom.get("operator") == "equals":
                    atom["operator"] = "is_checked"
                    atom.pop("value", None)
                elif is_standalone_ref and atom.get("operator") == "not_equals":
                    report.setdefault("standalone_not_equals_refs", []).append(
                        {"in": f.get("id"), "kind": kind, "trigger": trig})
                    # leave the atom for the human; do not run the generic rewrite
                else:
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

    # Pass 4: controls_fields -- v2 has no trigger-side conditional logic, so
    # every edge is either already mirrored by a target-side show_if/require_if
    # (drop it) OR must be MIRRORED into one (so the behavior survives), then the
    # trigger-side controls_fields is always removed. A `shows` action becomes the
    # target's show_if; `makes_required` becomes require_if (the actions the
    # shipped kits use). unlocks/locks/hides/makes_optional are reported as
    # UNCONVERTED (no clean target-side equivalent) rather than silently lost.
    for f in fields:
        controls = f.get("controls_fields")
        if not isinstance(controls, list):
            continue
        trigger_id = f.get("id")
        trig_type = f.get("type")  # post-pass-1 type (checkbox_group/select/...)
        trig_slug_map = slug_maps.get(trigger_id, {}) if isinstance(trigger_id, str) else {}
        standalone_old = (standalone_old_value.get(trigger_id)
                          if isinstance(trigger_id, str) else None)
        for control in controls:
            if not isinstance(control, dict):
                continue
            want = _control_condition(control, trigger_id, trig_type,
                                      trig_slug_map, standalone_old)
            # Mirror each show/require action onto its target -- but ONLY into the
            # matching bucket (shows -> show_if, makes_required -> require_if), and
            # only when THAT bucket does not already carry the condition. A
            # pre-existing condition in the OTHER bucket is a different effect and
            # must NOT suppress the mirror (fresh-eyes r2: the key-blind check
            # silently dropped require_if on 15 w7/w7-2 fields whose show_if
            # happened to match). Report any action key with no v2 equivalent.
            mirrored_here: List[str] = []
            noop_here = 0
            for action, key in (("shows", "show_if"),
                                ("makes_required", "require_if")):
                for tid in control.get(action) or []:
                    target = fields_by_id.get(tid) if isinstance(tid, str) else None
                    if not isinstance(target, dict):
                        continue
                    if _target_has_condition(target, key, want):
                        noop_here += 1  # already mirrored in THIS bucket
                        continue
                    _add_target_condition(target, key, dict(want))
                    mirrored_here.append(f"{tid}.{key}")
            unconverted = sorted(
                t for k in ("hides", "locks", "unlocks", "makes_optional")
                for t in (control.get(k) or []) if isinstance(t, str)
            )
            report["controls_mirrored"] += len(mirrored_here)
            if not mirrored_here and not unconverted and noop_here:
                # Every action was a no-op (target already mirrored the edge).
                report["controls_fields_dropped"] += 1
            if unconverted:
                # Actions with no target-side v2 equivalent -- the ONLY thing a
                # human still needs to review (show/require are handled above).
                report["unmirrored_controls"].append({
                    "trigger": trigger_id,
                    "operator": want.get("operator"),
                    "mirrored_into": sorted(mirrored_here),
                    "unconverted_actions": unconverted,
                })
        # v2 carries no trigger-side logic: controls_fields is always removed.
        f.pop("controls_fields", None)

    migrated["schema_version"] = vocab.SCHEMA_VERSION_V2
    return migrated, report


def _add_target_condition(target: Dict[str, Any], key: str,
                          atom: Dict[str, Any]) -> None:
    """Add a mirrored show_if/require_if atom to a target field as an OR
    alternative -- the field is shown/required under its OWN condition OR the
    mirrored trigger.

    Appending in place is safe ONLY when the existing condition is a PURE any_of
    (no all_of/none_of alongside it): appending into an any_of that sits beside an
    all_of/none_of would read as `all_of AND (any_of OR new) AND none_of`, NOT
    `(whole old condition) OR new` (Codex PR #346). For anything else -- a single
    atom, or a composite carrying all_of/none_of -- wrap the WHOLE existing
    condition as one arm of a fresh any_of so its AND/NOT semantics are preserved
    as a single OR alternative. (No shipped kit hits the composite case today;
    this keeps the merge correct for a future one.)"""
    existing = target.get(key)
    if not existing:
        target[key] = atom
        return
    is_pure_any_of = (
        isinstance(existing, dict)
        and isinstance(existing.get("any_of"), list)
        and not existing.get("all_of")
        and not existing.get("none_of")
    )
    if is_pure_any_of:
        existing["any_of"].append(atom)
    else:
        target[key] = {"any_of": [existing, atom]}


def _control_condition(control: Dict[str, Any], trigger_id: Any,
                       trigger_type: Optional[str], slug_map: Dict[str, str],
                       standalone_old_val: Optional[str] = None) -> Dict[str, Any]:
    """The equivalent show_if atom a controls_fields edge implies, NORMALIZED to
    v2 with the SAME rewrites the target-side atoms got (so a true mirror matches).
    Includes the standalone-unwrap fixup: `equals <the unwrapped trigger's old
    value>` -> is_checked, matching what pass 2 did to the target's show_if (bd
    c5r8) -- without it a genuinely-mirrored edge on a standalone checkbox would
    fail to match and be needlessly kept."""
    op = control.get("operator", "equals")
    val = control.get("value")
    if (standalone_old_val is not None and op == "equals"
            and str(val) == standalone_old_val):
        return {"field": trigger_id, "operator": "is_checked"}
    atom = {"field": trigger_id, "operator": op, "value": val}
    _rewrite_atom_value(atom, slug_map, trigger_type)
    # A no-value operator (is_checked / is_empty / is_not_empty) carries no value.
    if atom.get("operator") in ("is_checked", "is_empty", "is_not_empty"):
        atom.pop("value", None)
    return atom


def _target_has_condition(target: Dict[str, Any], key: str,
                          want: Dict[str, Any]) -> bool:
    """True if the target's condition under `key` (show_if OR require_if -- the
    SPECIFIC bucket, not both) already carries an atom MATCHING the control's
    implied condition on (field, operator, value).

    Key-specific by design (bd h76m.16, fresh-eyes r2): a `shows` action mirrors
    into show_if and a `makes_required` action into require_if, so a `shows` edge
    is "already mirrored" ONLY if show_if covers it -- a matching require_if (or
    vice versa) is a DIFFERENT effect and must NOT suppress the mirror, or the
    edge's real effect is silently lost. Also value/polarity-aware: an atom naming
    the same trigger but a different option value is a distinct condition, not a
    mirror."""
    for atom in _walk_condition_atoms(target.get(key)):
        if (atom.get("field") == want.get("field")
                and atom.get("operator") == want.get("operator")
                and atom.get("value") == want.get("value")):
            return True
    return False




def _load_dump(pdf: Optional[str], dump_json: Optional[str]) -> Optional[Dict[str, Any]]:
    """The AcroForm dump for combobox-option recovery: from a --pdf (run
    acroform_dump) or a pre-made --dump JSON. None when neither is given."""
    if dump_json:
        with open(dump_json, encoding="utf-8") as fh:
            return json.load(fh)
    if pdf:
        # scripts/bakeoff on sys.path (the repo-root insert at import handles
        # backend; add bakeoff for acroform_dump).
        bakeoff = os.path.join(_REPO, "scripts", "bakeoff")
        if bakeoff not in sys.path:
            sys.path.insert(0, bakeoff)
        import acroform_dump  # noqa: E402
        return acroform_dump.dump_pdf(pdf)
    return None


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Migrate a v1 form schema to v2.")
    ap.add_argument("--in", dest="inp", required=True, help="input v1 schema.json")
    ap.add_argument("--out", required=True, help="output migrated v2 schema.json")
    ap.add_argument("--archive", default=None,
                    help="write the pre-migration schema here "
                         "(schema_archived.json backup convention)")
    # A choice field mis-typed as an option-less combobox (the i-90 height
    # dropdowns) needs the PDF's choices to recover its options -- without a dump
    # such a field is left option-less and reported (needs_options). Supply the
    # form's PDF (--pdf, runs acroform_dump) or a pre-made dump JSON (--dump).
    ap.add_argument("--pdf", default=None,
                    help="the form PDF (for combobox-option recovery via acroform_dump)")
    ap.add_argument("--dump", default=None,
                    help="a pre-made acroform_dump JSON (alternative to --pdf)")
    ap.add_argument("--report", default=None,
                    help="write the FULL migration report JSON here (audit trail)")
    args = ap.parse_args(argv)

    with open(args.inp, encoding="utf-8") as fh:
        schema = json.load(fh)

    if args.archive:
        with open(args.archive, "w", encoding="utf-8") as fh:
            json.dump(schema, fh, indent=2)

    dump = _load_dump(args.pdf, args.dump)
    migrated, report = migrate(schema, dump)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(migrated, fh, indent=2)
    if args.report:
        # The FULL report (all keys) -- the audit trail (fresh-eyes/bd ztf1: a
        # hand-trimmed report hides real facts like options_from_dump).
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)

    print(f"[migrated] {args.inp} -> {args.out}")
    print(f"  checkbox_groups: {len(report['checkbox_groups'])}; "
          f"operators rewritten: {report['operators_rewritten']}; "
          f"behaviors folded: {report['behaviors_folded']}; "
          f"controls_fields dropped: {report['controls_fields_dropped']}; "
          f"controls mirrored -> show_if/require_if: {report['controls_mirrored']}; "
          f"conditional_fields dropped: {report['conditional_fields_dropped']}")
    # An UNCONVERTED action (unlocks/locks/hides/makes_optional -- no clean
    # target-side v2 equivalent) is the only thing a human still needs to review.
    unconverted = [u for u in report["unmirrored_controls"]
                   if u.get("unconverted_actions")]
    if unconverted:
        print(f"  WARNING: {len(unconverted)} controls_fields edge(s) carry "
              f"actions with NO v2 target-side equivalent (needs human review):",
              file=sys.stderr)
        for u in unconverted[:10]:
            print(f"    trigger={u['trigger']} -> unconverted "
                  f"{u['unconverted_actions']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
