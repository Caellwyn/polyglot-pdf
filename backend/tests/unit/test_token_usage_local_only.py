"""The token dashboard file is local-dev only, and the per-turn usage banner
is a structured log line, not a print (bd polyglot-pdf-wfgjz, sprint 23
B1a / PF-11). Two guards on the file write, each pinned on its own layer:
the logger refuses with K_SERVICE set, and the only call site is gated on
the backend/.env.DEV marker.
"""
import ast
import pathlib

import pytest


def _repo_root() -> pathlib.Path:
    p = pathlib.Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "backend" / "utils").is_dir():
            return parent
    raise AssertionError("repo root not found")


REPO_ROOT = _repo_root()
ADAPTER = REPO_ROOT / "backend" / "adapters" / "live_ai_gemini.py"

_EVENT = dict(
    form_id="f", form_session_id="fs", gemini_session_id="g",
    prompt_tokens=1, response_tokens=1, total_tokens=2,
    text_input=1, audio_input=0, text_output=1, audio_output=0,
    text_input_cost=0.0, audio_input_cost=0.0, text_output_cost=0.0, audio_output_cost=0.0,
    total_cost_usd=0.0,
    session_total_tokens=2, session_total_cost_usd=0.0,
    session_text_input=1, session_audio_input=0, session_text_output=1, session_audio_output=0,
)


def _logger_in(tmp_path, monkeypatch):
    import backend.utils.token_file_logger as tfl
    logger = tfl.TokenFileLogger.__new__(tfl.TokenFileLogger)
    logger.log_file = tmp_path / "token_usage.jsonl"
    return logger


def _call(logger, **overrides):
    import inspect
    params = inspect.signature(logger.log_token_event).parameters
    kwargs = {k: v for k, v in _EVENT.items() if k in params}
    for name, p in params.items():
        if name not in kwargs and p.default is inspect.Parameter.empty and name != "self":
            kwargs[name] = None
    kwargs.update(overrides)
    logger.log_token_event(**kwargs)


def test_deployed_instance_writes_no_token_file(tmp_path, monkeypatch):
    """Mutation-verified by deleting the K_SERVICE return in log_token_event."""
    monkeypatch.setenv("K_SERVICE", "polyglot-backend")
    logger = _logger_in(tmp_path, monkeypatch)
    _call(logger)
    assert not logger.log_file.exists() or logger.log_file.read_text(encoding="utf-8") == ""


def test_local_dev_still_writes_the_token_file(tmp_path, monkeypatch):
    monkeypatch.delenv("K_SERVICE", raising=False)
    logger = _logger_in(tmp_path, monkeypatch)
    _call(logger)
    assert logger.log_file.read_text(encoding="utf-8").strip()


def _call_site_gate():
    """The `if` guarding the get_token_logger() call in the adapter."""
    tree = ast.parse(ADAPTER.read_text(encoding="utf-8"))
    enclosing = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                        and sub.func.id == "get_token_logger"):
                    enclosing.append(node)
                    break
    assert enclosing, "get_token_logger() call site not found under an if"
    return max(enclosing, key=lambda n: n.lineno)  # the innermost if


def test_the_token_file_call_site_is_gated_on_the_dev_marker():
    """Mutation-verified by dropping DEV_LOGGING_ENABLED from the condition."""
    gate = _call_site_gate()
    names = {n.id for n in ast.walk(gate.test) if isinstance(n, ast.Name)}
    assert "DEV_LOGGING_ENABLED" in names, ast.dump(gate.test)[:200]


def test_the_usage_banner_is_a_structured_line_not_a_print():
    """Mutation-verified by restoring a print() of the token counts."""
    src = ADAPTER.read_text(encoding="utf-8")
    assert "[tokens] TOKEN USAGE" not in src
    tree = ast.parse(src)
    usage_calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                   and n.args and isinstance(n.args[0], ast.Constant)
                   and n.args[0].value == "token_usage"]
    assert len(usage_calls) == 1, "expected exactly one token_usage log call"
    call = usage_calls[0]
    assert isinstance(call.func, ast.Attribute) and call.func.attr == "info"
    kw = {k.arg for k in call.keywords}
    assert {"prompt_tokens", "response_tokens", "total_tokens", "turn_cost_usd"} <= kw
    # No print() carrying token counts anywhere in the adapter.
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "print":
            text = ast.unparse(n)
            assert "prompt_tokens" not in text and "total_cost" not in text, text
