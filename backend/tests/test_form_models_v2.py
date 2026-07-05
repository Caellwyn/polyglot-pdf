"""Schema v2 model tests (bd polyglot-pdf-h76m.3, P1.1).

Covers the bead's three exit criteria:
1. The shipped v1 kits (i-90, w7) validate UNCHANGED.
2. v2 fixtures validate; each v2 rule violation produces a field-path-specific
   error.
3. An unknown operator is rejected with an error naming the allowed set.

Plus: registry <-> enum agreement, slug minting, the is_checked dual-fate
shared fixture (also consumed by the P6.1 migration tests), the
controls_fields deprecation warning, and cycle detection.
"""

import copy
import json
import warnings as warnings_module
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.models import conditional_vocabulary as vocab
from backend.models.form_models import (
    ConditionalDisplay,
    ConditionalOperator,
    ConditionGroup,
    FieldType,
    FormSchema,
    iter_condition_atoms,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_kit(kit: str) -> dict:
    path = REPO_ROOT / "form-kits" / kit / "schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def v2_schema(fields: list, source: str = "pdf") -> dict:
    """Minimal valid v2 schema scaffold around the given fields."""
    doc = {
        "source": source,
        "schema_version": "2",
        "form_metadata": {"title": "Test", "version": "1"},
        "sections": [
            {
                "id": "s1",
                "label": "Section 1",
                "order": 1,
                "fields": [f["id"] for f in fields],
            }
        ],
        "fields": fields,
    }
    if source == "pdf":
        doc["extraction_info"] = {
            "extracted_at": "2026-07-04T00:00:00Z",
            "extraction_confidence": 1.0,
            "extractor_version": "test",
            "manual_review_required": False,
        }
    return doc


def group_field(field_id: str = "grp") -> dict:
    """A well-formed v2 checkbox_group (W-7 'reason' shaped)."""
    return {
        "id": field_id,
        "name": "Reason for submitting",
        "spoken_name": "reason",
        "type": "checkbox_group",
        "section_id": "s1",
        "options": [
            {
                "value": "dependent_spouse",
                "label": "Dependent spouse",
                "pdf_field_name": "c1_5[0]",
                "pdf_on_value": "1",
            },
            {
                "value": "other",
                "label": "Other",
                "pdf_field_name": "c1_9[0]",
                "pdf_on_value": "1",
            },
        ],
    }


def text_field(field_id: str = "dep", **extra) -> dict:
    return {
        "id": field_id,
        "name": "Dependent",
        "spoken_name": "dependent",
        "type": "text",
        "section_id": "s1",
        **extra,
    }


def checkbox_field(field_id: str = "cb", **extra) -> dict:
    return {
        "id": field_id,
        "name": "Standalone",
        "spoken_name": "standalone",
        "type": "checkbox",
        "section_id": "s1",
        "pdf_field_name": "cb[0]",
        **extra,
    }


def validate(doc: dict) -> FormSchema:
    return FormSchema.model_validate(doc)


def assert_v2_error(doc: dict, *needles: str):
    """The doc must fail v2 validation with every needle in the message."""
    with pytest.raises(ValidationError) as exc_info:
        validate(doc)
    message = str(exc_info.value)
    for needle in needles:
        assert needle in message, f"expected {needle!r} in:\n{message}"


# ---------------------------------------------------------------------------
# Exit criterion 1: shipped v1 kits validate UNCHANGED
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kit", ["i-90", "w7", "w7-2", "f1040"])
def test_v1_kit_validates_unchanged(kit):
    schema = validate(load_kit(kit))
    assert schema.schema_version is None  # no stamp -> legacy path
    # Legacy single-condition show_if keeps its wire shape (no coercion to
    # ConditionGroup on read -- round-trips through the editor stay v1).
    for field in schema.fields:
        if field.show_if is not None:
            assert isinstance(field.show_if, ConditionalDisplay)


def test_v1_kit_dump_keeps_legacy_show_if_shape():
    schema = validate(load_kit("i-90"))
    dumped = schema.model_dump(mode="json", exclude_none=True)
    with_show_if = [f for f in dumped["fields"] if "show_if" in f]
    assert with_show_if, "i-90 should carry show_if fields"
    for f in with_show_if:
        assert set(f["show_if"]) <= {"field", "operator", "value"}


# ---------------------------------------------------------------------------
# Exit criterion 2: v2 fixtures validate; violations -> field-path errors
# ---------------------------------------------------------------------------

def valid_v2_doc() -> dict:
    dep = text_field(
        show_if={
            "all_of": [{"field": "grp", "operator": "includes", "value": "other"}],
            "none_of": [
                {"field": "grp", "operator": "includes", "value": "dependent_spouse"}
            ],
        },
        require_if={"field": "grp", "operator": "is_not_empty"},
    )
    return v2_schema([group_field(), dep, checkbox_field()])


def test_v2_fixture_validates():
    schema = validate(valid_v2_doc())
    dep = schema.get_field("dep")
    assert isinstance(dep.show_if, ConditionGroup)
    assert isinstance(dep.require_if, ConditionalDisplay)
    assert schema.get_field("grp").type == FieldType.CHECKBOX_GROUP
    # (A AND B) AND NOT C flattens to its atoms for reference-style readers.
    assert {a.field for a in iter_condition_atoms(dep.show_if)} == {"grp"}


def test_v2_radio_shared_pdf_field_with_on_values_validates():
    radio = {
        "id": "marital",
        "name": "Marital status",
        "spoken_name": "marital status",
        "type": "radio",
        "section_id": "s1",
        "pdf_field_name": "P1_radio[0]",
        "options": [
            {"value": "single", "label": "Single", "pdf_on_value": "1"},
            {"value": "married", "label": "Married", "pdf_on_value": "2"},
        ],
    }
    validate(v2_schema([radio]))


def test_v2_web_source_skips_pdf_mapping_rules():
    # No extraction_info / pdf names anywhere: pdf-mapping rules are gated on
    # source == pdf, the rest of v2 still applies.
    grp = group_field()
    for opt in grp["options"]:
        opt.pop("pdf_field_name")
        opt.pop("pdf_on_value")
    cb = checkbox_field()
    cb.pop("pdf_field_name")
    validate(v2_schema([grp, cb], source="web"))


def test_v2_legacy_single_show_if_still_accepted():
    # v2 accepts the legacy single-condition shape (normalize-on-read is the
    # TS readers' job via P3.0 normalizeToComposite; the model keeps the wire
    # shape) as long as it passes the compat matrix.
    dep = text_field(show_if={"field": "grp", "operator": "includes", "value": "other"})
    schema = validate(v2_schema([group_field(), dep]))
    assert isinstance(schema.get_field("dep").show_if, ConditionalDisplay)


@pytest.mark.parametrize(
    "mutate, needles",
    [
        # checkbox with options -> forbidden
        (
            lambda doc: doc["fields"][2].update(
                options=[{"value": "a", "label": "A"}, {"value": "b", "label": "B"}]
            ),
            ("fields[2] (id=cb)", "options are forbidden"),
        ),
        # pdf checkbox missing pdf_field_name
        (
            lambda doc: doc["fields"][2].pop("pdf_field_name"),
            ("fields[2] (id=cb)", "requires a field-level pdf_field_name"),
        ),
        # choice field with < 2 options
        (
            lambda doc: doc["fields"][0]["options"].pop(),
            ("fields[0] (id=grp)", "at least 2 options"),
        ),
        # checkbox_group with NO options at all still reaches the aggregated
        # v2 report with its field path (validate_options deliberately does
        # not fire for checkbox_group -- Codex PR #299)
        (
            lambda doc: doc["fields"][0].pop("options"),
            ("fields[0] (id=grp)", "at least 2 options (found 0)"),
        ),
        # non-slug option value
        (
            lambda doc: doc["fields"][0]["options"][1].update(value="Other Reason"),
            ("fields[0] (id=grp)", "not a v2 slug"),
        ),
        # duplicate option values (the shipped f1040 bug class)
        (
            lambda doc: doc["fields"][0]["options"][1].update(value="dependent_spouse"),
            ("fields[0] (id=grp)", "duplicate option values"),
        ),
        # checkbox_group with field-level pdf_field_name
        (
            lambda doc: doc["fields"][0].update(pdf_field_name="c1[0]"),
            ("fields[0] (id=grp)", "NO field-level pdf_field_name"),
        ),
        # option not PDF-fillable
        (
            lambda doc: doc["fields"][0]["options"][1].pop("pdf_field_name"),
            ("fields[0] (id=grp)", "not PDF-fillable"),
        ),
        # equals on a checkbox_group trigger (the retired vq4m hack)
        (
            lambda doc: doc["fields"][1].update(
                show_if={"field": "grp", "operator": "equals", "value": "other"}
            ),
            ("fields[1] (id=dep)", "not valid on a 'checkbox_group' trigger"),
        ),
        # includes on a text trigger
        (
            lambda doc: doc["fields"][1].update(
                show_if={"field": "cb", "operator": "includes", "value": "x"}
            ),
            ("fields[1] (id=dep)", "operator 'includes' is not valid"),
        ),
        # condition referencing a non-existent field
        (
            lambda doc: doc["fields"][1].update(
                show_if={"field": "ghost", "operator": "is_not_empty"}
            ),
            ("fields[1] (id=dep)", "non-existent field 'ghost'"),
        ),
        # option-slug reference check: value outside the trigger's option set
        (
            lambda doc: doc["fields"][1].update(
                show_if={"field": "grp", "operator": "includes", "value": "c1_9[0]"}
            ),
            ("fields[1] (id=dep)", "not an option slug of 'grp'"),
        ),
        # arity: in requires a list
        (
            lambda doc: doc["fields"][1].update(
                show_if={"field": "dep2", "operator": "in", "value": "x"}
            ),
            ("fields[1] (id=dep)", "requires a non-empty list"),
        ),
        # arity: no-value operator given a value
        (
            lambda doc: doc["fields"][1].update(
                show_if={"field": "grp", "operator": "is_empty", "value": "x"}
            ),
            ("fields[1] (id=dep)", "takes no value"),
        ),
        # arity: scalar operator given a list
        (
            lambda doc: doc["fields"][1].update(
                show_if={"field": "dep2", "operator": "equals", "value": ["a", "b"]}
            ),
            ("fields[1] (id=dep)", "requires a single scalar"),
        ),
        # legacy conditional_fields is not v2 vocabulary
        (
            lambda doc: doc["fields"][1].update(conditional_fields=["cb"]),
            ("fields[1] (id=dep)", "conditional_fields is not part of schema v2"),
        ),
    ],
)
def test_v2_violation_yields_field_path_error(mutate, needles):
    doc = valid_v2_doc()
    doc["fields"].append(text_field("dep2"))
    doc["sections"][0]["fields"].append("dep2")
    mutate(doc)
    assert_v2_error(doc, *needles)


def test_v1_tolerates_what_v2_rejects():
    # The SAME duplicate-option/equals-on-group document parses fine without
    # the v2 stamp -- the shipped kits keep working until the P6.2 flip.
    doc = valid_v2_doc()
    doc["fields"][0]["options"][1]["value"] = "dependent_spouse"  # dupe
    doc["fields"][1]["show_if"] = {"field": "grp", "operator": "equals", "value": "1"}
    del doc["schema_version"]
    validate(doc)


# ---------------------------------------------------------------------------
# Exit criterion 3: unknown operator rejected naming the allowed set
# ---------------------------------------------------------------------------

def test_unknown_operator_rejected_naming_allowed_set():
    doc = valid_v2_doc()
    doc["fields"][1]["show_if"] = {
        "field": "grp",
        "operator": "is_selected",  # the real W-7 hallucination
        "value": "other",
    }
    with pytest.raises(ValidationError) as exc_info:
        validate(doc)
    message = str(exc_info.value)
    # Pydantic's enum error enumerates every permitted member.
    for op in ConditionalOperator:
        assert f"'{op.value}'" in message


# ---------------------------------------------------------------------------
# ConditionGroup shape rules
# ---------------------------------------------------------------------------

def test_value_taking_operator_requires_value_in_every_dialect():
    # equals with no value was rejected before value became Optional and must
    # stay rejected -- including on the v1 path (Codex PR #299).
    with pytest.raises(ValidationError, match="requires a value"):
        ConditionalDisplay.model_validate({"field": "x", "operator": "equals"})
    with pytest.raises(ValidationError, match="requires a value"):
        ConditionalDisplay.model_validate({"field": "x", "operator": "in"})
    # No-value operators may omit it (the reason for the Optional), and the
    # v1 kits' historical value:true on is_checked still parses.
    ConditionalDisplay.model_validate({"field": "x", "operator": "is_checked"})
    ConditionalDisplay.model_validate(
        {"field": "x", "operator": "is_checked", "value": True}
    )


def test_slug_pattern_uses_fullmatch():
    assert not vocab.is_valid_option_slug("valid\n")  # Codex PR #299
    assert not vocab.is_valid_option_slug("two words")
    assert vocab.is_valid_option_slug("valid")


def test_condition_group_requires_a_bucket():
    with pytest.raises(ValidationError, match="at least one non-empty bucket"):
        ConditionGroup()


def test_condition_group_rejects_nesting():
    # depth <= 1: a bucket member must be atomic; a nested group has no
    # field/operator and fails loudly.
    with pytest.raises(ValidationError):
        ConditionGroup.model_validate(
            {"all_of": [{"any_of": [{"field": "a", "operator": "equals", "value": 1}]}]}
        )


def test_mixed_atom_and_bucket_keys_rejected_loudly():
    # {"field", "operator", "all_of"} must NOT win the Union as a tolerant
    # ConditionalDisplay and silently drop the bucket (fresh-eyes finding).
    doc = valid_v2_doc()
    doc["fields"][1]["show_if"] = {
        "field": "grp",
        "operator": "includes",
        "value": "other",
        "all_of": [{"field": "grp", "operator": "is_not_empty"}],
    }
    assert_v2_error(doc, "mixes atomic keys")
    # Same mix hidden inside a bucket member is refused too.
    doc["fields"][1]["show_if"] = {
        "all_of": [
            {
                "field": "grp",
                "operator": "includes",
                "value": "other",
                "any_of": [{"field": "grp", "operator": "is_not_empty"}],
            }
        ]
    }
    assert_v2_error(doc, "must be atomic")
    # And it guards v1 documents identically (the validator is not v2-gated).
    doc["fields"][1]["show_if"] = {
        "field": "grp",
        "operator": "equals",
        "value": "1",
        "none_of": [{"field": "grp", "operator": "is_empty"}],
    }
    del doc["schema_version"]
    with pytest.raises(ValidationError, match="mixes atomic keys"):
        validate(doc)


def test_benign_extra_keys_on_legacy_condition_still_tolerated():
    # Stored editor drafts carry stray non-bucket keys; those keep parsing.
    doc = valid_v2_doc()
    doc["fields"][1]["require_if"] = {
        "field": "grp",
        "operator": "is_not_empty",
        "note": "legacy annotation",
    }
    schema = validate(doc)
    assert isinstance(schema.get_field("dep").require_if, ConditionalDisplay)


def test_legacy_dict_does_not_parse_as_group():
    doc = valid_v2_doc()
    schema = validate(doc)
    legacy = schema.get_field("dep").require_if
    assert isinstance(legacy, ConditionalDisplay)


def test_schema_version_coercion_and_legacy_tolerance():
    doc = valid_v2_doc()
    doc["schema_version"] = 2  # int coerces
    assert validate(doc).schema_version == "2"
    # Any non-'2' stamp takes the LEGACY path (stored drafts carry '1.0'
    # from before this key was modeled; rejecting them would break the v1
    # tolerance -- Codex PR #299). Prove it by pairing a stray stamp with
    # content only v2 rejects.
    doc["fields"][0]["options"][1]["value"] = "dependent_spouse"  # dupe
    for stamp in ("1.0", "3", 1.0):
        doc["schema_version"] = stamp
        assert validate(doc).schema_version == str(stamp)


# ---------------------------------------------------------------------------
# Registry <-> enum agreement (cheap sync check until P1.2's contract test)
# ---------------------------------------------------------------------------

def test_registry_and_enum_agree():
    assert vocab.ALLOWED_OPERATORS == {op.value for op in ConditionalOperator}
    field_type_values = {ft.value for ft in FieldType}
    assert vocab.CHOICE_FIELD_TYPES <= field_type_values
    assert vocab.CONDITION_TRIGGER_TYPES <= field_type_values
    for spec in vocab.OPERATORS.values():
        assert spec.trigger_types <= vocab.CONDITION_TRIGGER_TYPES
        assert spec.value_arity in ("none", "scalar", "list")


# ---------------------------------------------------------------------------
# is_checked dual fate -- the ONE shared fixture (also used by P6.1 tests)
# ---------------------------------------------------------------------------

def _trigger_for(trigger_type: str) -> dict:
    return group_field("trig") if trigger_type == "checkbox_group" else checkbox_field("trig")


@pytest.mark.parametrize(
    "case",
    json.loads((FIXTURES / "is_checked_dual_fate.json").read_text(encoding="utf-8"))["cases"],
    ids=lambda c: c["name"],
)
def test_is_checked_dual_fate(case):
    dep = text_field(show_if={"field": "trig", "operator": case["operator"]})
    doc = v2_schema([_trigger_for(case["trigger_type"]), dep])
    if case["valid_in_v2"]:
        validate(doc)
    else:
        assert_v2_error(doc, "fields[1] (id=dep)", f"'{case['trigger_type']}' trigger")
        # The migration target the fixture prescribes must itself be legal on
        # this trigger type -- the two rule sets agree by construction.
        target = case["migration"]["operator"]
        assert case["trigger_type"] in vocab.OPERATORS[target].trigger_types


# ---------------------------------------------------------------------------
# controls_fields: parsed but deprecated in v2
# ---------------------------------------------------------------------------

def test_v2_controls_fields_parses_with_deprecation_warning():
    doc = valid_v2_doc()
    doc["fields"][2]["controls_fields"] = [{"value": True, "shows": ["dep"]}]
    with pytest.warns(DeprecationWarning, match="controls_fields is deprecated"):
        schema = validate(doc)
    assert schema.get_field("cb").controls_fields


def test_v1_controls_fields_stays_silent():
    with warnings_module.catch_warnings():
        warnings_module.simplefilter("error", DeprecationWarning)
        validate(load_kit("i-90"))  # carries 13 controls_fields entries


# ---------------------------------------------------------------------------
# Cycle warning + composite reference validation
# ---------------------------------------------------------------------------

def test_conditional_cycle_warns_not_errors():
    a = text_field("a", show_if={"field": "b", "operator": "is_not_empty"})
    b = text_field("b", show_if={"field": "a", "operator": "is_not_empty"})
    schema = validate(v2_schema([a, b]))
    result = schema.validate_all_references()
    assert result["errors"] == []
    assert any("Conditional cycle" in w for w in result["warnings"])


def test_validate_all_references_walks_composite_and_require_if():
    dep = text_field(
        show_if={"any_of": [{"field": "nope", "operator": "is_not_empty"}]},
        require_if={"field": "also_nope", "operator": "is_not_empty"},
    )
    doc = v2_schema([group_field(), dep])
    # Bypass v2 parse-time strictness to reach the reference auditor the
    # editor gate calls on v1 drafts too.
    del doc["schema_version"]
    result = validate(doc).validate_all_references()
    joined = "\n".join(result["errors"])
    assert "show_if references non-existent field 'nope'" in joined
    assert "require_if references non-existent field 'also_nope'" in joined


# ---------------------------------------------------------------------------
# Slug minting (the deterministic re-anchor for P5.2 repair)
# ---------------------------------------------------------------------------

def test_mint_option_slug():
    assert vocab.mint_option_slug("Dependent of U.S. citizen/resident alien") == \
        "dependent_of_u_s_citizen_resident_alien"
    assert vocab.mint_option_slug("Hispanic or Latino") == "hispanic_or_latino"
    assert vocab.mint_option_slug("  --  ") == "option"  # fallback
    minted = vocab.mint_option_slug("Cafe con leche")
    assert vocab.is_valid_option_slug(minted)


def test_mint_unique_slugs_dedupes_stably():
    assert vocab.mint_unique_slugs(["Other", "Other", "other"]) == [
        "other",
        "other_2",
        "other_3",
    ]
    # A distinct label whose natural slug lands on a suffixed one must not
    # collide (bd polyglot-pdf-986p): the batch-wide used-set wins.
    minted = vocab.mint_unique_slugs(["Other", "Other", "Other 2"])
    assert minted == ["other", "other_2", "other_2_2"]
    assert len(set(minted)) == len(minted)


def test_minted_slugs_pass_the_v2_validator():
    doc = valid_v2_doc()
    labels = [o["label"] for o in doc["fields"][0]["options"]]
    slugs = vocab.mint_unique_slugs(labels)
    for opt, slug in zip(doc["fields"][0]["options"], slugs):
        opt["value"] = slug
    # show_if references must track the re-mint to stay valid.
    doc["fields"][1]["show_if"] = {
        "all_of": [{"field": "grp", "operator": "includes", "value": slugs[1]}]
    }
    doc["fields"][1].pop("require_if")
    validate(doc)
