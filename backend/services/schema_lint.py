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
- dump-widget-unclaimed WARNING (dump only) a fillable PDF widget that NO field
                                maps to (extraction dropped it -- unfillable
                                through the app); buttons + barcodes excluded
- field-unbacked        ERROR   (source=pdf) a field whose type carries its OWN
                                widget identity but has NO pdf_field_name at
                                all -- un-fillable, un-verifiable, un-fixable
                                (bd polyglot-pdf-xazf; needs no dump)
- field-claim-unresolvable ERROR (dump only) a field/option pdf_field_name that
                                resolves to ZERO dump widgets -- previously
                                silently DROPPED by the claims walk (bd xazf)
- readonly-conditional-no-unlock WARNING a read_only field shown/required by a
                                condition but with no unlock_method -- it is
                                permanently non-fillable when shown
- unlock-missing-flag-change WARNING an unlock_method with no
                                pdf_field_flag_change -- the PDF filler cannot
                                flip the read-only bit, so the field silently
                                stays locked in the filled PDF
- legacy-trigger-side-logic ERROR (v2 only) a schema still carries the removed
                                controls_fields / conditional_fields key
- required-top-level     ERROR   (v2 only) a field carries a TRUTHY top-level
                                `required`; the canonical location is
                                validation.required (read by every kit + the
                                frontend) so a top-level true is silently ignored
                                and the field is treated as optional
- translation-*          WARNING the translation verify/rectify gate's flag
                                taxonomy (TRANSLATION_FLAG_RULES below), re-
                                emitted verbatim from the persisted bake report
                                at _bakeoff.authoring.option_translation.flags
- help-instructions-missing WARNING ONE AGGREGATED finding per schema: N of M
                                askable fields (read_only + signature
                                excluded) have no help.instructions -- the
                                guidance-coverage worklist WITHOUT a per-field
                                flood (a fresh pre-enrichment draft would
                                otherwise emit one warning per field). bd
                                wsao.3
- help-instructions-too-long WARNING instructions exceed the hard bound
                                (guidance_contract.INSTRUCTIONS_HARD_CHARS).
                                Lint-only: nothing truncates -- the full text
                                rides into the model context on every ask and
                                can be spoken aloud whole
- help-instructions-label-restatement WARNING instructions add nothing beyond
                                the field's own name/option labels
