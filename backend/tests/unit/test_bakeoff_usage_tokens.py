"""bd polyglot-pdf-nwnys: scripts/bakeoff Gemini usage records must count
thinking tokens.

Gemini reports thinking in `thoughts_token_count`, outside
`candidates_token_count`, and bills it at the output rate. The bake-off arms
run on gemini-2.5-pro (thinking cannot be disabled), so a record built from
candidates_token_count alone under-states output cost.

Two pins:
  1. gemini_usage_tokens() folds thoughts into "output".
  2. The SET: no scripts/bakeoff module other than usage_tokens.py reads
     candidates_token_count -- every Gemini usage record goes through the
     helper, so a new arm that hand-rolls the record fails here.
"""

from __future__ import annotations

import importlib.util
import pathlib
import types

_BAKEOFF_DIR = pathlib.Path(__file__).resolve().parents[3] / "scripts" / "bakeoff"


def _load_usage_tokens():
    # Loaded by FILE PATH: bake-off modules use bare sibling imports, which
    # pytest's importlib import-mode does not resolve.
    spec = importlib.util.spec_from_file_location(
        "bakeoff_usage_tokens", _BAKEOFF_DIR / "usage_tokens.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _usage(**kw):
    return types.SimpleNamespace(**kw)


def test_thinking_tokens_fold_into_output():
    fn = _load_usage_tokens().gemini_usage_tokens
    tok = fn(_usage(prompt_token_count=1000, candidates_token_count=200,
                    thoughts_token_count=512))
    assert tok == {"input": 1000, "output": 712, "thoughts": 512}


def test_no_thinking_reported_leaves_output_unchanged():
    fn = _load_usage_tokens().gemini_usage_tokens
    tok = fn(_usage(prompt_token_count=10, candidates_token_count=3,
                    thoughts_token_count=None))
    assert tok == {"input": 10, "output": 3, "thoughts": 0}


def test_missing_answer_count_is_unknown_not_zero():
    fn = _load_usage_tokens().gemini_usage_tokens
    tok = fn(_usage(prompt_token_count=10, thoughts_token_count=5))
    assert tok["output"] is None


def test_every_bakeoff_gemini_usage_record_goes_through_the_helper():
    readers = sorted(
        p.name for p in _BAKEOFF_DIR.rglob("*.py")
        if "candidates_token_count" in p.read_text(encoding="utf-8")
    )
    assert readers == ["usage_tokens.py"], (
        "only scripts/bakeoff/usage_tokens.py may read candidates_token_count; "
        "build Gemini token records with gemini_usage_tokens() so thinking "
        f"tokens are counted. Direct readers: {readers}")
    callers = sorted(
        p.name for p in _BAKEOFF_DIR.rglob("*.py")
        if p.name != "usage_tokens.py"
        and "gemini_usage_tokens(usage)" in p.read_text(encoding="utf-8")
    )
    # The four Gemini call sites (arm_gemini, arm_documentai, and the two
    # llm_providers runners).
    assert callers == ["arm_documentai.py", "arm_gemini.py", "llm_providers.py"]
    providers = (_BAKEOFF_DIR / "llm_providers.py").read_text(encoding="utf-8")
    assert providers.count("gemini_usage_tokens(usage)") == 2
