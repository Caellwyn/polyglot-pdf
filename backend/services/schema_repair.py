"""Post-LLM schema repair pass (bd h76m.13, P5.2; absorbs bd 4c58).

Extraction models invent conditional vocabulary when the schema cannot say
what they mean (the W-7 failure: is_selected/contains_any referencing raw
widget names; the P5.1 ablation added `or` with option_id-bearing atoms).
This pass deterministically rewrites what is rewritable into the FINAL v2
vocabulary and drops -- loudly, recorded -- what is not:

- option.value slugs: choice fields whose option values violate the v2 slug
  convention (or collide within the field) get slugs minted from their
  labels (conditional_vocabulary.mint_unique_slugs); old value / widget
  leaf / label -> new slug maps drive the reference rewrites below.
- alias table (ALIASES, beside the registry): the observed invented
  operators -- is_selected -> includes/equals (by trigger kind),
  contains_any -> any_of of membership atoms, or -> any_of of its inner
  atoms. The table encodes the LLMs' INVENTED vocabulary as an input
  contract: log its hit rate per extraction and expect the P1.2
  contract-from-model few-shot to drive it toward zero (review at P6; an
  alias that still fires belongs in the prompt, not the table, forever).
- condition value resolution: full widget path / leaf / label / stale
  option value -> the trigger option's CURRENT value. An atom whose
  operator or value cannot be resolved is DROPPED with a recorded ERROR --
  the field stays visible (fail-open, matching the runtime's
  unknown-operator fallback).
- hallucinated widgets FAIL LOUDLY: with a dump supplied, an option
  pdf_field_name matching no dump widget raises RepairError (nothing
  downstream can fix an invented widget).

Pure function: repair(schema, dump=None) -> (repaired_copy, repairs).
`repairs` entries: {"action", "path", "detail", "error": bool}. The caller
records them under _bakeoff.authoring.repairs (extract_form does) and the
editor's one-click "Repair all" (P5.3) serves THIS implementation, so CLI
and editor output are equal by construction.

CLI:  python scripts/authoring/schema_repair.py --in DRAFT.json --out FIXED.json

ASCII only.
"""
from __future__ import annotations

import copy
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.models import conditional_vocabulary as vocab
from backend.models.form_models import SupplementType
from backend.services import controls_fields_mirror as cfm

_CHOICE_TYPES = frozenset({"select", "radio", "checkbox_group"})
_GROUP_MEMBERSHIP_TYPES = frozenset({"checkbox_group", "checkbox"})
_NO_VALUE_OPS = frozenset(
    n for n, s in vocab.OPERATORS.items() if s.value_arity == "none"
)


class RepairError(ValueError):
    """A defect repair cannot fix and must not paper over (hallucinated
    widgets: the draft references a widget the PDF does not have)."""


def _leaf(name: Optional[str]) -> Optional[str]:
    if not isinstance(name, str) or not name:
        return None
    return name.split(".")[-1]


def _is_choice_field(f: dict) -> bool:
    """Choice = option-bearing selection field, incl. the v1 checkbox-group
    modeling (type checkbox WITH 2+ options)."""
    ftype = str(f.get("type"))
    options = f.get("options")
    if not isinstance(options, list) or len(options) < 2:
        return False
    return ftype in _CHOICE_TYPES or ftype == "checkbox"


def _membership_trigger(f: dict) -> bool:
    """True when a condition on this trigger selects FROM A SET (multi-select
    group) -- rewrites use includes; single-select triggers keep equals."""
    ftype = str(f.get("type"))
    if ftype == "checkbox_group":
        return True
    # v1 group modeling: type checkbox with options (+ optional group_kind).
    return ftype == "checkbox" and isinstance(f.get("options"), list) and bool(f.get("options"))


# --------------------------------------------------------------------------- #
# Step 1: option-value slugs.
# --------------------------------------------------------------------------- #

