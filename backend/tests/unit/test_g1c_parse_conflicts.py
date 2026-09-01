"""Guard for the G1c probe's response parser (bd polyglot-pdf-08zv).

`_parse_conflicts` decides whether a checker model response is a usable verdict or a
MODEL-FORMAT failure. The distinction matters for accuracy: a model-format failure
(non-JSON, OR valid-JSON-of-the-wrong-shape like a bare `[]`) must be scored as an
empty verdict (a miss / clean-pass), NOT excluded as a transport error -- excluding
it would inflate the measured precision/recall. The original parser called
`verdict.get(...)` directly, so a valid `[]` raised AttributeError and fell into the
transport-error path (Codex review on PR #262). These tests pin the corrected
contract: wrong-shape JSON -> None (model-format failure), dict -> conflicts list.
"""
from pathlib import Path

import pytest

# backend/tests/unit/test_g1c_parse_conflicts.py -> parents[3] is the repo root.
_I90_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "form-kits" / "i-90" / "schema.json"

# probe_g1c_tuning imports probe_g1b_model_size_bakeoff, which imports g1b_corpus,
# which computes corpus_fingerprint() (and so reads the i-90 schema) at MODULE
# level -- so this whole file fails at collection, not at test time, once the
# i-90 kit is gone (bd polyglot-pdf-hydb0, deprecated in favor of i-90_v2).
# pytest.mark.skipif is not enough here: the crash happens in the import
# statement itself, before pytest can apply the marker, so this must skip
# BEFORE importing -- same absent-file check as test_ai_context.py /
# test_measure_harness_i90v2_plan.py, just moved ahead of the import.
if not _I90_SCHEMA_PATH.exists():
    pytest.skip(
        "form-kits/i-90/schema.json not present (kit deprecated, bd "
        "polyglot-pdf-hydb0) -- probe_g1c_tuning's import chain needs it "
        "until the G1b/G1c corpus is re-authored against i-90_v2",
        allow_module_level=True,
    )

from backend.scripts.probe_g1c_tuning import _parse_conflicts  # noqa: E402


def test_non_json_is_model_format_failure():
    assert _parse_conflicts("not json at all") is None


def test_valid_json_wrong_shape_is_model_format_failure():
    # valid JSON but not the {conflicts: [...]} object -> None (the AttributeError
    # bug Codex caught: these used to be miscounted as transport errors)
    assert _parse_conflicts("[]") is None
    assert _parse_conflicts('"a string"') is None
    assert _parse_conflicts("42") is None


def test_dict_with_conflicts_list_passes_through():
    assert _parse_conflicts('{"conflicts": []}') == []
    assert _parse_conflicts('{"conflicts": [{"field_ids": ["a", "b"]}]}') == [
        {"field_ids": ["a", "b"]}]


def test_dict_with_missing_or_nonlist_conflicts_is_empty():
    assert _parse_conflicts("{}") == []
    assert _parse_conflicts('{"conflicts": "oops"}') == []
    assert _parse_conflicts('{"other": 1}') == []
