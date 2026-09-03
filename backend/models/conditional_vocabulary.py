"""Machine-readable registry of the schema-v2 conditional-logic vocabulary.

Single source of truth for WHAT the conditional vocabulary is (bd
polyglot-pdf-h76m.3, P1.1 of the schema-v2 epic). Consumers:

- backend/models/form_models.py -- the v2 operator/trigger compatibility and
  value-arity validators read this registry (never a hand-copied list).
- scripts/bakeoff/schema_contract.py (P1.2) -- the machine core of the
  extraction contract is RENDERED from this registry, so the prompt the LLM
  sees and the validator that judges its output cannot drift.
- backend/services/schema_lint.py (P2.1) and schema_repair.py (P5.2) --
  lint rules and the invented-operator alias table read this registry (the
  lint core lives in backend/ so the promotion gate imports it in-process;
  scripts/authoring/extract_form.py imports it via the repo root).

Deliberately import-free of form_models: the registry speaks in the STRING
values of the enums (FieldType/ConditionalOperator), so form_models can import
this module without a cycle. form_models raises at IMPORT time if the registry
and its enums disagree (see the sync guard below its enum definitions); the
P1.2 contract test adds the rendered-contract layer on top.
"""

from dataclasses import dataclass
from typing import Dict, FrozenSet, List
import re
import unicodedata


SCHEMA_VERSION_V1 = "1"
SCHEMA_VERSION_V2 = "2"

# Field types that carry an options[] list (one logical question, N choices).
# checkbox is NOT here: in v2 a checkbox is a STANDALONE boolean and options
# are forbidden on it (a W-7-style multi-box question is a checkbox_group).
CHOICE_FIELD_TYPES: FrozenSet[str] = frozenset({"select", "radio", "checkbox_group"})

# Field types whose stored value is a LIST of selected option slugs.
MULTI_VALUED_FIELD_TYPES: FrozenSet[str] = frozenset({"checkbox_group"})

# Field types that may appear as the TRIGGER of a condition at all.
# signature/address_group/table have no comparable scalar value.
CONDITION_TRIGGER_TYPES: FrozenSet[str] = frozenset({
    "text", "textarea", "date", "number", "tel", "email",
    "select", "radio", "checkbox", "checkbox_group",
})

_SCALAR_TRIGGERS: FrozenSet[str] = frozenset({
    "text", "textarea", "date", "number", "tel", "email", "select", "radio",
})


@dataclass(frozen=True)
class OperatorSpec:
    """Compatibility + arity contract for one conditional operator (v2)."""

    name: str
    # "none"   -> operator ignores value (is_checked / is_empty / is_not_empty)
    # "scalar" -> value is a single str/int/float/bool
    # "list"   -> value is a list of scalars (in / not_in)
    value_arity: str
    # FieldType string values this operator may trigger on (v2 compat matrix).
    trigger_types: FrozenSet[str]
    # When True and the trigger is a choice field, the condition's value(s)
    # must be drawn from the trigger's option .value slugs.
    value_must_be_trigger_option: bool = False
    notes: str = ""


def _spec(name: str, arity: str, triggers: FrozenSet[str],
          option_ref: bool = False, notes: str = "") -> OperatorSpec:
    return OperatorSpec(
        name=name,
        value_arity=arity,
        trigger_types=triggers,
        value_must_be_trigger_option=option_ref,
        notes=notes,
    )


# The v2 operator/trigger compatibility matrix. Design decisions (plan section
# "Design direction", maintainer-approved 2026-07-03):
# - equals/not_equals on a checkbox_group trigger is INVALID in v2: the vq4m
#   equals-means-membership hack is retired; membership is includes/not_includes.
# - is_checked is bool sugar on a STANDALONE checkbox only; on a group trigger
#   the meaning is "any selected" which v2 spells is_not_empty (the is_checked
#   dual fate -- see backend/tests/fixtures/is_checked_dual_fate.json, shared
#   with the P6.1 migration tests).
# - contains is SUBSTRING matching on free-text triggers only (its historical
#   array-membership reading is includes now).
# - greater_than/less_than are numeric/date comparisons.
# - in/not_in are scalar-trigger set membership ("trigger value is one of").
OPERATORS: Dict[str, OperatorSpec] = {
    spec.name: spec for spec in (
        _spec("equals", "scalar", _SCALAR_TRIGGERS | frozenset({"checkbox"}),
              option_ref=True,
              notes="Strict scalar equality. NOT valid on checkbox_group (use includes)."),
        _spec("not_equals", "scalar", _SCALAR_TRIGGERS | frozenset({"checkbox"}),
              option_ref=True,
              notes="Strict scalar inequality. NOT valid on checkbox_group (use not_includes)."),
        _spec("contains", "scalar", frozenset({"text", "textarea", "tel", "email"}),
              notes="Substring match on free-text triggers."),
        _spec("greater_than", "scalar", frozenset({"number", "date"})),
        _spec("less_than", "scalar", frozenset({"number", "date"})),
        _spec("is_checked", "none", frozenset({"checkbox"}),
              notes="Bool sugar on a standalone checkbox. On groups use is_not_empty."),
        _spec("is_empty", "none", CONDITION_TRIGGER_TYPES),
        _spec("is_not_empty", "none", CONDITION_TRIGGER_TYPES),
        _spec("in", "list", _SCALAR_TRIGGERS, option_ref=True,
              notes="Trigger value is one of the listed values."),
        _spec("not_in", "list", _SCALAR_TRIGGERS, option_ref=True,
              notes="Trigger value is none of the listed values."),
        _spec("includes", "scalar", frozenset({"checkbox_group"}), option_ref=True,
              notes="The named option slug is in the group's selected set."),
        _spec("not_includes", "scalar", frozenset({"checkbox_group"}), option_ref=True,
              notes="The named option slug is NOT in the group's selected set."),
    )
}