def _mint_slugs(fields: List[dict], repairs: List[dict]) -> Dict[str, Dict[str, str]]:
    """Mint v2 slugs for choice fields whose option values violate the slug
    convention or collide. Returns per-field resolution maps: any known alias
    of an option (old value, widget full path, widget leaf, label) -> the
    option's CURRENT value."""
    resolution: Dict[str, Dict[str, str]] = {}
    for i, f in enumerate(fields):
        if not isinstance(f, dict):
            continue
        fid = str(f.get("id"))
        options = f.get("options") if isinstance(f.get("options"), list) else []
        dict_opts = [o for o in options if isinstance(o, dict)]
        if not dict_opts:
            continue

        # Alias -> value map with COLLISION tracking (fresh-eyes, PR review):
        # an alias key (old value, widget path/leaf, label) claimed by two
        # DIFFERENT options is ambiguous -- registering last-writer-wins would
        # silently rewire a condition to the wrong option (the shared old
        # value "1" is exactly the W-7 corruption). Collided keys are removed
        # so an ambiguous reference falls through to the fail-open drop path
        # (recorded ERROR) instead of a silent guess.
        res: Dict[str, str] = {}
        collided: set = set()

        def _register(key: Any, slug: str) -> None:
            if not isinstance(key, str) or not key:
                return
            if key in res and res[key] != slug:
                collided.add(key)
            else:
                res[key] = slug

        needs_mint = False
        if _is_choice_field(f):
            values = [str(o.get("value")) for o in dict_opts if o.get("value") is not None]
            invalid = any(not vocab.is_valid_option_slug(v) for v in values)
            missing = any(o.get("value") in (None, "") for o in dict_opts)
            dupes = len(set(values)) != len(values)
            needs_mint = invalid or missing or dupes

        if needs_mint:
            labels = [
                str(o.get("label") or o.get("value") or "option") for o in dict_opts
            ]
            slugs = vocab.mint_unique_slugs(labels)
            renames = []
            for o, slug in zip(dict_opts, slugs):
                old = o.get("value")
                if old is not None and str(old) != slug:
                    renames.append(f"{old!r} -> {slug!r}")
                if old is not None:
                    _register(str(old), slug)
                o["value"] = slug
            if renames:
                repairs.append({
                    "action": "mint-option-slugs",
                    "path": f"fields[{i}] (id={fid})",
                    "detail": "; ".join(renames[:10]),
                    "error": False,
                })

        # Register every alias -> CURRENT value (post-mint or untouched).
        for o in dict_opts:
            cur = o.get("value")
            if cur is None:
                continue
            cur = str(cur)
            _register(cur, cur)
            pfn = o.get("pdf_field_name")
            if isinstance(pfn, str) and pfn:
                _register(pfn, cur)
                _register(_leaf(pfn), cur)
            label = o.get("label")
            if isinstance(label, str) and label:
                _register(label, cur)
        for key in collided:
            res.pop(key, None)
        if res:
            resolution[fid] = res
    return resolution


# --------------------------------------------------------------------------- #
# Step 2: conditional rewrites (aliases + value resolution).
# --------------------------------------------------------------------------- #

def _resolve_value(trigger: Optional[dict], value: Any,
                   resolution: Dict[str, Dict[str, str]]) -> Tuple[Any, bool]:
    """Resolve a condition value against the trigger's option aliases.
    Returns (resolved, ok). Non-option triggers pass values through."""
    if trigger is None:
        return value, True
    fid = str(trigger.get("id"))
    res = resolution.get(fid)
    if not res:
        # Trigger has no options -- nothing to resolve against.
        return value, not _is_choice_field(trigger)
    v = str(value)
    if v in res:
        return res[v], True
    lv = _leaf(v)
    if lv and lv in res:
        return res[lv], True
    return value, False


def _membership_op(trigger: Optional[dict]) -> str:
    """The registry-valid membership operator for this trigger: `includes`
    only where the compat matrix allows it (checkbox_group); on a v1-typed
    group (type checkbox with options) the valid spelling is `equals`, whose
    evaluator branch does membership on array values (the vq4m semantics the
    P6.1 migration later rewrites to includes when it retypes the field)."""
    if trigger is None or not _membership_trigger(trigger):
        return "equals"
    ttype = str(trigger.get("type"))
    if ttype in vocab.OPERATORS["includes"].trigger_types:
        return "includes"
    return "equals"


# Trigger-compat rewrites for REGISTRY-VALID operators sitting on a trigger
# type the compat matrix forbids (e.g. `contains` on a checkbox trigger --
# its historical array-membership reading; `includes` on a v1-typed group).
_COMPAT_MEMBERSHIP_OPS = frozenset({"contains", "includes"})
_COMPAT_NEGATED_OPS = frozenset({"not_includes"})


