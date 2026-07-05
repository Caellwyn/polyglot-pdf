"""Every authoring few-shot exemplar is a valid, lint-clean v2 schema.

bd polyglot-pdf-h76m.4 (P1.2). The exemplars under scripts/authoring/fewshot/
are shown to the extraction model so it imitates the schema-v2 conventions; a
broken exemplar would teach the model to emit broken schemas. So each one MUST
pass FormSchema.model_validate under the strict v2 rules AND lint clean
(schema_lint -> 0 errors). ASCII only.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from backend.models.form_models import FormSchema
from backend.models import conditional_vocabulary as vocab
from backend.services.schema_lint import SEVERITY_ERROR, lint_schema

_REPO = pathlib.Path(__file__).resolve().parent.parent
_FEWSHOT = _REPO / "scripts" / "authoring" / "fewshot"


def _exemplar_files():
    return sorted(_FEWSHOT.glob("*.json"))


def test_fewshot_dir_has_at_least_one_exemplar():
    assert _exemplar_files(), f"no exemplars found under {_FEWSHOT}"


@pytest.mark.parametrize("path", _exemplar_files(), ids=lambda p: p.name)
def test_exemplar_is_valid_v2_and_lint_clean(path):
    schema = json.loads(path.read_text(encoding="utf-8"))
    # Must be stamped v2 (it teaches the v2 conventions) and validate strictly.
    assert str(schema.get("schema_version")) == vocab.SCHEMA_VERSION_V2, (
        f"{path.name}: exemplar must be stamped schema_version '2'"
    )
    FormSchema.model_validate(schema)  # raises on any v2 violation
    errors = [f for f in lint_schema(schema) if f.severity == SEVERITY_ERROR]
    assert not errors, (
        f"{path.name} has lint errors: "
        + "; ".join(f"[{f.rule}] {f.path}" for f in errors[:5])
    )


@pytest.mark.parametrize("path", _exemplar_files(), ids=lambda p: p.name)
def test_exemplar_is_ascii(path):
    # cp1252 safety (scar #6): the exemplars are read as text into the prompt.
    path.read_text(encoding="utf-8").encode("ascii")
