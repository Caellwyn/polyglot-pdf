"""Config invariants for the genai-2.8.0 round-trip fixes.

Two regression guards, both pure-unit (no live Gemini):

1. update_form_fields.value carries an explicit type. A REQUIRED tool param with
   no type makes gemini-3.1 reject the call under google-genai 2.8.0 (it
   verbalizes "I had an issue processing that value" and the field never fills) --
   bd polyglot-pdf-wpw.4. The type must stay declared or 3.1 silently breaks again.

2. The context-compression token settings survive a set-but-EMPTY env var. The
   `int(os.getenv(key, "default"))` form returns the default only when the var is
   UNSET; set-but-empty yields "" and int("") raises at import, so the backend
   will not boot. The hardened `int(os.getenv(key) or "default")` form must hold
   -- bd polyglot-pdf-l3a.2 (same class as the VAD_*_MS hardening in PR #156).
"""

import importlib

import pytest

from backend.config import Settings


def _update_form_fields_decl():
    decls = Settings().TOOL_DECLARATIONS
    matches = [d for d in decls if d.get("name") == "update_form_fields"]
    assert matches, "update_form_fields declaration missing from TOOL_DECLARATIONS"
    return matches[0]


def test_update_form_fields_value_param_is_typed():
    """The `value` param must declare a type (3.1 rejects an untyped required
    param under genai 2.8.0 -- bd polyglot-pdf-wpw.4)."""
    decl = _update_form_fields_decl()
    value = decl["parameters"]["properties"]["value"]
    assert value.get("type"), (
        "update_form_fields.value has no type -- gemini-3.1 will reject the call "
        "under google-genai 2.8.0 (bd polyglot-pdf-wpw.4)"
    )


def test_every_required_tool_param_is_typed():
    """No REQUIRED tool param may be untyped (the same 2.8.0 rejection class
    applies to any required param, not just update_form_fields.value)."""
    untyped = []
    for decl in Settings().TOOL_DECLARATIONS:
        params = decl.get("parameters", {})
        props = params.get("properties", {})
        for req in params.get("required", []):
            pdef = props.get(req, {})
            if "type" not in pdef:
                untyped.append(f"{decl.get('name')}.{req}")
    assert not untyped, f"untyped REQUIRED tool params (3.1 will reject): {untyped}"


@pytest.mark.parametrize(
    "trigger_env, window_env",
    [
        ("", ""),          # both set-but-empty (the bug)
        ("", "3000"),      # only trigger empty
        ("5000", ""),      # only window empty
    ],
)
def test_compression_tokens_survive_empty_env(monkeypatch, trigger_env, window_env):
    """Set-but-empty compression env must NOT crash Settings() construction --
    it falls back to the defaults instead of raising int('') (bd polyglot-pdf-l3a.2).

    Settings reads os.environ at CLASS-DEFINITION time, so we monkeypatch the env
    and reimport the config module to re-evaluate the field defaults.
    """
    monkeypatch.setenv("CONTEXT_COMPRESSION_TRIGGER_TOKENS", trigger_env)
    monkeypatch.setenv("CONTEXT_COMPRESSION_WINDOW_TOKENS", window_env)

    import backend.config as config_module

    reloaded = importlib.reload(config_module)
    try:
        s = reloaded.Settings()
        # Empty -> default; a real value -> that value.
        assert s.CONTEXT_COMPRESSION_TRIGGER_TOKENS == (
            5000 if trigger_env == "" else int(trigger_env)
        )
        assert s.CONTEXT_COMPRESSION_WINDOW_TOKENS == (
            3000 if window_env == "" else int(window_env)
        )
    finally:
        # Restore the pristine module for any later test importing backend.config.
        monkeypatch.delenv("CONTEXT_COMPRESSION_TRIGGER_TOKENS", raising=False)
        monkeypatch.delenv("CONTEXT_COMPRESSION_WINDOW_TOKENS", raising=False)
        importlib.reload(config_module)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
