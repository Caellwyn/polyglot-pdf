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
                                (guidance_contract.INSTRUCTIONS_HARD_CHARS) --
                                they ride the SPOKEN ask-hint
- help-instructions-label-restatement WARNING instructions add nothing beyond
                                the field's own name/option labels
- help-instructions-screen-ref WARNING instructions carry on-screen deixis or
                                a "see page/instructions" cross-reference --
                                meaningless in a spoken channel
- help-details-not-contained WARNING a help.details paragraph is NOT a
                                verbatim (normalized) excerpt of
                                metadata.booklet_text -- the zero-trust
                                extractive contract (guidance_contract)
- help-details-no-reference-floor WARNING help.details present but the schema
                                carries no metadata.booklet_text -- the
                                containment check cannot run
- help-details-oversize  WARNING details exceed
                                guidance_contract.DETAILS_OVERSIZE_WORDS words
- help-details-headings-missing WARNING a long details block has no heading
                                lines (unnavigable for secretary/human review)

ASCII only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from backend.models import conditional_vocabulary as vocab
from backend.services import guidance_contract

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
            "no field maps to this AcroForm widget (extraction likely dropped "
            "it) -- backfill or model it explicitly",
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
                "field is read_only and conditionally shown/required but has no "
                "unlock_method -- it will be permanently non-fillable when shown "
                "(add conditional_behavior.unlock_method=flip_readonly_bit)",
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
                "unlock_method is set but pdf_field_flag_change is missing -- "
                "the PDF filler cannot flip the read-only bit without it, so "
                "the field silently stays locked in the filled PDF (add "
                "pdf_field_flag_change {bit: 0, current_value: 1, "
                "required_value: 0} beside the unlock_method)",
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
                        f"{legacy_key} was removed in schema v2 (its behavior "
                        f"lives target-side in show_if / require_if now) -- "
                        f"migrate it",
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
                    "required must live at validation.required, not the field top "
                    "level -- a top-level required is read by no consumer, so this "
                    "field is silently OPTIONAL; move it into validation",
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
                f"field is still filed in 'To review' section {sid!r} -- "
                f"re-file it into a real section (schema editor) before the "
                f"form can be marked complete",
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
                f"'To review' section {sid!r} still lists {len(stale)} field "
                f"id(s) ({', '.join(stale[:5])}{', ...' if len(stale) > 5 else ''}) "
                f"-- empty it (re-file or remove the stale ids) before the "
                f"form can be marked complete",
            ))

    _check_guidance(fields, schema, out)

    _emit_translation_flags(schema, out)

    if dump is not None:
        _check_dump_claims(fields, dump, out)

    return out


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
            f"{len(uncovered)} of {len(askable)} askable fields have no "
            f"help.instructions ({sample}{more}) -- the voice AI has no "
            f"authored guidance for them (sprint-16 coverage worklist)",
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
                f"instructions are {len(instr)} chars (hard bound "
                f"{guidance_contract.INSTRUCTIONS_HARD_CHARS}) -- they ride "
                f"the spoken ask-hint; move depth into help.details",
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
                    "instructions merely restate the field label/options -- "
                    "empty beats filler (guidance contract)",
                ))
            if guidance_contract.SCREEN_REF_RE.search(instr):
                out.append(LintFinding(
                    SEVERITY_WARNING, "help-instructions-screen-ref",
                    f"{field_path}.help.instructions",
                    "instructions carry on-screen deixis or a 'see page/"
                    "instructions' cross-reference -- meaningless when spoken",
                ))

        if not details.strip():
            continue

        if not booklet.strip():
            out.append(LintFinding(
                SEVERITY_WARNING, "help-details-no-reference-floor",
                f"{field_path}.help.details",
                "help.details present but the schema has no "
                "form_metadata.booklet_text -- the verbatim-containment check "
                "cannot run; bake the booklet floor",
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
                        f"details paragraph is not a verbatim excerpt of the "
                        f"booklet text (normalized substring check failed): "
                        f"\"{head}...\" -- the details channel is "
                        f"SELECT-not-REWRITE (guidance contract)",
                    ))

        word_count = len(details.split())
        if word_count > guidance_contract.DETAILS_OVERSIZE_WORDS:
            out.append(LintFinding(
                SEVERITY_WARNING, "help-details-oversize",
                f"{field_path}.help.details",
                f"details are {word_count} words (bound "
                f"{guidance_contract.DETAILS_OVERSIZE_WORDS}); also check the "
                f"per-form inline token budget (wsao.2 findings)",
            ))

        if (len(details) > guidance_contract.DETAILS_HEADINGS_REQUIRED_CHARS
                and not guidance_contract.has_heading(details)):
            out.append(LintFinding(
                SEVERITY_WARNING, "help-details-headings-missing",
                f"{field_path}.help.details",
                f"details exceed "
                f"{guidance_contract.DETAILS_HEADINGS_REQUIRED_CHARS} chars "
                f"with no heading lines -- add the booklet's own headings "
                f"(## / 'a.' / 'Exception N.')",
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
