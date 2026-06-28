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
from backend.scripts.probe_g1c_tuning import _parse_conflicts


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