- help-instructions-screen-ref WARNING instructions point at things only a
                                reader can see ("see page 7", "the box
                                below") -- meaningless in a spoken channel
- help-details-not-contained WARNING a help.details paragraph is NOT a
                                verbatim (normalized) excerpt of
                                metadata.booklet_text -- the zero-trust
                                extractive contract (guidance_contract)
- help-details-no-reference-floor WARNING help.details present but the schema
                                carries no metadata.booklet_text -- the
                                containment check cannot run
- help-details-oversize  WARNING details exceed the INLINE budget
                                (guidance_contract.DETAILS_INLINE_MAX_CHARS,
                                bd wsao.8) -- the overflow reaches only the
                                secretary; the engine should select+index to
                                fit
- help-details-headings-missing WARNING a long details block has no heading
                                lines (unnavigable for secretary/human review)
- guidance-identity-stale WARNING a field's name / spoken_name / option
                                label/spoken-label/value bindings / TYPE
                                changed since its guidance was authored (the
                                bake's identity_sha1 no longer matches), so the
                                guidance may describe something the assistant
                                no longer says -- or a spoken label may now
                                select a different stored answer (label swap),
                                or a type change may have rewritten the
                                expected answer shape (bd polyglot-pdf-stkz).
                                Drives the editor's human acknowledgment gate
                                -- never an auto re-bake (bd polyglot-pdf-anim)

ASCII only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from backend.models import conditional_vocabulary as vocab
from backend.services import guidance_contract
# Single source for "which field types legitimately carry NO field-level
# pdf_field_name" (identity lives per-option/column/slot) -- shared with the
# repair pass's no-name check so the two ledger gates can never drift
# (bd polyglot-pdf-l1a9 / xazf). Import is cycle-safe: schema_repair imports
# only vocab/form_models/controls_fields_mirror, never this module.
from backend.services.schema_repair import FIELD_LEVEL_NAME_EXEMPT_TYPES

SEVERITY_ERROR = "ERROR"
SEVERITY_WARNING = "WARNING"

# Well-known id prefix the deterministic division pass gives sections holding
# fields a human must re-file (scripts/authoring/derive_sections.py, bd
# 6cfu.2/.3). The 'to-review-pending' lint rule -- and through it the publish
# gate -- keys on this prefix; the schema editor highlights it.
TO_REVIEW_PREFIX = "sec_to_review"

_ATOM_KEYS = frozenset({"field", "operator"})

# The translation verify/rectify gate's flag taxonomy (bd polyglot-pdf-9djc;
# produced by backend/services/option_translation.py::bake_label_translations).
# Both bake surfaces persist the report -- flags included -- under
# _bakeoff.authoring.option_translation (extraction step 3f and the editor
# translate-options route), and lint RE-EMITS those flags as findings so the
# editor ValidationPanel shows the translation worklist on every lint pass
# with zero extra plumbing. Severity is pinned WARNING regardless of what the
# stored dict claims: flags inform, they never block publish (plan sprint 14,
# fail-open contract).
TRANSLATION_FLAG_RULES = frozenset({
    "translation-drift-rectified",
    "translation-drift-unresolved",
    "translation-ambiguous-source",
    "translation-mechanical",
    # Per-language coverage gaps (bd polyglot-pdf-x41u): a missing
    # translation falls back to the English label mid-session, so the bake
    # reports gaps through the same flag channel.
    "translation-coverage",
})

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
            f"this condition is a {type(cond).__name__}, not a set of "
            "rules -- rebuild it in the editor's condition builder",
        ))
        return []

    buckets = vocab.CONDITION_GROUP_BUCKETS & cond.keys()
    has_atom_keys = bool(_ATOM_KEYS & cond.keys())

    if buckets and has_atom_keys:
        out.append(LintFinding(
            SEVERITY_ERROR, "composite-depth", path,
            "this condition mixes a single rule with a group of rules "
            f"({', '.join(sorted(buckets))}) -- pick one shape, not both",
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
                "this group must be a list of rules -- rebuild it in the "
                "editor's condition builder",
            ))
            continue
        for i, member in enumerate(members):
            member_path = f"{path}.{bucket}[{i}]"
            if not isinstance(member, dict):
                out.append(LintFinding(
                    SEVERITY_ERROR, "condition-malformed", member_path,
                    f"this rule is a {type(member).__name__}, not a single "
                    "field/operator rule -- rebuild it in the editor's "
                    "condition builder",
                ))
                continue
            if vocab.CONDITION_GROUP_BUCKETS & member.keys():
                out.append(LintFinding(
                    SEVERITY_ERROR, "composite-depth", member_path,
                    "a rule inside a group cannot itself contain another "
                    "group -- only one level of grouping is allowed; "
                    "flatten it",
                ))
                continue
            atoms.append((member_path, member))
    if not atoms and len(out) == problems_before:
        # All buckets present but empty (e.g. {"all_of": []}): ConditionGroup
        # rejects this shape (at least one non-empty bucket), so the raw-draft
        # path must report it too (Codex PR #302).
        out.append(LintFinding(
            SEVERITY_ERROR, "condition-malformed", path,
            "this group of rules is empty -- add at least one rule, or "
            "remove the group",
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
            "this rule has no comparison type set -- open it in the "
            "condition builder and choose one",
        ))
        return
    spec = vocab.OPERATORS.get(operator)
    if spec is None:
        out.append(LintFinding(
            SEVERITY_ERROR, "unknown-operator", atom_path,
            f"the condition uses {operator!r}, which is not a recognized "
            f"rule -- change it to one of: "
            f"{', '.join(sorted(vocab.ALLOWED_OPERATORS))}",
        ))
        return

    if resolve_trigger:
        ref = atom.get("field")
        if not isinstance(ref, str) or not ref:
            out.append(LintFinding(
                SEVERITY_ERROR, "condition-malformed", atom_path,
                "this rule does not say which field triggers it -- open it "
                "in the condition builder and pick a field",
            ))
            return
        trigger_field = fields_by_id.get(ref)
        if trigger_field is None:
            out.append(LintFinding(
                SEVERITY_ERROR, "ref-unresolved-field", atom_path,
                f"this rule points at field {ref!r}, which does not exist "
                "in this form -- pick a real field or delete the rule",
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
                    f"a {trigger_type!r} field cannot trigger a condition -- "
                    "pick a different trigger field, or remove this rule",
                ))
                return
        elif trigger_type not in spec.trigger_types and not tolerated_v1_idiom:
            out.append(LintFinding(
                SEVERITY_ERROR, "operator-trigger", atom_path,
                f"{operator!r} cannot be used on a {trigger_type!r} field -- "
                f"valid comparisons for this field type are: "
                f"{', '.join(sorted(spec.trigger_types))}",
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
                f"{operator!r} does not take a comparison value, but one is "
                "set -- remove it",
            ))
        return
    if spec.value_arity == "list":
        if not isinstance(value, list) or not value:
            out.append(LintFinding(
                SEVERITY_ERROR, "value-arity", atom_path,
                f"{operator!r} needs a list of one or more values to "
                "compare against -- add at least one",
            ))
            return
        values = value
    else:  # scalar
        if value is None or isinstance(value, list):
            out.append(LintFinding(
                SEVERITY_ERROR, "value-arity", atom_path,
                f"{operator!r} needs a single comparison value, not a list "
                "or nothing -- set exactly one",
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
                        f"this rule compares against {v!r}, which is not one "
                        f"of the answer choices on trigger field "
                        f"{trigger_field.get('id')!r} -- pick one of its "
                        "real choices",
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
                "this answer choice has no stored value -- set one (it can "
                "differ from the label the user sees)",
            ))
            continue
        value_str = str(value)
        if "," in value_str:
            out.append(LintFinding(
                SEVERITY_ERROR, "option-value-comma", opt_path,
                f"the value {value_str!r} contains a comma, which breaks "
                "multi-select answers spoken aloud -- remove the comma "
                "from the value",
            ))
        if is_v2 and not vocab.is_valid_option_slug(value_str):
            out.append(LintFinding(
                SEVERITY_ERROR, "option-value-slug", opt_path,
                f"the value {value_str!r} is not in the required format "
                "(lowercase letters, numbers, hyphens, underscores only) -- "
                "regenerate it from the label",
            ))
        seen_values[value_str] = seen_values.get(value_str, 0) + 1
    for value_str, count in seen_values.items():
        if count > 1:
            out.append(LintFinding(
                SEVERITY_ERROR, "option-value-duplicate", field_path,
                f"{count} answer choices on this field share the value "
                f"{value_str!r} -- give each choice its own unique value",
            ))