def _rewrite_atom(atom: dict, trigger: Optional[dict],
                  resolution: Dict[str, Dict[str, str]],
                  path: str, repairs: List[dict],
                  count_alias: Callable[[str], None]) -> Optional[dict]:
    """Rewrite one atomic condition dict. Returns the clean atom, or None
    when it must be dropped (recorded ERROR; fail-open)."""
    operator = str(atom.get("operator") or "")
    value = atom.get("value")

    # option_id (the P5.1-observed invention): a widget path naming the
    # intended option -- a better resolution key than the (often shared)
    # value. When present it is AUTHORITATIVE: an unresolvable option_id
    # drops the condition rather than falling back to the value, which may
    # coincidentally match a DIFFERENT option and silently rewire the
    # condition (fresh-eyes round 2, bd furs -- the same never-guess rule
    # as alias collisions).
    option_id = atom.get("option_id")
    if isinstance(option_id, str) and option_id:
        resolved, ok = _resolve_value(trigger, option_id, resolution)
        if not ok:
            repairs.append({
                "action": "drop-condition", "path": path,
                "detail": f"option_id {option_id!r} resolves to no option of "
                          f"trigger {(trigger or {}).get('id')!r} -- condition "
                          "dropped, field stays visible",
                "error": True,
            })
            return None
        value = resolved
        count_alias("option_id")

    if operator == "is_selected":
        new_op = _membership_op(trigger)
        count_alias("is_selected")
        repairs.append({
            "action": "alias-operator", "path": path,
            "detail": f"is_selected -> {new_op}", "error": False,
        })
        operator = new_op
    elif operator not in vocab.ALLOWED_OPERATORS:
        repairs.append({
            "action": "drop-condition", "path": path,
            "detail": f"unknown operator {operator!r} (no alias) -- condition "
                      "dropped, field stays visible",
            "error": True,
        })
        return None

    # Trigger-compat pass: a registry-valid operator on a trigger type the
    # compat matrix forbids. Known membership misspellings rewrite; the v1
    # is_checked-on-group idiom is lint-tolerated and left for the P6.1
    # migration; anything else drops (fail-open).
    spec = vocab.OPERATORS.get(operator)
    ttype = str(trigger.get("type")) if trigger else None
    if (spec is not None and ttype
            and ttype in vocab.CONDITION_TRIGGER_TYPES
            and ttype not in spec.trigger_types):
        if operator in _COMPAT_MEMBERSHIP_OPS and _is_choice_field(trigger):
            new_op = _membership_op(trigger)
            repairs.append({
                "action": "alias-operator", "path": path,
                "detail": f"{operator} on {ttype!r} trigger -> {new_op} "
                          "(membership reading)", "error": False,
            })
            count_alias(f"{operator}@{ttype}")
            operator = new_op
        elif operator in _COMPAT_NEGATED_OPS and _is_choice_field(trigger):
            repairs.append({
                "action": "alias-operator", "path": path,
                "detail": f"{operator} on {ttype!r} trigger -> not_equals "
                          "(membership reading)", "error": False,
            })
            count_alias(f"{operator}@{ttype}")
            operator = "not_equals"
        elif operator == "is_checked" and _is_choice_field(trigger):
            pass  # v1 idiom, lint-tolerated; P6.1 migrates it
        else:
            repairs.append({
                "action": "drop-condition", "path": path,
                "detail": f"operator {operator!r} is not valid on a {ttype!r} "
                          "trigger and has no safe rewrite -- condition "
                          "dropped, field stays visible",
                "error": True,
            })
            return None

    if operator in _NO_VALUE_OPS:
        return {"field": atom.get("field"), "operator": operator}

    values = value if isinstance(value, list) else [value]
    resolved_values = []
    for v in values:
        rv, ok = _resolve_value(trigger, v, resolution)
        if not ok:
            repairs.append({
                "action": "drop-condition", "path": path,
                "detail": f"value {v!r} resolves to no option of trigger "
                          f"{(trigger or {}).get('id')!r} -- condition dropped, "
                          "field stays visible",
                "error": True,
            })
            return None
        if rv != v:
            repairs.append({
                "action": "rewrite-condition-value", "path": path,
                "detail": f"{v!r} -> {rv!r}", "error": False,
            })
        resolved_values.append(rv)

    out: dict = {"field": atom.get("field"), "operator": operator}
    out["value"] = resolved_values if isinstance(value, list) else resolved_values[0]
    return out


def _walk_condition_atoms(cond: Any) -> List[dict]:
    """Every atomic {field, operator, value} dict in a show_if/require_if.

    Handles a single atom and a composite group (all_of/any_of/none_of buckets
    of atoms). Depth <= 1 by the v2 contract. Mirrors
    migrate_schema_v2._walk_condition_atoms (kept local rather than shared: it
    is a trivial v2-shape walk with no controls_fields-specific logic, so it
    does not belong in the extracted controls_fields_mirror core)."""
    if not isinstance(cond, dict):
        return []
    buckets = vocab.CONDITION_GROUP_BUCKETS & cond.keys()
    if not buckets:
        return [cond]
    atoms: List[dict] = []
    for bucket in buckets:
        members = cond.get(bucket)
        if isinstance(members, list):
            atoms.extend(m for m in members if isinstance(m, dict))
    return atoms


