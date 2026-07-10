"""Shared controls_fields -> target-side show_if/require_if mirroring helpers
(bd h76m.16, extracted for bd polyglot-pdf-c3y6).

v2 has NO trigger-side conditional logic (only target-side show_if/require_if).
A v1/draft `controls_fields` edge is a TRIGGER-side action list (shows/hides/
unlocks/locks/makes_required/makes_optional -> target ids). Only `shows` and
`makes_required` have a clean v2 target-side equivalent (show_if / require_if
respectively); the other four actions (hides/locks/unlocks/makes_optional) are
read-only/negation logic with nothing to mirror into and must be REPORTED, not
silently dropped.

These three PURE functions are the shared mirroring core, used by BOTH:
- scripts/migrate_schema_v2.py Pass 4 (the proven v1->v2 migration, unchanged
  behavior -- these functions were extracted from it verbatim);
- backend/services/schema_repair.py's own controls_fields repair step (bd
  polyglot-pdf-c3y6), which routes the resulting atom through repair's OWN
  atom-rewrite machinery (_rewrite_atom/_rewrite_condition) for slug-alias
  resolution rather than migrate's _rewrite_atom_value.

Dict-in/dict-out; no I/O, no imports from either caller module.

ASCII only.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

# The controls_fields action keys (trigger-side). Kept here (not just in
# migrate_schema_v2) since schema_repair's mirroring step also needs the full
# set to compute the "unconverted" (no v2 target-side equivalent) actions.
ACTION_KEYS = ("shows", "hides", "unlocks", "locks",
               "makes_required", "makes_optional")

# Actions with a clean v2 target-side equivalent: shows -> show_if,
# makes_required -> require_if. Order matters only for iteration determinism.
MIRRORABLE_ACTIONS = (("shows", "show_if"), ("makes_required", "require_if"))

# The remaining actions have NO v2 target-side equivalent (read-only/negation
# logic) and are reported as unconverted rather than mirrored.
UNCONVERTIBLE_ACTIONS = ("hides", "locks", "unlocks", "makes_optional")


def control_condition(control: Dict[str, Any], trigger_id: Any,
                      standalone_old_val: Optional[str] = None
                      ) -> Dict[str, Any]:
    """The RAW show_if-shaped atom a controls_fields edge implies, BEFORE any
    caller-specific v2 normalization (slug rewriting / operator aliasing --
    that is the caller's job, via its own atom-rewrite machinery).

    Includes the standalone-unwrap fixup: `equals <the unwrapped trigger's old
    single-option value>` -> is_checked (bd c5r8) -- a v1 checkbox with exactly
    one option becomes a plain v2 `checkbox` with the option (and its value)
    gone, so a bare `equals <that value>` would dangle against the now-boolean
    trigger. This fixup is controls_fields-specific (the generic atom rewriters
    in both callers do not know about the vanished option value), so it lives
    here, in the SHARED core, rather than being duplicated by each caller.

    The "value" key is ALWAYS present in the returned atom (even when None) --
    matching the original migrate_schema_v2._control_condition construction
    verbatim, since a caller's atom-rewrite step (e.g. _rewrite_atom_value's
    `atom.get("value", "")` emptiness check) is sensitive to whether the key is
    present-but-None vs. absent."""
    op = control.get("operator", "equals")
    val = control.get("value")
    if (standalone_old_val is not None and op == "equals"
            and str(val) == standalone_old_val):
        return {"field": trigger_id, "operator": "is_checked"}
    return {"field": trigger_id, "operator": op, "value": val}


def target_has_condition(target: Dict[str, Any], key: str,
                         want: Dict[str, Any],
                         walk_atoms) -> bool:
    """True if the target's condition under `key` (show_if OR require_if -- the
    SPECIFIC bucket, not both) already carries an atom MATCHING the mirrored
    condition on (field, operator, value).

    Key-specific by design (bd h76m.16, fresh-eyes r2): a `shows` action
    mirrors into show_if and a `makes_required` action into require_if, so a
    `shows` edge is "already mirrored" ONLY if show_if covers it -- a matching
    require_if (or vice versa) is a DIFFERENT effect and must NOT suppress the
    mirror, or the edge's real effect is silently lost. Also value/polarity-
    aware: an atom naming the same trigger but a different option value is a
    distinct condition, not a mirror.

    `walk_atoms` is the caller's own atom-flattening function (a show_if/
    require_if may be a single atom or a composite all_of/any_of/none_of group;
    both callers already have one -- migrate's _walk_condition_atoms / a
    caller-supplied equivalent) so this stays free of any registry import.
    """
    for atom in walk_atoms(target.get(key)):
        if (atom.get("field") == want.get("field")
                and atom.get("operator") == want.get("operator")
                and atom.get("value") == want.get("value")):
            return True
    return False


def add_target_condition(target: Dict[str, Any], key: str,
                         atom: Dict[str, Any]) -> None:
    """Add a mirrored show_if/require_if atom to a target field as an OR
    alternative -- the field is shown/required under its OWN condition OR the
    mirrored trigger.

    Appending in place is safe ONLY when the existing condition is a PURE
    any_of (no all_of/none_of alongside it): appending into an any_of that sits
    beside an all_of/none_of would read as `all_of AND (any_of OR new) AND
    none_of`, NOT `(whole old condition) OR new` (Codex PR #346). For anything
    else -- a single atom, or a composite carrying all_of/none_of -- wrap the
    WHOLE existing condition as one arm of a fresh any_of so its AND/NOT
    semantics are preserved as a single OR alternative.
    """
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


def mirror_controls_fields(
    field: Dict[str, Any],
    fields_by_id: Dict[str, Dict[str, Any]],
    walk_atoms,
    normalize_atom,
    standalone_old_value: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Process one field's `controls_fields` list end to end: mirror shows/
    makes_required edges into their targets' show_if/require_if, report
    unconvertible actions and dangling targets, and return a summary dict
    the caller uses to build its own audit-trail ("repairs" / "report")
    entries. Does NOT pop controls_fields off `field` -- the caller does that
    (its own drop-logging idiom differs between migrate and repair).

    Returns:
      {
        "mirrored": [{"trigger": id, "target": id, "key": "show_if"|"require_if",
                      "atom": dict}, ...],
        "noop": int,                    # actions already mirrored (key-specific)
        "unconverted": [{"trigger": id, "operator": str, "value": Any,
                         "mirrored_into": [...], "unconverted_actions": [...],
                         "dangling_targets": [...]}, ...],
        "dangling": ["<target_id>.<key>", ...],
      }

    `walk_atoms`: caller's show_if/require_if -> flat atom list function.
    `normalize_atom`: caller's OWN atom-rewrite function, called as
      normalize_atom(atom) -> atom (in place or returning a replacement) --
      this is where each caller applies its own v2 normalization (migrate's
      _rewrite_atom_value keyed on trigger type + slug map; schema_repair's
      _rewrite_atom keyed on its resolution/alias machinery). The RAW atom
      from control_condition() is passed through this before matching/mirroring
      so a genuinely-mirrored edge (already-v2 target condition) compares
      equal, and a newly-mirrored edge gets the SAME rewrites every other
      repaired/migrated atom gets.
    """
    trigger_id = field.get("id")
    controls = field.get("controls_fields")
    result: Dict[str, Any] = {
        "mirrored": [], "noop": 0, "unconverted": [], "dangling": [],
    }
    if not isinstance(controls, list):
        return result
    standalone_old = (standalone_old_value or {}).get(trigger_id) \
        if isinstance(trigger_id, str) else None

    for control in controls:
        if not isinstance(control, dict):
            continue
        raw_atom = control_condition(control, trigger_id, standalone_old)
        want = normalize_atom(copy.deepcopy(raw_atom))

        mirrored_here: List[str] = []
        dangling_here: List[str] = []
        noop_here = 0
        # want is None when the caller's own normalization dropped the atom
        # (e.g. an unresolvable value or unknown operator -- the caller has
        # ALREADY recorded its own drop entry for that). There is nothing
        # valid to mirror in that case: every shows/makes_required target for
        # this control is skipped rather than mirroring a half-resolved atom
        # into it (that would reintroduce exactly the garbage repair exists to
        # remove). The unconvertible-action accounting below is independent of
        # this and still runs.
        if want is not None:
            for action, key in MIRRORABLE_ACTIONS:
                for tid in control.get(action) or []:
                    target = fields_by_id.get(tid) if isinstance(tid, str) else None
                    if not isinstance(target, dict):
                        # A shows/makes_required target id that resolves to no
                        # field (a dangling/typo'd ref) has no place to mirror
                        # into. REPORT it -- never drop it with no trace (bd
                        # polyglot-pdf-dghy).
                        if isinstance(tid, str):
                            dangling_here.append(f"{tid}.{key}")
                        continue
                    if target_has_condition(target, key, want, walk_atoms):
                        noop_here += 1  # already mirrored in THIS bucket
                        continue
                    add_target_condition(target, key, dict(want))
                    mirrored_here.append(f"{tid}.{key}")
                    result["mirrored"].append({
                        "trigger": trigger_id, "target": tid, "key": key,
                        "atom": dict(want),
                    })

        unconverted = sorted(
            t for k in UNCONVERTIBLE_ACTIONS
            for t in (control.get(k) or []) if isinstance(t, str)
        )
        # Action-key -> target pairs, for a human-readable log message (which
        # unconvertible ACTION -- unlocks/locks/hides/makes_optional -- named
        # which target). `unconverted` above stays TARGET IDS ONLY (matching
        # migrate_schema_v2's report shape byte-for-byte, pinned by its own
        # tests); this is an ADDITIONAL field, not a replacement.
        unconverted_action_keys = sorted(
            f"{k}:{t}" for k in UNCONVERTIBLE_ACTIONS
            for t in (control.get(k) or []) if isinstance(t, str)
        )
        result["noop"] += noop_here
        result["dangling"].extend(sorted(dangling_here))
        if unconverted or dangling_here:
            result["unconverted"].append({
                "trigger": trigger_id,
                "operator": (want or raw_atom).get("operator"),
                "value": (want or raw_atom).get("value"),
                "mirrored_into": sorted(mirrored_here),
                "unconverted_actions": unconverted,
                "unconverted_action_keys": unconverted_action_keys,
                "dangling_targets": sorted(dangling_here),
            })

    return result
