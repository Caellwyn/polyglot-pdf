"""The migrated i-90 kit holds the P0 baseline's load-bearing fill invariants
(bd polyglot-pdf-c5r8, P6.1b).

After P6.1a's migrate_schema_v2.py was applied to the shipped i-90 kit
(form-kits/i-90/schema.json is now v2, the v1 original archived), this pins that
the migration did NOT regress the two load-bearing rows of the P0 baseline
(docs/research/2026-07-04-h76m.1-i90-p0-baseline.md): 100% CHOICE fill (28/28)
and 100% TEXT fill (the leaf-convention row intentionally changes -- the
migration re-mints option values to semantic slugs -- and is NOT asserted here,
per the baseline doc).

Also pins that the committed migrated schema is a valid, lint-clean v2 schema.

Imports roundtrip_fill by adding scripts/bakeoff to sys.path (repo precedent:
test_extract_form_lint.py). ASCII only.
"""
from __future__ import annotations

import json
import pathlib
import sys
import warnings

import pytest

_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts" / "bakeoff"))

from backend.models.form_models import FormSchema  # noqa: E402
from backend.models import conditional_vocabulary as vocab  # noqa: E402
from backend.services.schema_lint import lint_schema, has_errors  # noqa: E402

_KIT = _REPO / "form-kits" / "i-90"
_SCHEMA = _KIT / "schema.json"
_PDF = _KIT / "form.pdf"
_ARCHIVED = _KIT / "schema_archived.json"

pytestmark = pytest.mark.skipif(not _SCHEMA.exists(), reason="i-90 kit not present")


def _schema():
    return json.loads(_SCHEMA.read_text(encoding="utf-8"))


def _dump():
    import acroform_dump  # scripts/bakeoff on sys.path
    return acroform_dump.dump_pdf(str(_PDF))


def test_committed_i90_is_v2():
    assert str(_schema().get("schema_version")) == vocab.SCHEMA_VERSION_V2


def test_archived_i90_is_the_v1_original():
    # The backup carries the pre-migration schema (v1: no/1 schema_version).
    archived = json.loads(_ARCHIVED.read_text(encoding="utf-8"))
    assert str(archived.get("schema_version")) != vocab.SCHEMA_VERSION_V2


def test_migrated_i90_validates_v2_and_lints_clean():
    schema = _schema()
    with warnings.catch_warnings():
        # controls_fields is demote-not-delete in v2 (retired at P6.2) -- it
        # raises a DeprecationWarning, not an error.
        warnings.simplefilter("ignore", DeprecationWarning)
        FormSchema.model_validate(schema)
    assert not has_errors(lint_schema(schema, _dump()))
    # Field count survives migration unchanged (baseline: 132).
    assert len(schema["fields"]) == 132


def test_migrated_i90_roundtrip_fill_matches_p0_baseline():
    import roundtrip_fill  # scripts/bakeoff on sys.path
    result = roundtrip_fill.run(str(_SCHEMA), str(_PDF))
    # The two load-bearing P0 baseline rows: both 100% fill success.
    assert result["choice_fill_success"]["pct"] == 100.0, result["choice_fill_success"]
    assert result["choice_fill_success"]["attempted"] == 28  # baseline inventory
    assert result["text_fill_success"]["pct"] == 100.0, result["text_fill_success"]
    # Pin the TEXT inventory too (fresh-eyes): a pct-only assertion would pass
    # even if a future edit dropped TEXT fields (as long as the survivors filled).
    # 110 = the P0 baseline's 108 + the 2 height comboboxes now text/select-fillable.
    assert result["text_fill_success"]["attempted"] == 110