# ---------------------------------------------------------------------------
# show_if cycle detection (WARNING).
# ---------------------------------------------------------------------------

def _check_cycles(
    graph: Dict[str, List[str]],
    out: List[LintFinding],
) -> None:
    """DFS over the show_if trigger graph (edges collected by the main lint
    loop as it walks each field's show_if); each cycle is reported once.

    Takes the already-built graph rather than re-walking show_if itself --
    the main loop's per-field show_if walk (which also runs the atom checks)
    collects these same trigger edges, so re-invoking _walk_condition here
    would redundantly re-parse every show_if a second time (bd polyglot-pdf-
    tmby nit 2).
    """
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
                        "these fields' show/hide rules point at each other "
                        "in a loop, so none of them can ever resolve: "
                        + " -> ".join(path[path.index(nxt):] + [nxt])
                        + " -- break the loop by removing or changing one "
                        "of these rules",
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


def _dump_entry(dump: Dict[str, Any], name: str) -> Optional[Dict[str, Any]]:
    """The AcroForm dump entry for widget `name`, or None if absent."""
    entries = dump.get("fields") if isinstance(dump, dict) else None
    if not isinstance(entries, list):
        return None
    for e in entries:
        if isinstance(e, dict) and e.get("name") == name:
            return e
    return None


# Substrings marking a widget as machine-generated / not a user-fillable field
# (2D barcodes on USCIS/IRS forms: PDF417, QR, Code128 -- always named *BarCode*
# / *PDF417* / *QRCode*). Matched case-insensitively against the widget name AND
# its /TU. logical_type alone can't tell these apart: a PDF417 barcode is a
# read-only MULTILINE text widget, and this project DELIBERATELY fills read-only
# text/checkbox fields via unlock_method: flip_readonly_bit (i-90 has 20 real
# read-only-text fields + real read-only checkboxes), so "read_only" is not a
# safe "unfillable" signal here (bd polyglot-pdf-w0eq, caught pre-PR).
_MACHINE_WIDGET_MARKERS = ("barcode", "pdf417", "qrcode")


def is_fillable_widget(dump: Dict[str, Any], name: str) -> bool:
    """Whether an AcroForm widget is a user-fillable form field (vs a decorative
    button or a machine-generated barcode). The single source of truth for BOTH
    the under-claim lint rule and extract_form's coverage backfill, so the two
    never disagree on what counts as a coverage gap (bd polyglot-pdf-w0eq)."""
    e = _dump_entry(dump, name) or {}
    if e.get("logical_type") == "button":
        return False  # decorative reset/print buttons
    hay = (name + " " + str(e.get("tu") or "")).lower()
    widgets = e.get("widgets") or [{}]
    for w in widgets:
        hay += " " + str(w.get("tu") or "").lower()
    return not any(m in hay for m in _MACHINE_WIDGET_MARKERS)


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
                "this PDF box is claimed by more than one field, so filling "
                "it will misbehave -- unclaim it from all but one field: "
                + ", ".join(sorted(owners)),
            ))
            continue
        option_kinds = [kind for _, kind in claimants if kind != "field"]
        if len(option_kinds) > 1:
            (owner,) = owners
            out.append(LintFinding(
                SEVERITY_ERROR, "dump-widget-multiclaim", f"widget {name!r}",
                f"this PDF box is claimed by more than one answer choice on "
                f"field {owner!r}, so filling it will misbehave -- unclaim "
                "it from all but one choice: "
                + ", ".join(sorted(option_kinds)),
            ))
        # field-level + a single option of the SAME field is the benign
        # groups-of-one convention (standalone checkbox describing its widget
        # in both places) -- not a finding.

    # Under-claim: a real AcroForm widget that NO field maps to. The LLM
    # extraction pass stochastically omits a field entirely (w7 is the
    # same PDF, yet a re-extraction drops a different widget each run); without
    # this the loss was silent, since the block above only flagged OVER-claim
    # (bd polyglot-pdf-w0eq, P6.1c). A WARNING, not an ERROR: some widgets are
    # legitimately unmodeled (reset/print buttons), and the extractor's
    # deterministic coverage backfill claims the rest -- so a clean extraction
    # emits none of these. Fillable widgets only (buttons excluded): an unfilled
    # decorative button is not a coverage defect.
    fillable_unclaimed = sorted(
        n for n in dump_names
        if n not in claims and is_fillable_widget(dump, n)
    )
    for name in fillable_unclaimed:
        out.append(LintFinding(
            SEVERITY_WARNING, "dump-widget-unclaimed", f"widget {name!r}",
            "this fillable box on the PDF has no field pointing at it, so "
            "it can never be filled in -- add a field for it, or map it "
            "onto an existing field",
        ))


