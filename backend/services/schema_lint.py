"""Schema lint: structured findings over a RAW form-schema dict (bd h76m.5, P2.1).

Why this exists beside the Pydantic model: the v2 strictness validators in
backend/models/form_models.py RAISE on a v2-stamped schema, but the pipeline
needs structured, per-finding reports over BOTH wire shapes -- including drafts
too broken to parse at all (the archived W-7 draft with invented operators is
the canonical example). So this module lints the raw dict, never model classes:
it must keep working on exactly the inputs model_validate rejects.

Pure function, no I/O: lint_schema(schema, dump=None) -> List[LintFinding].
The optional dump is the acroform_dump.py JSON (scripts/bakeoff) for the
widget-claim rule; without it the PDF-mapping rules are skipped.

Severity contract (the two-gate seam, plan P2.1/P5.3): ERROR findings block
Mark-complete promotion (zero ERRORs to promote -- wired in
backend/routes/editor_kit_routes.py); WARNING findings inform but never block.
Both v1 (schema_version None/'1') and v2 ('2') shapes are accepted until the
P6.2 strictness flip; rules that only make sense for v2 (option-value slug
format) are gated on the version stamp.

Rules (stable ids; one finding per violation site):
- unknown-operator      ERROR   operator not in the v2 registry
- value-arity           ERROR   value shape does not match the operator's arity
- option-value-missing  ERROR   an option has no/empty value
- option-value-duplicate ERROR  two options of one field share a value
- option-value-comma    ERROR   an option value contains a comma (breaks the
                                voice comma-join contract)
- option-value-slug     ERROR   (v2 only) option value is not a valid slug
- ref-unresolved-field  ERROR   a condition or control action references a
                                non-existent field id
- operator-trigger      ERROR   operator is not valid on the trigger field's
                                type (one v1 tolerance: is_checked on an
                                option-bearing trigger, the shipped vq4m-era
                                idiom that P6.1 migrates to is_not_empty)
- ref-option-value      ERROR   an option-referencing condition value is not
                                one of the trigger field's option values
- condition-malformed   ERROR   a show_if/require_if is not a dict / an atom
                                is missing field/operator
- composite-depth       ERROR   nested ConditionGroup buckets, or atom keys
                                mixed with bucket keys (depth <= 1 is the
                                contract)
- show-if-cycle         WARNING show_if dependencies form a cycle
- dump-widget-multiclaim ERROR  (dump only) one PDF widget claimed by more
                                than one field, or by more than one option of
                                the same field

ASCII only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from backend.models import conditional_vocabulary as vocab

SEVERITY_ERROR = "ERROR"
SEVERITY_WARNING = "WARNING"

_ATOM_KEYS = frozenset({"field", "operator"})

# Every field-anchored finding path embeds its field id as "(id=X)" (see the
# _walk/_check helpers below); the editor's ValidationPanel focuses a finding by
# selecting that field, so the id extraction is authored HERE (one Python
# implementation) rather than re-parsed in the frontend (bd h76m.11, P4.3).
_FIELD_ID_RE = re.compile(r"\(id=(.*?)\)")


def field_id_of(path: str) -> Optional[str]:
    """The schema field id a finding path anchors to, or None.

    Field-anchored paths carry "(id=X)" (fields[3] (id=x).show_if,
    "fields (id=y)" for show-if-cycle warnings); non-field paths ("$",
    "widget 'foo'") have no id and return None -- the panel simply renders
    those without a click-to-focus target. A literal "(id=None)" (a field
    with no id key) is treated as no anchor: there is nothing to focus.
    """
    m = _FIELD_ID_RE.search(path or "")
    if not m:
        return None
    fid = m.group(1)
    return fid if fid and fid != "None" else None


@dataclass(frozen=True)
class LintFinding:
    severity: str  # SEVERITY_ERROR | SEVERITY_WARNING
    rule: str      # stable rule id (see module docstring)
    path: str      # e.g. "fields[3] (id=x).show_if"
    message: str

    def as_dict(self) -> Dict[str, Optional[str]]:
        return {
            "severity": self.severity,
            "rule": self.rule,
            "path": self.path,
            "message": self.message,
            # field_id lets the editor focus the offending field on click; it is
            # derived from `path`, never a second source of truth.
            "field_id": field_id_of(self.path),
        }


def has_errors(findings: List[LintFinding]) -> bool:
    return any(f.severity == SEVERITY_ERROR for f in findings)


def summarize(findings: List[LintFinding]) -> str:
    errors = sum(1 for f in findings if f.severity == SEVERITY_ERROR)
    warnings = len(findings) - errors
    return f"{errors} error(s), {warnings} warning(s)"


# ---------------------------------------------------------------------------
# Raw-dict condition walking (never the Pydantic classes -- see module doc).
# ---------------------------------------------------------------------------

def _walk_condition(
    cond: Any, path: str, out: List[LintFinding]
) -> List[Tuple[str, Dict[str, Any]]]:
    """Flatten a raw show_if/require_if value to its atom dicts.

    Returns (atom_path, atom_dict) pairs; structural problems (non-dict,
    nesting, atom/bucket key mixing) are appended to `out` and the offending
    node is skipped rather than raising -- lint reports, it never throws.
    """
    if cond is None:
        return []
    if not isinstance(cond, dict):
        out.append(LintFinding(
            SEVERITY_ERROR, "condition-malformed", path,
            f"condition must be an object, found {type(cond).__name__}",
        ))
        return []

    buckets = vocab.CONDITION_GROUP_BUCKETS & cond.keys()
    has_atom_keys = bool(_ATOM_KEYS & cond.keys())

    if buckets and has_atom_keys:
        out.append(LintFinding(
            SEVERITY_ERROR, "composite-depth", path,
            "condition mixes atomic keys (field/operator) with composite "
            f"buckets ({', '.join(sorted(buckets))}) -- use ONE shape",
        ))
        return []

    if not buckets:
        return [(path, cond)]

    atoms: List[Tuple[str, Dict[str, Any]]] = []
    problems_before = len(out)
    for bucket in sorted(buckets):
        members = cond.get(bucket)
        if not isinstance(members, list):
            out.append(LintFinding(
                SEVERITY_ERROR, "condition-malformed", f"{path}.{bucket}",
                "bucket must be a list of atomic conditions",
            ))
            continue
        for i, member in enumerate(members):
            member_path = f"{path}.{bucket}[{i}]"
            if not isinstance(member, dict):
                out.append(LintFinding(
                    SEVERITY_ERROR, "condition-malformed", member_path,
                    f"bucket member must be an object, found {type(member).__name__}",
                ))
                continue
            if vocab.CONDITION_GROUP_BUCKETS & member.keys():
                out.append(LintFinding(
                    SEVERITY_ERROR, "composite-depth", member_path,
                    "bucket members must be atomic {field, operator, value} "
                    "conditions -- nesting is not allowed (depth <= 1)",
                ))
                continue
            atoms.append((member_path, member))
    if not atoms and len(out) == problems_before:
        # All buckets present but empty (e.g. {"all_of": []}): ConditionGroup
        # rejects this shape (at least one non-empty bucket), so the raw-draft
        # path must report it too (Codex PR #302).
        out.append(LintFinding(
            SEVERITY_ERROR, "condition-malformed", path,
            "composite condition has no conditions (at least one non-empty "
            "bucket of all_of/any_of/none_of is required)",
        ))
    return atoms


def _check_atom(
    atom_path: str,
    atom: Dict[str, Any],
    trigger_field: Optional[Dict[str, Any]],
    out: List[LintFinding],
    fields_by_id: Dict[str, Dict[str, Any]],
    resolve_trigger: bool,
    is_v2: bool,
) -> None:
    """Operator/arity/reference/compatibility checks for one atomic condition.

    resolve_trigger: show_if/require_if atoms name their trigger via
    atom['field'] (resolved from fields_by_id); a controls_fields entry's
    trigger is the OWNING field (passed as trigger_field, no 'field' key).
    """
    operator = atom.get("operator")
    if not isinstance(operator, str) or not operator:
        out.append(LintFinding(
            SEVERITY_ERROR, "condition-malformed", atom_path,
            "condition is missing its operator",
        ))
        return
    spec = vocab.OPERATORS.get(operator)
    if spec is None:
        out.append(LintFinding(
            SEVERITY_ERROR, "unknown-operator", atom_path,
            f"operator {operator!r} is not in the v2 registry (allowed: "
            f"{', '.join(sorted(vocab.ALLOWED_OPERATORS))})",
        ))
        return

    if resolve_trigger:
        ref = atom.get("field")
        if not isinstance(ref, str) or not ref:
            out.append(LintFinding(
                SEVERITY_ERROR, "condition-malformed", atom_path,
                "condition is missing its trigger field id",
            ))
            return
        trigger_field = fields_by_id.get(ref)
        if trigger_field is None:
            out.append(LintFinding(
                SEVERITY_ERROR, "ref-unresolved-field", atom_path,
                f"references non-existent field {ref!r}",
            ))
            return

    # Operator/trigger compatibility (Codex PR #302): for v1 schemas lint is
    # the ONLY gate that can catch a mismatch (the model's compat validator
    # runs on v2-stamped schemas only), and the runtime evaluator has no
    # branch for e.g. `includes` on a text trigger. ONE version-gated
    # tolerance: v1 `is_checked` on an option-bearing trigger is the shipped
    # vq4m-era idiom ("any box checked"; i-90 uses it on radio groups) --
    # the P6.1 migration rewrites it to is_not_empty.
    trigger_type = trigger_field.get("type") if trigger_field else None
    if isinstance(trigger_type, str) and trigger_type:
        tolerated_v1_idiom = (
            not is_v2
            and operator == "is_checked"
            and trigger_type in (vocab.CHOICE_FIELD_TYPES | {"checkbox"})
        )
        if trigger_type not in vocab.CONDITION_TRIGGER_TYPES:
            if not tolerated_v1_idiom:
                out.append(LintFinding(
                    SEVERITY_ERROR, "operator-trigger", atom_path,
                    f"field type {trigger_type!r} cannot trigger conditions",
                ))
                return
        elif trigger_type not in spec.trigger_types and not tolerated_v1_idiom:
            out.append(LintFinding(
                SEVERITY_ERROR, "operator-trigger", atom_path,
                f"operator {operator!r} is not valid on a {trigger_type!r} "
                f"trigger (valid on: {', '.join(sorted(spec.trigger_types))})",
            ))
            return

    value = atom.get("value")
    if spec.value_arity == "none":
        # A vestigial value on a no-value operator is tolerated on v1 drafts
        # (the operator ignores it) but is a real arity error on a v2-stamped
        # schema -- the model rejects that exact shape, and lint must agree
        # on the Pydantic-rejected raw-draft path (Codex PR #302).
        if is_v2 and value is not None:
            out.append(LintFinding(
                SEVERITY_ERROR, "value-arity", atom_path,
                f"operator {operator!r} takes no value (found one)",
            ))
        return
    if spec.value_arity == "list":
        if not isinstance(value, list) or not value:
            out.append(LintFinding(
                SEVERITY_ERROR, "value-arity", atom_path,
                f"operator {operator!r} requires a non-empty list value",
            ))
            return
        values = value
    else:  # scalar
        if value is None or isinstance(value, list):
            out.append(LintFinding(
                SEVERITY_ERROR, "value-arity", atom_path,
                f"operator {operator!r} requires a single scalar value",
            ))
            return
        values = [value]

    if (
        spec.value_must_be_trigger_option
        and trigger_field is not None
        and str(trigger_field.get("type")) in vocab.CHOICE_FIELD_TYPES
    ):
        options = trigger_field.get("options")
        if not isinstance(options, list):
            options = []  # malformed options never crash the never-throws contract
        # Both runtime option shapes: {value,label} dicts and legacy plain
        # strings (a string option's value is the string itself -- same
        # contract as the frontend's optionValue()).
        option_values = {
            str(o.get("value")) if isinstance(o, dict) else str(o)
            for o in options
            if (isinstance(o, dict) and o.get("value") is not None)
            or isinstance(o, str)
        }
        if option_values:
            for v in values:
                # Empty string is the v1 emptiness idiom (equals/not_equals ""
                # means "field is empty/not empty" -- the i-90 gold uses it on
                # unit-type radios), not an option reference; the P6.1
                # migration rewrites it to is_empty/is_not_empty.
                if str(v) == "":
                    continue
                if str(v) not in option_values:
                    out.append(LintFinding(
                        SEVERITY_ERROR, "ref-option-value", atom_path,
                        f"value {v!r} is not an option value of trigger "
                        f"{trigger_field.get('id')!r}",
                    ))


# ---------------------------------------------------------------------------
# Per-field option-value convention.
# ---------------------------------------------------------------------------

def _check_options(
    field_path: str, f: Dict[str, Any], is_v2: bool, out: List[LintFinding]
) -> None:
    options = f.get("options")
    if not isinstance(options, list):
        return
    seen_values: Dict[str, int] = {}
    for i, o in enumerate(options):
        opt_path = f"{field_path}.options[{i}]"
        if isinstance(o, str):
            # Legacy plain-string option: the string IS the value (the
            # frontend's optionValue() contract), so the value-hygiene rules
            # apply to it directly (Codex PR #302 -- skipping these let
            # duplicate/comma defects through in string-option schemas).
            value = o
        elif isinstance(o, dict):
            value = o.get("value")
        else:
            continue
        if value is None or (isinstance(value, str) and value.strip() == ""):
            out.append(LintFinding(
                SEVERITY_ERROR, "option-value-missing", opt_path,
                "option has no value (every option needs a stable value)",
            ))
            continue
        value_str = str(value)
        if "," in value_str:
            out.append(LintFinding(
                SEVERITY_ERROR, "option-value-comma", opt_path,
                f"option value {value_str!r} contains a comma -- commas are the "
                "voice multi-select join delimiter and are forbidden in values",
            ))
        if is_v2 and not vocab.is_valid_option_slug(value_str):
            out.append(LintFinding(
                SEVERITY_ERROR, "option-value-slug", opt_path,
                f"option value {value_str!r} is not a v2 slug "
                "(lowercase ascii [a-z0-9_-], minted from the label)",
            ))
        seen_values[value_str] = seen_values.get(value_str, 0) + 1
    for value_str, count in seen_values.items():
        if count > 1:
            out.append(LintFinding(
                SEVERITY_ERROR, "option-value-duplicate", field_path,
                f"option value {value_str!r} appears {count} times (option "
                "values must be unique per field)",
            ))


# ---------------------------------------------------------------------------
# show_if cycle detection (WARNING).
# ---------------------------------------------------------------------------

def _check_cycles(
    fields: List[Dict[str, Any]],
    fields_by_id: Dict[str, Dict[str, Any]],
    out: List[LintFinding],
) -> None:
    """DFS over the show_if trigger graph; each cycle is reported once."""
    graph: Dict[str, List[str]] = {}
    for f in fields:
        fid = f.get("id")
        if not isinstance(fid, str):
            continue
        scratch: List[LintFinding] = []  # structural problems reported elsewhere
        triggers: List[str] = []
        for _, atom in _walk_condition(f.get("show_if"), "", scratch):
            ref = atom.get("field")
            if isinstance(ref, str) and ref in fields_by_id:
                triggers.append(ref)
        graph[fid] = triggers

    # Iterative DFS (explicit stack): a long acyclic show_if chain in a large
    # generated form must not hit Python's recursion limit -- the linter never
    # throws (Codex PR #302).
    WHITE, GRAY, BLACK = 0, 1, 2
    color: Dict[str, int] = {fid: WHITE for fid in graph}
    reported: set = set()

    for start in graph:
        if color[start] != WHITE:
            continue
        color[start] = GRAY
        stack = [(start, iter(graph.get(start, [])))]
        path = [start]
        while stack:
            node, neighbors = stack[-1]
            nxt = next(neighbors, None)
            if nxt is None:
                stack.pop()
                path.pop()
                color[node] = BLACK
                continue
            state = color.get(nxt, BLACK)
            if state == GRAY:
                cycle = tuple(sorted(path[path.index(nxt):]))
                if cycle not in reported:
                    reported.add(cycle)
                    out.append(LintFinding(
                        SEVERITY_WARNING, "show-if-cycle",
                        f"fields (id={nxt})",
                        "show_if dependencies form a cycle: "
                        + " -> ".join(path[path.index(nxt):] + [nxt]),
                    ))
            elif state == WHITE:
                color[nxt] = GRAY
                stack.append((nxt, iter(graph.get(nxt, []))))
                path.append(nxt)


# ---------------------------------------------------------------------------
# Dump widget claims (ERROR, only when a dump is provided).
# ---------------------------------------------------------------------------

def _dump_names(dump: Dict[str, Any]) -> List[str]:
    entries = dump.get("fields") if isinstance(dump, dict) else None
    if not isinstance(entries, list):
        return []
    return [
        e.get("name") for e in entries
        if isinstance(e, dict) and isinstance(e.get("name"), str)
    ]


def _match_dump_names(claim: str, dump_names: List[str]) -> List[str]:
    """Resolve a schema pdf_field_name to dump widget names.

    Same convention as the filler's find_widget (pdf_fill_routes.py): exact
    match first, else a dot-boundary suffix match (schemas store the XFA leaf,
    the dump stores the full path)."""
    exact = [n for n in dump_names if n == claim]
    if exact:
        return exact
    return [n for n in dump_names if n.endswith("." + claim)]


def _check_dump_claims(
    fields: List[Dict[str, Any]], dump: Dict[str, Any], out: List[LintFinding]
) -> None:
    dump_names = _dump_names(dump)
    if not dump_names:
        return
    # dump widget name -> list of (field_id, claim kind)
    claims: Dict[str, List[Tuple[str, str]]] = {}

    def register(claim: Optional[Any], fid: str, kind: str) -> None:
        if not isinstance(claim, str) or not claim:
            return
        for name in _match_dump_names(claim, dump_names):
            claims.setdefault(name, []).append((fid, kind))

    for f in fields:
        fid = str(f.get("id"))
        register(f.get("pdf_field_name"), fid, "field")
        options = f.get("options")
        if not isinstance(options, list):
            continue  # malformed options never crash the never-throws contract
        for i, o in enumerate(options):
            if isinstance(o, dict):
                register(o.get("pdf_field_name"), fid, f"option[{i}]")

    for name, claimants in claims.items():
        owners = {fid for fid, _ in claimants}
        if len(owners) > 1:
            out.append(LintFinding(
                SEVERITY_ERROR, "dump-widget-multiclaim", f"widget {name!r}",
                "claimed by more than one field: "
                + ", ".join(sorted(owners)),
            ))
            continue
        option_kinds = [kind for _, kind in claimants if kind != "field"]
        if len(option_kinds) > 1:
            (owner,) = owners
            out.append(LintFinding(
                SEVERITY_ERROR, "dump-widget-multiclaim", f"widget {name!r}",
                f"claimed by more than one option of field {owner!r}: "
                + ", ".join(sorted(option_kinds)),
            ))
        # field-level + a single option of the SAME field is the benign
        # groups-of-one convention (standalone checkbox describing its widget
        # in both places) -- not a finding.


# ---------------------------------------------------------------------------
# Entry point.
# ---------------------------------------------------------------------------

def lint_schema(
    schema: Dict[str, Any], dump: Optional[Dict[str, Any]] = None
) -> List[LintFinding]:
    """Lint a raw form-schema dict (and optionally its acroform dump).

    Never raises on malformed input -- malformed structure IS a finding.
    """
    out: List[LintFinding] = []
    if not isinstance(schema, dict):
        return [LintFinding(
            SEVERITY_ERROR, "condition-malformed", "$",
            f"schema must be an object, found {type(schema).__name__}",
        )]

    is_v2 = str(schema.get("schema_version")) == vocab.SCHEMA_VERSION_V2
    raw_fields = schema.get("fields")
    if not isinstance(raw_fields, list):
        # A non-list fields value (123, true, "oops") is malformed input, and
        # lint never throws on malformed input -- treat as empty (Codex PR
        # #302: iterating a non-iterable crashed the never-throws contract).
        raw_fields = []
    fields = [f for f in raw_fields if isinstance(f, dict)]
    fields_by_id: Dict[str, Dict[str, Any]] = {
        f["id"]: f for f in fields if isinstance(f.get("id"), str)
    }

    for i, f in enumerate(fields):
        field_path = f"fields[{i}] (id={f.get('id')})"

        _check_options(field_path, f, is_v2, out)

        for kind in ("show_if", "require_if"):
            for atom_path, atom in _walk_condition(
                f.get(kind), f"{field_path}.{kind}", out
            ):
                _check_atom(atom_path, atom, None, out, fields_by_id,
                            resolve_trigger=True, is_v2=is_v2)

        controls = f.get("controls_fields")
        if isinstance(controls, list):
            for j, control in enumerate(controls):
                if not isinstance(control, dict):
                    continue
                control_path = f"{field_path}.controls_fields[{j}]"
                # Trigger-side: the condition tests the OWNING field's value;
                # a missing operator defaults to equals (the model's default).
                atom = {
                    "operator": control.get("operator", "equals"),
                    "value": control.get("value"),
                }
                _check_atom(control_path, atom, f, out, fields_by_id,
                            resolve_trigger=False, is_v2=is_v2)
                for action in ("shows", "hides", "unlocks", "locks",
                               "makes_required", "makes_optional"):
                    targets = control.get(action)
                    if not isinstance(targets, list):
                        continue
                    for target in targets:
                        if isinstance(target, str) and target not in fields_by_id:
                            out.append(LintFinding(
                                SEVERITY_ERROR, "ref-unresolved-field",
                                f"{control_path}.{action}",
                                f"references non-existent field {target!r}",
                            ))

    _check_cycles(fields, fields_by_id, out)

    if dump is not None:
        _check_dump_claims(fields, dump, out)

    return out