ALLOWED_OPERATORS: FrozenSet[str] = frozenset(OPERATORS)

# Buckets a composite ConditionGroup may carry (flat: each bucket holds ATOMIC
# conditions only; depth <= 1 by construction, nesting is a wire break).
CONDITION_GROUP_BUCKETS: FrozenSet[str] = frozenset({"all_of", "any_of", "none_of"})


# ---------------------------------------------------------------------------
# Option-slug convention (v2): option.value is a SEMANTIC SLUG minted from the
# label -- lowercase ascii, no commas/spaces, unique per field, immutable once
# minted. Widget identity lives ONLY in option.pdf_field_name / pdf_on_value.
# ---------------------------------------------------------------------------

OPTION_SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_SLUG_SEPARATOR_RUNS = re.compile(r"[^a-z0-9]+")


def is_valid_option_slug(value: str) -> bool:
    """True when value satisfies the v2 option-slug convention.

    fullmatch, not match: with match() a trailing '\\n' sneaks past '$'
    (Python regex allows $ before a final newline -- Codex PR #299).
    """
    return bool(OPTION_SLUG_PATTERN.fullmatch(value))


def mint_option_slug(label: str, fallback: str = "option") -> str:
    """Deterministically mint the v2 option slug for a label.

    Lowercase, ASCII-transliterated (accents stripped), every run of
    non-alphanumerics collapsed to one underscore. Deterministic and
    idempotent: mint(mint(x)-ish labels) is stable, so repair re-anchoring
    from the (mandatory) label reproduces the same slug.
    """
    ascii_label = (
        unicodedata.normalize("NFKD", label)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    slug = _SLUG_SEPARATOR_RUNS.sub("_", ascii_label).strip("_")
    return slug or fallback


_TRAILING_CODE = re.compile(r"\s*\([A-Z0-9]{1,4}\)\s*$")


def strip_trailing_code(label: str) -> str:
    """'Alabama (AL)' -> 'Alabama'. The parenthesized export code a dropdown
    label carries for proof-reading (bd polyglot-pdf-jpjcv) must not leak into
    the SLUG: mint_option_slug('Alabama (AL)') is 'alabama_al', and 'alabama'
    is what reads well in a condition and what the c5r8 kit used."""
    return _TRAILING_CODE.sub("", label or "")


def mint_select_slugs(labels: List[str], codes: List[str]) -> List[str]:
    """Slugs for a SELECT's options (bd polyglot-pdf-g2fpr).

    A select's value is a semantic slug and its PDF export code lives in
    pdf_on_value. Two rules the generic minter does not know:
      - a code that is ALREADY a valid slug ('5', '11') IS the value: the
        label for the number five is "5", and re-minting it from a label
        would invent a word for a number;
      - a label's trailing "(CODE)" is stripped before minting.
    Uniqueness is enforced across the WHOLE set (kept codes are reserved
    first, so a minted sibling cannot collide with one).
    """
    assert len(labels) == len(codes)
    keep = [c if (isinstance(c, str) and is_valid_option_slug(c)) else None
            for c in codes]
    reserved = [c for c in keep if c is not None]
    to_mint = [strip_trailing_code(l) for l, k in zip(labels, keep) if k is None]
    minted = iter(mint_unique_slugs(reserved + to_mint)[len(reserved):])
    return [k if k is not None else next(minted) for k in keep]


def mint_unique_slugs(labels: List[str]) -> List[str]:
    """Mint slugs for a field's option labels, deduped with _2/_3... suffixes.

    Duplicate labels within one field are rare but legal on real forms (e.g.
    two 'Other' boxes); the Nth duplicate gets a stable positional suffix. The
    suffix is bumped past any slug ALREADY minted in this batch, so a distinct
    label whose natural slug collides with a suffixed one (['Other', 'Other',
    'Other 2'] -> other, other_2, other_2_2) cannot manufacture a duplicate
    (bd polyglot-pdf-986p).
    """
    used: set = set()
    result: List[str] = []
    for label in labels:
        base = mint_option_slug(label)
        candidate = base
        n = 1
        while candidate in used:
            n += 1
            candidate = f"{base}_{n}"
        used.add(candidate)
        result.append(candidate)
    return result