def _check_field_backing(
    fields: List[Dict[str, Any]],
    schema: Dict[str, Any],
    dump: Optional[Dict[str, Any]],
    out: List[LintFinding],
) -> None:
    """The publish-gate ledger backstop (bd polyglot-pdf-xazf, sprint 17).

    Extraction-time repair hard-fails these defects (bd l1a9), but a HUMAN can
    reintroduce either into a stored draft after repair passed -- so the
    mark-complete gate must catch them too.

    field-unbacked (ERROR, schema-only -- fires with NO dump): a source=pdf
    field whose type carries its own widget identity (outside
    FIELD_LEVEL_NAME_EXEMPT_TYPES) but has no pdf_field_name at all.

    field-claim-unresolvable (ERROR, DUMP-GATED): a field/option claim that
    resolves to zero dump widgets -- _check_dump_claims' register() walk
    silently drops these (its claims map only ever gains RESOLVED names), which
    is exactly how the original phantom-field confusion stayed invisible. Like
    every dump-* rule, this is structurally silent on the dump-less /lint
    route (it POSTs a bare schema, no kit id -- accepted asymmetry); the
    mark-complete gate loads the kit dump and is the enforcing call site.
    """
    is_pdf = str(schema.get("source")) == "pdf"
    if is_pdf:
        for i, f in enumerate(fields):
            if str(f.get("type")) in FIELD_LEVEL_NAME_EXEMPT_TYPES:
                continue
            if not f.get("pdf_field_name"):
                out.append(LintFinding(
                    SEVERITY_ERROR, "field-unbacked",
                    f"fields[{i}] (id={f.get('id')})",
                    f"field {f.get('id')!r} is not connected to any box on "
                    "the PDF, so an answer here can never be written to the "
                    "form and there is no way to check it -- connect it to "
                    "a PDF box, or mark the field ignored",
                ))

    if dump is None:
        return
    dump_names = _dump_names(dump)
    if not dump_names:
        return
    for i, f in enumerate(fields):
        claims: List[Tuple[Any, str]] = [(f.get("pdf_field_name"), "field")]
        options = f.get("options")
        if isinstance(options, list):
            for j, o in enumerate(options):
                if isinstance(o, dict):
                    claims.append((o.get("pdf_field_name"), f"option[{j}]"))
        for claim, kind in claims:
            if (isinstance(claim, str) and claim
                    and not _match_dump_names(claim, dump_names)):
                out.append(LintFinding(
                    SEVERITY_ERROR, "field-claim-unresolvable",
                    f"fields[{i}] (id={f.get('id')}) {kind}",
                    f"this field is connected to PDF box {claim!r}, but no "
                    "box with that name exists in this PDF -- reconnect it "
                    "to a real box",
                ))


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
            "this schema file is not structured as a form (its top "
            "level is not a set of named properties) -- restore it from "
            "a working copy or re-run extraction",
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

    # show_if trigger graph, collected alongside the main walk below (fid ->
    # list of trigger field ids referenced from that field's show_if atoms) so
    # _check_cycles can DFS it directly instead of re-walking show_if itself.
    show_if_graph: Dict[str, List[str]] = {}

    for i, f in enumerate(fields):
        field_path = f"fields[{i}] (id={f.get('id')})"
        fid = f.get("id")

        _check_options(field_path, f, is_v2, out)

        show_if_atoms = _walk_condition(f.get("show_if"), f"{field_path}.show_if", out)
        triggers: List[str] = []
        for atom_path, atom in show_if_atoms:
            _check_atom(atom_path, atom, None, out, fields_by_id,
                        resolve_trigger=True, is_v2=is_v2)
            ref = atom.get("field")
            if isinstance(ref, str) and ref in fields_by_id:
                triggers.append(ref)
        if isinstance(fid, str):
            show_if_graph[fid] = triggers

        for atom_path, atom in _walk_condition(
            f.get("require_if"), f"{field_path}.require_if", out
        ):
            _check_atom(atom_path, atom, None, out, fields_by_id,
                        resolve_trigger=True, is_v2=is_v2)

        # Read-only + conditional but NO unlock mechanism = a field that becomes
        # VISIBLE under its show_if/require_if but is permanently NON-fillable,
        # because FieldRenderer only lifts read_only when a conditional_behavior /
        # conditional_logic unlock_method is present (bd polyglot-pdf-3fz7 -- i-90's
        # 3 Part-4 accommodation checkboxes). A WARNING (guardrail-first inventory,
        # bd polyglot-pdf-h76m.16 follow-up): a genuinely-fixed-read-only field
        # (a computed/display value shown but never filled) is rare, so the human
        # reviews it. Note: a signature is read-only-by-nature and NOT conditional,
        # so it does not trip this.
        # Only flip_readonly_bit actually lifts read_only in FieldRenderer's
        # shouldUnlock (it string-compares that exact value on BOTH the canonical
        # conditional_behavior key and the legacy conditional_logic alias). Any
        # other unlock_method (e.g. set_property) lints as still-locked, matching
        # runtime -- a non-flip value would leave the field permanently
        # non-fillable when shown (bd polyglot-pdf-rsy3).
        # isinstance-guard (not `or {}`): a truthy non-dict would crash .get(),
        # breaking lint's never-throws contract on malformed editor input.
        cb = f.get("conditional_behavior")
        cb = cb if isinstance(cb, dict) else {}
        cl = f.get("conditional_logic")
        cl = cl if isinstance(cl, dict) else {}
        has_unlock = "flip_readonly_bit" in (
            cb.get("unlock_method"), cl.get("unlock_method"))
        if (f.get("read_only") and not has_unlock
                and (f.get("show_if") or f.get("require_if"))):
            out.append(LintFinding(
                SEVERITY_WARNING, "readonly-conditional-no-unlock", field_path,
                "this field is locked and only appears under a condition, "
                "but nothing unlocks it -- once it appears, no one can ever "
                "fill it in; set its unlock method to flip_readonly_bit",
            ))
        # An unlock_method WITHOUT pdf_field_flag_change is invisible-broken
        # (bd polyglot-pdf-xbfm fresh-eyes): the editor UI and the check above
        # both key on unlock_method alone, but the PDF filler's
        # apply_field_flag_changes early-returns unless pdf_field_flag_change
        # is present in conditional_behavior OR conditional_logic -- the field
        # LOOKS unlocked everywhere and silently stays read-only in the filled
        # PDF. Gold always pairs both (i-90 shape: bit 0, 1 -> 0).
        if has_unlock and not (cb.get("pdf_field_flag_change")
                               or cl.get("pdf_field_flag_change")):
            out.append(LintFinding(
                SEVERITY_WARNING, "unlock-missing-flag-change", field_path,
                "this field is set to unlock, but is missing the PDF flag "
                "change that actually unlocks it -- the filled PDF will "
                "silently stay locked even though the form looks correct; "
                "add pdf_field_flag_change (bit 0, current value 1, "
                "required value 0) next to the unlock method",
            ))

        # controls_fields / conditional_fields were DELETED at the P6.2 flip (bd
        # h76m.16). The model IGNORES the extra key (extra="ignore"), so a stale
        # or mis-migrated V2 kit still carrying one would publish with its
        # trigger-side shows/makes_required behavior silently dropped at runtime
        # (Codex PR #346). Lint ERRORs on it -- but ONLY for a schema that CLAIMS
        # to be v2 (is_v2): a raw pre-migration extraction DRAFT legitimately
        # still carries controls_fields until the repair/migrate pipeline converts
        # it, and lint runs on that draft mid-pipeline. The dependency must be
        # expressed target-side as show_if / require_if before a kit is v2.
        if is_v2:
            for legacy_key in ("controls_fields", "conditional_fields"):
                if f.get(legacy_key):
                    out.append(LintFinding(
                        SEVERITY_ERROR, "legacy-trigger-side-logic",
                        f"{field_path}.{legacy_key}",
                        f"this field still uses the old {legacy_key} way of "
                        "showing/requiring other fields, which the app no "
                        "longer reads -- that behavior is silently lost; "
                        "rebuild it as a show_if / require_if rule on the "
                        "target field(s) instead",
                    ))

            # required lives at validation.required, the shape every kit + the
            # frontend isFieldRequired reader + the Pydantic model consume. An
            # old-extractor top-level `required` is read by NO consumer, so a
            # field marked required=true there is silently treated as OPTIONAL
            # -- a lost-intent gate (bd polyglot-pdf-a1ql). ERROR so a drifted kit
            # cannot publish. Only a TRUTHY top-level required is flagged: a top-
            # level required=false carries no lost intent (the field is optional
            # either way) and legacy/merged fields still emit that inert key.
            if f.get("required"):
                out.append(LintFinding(
                    SEVERITY_ERROR, "required-top-level",
                    f"{field_path}.required",
                    "this field is marked required in the wrong place, so "
                    "nothing actually enforces it -- the form will silently "
                    "accept it left blank; move the required setting into "
                    "the field's validation rules",
                ))

    _check_cycles(show_if_graph, out)

    # 'To review' review gate (bd polyglot-pdf-6cfu.3). The deterministic
    # division pass (scripts/authoring/derive_sections.py, bd 6cfu.2) files
    # fields it cannot confidently place into sections whose id carries the
    # well-known `sec_to_review` prefix, for a HUMAN reviewer to re-file in
    # the editor. A field still sitting in one is un-reviewed by definition,
    # so it lints as an ERROR -- which the publish gate (editor status ->
    # complete) already blocks on. One finding per un-reviewed field (keyed
    # on the field's own section_id, so a dangling pointer is caught even if
    # the section entry vanished), plus one per to-review section whose
    # fields[] list is one-sidedly stale (lists ids no field points back
    # from) -- never both for the same state.
    flagged_review_fields: set = set()
    for i, f in enumerate(fields):
        sid = f.get("section_id")
        if isinstance(sid, str) and sid.startswith(TO_REVIEW_PREFIX):
            if isinstance(f.get("id"), str):
                flagged_review_fields.add(f["id"])
            out.append(LintFinding(
                SEVERITY_ERROR, "to-review-pending",
                f"fields[{i}] (id={f.get('id')})",
                f"this field is still sitting in the holding section "
                f"{sid!r}, waiting for a human to decide where it belongs -- "
                f"move it into a real section before the form can be "
                f"marked complete",
            ))
    raw_sections = schema.get("sections")
    sections = [s for s in raw_sections if isinstance(s, dict)] \
        if isinstance(raw_sections, list) else []
    for i, s in enumerate(sections):
        sid = s.get("id")
        if not (isinstance(sid, str) and sid.startswith(TO_REVIEW_PREFIX)):
            continue
        listed = s.get("fields")
        listed = [x for x in listed if isinstance(x, str)] \
            if isinstance(listed, list) else []
        stale = [x for x in listed if x not in flagged_review_fields]
        if stale:
            out.append(LintFinding(
                SEVERITY_ERROR, "to-review-pending",
                f"sections[{i}] (id={sid})",
                f"the holding section {sid!r} still lists {len(stale)} field "
                f"id(s) ({', '.join(stale[:5])}{', ...' if len(stale) > 5 else ''}) "
                f"that are leftovers -- any real fields among them are "
                f"already filed in a proper section, and the rest name no "
                f"field at all; delete these ids from the holding section's "
                f"list so the form can be marked complete",
            ))

    _check_guidance(fields, schema, out)

    _emit_translation_flags(schema, out)
    _emit_guidance_flags(schema, out)
    _check_guidance_identity_drift(schema, out)

    if dump is not None:
        _check_dump_claims(fields, dump, out)

    # Ledger backstop (bd xazf): field-unbacked fires dump-less; the
    # unresolvable-claim half is dump-gated inside (accepted dump-* asymmetry).
    _check_field_backing(fields, schema, dump, out)

    return out