def _rewrite_condition(cond: Any, owner_path: str, fields_by_id: Dict[str, dict],
                       resolution: Dict[str, Dict[str, str]],
                       repairs: List[dict],
                       count_alias: Callable[[str], None]) -> Any:
    """Rewrite a show_if/require_if of ANY observed shape into clean v2:
    atom, ConditionGroup, contains_any atom, or the `or`/`and` pseudo-group
    ({operator: or, conditions: [...]}). None stays None; a shape with no
    surviving atoms becomes None (fail-open)."""
    if not isinstance(cond, dict):
        return cond

    def trigger_of(atom: dict) -> Optional[dict]:
        ref = atom.get("field")
        return fields_by_id.get(ref) if isinstance(ref, str) else None

    # Already-composite v2 group: rewrite bucket members in place.
    buckets = vocab.CONDITION_GROUP_BUCKETS & cond.keys()
    if buckets and not (
        {"field", "operator"} & cond.keys()
    ):
        new_group: dict = {}
        for bucket in sorted(buckets):
            members = cond.get(bucket)
            if not isinstance(members, list):
                continue
            kept = []
            for j, member in enumerate(members):
                if not isinstance(member, dict):
                    continue
                atom = _rewrite_atom(member, trigger_of(member), resolution,
                                     f"{owner_path}.{bucket}[{j}]", repairs,
                                     count_alias)
                if atom is not None:
                    kept.append(atom)
            if kept:
                new_group[bucket] = kept
        return new_group or None

    operator = str(cond.get("operator") or "")

    # The or/and pseudo-group invention: {operator: or|and, conditions: [...]}.
    inner = cond.get("conditions")
    if operator in ("or", "and") and isinstance(inner, list):
        count_alias(operator)
        bucket = "any_of" if operator == "or" else "all_of"
        repairs.append({
            "action": "alias-operator", "path": owner_path,
            "detail": f"pseudo-group '{operator}' -> {bucket}", "error": False,
        })
        kept = []
        for j, member in enumerate(inner):
            if not isinstance(member, dict):
                continue
            atom = _rewrite_atom(member, trigger_of(member), resolution,
                                 f"{owner_path}.conditions[{j}]", repairs,
                                 count_alias)
            if atom is not None:
                kept.append(atom)
        return {bucket: kept} if kept else None

    # contains_any: any_of membership over the value list.
    if operator == "contains_any":
        count_alias("contains_any")
        repairs.append({
            "action": "alias-operator", "path": owner_path,
            "detail": "contains_any -> any_of membership", "error": False,
        })
        values = cond.get("value")
        values = values if isinstance(values, list) else [values]
        trigger = trigger_of(cond)
        kept = []
        for v in values:
            atom = _rewrite_atom(
                {"field": cond.get("field"),
                 "operator": _membership_op(trigger), "value": v},
                trigger, resolution, owner_path, repairs, count_alias)
            if atom is not None:
                kept.append(atom)
        if not kept:
            return None
        return {"any_of": kept} if len(kept) > 1 else kept[0]

    # Plain (possibly aliased) atom.
    return _rewrite_atom(cond, trigger_of(cond), resolution, owner_path,
                         repairs, count_alias)


# --------------------------------------------------------------------------- #
# Step 3: hallucinated-widget check (dump given -> fail loudly).
# --------------------------------------------------------------------------- #

def _check_widgets_exist(fields: List[dict], dump: dict) -> None:
    names = [
        e.get("name") for e in (dump.get("fields") or [])
        if isinstance(e, dict) and isinstance(e.get("name"), str)
    ]
    name_set = set(names)

    def exists(claim: str) -> bool:
        return claim in name_set or any(n.endswith("." + claim) for n in names)

    hallucinated = []
    for f in fields:
        if not isinstance(f, dict):
            continue
        for claim in [f.get("pdf_field_name")] + [
            o.get("pdf_field_name") for o in (f.get("options") or [])
            if isinstance(o, dict)
        ]:
            if isinstance(claim, str) and claim and not exists(claim):
                hallucinated.append(f"{f.get('id')}: {claim}")
    if hallucinated:
        raise RepairError(
            "draft references widgets the PDF does not have (repair cannot "
            "invent mappings): " + "; ".join(hallucinated[:10]))


