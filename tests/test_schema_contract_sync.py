"""Contract-from-model sync guard (bd polyglot-pdf-h76m.4, P1.2).

scripts/bakeoff/schema_contract.py renders its MACHINE CORE -- the conditional
operator list and the canonical example -- from the single source of truth
(backend.models.conditional_vocabulary + FormSchema). These tests pin that the
rendered contract cannot drift from the registry/model:

- the rendered operator set EQUALS the registry's ALLOWED_OPERATORS, and every
  operator name appears in the prompt string;
- the backend-less STATIC fallback equals the registry render (so a backend-less
  bake-off checkout ships the same core CI validates);
- the canonical example MUST FormSchema.model_validate under the strict v2 rules.

Exit criteria:
1. The sync test FAILS on registry/contract drift (proven here by simulating a
   registry that gained an operator the static fallback lacks -- the same
   equality assertion that guards the real module trips).
2. The contract's example block passes FormSchema.model_validate.

Imports schema_contract by adding scripts/bakeoff to sys.path (repo precedent:
tests/test_extract_form_lint.py). ASCII only.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts" / "bakeoff"))

import schema_contract as sc  # noqa: E402
from backend.models import conditional_vocabulary as vocab  # noqa: E402
from backend.models.form_models import FormSchema  # noqa: E402


def test_registry_is_available_in_this_suite():
    # CI runs with the backend importable, so the drift GUARD (the registry
    # render) is actually exercised here -- not silently skipped to the static
    # fallback. A backend-less checkout is the only place REGISTRY_AVAILABLE is
    # False, and that path is the bake-off arms', not this suite's.
    assert sc.REGISTRY_AVAILABLE is True


def test_rendered_operator_names_match_registry():
    rendered = set(sc.allowed_operator_names())
    assert rendered == set(vocab.ALLOWED_OPERATORS)


def test_static_fallback_equals_the_registry_render():
    # The backend-less static snapshot must equal what the registry renders, so
    # a bake-off arm running without the backend sees the SAME core CI validates.
    # This is the assertion that trips on drift (exit criterion 1): add/rename an
    # operator or change a trigger set in the registry and forget to update the
    # snapshot, and these lists diverge.
    assert sc._STATIC_OPERATOR_LINES == sc.render_operator_lines()


def test_every_operator_name_appears_in_the_prompt():
    for name in vocab.ALLOWED_OPERATORS:
        assert name in sc.SCHEMA_CONTRACT, f"operator {name!r} missing from the contract prompt"


def test_canonical_example_validates_as_v2():
    # Exit criterion 2: the contract's example block passes FormSchema.model_validate
    # under the strict v2 rules (it is stamped schema_version '2').
    model = FormSchema.model_validate(sc.CANONICAL_EXAMPLE)
    assert model.schema_version == vocab.SCHEMA_VERSION_V2
    # It exercises the load-bearing v2 conventions: a checkbox_group with slug
    # option values, and an `includes` membership show_if referencing a slug.
    reason = next(f for f in model.fields if f.id == "reason")
    assert reason.type.value == "checkbox_group"
    assert [o.value for o in reason.options] == ["new_application", "renewal", "other"]
    for o in reason.options:
        assert vocab.is_valid_option_slug(o.value)
    other = next(f for f in model.fields if f.id == "other_detail")
    assert other.show_if is not None
    assert other.show_if.operator.value == "includes"
    assert other.show_if.value == "other"


def test_rendered_example_is_ascii_and_parses():
    import json
    text = sc.render_example()
    text.encode("ascii")  # raises if any non-ASCII slipped in
    assert json.loads(text) == sc.CANONICAL_EXAMPLE


def test_render_contract_embeds_operator_block_and_example():
    contract = sc.render_contract()
    assert "CONDITIONAL OPERATORS" in contract
    assert "CANONICAL v2 EXAMPLE" in contract
    # The example object's slug value must be present verbatim (proves the
    # example block, not just a placeholder, was rendered in).
    assert '"new_application"' in contract


def test_drift_is_detected(monkeypatch):
    """Exit criterion 1, proven WITHOUT leaving a real failure in the tree.

    Simulate the registry gaining an operator the rendered contract's static
    snapshot does not know about, and confirm the sync assertions trip. This is
    the exact failure a real drift (new operator / changed trigger set, snapshot
    not updated) would produce -- so the guard demonstrably bites.
    """
    drifted = dict(vocab.OPERATORS)
    drifted["brand_new_operator"] = vocab._spec(
        "brand_new_operator", "scalar", frozenset({"text"})
    )
    monkeypatch.setattr(vocab, "OPERATORS", drifted)

    # The name-set guard now sees an operator the static snapshot lacks.
    rendered_names = set(sc.allowed_operator_names())  # registry-first -> includes the new op
    assert "brand_new_operator" in rendered_names
    assert rendered_names != {ln.strip().split()[0] for ln in sc._STATIC_OPERATOR_LINES}

    # And the static-vs-render equality assertion (the module's real guard) fails.
    with pytest.raises(AssertionError):
        assert sc._STATIC_OPERATOR_LINES == sc.render_operator_lines()