def _emit_guidance_flags(schema: Dict[str, Any], out: List[LintFinding]) -> None:
    """Re-emit the guidance verify loop's persisted flags as findings (bd
    wsao.5) -- the instructions_enrich analog of _emit_translation_flags:
    flags live at _bakeoff.authoring.instructions_enrich.flags, severity is
    pinned WARNING (inform, never block), malformed entries are skipped
    (never-throws)."""
    authoring = schema.get("_bakeoff")
    authoring = authoring.get("authoring") if isinstance(authoring, dict) else None
    enrich = authoring.get("instructions_enrich") if isinstance(authoring, dict) else None
    flags = enrich.get("flags") if isinstance(enrich, dict) else None
    if not isinstance(flags, list):
        return
    for flag in flags:
        if not isinstance(flag, dict):
            continue
        rule = flag.get("rule")
        path = flag.get("path")
        message = flag.get("message")
        if rule not in guidance_contract.GUIDANCE_FLAG_RULES:
            continue
        if not isinstance(path, str) or not isinstance(message, str):
            continue
        out.append(LintFinding(SEVERITY_WARNING, rule, path, message))


def _check_guidance(fields: List[Dict[str, Any]], schema: Dict[str, Any],
                    out: List[LintFinding]) -> None:
    """Guidance-content rules (bd wsao.3; sprint-16 plan). All WARNING --
    guidance quality informs the authoring worklist, never blocks publish.
    Bounds + normalization live in guidance_contract (one module shared with
    the enrichment + judge prompts, so mechanical checks cannot drift from
    what the prompts demand)."""
    meta = schema.get("form_metadata")
    booklet = meta.get("booklet_text") if isinstance(meta, dict) else None
    booklet = booklet if isinstance(booklet, str) else ""
    booklet_norm: Optional[str] = None  # lazily normalized once (perf)

    # Coverage is ONE aggregated finding, not per-field: a fresh
    # pre-enrichment draft has no guidance on ANY field, and a per-field rule
    # would flood the ValidationPanel (and every zero-findings test fixture)
    # with dozens of identical warnings. Askable = fields a user is actually
    # asked (read_only + signature excluded -- decide-and-note).
    askable = [f for f in fields
               if not f.get("read_only") and f.get("type") != "signature"]
    # FORM-LEVEL details (metadata.details, the wsao.1 floor's guidance block)
    # are a first-class engine output under the SAME zero-trust contract as
    # per-field details -- the containment check must see them too (wsao.4
    # outer review: 3 glued-non-adjacent paragraphs shipped as "clean"
    # through this exact blind spot).
    form_details = meta.get("details") if isinstance(meta, dict) else None
    form_details = form_details if isinstance(form_details, str) else ""
    if form_details.strip():
        if not booklet.strip():
            out.append(LintFinding(
                SEVERITY_WARNING, "help-details-no-reference-floor",
                "$.form_metadata.details",
                "this form has details text, but no official booklet text "
                "to check it against, so it cannot be verified as accurate "
                "-- add the booklet text for this form",
            ))
        else:
            if booklet_norm is None:
                booklet_norm = guidance_contract.normalize_for_containment(
                    booklet)
            for para in guidance_contract.details_paragraphs(form_details):
                res = guidance_contract.check_containment_normalized(
                    para, booklet_norm)
                if not res.contained:
                    head = para[:60].replace("\n", " ")
                    out.append(LintFinding(
                        SEVERITY_WARNING, "help-details-not-contained",
                        "$.form_metadata.details",
                        f"this form-level details text is not an exact "
                        f"quote from the official booklet: \"{head}...\" -- "
                        f"details must be copied word-for-word from the "
                        f"booklet, never paraphrased or written from "
                        f"memory; replace it with a real excerpt",
                    ))

    def _instr_of(f: Dict[str, Any]) -> str:
        # Raw LLM drafts carry lists/numbers where strings belong; lint never
        # throws on malformed input (wsao.3 fresh-eyes).
        h = f.get("help")
        v = h.get("instructions") if isinstance(h, dict) else None
        return v if isinstance(v, str) else ""

    uncovered = [f for f in askable if not _instr_of(f).strip()]
    if uncovered:
        sample = ", ".join(str(f.get("id")) for f in uncovered[:5])
        more = ", ..." if len(uncovered) > 5 else ""
        out.append(LintFinding(
            SEVERITY_WARNING, "help-instructions-missing", "$.fields",
            f"{len(uncovered)} of {len(askable)} fields the assistant asks "
            f"about have no spoken guidance written yet ({sample}{more}) -- "
            f"the assistant will ask about them with no help text at all; "
            f"write instructions for each one",
        ))

    for i, f in enumerate(fields):
        field_path = f"fields[{i}] (id={f.get('id')})"
        help_obj = f.get("help")
        help_obj = help_obj if isinstance(help_obj, dict) else {}
        instr = help_obj.get("instructions")
        instr = instr if isinstance(instr, str) else ""
        details = help_obj.get("details")
        details = details if isinstance(details, str) else ""

        if len(instr) > guidance_contract.INSTRUCTIONS_HARD_CHARS:
            out.append(LintFinding(
                SEVERITY_WARNING, "help-instructions-too-long",
                f"{field_path}.help.instructions",
                f"these instructions are {len(instr)} characters, over the "
                f"{guidance_contract.INSTRUCTIONS_HARD_CHARS}-character "
                f"limit -- nothing gets cut off, but the assistant may read "
                f"all of it out loud every time it asks this question, and "
                f"it adds cost on every turn; shorten it to a quick spoken "
                f"hint and move the extra depth into Details, which is "
                f"never spoken aloud",
            ))

        if instr.strip():
            # non-list options never crash the never-throws contract (same
            # guard as every sibling options read in this file)
            opts = f.get("options")
            opts = opts if isinstance(opts, list) else []
            labels = [o.get("label", "") for o in opts if isinstance(o, dict)]
            if guidance_contract.is_label_restatement(
                    instr, f.get("name"), labels):
                out.append(LintFinding(
                    SEVERITY_WARNING, "help-instructions-label-restatement",
                    f"{field_path}.help.instructions",
                    "these instructions just repeat the field's name or "
                    "answer choices without adding anything -- either "
                    "write something that actually helps, or clear it "
                    "and leave it empty",
                ))
            if guidance_contract.SCREEN_REF_RE.search(instr):
                out.append(LintFinding(
                    SEVERITY_WARNING, "help-instructions-screen-ref",
                    f"{field_path}.help.instructions",
                    "the instructions say things like 'see page 7' or "
                    "'check the box below', which mean nothing when spoken "
                    "aloud -- rewrite them to say the actual requirement "
                    "in words",
                ))

        if not details.strip():
            continue

        if not booklet.strip():
            out.append(LintFinding(
                SEVERITY_WARNING, "help-details-no-reference-floor",
                f"{field_path}.help.details",
                "this field has details text, but no official booklet text "
                "to check it against, so it cannot be verified as accurate "
                "-- add the booklet text for this form",
            ))
        else:
            # normalize the (potentially 80KB+) booklet ONCE per schema, not
            # per paragraph -- quadratic cost on the hosted lint route
            # otherwise (wsao.3 outer review)
            if booklet_norm is None:
                booklet_norm = guidance_contract.normalize_for_containment(booklet)
            for para in guidance_contract.details_paragraphs(details):
                res = guidance_contract.check_containment_normalized(
                    para, booklet_norm)
                if not res.contained:
                    head = para[:60].replace("\n", " ")
                    out.append(LintFinding(
                        SEVERITY_WARNING, "help-details-not-contained",
                        f"{field_path}.help.details",
                        f"this details text is not an exact quote from the "
                        f"official booklet: \"{head}...\" -- details must be "
                        f"copied word-for-word from the booklet, never "
                        f"paraphrased or written from memory; replace it "
                        f"with a real excerpt",
                    ))

        if len(details) > guidance_contract.DETAILS_INLINE_MAX_CHARS:
            out.append(LintFinding(
                SEVERITY_WARNING, "help-details-oversize",
                f"{field_path}.help.details",
                f"these details are {len(details)} characters, over the "
                f"{guidance_contract.DETAILS_INLINE_MAX_CHARS}-character "
                f"budget the assistant carries while the user is on this "
                f"field -- the extra text is cut at a paragraph break and "
                f"replaced with a list of the dropped headings, which the "
                f"assistant can still look up on request, but that takes an "
                f"extra step; trim the excerpt to the parts that matter "
                f"most so the answer is at hand immediately",
            ))

        if (len(details) > guidance_contract.DETAILS_HEADINGS_REQUIRED_CHARS
                and not guidance_contract.has_heading(details)):
            out.append(LintFinding(
                SEVERITY_WARNING, "help-details-headings-missing",
                f"{field_path}.help.details",
                f"this details text is long "
                f"(over {guidance_contract.DETAILS_HEADINGS_REQUIRED_CHARS} "
                f"characters) with no headings, so no one can scan it or "
                f"jump to a section -- add the booklet's own headings "
                f"(for example '## Exceptions' or 'a. Nonresident aliens')",
            ))