# --------------------------------------------------------------------------- #
# Step 4: strict-model validity fixes the LLM keeps getting wrong
# (bd polyglot-pdf-n3mn -- surfaced by the 6s71 paid verification run).
# --------------------------------------------------------------------------- #

_VALID_SUPPLEMENTS = frozenset(m.value for m in SupplementType)


def _normalize_checkbox_shapes(fields: List[dict],
                               repairs: List[dict]) -> Dict[str, str]:
    """The v1/LLM checkbox idioms that v2's model rejects (migrate Pass 1
    parity -- _is_group_checkbox / _unwrap_single_option_checkbox).

    - A checkbox with EXACTLY ONE option is a standalone boolean box: v2
      forbids options on a `checkbox`, so lift the option's pdf_field_name
      onto the field (when the field lacks one) and drop options[]. The
      f1040 draft carries 37 of these (bd polyglot-pdf-n3mn).
    - A checkbox with >= 2 options is the v1 group idiom: retype to
      checkbox_group (whose per-box identity lives on options[]), dropping
      any field-level pdf_field_name the group must not carry.

    Returns trigger id -> the unwrapped single option's OLD value, so
    conditions that referenced it can move to the is_checked idiom (the
    value vanishes with the unwrap -- bd c5r8)."""
    standalone_old: Dict[str, str] = {}
    for i, f in enumerate(fields):
        if f.get("type") != "checkbox":
            continue
        fid = f.get("id")
        path = f"fields[{i}] (id={fid})"
        opts = f.get("options")
        if not isinstance(opts, list) or not opts:
            continue
        if len(opts) == 1:
            opt = opts[0]
            if isinstance(opt, dict):
                if opt.get("value") is not None and isinstance(fid, str):
                    standalone_old[fid] = str(opt["value"])
                if not f.get("pdf_field_name") and opt.get("pdf_field_name"):
                    f["pdf_field_name"] = opt["pdf_field_name"]
            f.pop("options", None)
            repairs.append({
                "action": "unwrap-standalone-checkbox", "path": path,
                "detail": "single-option checkbox -> plain v2 boolean "
                          "checkbox (options dropped)",
                "error": False,
            })
        else:
            f["type"] = "checkbox_group"
            f.pop("pdf_field_name", None)
            repairs.append({
                "action": "retype-checkbox-group", "path": path,
                "detail": f"checkbox with {len(opts)} options -> "
                          "checkbox_group (v1 group idiom)",
                "error": False,
            })
    return standalone_old


def _retarget_unwrapped_conditions(fields: List[dict],
                                   standalone_old: Dict[str, str],
                                   repairs: List[dict]) -> None:
    """Rewrite `equals <old single-option value>` on an unwrapped standalone
    checkbox to `is_checked` -- the option (and its value) vanished with the
    unwrap, so the equals would dangle against the now-boolean trigger and
    never fire (migrate Pass 2's standalone fixup; bd c5r8). Only `equals`
    moves; migrate deliberately leaves a standalone not_equals for human
    review, and repair matches that."""
    if not standalone_old:
        return
    for i, f in enumerate(fields):
        for kind in ("show_if", "require_if"):
            cond = f.get(kind)
            if not isinstance(cond, dict):
                continue
            for atom in _walk_condition_atoms(cond):
                tid = atom.get("field")
                old = standalone_old.get(tid) if isinstance(tid, str) else None
                if (old is not None and atom.get("operator") == "equals"
                        and str(atom.get("value")) == old):
                    atom["operator"] = "is_checked"
                    atom.pop("value", None)
                    repairs.append({
                        "action": "alias-operator",
                        "path": f"fields[{i}] (id={f.get('id')}).{kind}",
                        "detail": f"equals {old!r} on unwrapped standalone "
                                  "checkbox -> is_checked",
                        "error": False,
                    })


def _repair_overflow_supplement(f: dict, path: str, repairs: List[dict]) -> None:
    """Alias an invented overflow_to_supplement value to the enum.

    SupplementType has a single member ("supplement_a", the feature is not
    fully implemented), but the LLM improvises names for the same intent
    (i-90 emitted "additional_information" -- its supplement IS the
    "Additional Information" part). Any invalid STRING means "overflows to
    the supplement", so alias it; a non-string has no readable intent and is
    dropped. Either way the draft passes FormSchema.model_validate instead
    of failing the enum."""
    val = f.get("overflow_to_supplement")
    if val is None or (isinstance(val, str) and val in _VALID_SUPPLEMENTS):
        return
    if isinstance(val, str):
        canonical = SupplementType.TYPE.value
        f["overflow_to_supplement"] = canonical
        repairs.append({
            "action": "alias-overflow-supplement", "path": path,
            "detail": f"{val!r} -> {canonical!r} (only SupplementType member)",
            "error": False,
        })
    else:
        f.pop("overflow_to_supplement", None)
        repairs.append({
            "action": "drop-overflow-supplement", "path": path,
            "detail": f"non-string overflow_to_supplement {val!r} dropped",
            "error": False,
        })


