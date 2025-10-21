import types
import pytest

from backend.utils.json_recovery import extract_json_from_part


def test_plain_json_string():
    s = '{"a": 1, "b": "x"}'
    parsed = extract_json_from_part(s)
    assert isinstance(parsed, dict)
    assert parsed["a"] == 1


def test_code_fence_json():
    s = "```json\n{\"k\": \"v\"}\n```"
    parsed = extract_json_from_part(s)
    assert parsed == {"k": "v"}


def test_embedded_json_in_text():
    s = "Some text before {\"n\": 2, \"m\": [1,2]} trailing"
    parsed = extract_json_from_part(s)
    assert parsed["n"] == 2


def test_object_with_executable_code_attr():
    o = types.SimpleNamespace()
    o.executable_code = "```\n{\"x\": 5}\n```"
    parsed = extract_json_from_part(o)
    assert parsed == {"x": 5}


def test_non_json_returns_none():
    s = "no json here"
    parsed = extract_json_from_part(s)
    assert parsed is None