def _emit_translation_flags(schema: Dict[str, Any], out: List[LintFinding]) -> None:
    """Re-emit the persisted translation verify/rectify flags as findings.

    The bake stores LintFinding-shaped dicts at
    _bakeoff.authoring.option_translation.flags; anything malformed (non-dict
    entries, unknown rules, missing path/message) is silently skipped -- lint
    never throws on malformed input, and a stale/hand-edited provenance slot
    must not break linting. field_id derivation happens downstream via
    as_dict()/field_id_of on the stored path, same as native findings.
    """
    authoring = schema.get("_bakeoff")
    authoring = authoring.get("authoring") if isinstance(authoring, dict) else None
    translation = authoring.get("option_translation") if isinstance(authoring, dict) else None
    flags = translation.get("flags") if isinstance(translation, dict) else None
    if not isinstance(flags, list):
        return
    for flag in flags:
        if not isinstance(flag, dict):
            continue
        rule = flag.get("rule")
        path = flag.get("path")
        message = flag.get("message")
        if rule not in TRANSLATION_FLAG_RULES:
            continue
        if not isinstance(path, str) or not isinstance(message, str):
            continue
        out.append(LintFinding(SEVERITY_WARNING, rule, path, message))


def _check_guidance_identity_drift(
    schema: Dict[str, Any], out: List[LintFinding]
) -> None:
    """Flag fields whose answer-shaping identity changed since their guidance
    was authored (bd polyglot-pdf-anim).

    The bake records identity_sha1 (name + spoken_name + option
    label/spoken_label/value bindings + type) in
    _bakeoff.authoring.instructions_enrich.provenance. A human rename,
    option relabel or TYPE CHANGE afterwards may leave the authored guidance
    describing something the AI no longer says, or asking for an answer in a
    shape the field no longer accepts -- but a trivial rename does not warrant
    an LLM re-author, so this is a WARNING that drives the editor's
    human-acknowledgment gate, not an ERROR and not an automatic re-bake.

    A TYPE change (text -> date, text -> number) flags because it rewrites the
    expected answer shape without touching any spoken text (bd
    polyglot-pdf-stkz); see identity_payload's docstring for why the test is
    "does this make the guidance wrong?" rather than "is this spoken?".

    A label SWAP (labels trading places across values, label multiset
    unchanged) flags too: the assistant's unchanged words would select a
    different stored answer, which is the drift that matters MOST (bd anim
    handoff decision -- see identity_payload's docstring for the tradeoffs).

    Silent (never fires) when there is nothing to compare against: no provenance
    record, or a record predating identity tracking. Gating a field on a hash
    the bake never wrote would be unactionable noise. Likewise silent when the
    field no longer carries ANY authored guidance (a human emptied help after
    the bake) -- there is nothing to confirm.

    The hash comes from guidance_contract.identity_sha1 -- the SAME function the
    bake writes with, so the written and compared values cannot drift.
    """
    authoring = schema.get("_bakeoff")
    authoring = authoring.get("authoring") if isinstance(authoring, dict) else None
    enrich = authoring.get("instructions_enrich") if isinstance(authoring, dict) else None
    prov = enrich.get("provenance") if isinstance(enrich, dict) else None
    if not isinstance(prov, dict) or not prov:
        return
    fields = schema.get("fields")
    if not isinstance(fields, list):
        return
    for field in fields:
        if not isinstance(field, dict):
            continue
        fid = field.get("id")
        rec = prov.get(fid) if isinstance(fid, str) else None
        if not isinstance(rec, dict):
            continue
        baked = rec.get("identity_sha1")
        if not isinstance(baked, str) or not baked:
            continue  # pre-anim bake: nothing to be stale against
        help_obj = field.get("help")
        if not isinstance(help_obj, dict) or not any(
                isinstance(help_obj.get(k), str) and help_obj.get(k).strip()
                for k in ("instructions", "details", "format_hint")):
            # A human emptied the guidance after the bake: there is nothing
            # left to confirm, and gating would render the ack box under an
            # empty textarea with copy about text that no longer exists --
            # the unactionable-noise case this rule exists to avoid (Opus
            # round 5). help-instructions-missing already surfaces the
            # emptiness itself.
            continue
        # ONE computation reused for both the comparison and the path token:
        # two separate identity_sha1() calls invited a future edit to one
        # without the other, letting the compared and reported hashes diverge
        # (Opus round 5).
        current = guidance_contract.identity_sha1(field)
        if baked == current:
            continue
        # The CURRENT identity hash rides the PATH, not the message: the editor
        # pins a human's acknowledgment to the exact content they read, and the
        # path is a machine anchor no UI renders as prose (the message IS shown
        # -- in the lint strip, the flagged-reasons banner and the row tooltip
        # -- so a raw hash there is unexplained noise for a non-technical
        # reviewer; bd anim fresh-eyes round 2 finding 2).
        #
        # Pinning to the BAKED hash instead would be a permanent waiver: the
        # baked value does not change when the user edits, so one ack would
        # silently cover every later edit until the next re-bake (round 1
        # finding 1). field_id_of() ignores the trailing segment, so the
        # editor's click-to-focus still resolves this path.
        out.append(LintFinding(
            SEVERITY_WARNING, "guidance-identity-stale",
            f"fields (id={fid}).help[identity:{current}]",
            # Names EVERY hashed input (bd polyglot-pdf-stkz added type). A
            # message that lists only name/spoken name/options tells a
            # reviewer something false after a text -> date edit: they check
            # those three, find them identical, and conclude the gate is
            # broken -- which is how a gate loses credibility and starts
            # getting clicked through.
            "this field's name / spoken name / options / answer type changed "
            "since its guidance was written, so the guidance may no longer "
            "match what the assistant says -- confirm it still reads "
            "correctly (or re-author it) before marking the field reviewed",
        ))