def _complete_supplements(schema: dict, repairs: List[dict]) -> None:
    """Complete a contract-shaped supplements entry to the model shape.

    The extractor contract's top-level shape taught `supplements` as
    {id, label} while FormSupplement requires {id, name, purpose, fields}
    (bd polyglot-pdf-n3mn -- the i-90 draft followed the contract faithfully
    and failed the model). Deterministic completion: name <- label (or the
    humanized id); purpose <- name (the model wants prose the draft does not
    carry; the human editor refines it); fields <- [] when absent. The
    contract now teaches the full shape too -- this is the net for older
    drafts and model drift."""
    supps = schema.get("supplements")
    if not isinstance(supps, list):
        return
    for j, s in enumerate(supps):
        if not isinstance(s, dict):
            continue
        completed = []
        if not s.get("name"):
            s["name"] = (s.get("label") or _humanize_slug(s.get("id"))
                         or f"Supplement {j + 1}")
            completed.append("name")
        if not s.get("purpose"):
            s["purpose"] = s["name"]
            completed.append("purpose")
        if not isinstance(s.get("fields"), list):
            s["fields"] = []
            completed.append("fields")
        if completed:
            repairs.append({
                "action": "complete-supplement",
                "path": f"supplements[{j}] (id={s.get('id')})",
                "detail": "filled required key(s) the draft lacked: "
                          + ", ".join(completed),
                "error": False,
            })


def _dump_tu_by_name(dump: Optional[dict]) -> Dict[str, str]:
    """pdf field name -> /TU tooltip, from an acroform dump (when given).

    Tolerant of the dump's nesting: a field entry may carry "tu" at its top
    level or on a member of its "widgets" list (acroform_dump emits both
    shapes across versions)."""
    out: Dict[str, str] = {}
    if not isinstance(dump, dict):
        return out
    for e in dump.get("fields") or []:
        if not isinstance(e, dict) or not isinstance(e.get("name"), str):
            continue
        tu = e.get("tu")
        if not tu:
            for w in e.get("widgets") or []:
                if isinstance(w, dict) and w.get("tu"):
                    tu = w["tu"]
                    break
        if isinstance(tu, str) and tu.strip():
            out[e["name"]] = tu.strip()
    return out


def _humanize_slug(val: Any) -> Optional[str]:
    """A display label from a semantic slug, or None if it has no words
    (e.g. the bare "1" an f1040 checkbox option carries)."""
    if val is None:
        return None
    s = str(val).replace("_", " ").replace("-", " ").strip()
    if not s or not any(c.isalpha() for c in s):
        return None
    return s[0].upper() + s[1:]


def _synthesize_option_labels(f: dict, path: str, tu_by_name: Dict[str, str],
                              repairs: List[dict]) -> None:
    """Fill in a missing/empty option label (FormSchema requires one).

    The LLM omits option labels (f1040 emitted 37 label-less options; those
    particular ones were lone-option checkboxes, which the shape
    normalization now unwraps entirely -- this covers the remaining
    option-bearing shapes: radio / select / checkbox_group). Source
    priority: the widget's /TU tooltip (when a dump was supplied) -> the
    FIELD's own label/name when it is the field's ONLY option (a lone
    option's label IS the field's question) -> a humanized value slug ->
    a humanized pdf_on_value -> "Option N"."""
    opts = f.get("options")
    if not isinstance(opts, list):
        return
    single = len(opts) == 1
    for j, o in enumerate(opts):
        if not isinstance(o, dict) or o.get("label"):
            continue
        label: Optional[str] = None
        pfn = o.get("pdf_field_name")
        if isinstance(pfn, str) and pfn:
            label = tu_by_name.get(pfn) or next(
                (tu for name, tu in tu_by_name.items()
                 if name.endswith("." + pfn)), None)
        if not label and single:
            fl = f.get("label") or f.get("name")
            label = fl.strip() if isinstance(fl, str) and fl.strip() else None
        if not label:
            label = (_humanize_slug(o.get("value"))
                     or _humanize_slug(o.get("pdf_on_value")))
        if not label:
            label = f"Option {j + 1}"
        o["label"] = label
        repairs.append({
            "action": "synthesize-option-label",
            "path": f"{path}.options[{j}]",
            "detail": f"missing label -> {label!r}",
            "error": False,
        })


# --------------------------------------------------------------------------- #
# Entry point.
# --------------------------------------------------------------------------- #

def repair(schema: dict, dump: Optional[dict] = None) -> Tuple[dict, List[dict]]:
    """Deterministic, idempotent repair toward the v2 vocabulary.

    Returns (repaired_copy, repairs). Raises RepairError on hallucinated
    widgets (only checkable when a dump is supplied)."""
    repaired = copy.deepcopy(schema)
    repairs: List[dict] = []
    fields = [f for f in (repaired.get("fields") or []) if isinstance(f, dict)]

    if dump is not None:
        _check_widgets_exist(fields, dump)

    alias_hits: Dict[str, int] = {}

    def count_alias(name: str) -> None:
        alias_hits[name] = alias_hits.get(name, 0) + 1

    # Checkbox-shape normalization FIRST (before slug minting and the
    # condition rewrites, matching migrate's Pass 1 -> Pass 2 ordering): a
    # lone-option checkbox unwraps to the standalone boolean idiom (its old
    # option value feeding both the native-condition retarget below and the
    # controls_fields mirroring's is_checked fixup -- bd c5r8 / bd
    # polyglot-pdf-n3mn), and a multi-option checkbox retypes to
    # checkbox_group so minting sees the final type.
    standalone_old_value = _normalize_checkbox_shapes(fields, repairs)
    _retarget_unwrapped_conditions(fields, standalone_old_value, repairs)

    resolution = _mint_slugs(fields, repairs)
    fields_by_id = {str(f.get("id")): f for f in fields}

    tu_by_name = _dump_tu_by_name(dump)

    for i, f in enumerate(fields):
        fid = str(f.get("id"))
        for kind in ("show_if", "require_if"):
            if kind not in f or f.get(kind) is None:
                continue
            new_cond = _rewrite_condition(
                f.get(kind), f"fields[{i}] (id={fid}).{kind}",
                fields_by_id, resolution, repairs, count_alias)
            if new_cond is None:
                f.pop(kind, None)
            else:
                f[kind] = new_cond

        # Strict-model validity fixes (bd polyglot-pdf-n3mn): an invented
        # overflow_to_supplement enum value and a missing option label both
        # fail FormSchema.model_validate on an otherwise-clean draft.
        _repair_overflow_supplement(f, f"fields[{i}] (id={fid})", repairs)
        _synthesize_option_labels(f, f"fields[{i}] (id={fid})", tu_by_name,
                                  repairs)

    # controls_fields / conditional_fields: v2 has NO trigger-side conditional
    # logic (bd h76m.16 deleted both from the model). Rather than silently
    # dropping a draft's controls_fields (leaving its shows/makes_required
    # behavior lost, and the schema RED under legacy-trigger-side-logic),
    # mirror each edge into the TARGET field's show_if/require_if -- the same
    # deterministic conversion scripts/migrate_schema_v2.py Pass 4 proved (bd
    # polyglot-pdf-c3y6). The mirrored atom is routed through THIS module's
    # own atom-rewrite machinery (_rewrite_atom, via the resolution/alias map
    # already built above) so it gets the identical slug/operator aliasing
    # every other repaired atom gets.
    #
    # This is a SECOND pass over fields, deliberately AFTER the show_if/
    # require_if rewrite loop above finished for ALL fields (mirroring
    # migrate_schema_v2's Pass 2 -> Pass 4 ordering): the already-mirrored
    # suppression compares the NORMALIZED mirrored atom against the target's
    # condition, so every target must already be normalized -- a fused single
    # loop would compare against a raw not-yet-rewritten condition whenever
    # the trigger precedes its target in field order, missing the match and
    # duplicating the edge into a spurious any_of (fresh-eyes finding on this
    # bead).
    for i, f in enumerate(fields):
        fid = str(f.get("id"))
        controls = f.get("controls_fields")
        if isinstance(controls, list):
            path = f"fields[{i}] (id={fid}).controls_fields"

            def _normalize(atom: dict, _path=path) -> Optional[dict]:
                trig = fields_by_id.get(atom.get("field")) \
                    if isinstance(atom.get("field"), str) else None
                # v1-semantics pre-pass (migrate_schema_v2._rewrite_atom_value
                # parity -- Opus review gap on this bead): a controls_fields
                # edge is a v1 construct, so equals/not_equals on a
                # checkbox_group trigger MEANS membership -- alias it the way
                # the migration does instead of letting the v2 fail-open
                # trigger-compat drop lose the edge. Emptiness first, then
                # membership, mirroring the migration's ordering. This applies
                # ONLY to mirrored v1 edges; a native v2 show_if atom keeps
                # the stricter drop policy.
                op = atom.get("operator")
                ttype = str(trig.get("type")) if isinstance(trig, dict) else None
                if (op in ("equals", "not_equals")
                        and str(atom.get("value", "")) == ""):
                    # v1 emptiness idiom, ANY trigger type (migrate applies it
                    # unguarded, BEFORE the membership rewrite): equals ""
                    # means "field is empty" -- v2 spells that is_empty/
                    # is_not_empty (no value).
                    atom["operator"] = ("is_empty" if op == "equals"
                                        else "is_not_empty")
                    atom.pop("value", None)
                elif ttype == "checkbox_group" and op in ("equals", "not_equals"):
                    new_op = ("includes" if op == "equals"
                              else "not_includes")
                    repairs.append({
                        "action": "alias-operator", "path": _path,
                        "detail": f"{op} on checkbox_group trigger -> "
                                  f"{new_op} (v1 controls_fields "
                                  "membership reading)",
                        "error": False,
                    })
                    count_alias(f"{op}@controls_fields")
                    atom["operator"] = new_op
                elif (op == "is_checked"
                        and ttype in vocab.CHOICE_FIELD_TYPES):
                    # is_checked on an OPTION-BEARING trigger (checkbox_group/
                    # radio/select) means "a selection exists" -> is_not_empty
                    # (migrate _rewrite_atom_value's dual-fate rule; the
                    # standalone `checkbox` trigger keeps is_checked). Without
                    # this the mirrored atom itself lints operator-trigger RED
                    # (Opus review gap, round 2).
                    repairs.append({
                        "action": "alias-operator", "path": _path,
                        "detail": f"is_checked on {ttype!r} trigger -> "
                                  "is_not_empty (v1 controls_fields "
                                  "selection-exists reading)",
                        "error": False,
                    })
                    count_alias("is_checked@controls_fields")
                    atom["operator"] = "is_not_empty"
                    atom.pop("value", None)
                return _rewrite_atom(atom, trig, resolution, _path, repairs,
                                     count_alias)

            outcome = cfm.mirror_controls_fields(
                f, fields_by_id, _walk_condition_atoms, _normalize,
                standalone_old_value)
            for m in outcome["mirrored"]:
                repairs.append({
                    "action": "mirror-controls-fields",
                    "path": path,
                    "detail": f"{m['trigger']} {m['key']} <- "
                              f"{m['atom']} (mirrored onto {m['target']})",
                    "error": False,
                })
            for tid in outcome["dangling"]:
                repairs.append({
                    "action": "controls-fields-dangling",
                    "path": path,
                    "detail": f"controls_fields target {tid!r} resolves to no "
                              "field -- edge dropped, needs human review",
                    "error": True,
                })
            for u in outcome["unconverted"]:
                if u["unconverted_action_keys"]:
                    repairs.append({
                        "action": "controls-fields-unmirrored",
                        "path": path,
                        "detail": f"trigger {u['trigger']!r} action(s) "
                                  f"{u['unconverted_action_keys']} have no v2 "
                                  "target-side equivalent -- dropped, needs "
                                  "human review",
                        "error": False,
                    })
        # conditional_fields is a plain legacy list of field ids (no
        # trigger-side actions to mirror -- unlike controls_fields it never
        # carried operator/value/action-key structure), so there is nothing
        # target-side to convert it INTO; it is simply removed, logged.
        if "conditional_fields" in f:
            repairs.append({
                "action": "drop-conditional-fields",
                "path": f"fields[{i}] (id={fid}).conditional_fields",
                "detail": "legacy conditional_fields removed (no v2 "
                          "target-side equivalent to mirror into)",
                "error": False,
            })
        f.pop("controls_fields", None)
        f.pop("conditional_fields", None)

    # Schema-level: complete a contract-shaped supplements entry (bd
    # polyglot-pdf-n3mn).
    _complete_supplements(repaired, repairs)

    if alias_hits:
        repairs.append({
            "action": "alias-hit-rate", "path": "$",
            "detail": ", ".join(f"{k}={v}" for k, v in sorted(alias_hits.items())),
            "error": False,
        })
    return repaired, repairs


def alias_hit_count(repairs: List[dict]) -> int:
    """Total invented-vocabulary hits this pass (the P6 decay metric)."""
    return sum(1 for r in repairs if r["action"] == "alias-operator")
