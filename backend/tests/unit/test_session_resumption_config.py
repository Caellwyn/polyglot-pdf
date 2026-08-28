"""Gemini Live session-resumption config (bd polyglot-pdf-2nikx).

Maintainer-directed feature so the naive-arm cost-measurement harness
(scripts/spikes/measure_form_session_costs.py) can recover from a mid-run
model wedge by resume-reconnecting instead of aborting. SESSION_RESUMPTION_ENABLED
defaults FALSE -- production behavior must be byte-identical with the flag off
(the repo already weighed and declined resumption for production in June,
journal 2026-06-15-bd-l3a.3; this flag does not reopen that decision, it only
lets the harness opt in for itself).

Four things pinned here, all hermetic (no network):
1. The flag defaults False.
2. Flag OFF -> the built live-config dict carries NO session_resumption key at
   all (production inertness -- THE load-bearing assertion; mutation-verified
   by forcing the key in and watching this test go red).
3. Flag ON -> the config carries session_resumption, and a stored handle rides
   it (a fresh adapter with no handle yet sends handle=None; an adapter that
   already captured one from a prior session sends that value).
4. The receive loop captures a handle from a synthetic
   LiveServerSessionResumptionUpdate-shaped message, mirroring the existing
   on_go_away receive-loop test pattern (SimpleNamespace-faked SDK shapes).
"""

from types import SimpleNamespace

import pytest

from backend.config import Settings


# ---------------------------------------------------------------------------
# 1. Default
# ---------------------------------------------------------------------------


def test_session_resumption_defaults_false():
    """SESSION_RESUMPTION_ENABLED must default False -- production behavior
    stays unchanged unless something explicitly opts in."""
    assert Settings().SESSION_RESUMPTION_ENABLED is False


# ---------------------------------------------------------------------------
# 2. Flag OFF -> config carries no session_resumption key (production inertness)
# ---------------------------------------------------------------------------


def test_build_live_config_omits_session_resumption_when_disabled():
    """LOAD-BEARING: with SESSION_RESUMPTION_ENABLED=False, the built live
    connect config must NOT carry a session_resumption key at all -- not an
    empty dict, not a null-handle dict, ABSENT. A deployed session (the flag's
    default) must send the exact same config shape as before this feature
    existed. Mutation-verify this by forcing the key in unconditionally and
    watching this assertion fail.
    """
    from backend.adapters.live_ai_gemini import LiveAIGemini

    settings = Settings(SESSION_RESUMPTION_ENABLED=False)
    adapter = LiveAIGemini(api_key="test_key")

    cfg = adapter._build_live_config(settings)

    assert "session_resumption" not in cfg


# ---------------------------------------------------------------------------
# 3. Flag ON -> config carries session_resumption, with the stored handle
# ---------------------------------------------------------------------------


def test_build_live_config_includes_session_resumption_when_enabled():
    """With the flag on and no handle captured yet, the config requests
    resumption with handle=None (a fresh session -- nothing to resume)."""
    from backend.adapters.live_ai_gemini import LiveAIGemini

    settings = Settings(SESSION_RESUMPTION_ENABLED=True)
    adapter = LiveAIGemini(api_key="test_key")
    assert adapter.get_resumption_handle() is None

    cfg = adapter._build_live_config(settings)

    assert "session_resumption" in cfg
    assert cfg["session_resumption"] == {"handle": None}


def test_build_live_config_carries_stored_handle_on_reconnect():
    """A handle captured from a PRIOR session on this adapter instance must
    ride the NEXT connect's config -- this is the whole mechanism a resume
    reconnect depends on (the adapter instance persists the handle across
    _run_session_loop restarts; see get_resumption_handle's docstring)."""
    from backend.adapters.live_ai_gemini import LiveAIGemini

    settings = Settings(SESSION_RESUMPTION_ENABLED=True)
    adapter = LiveAIGemini(api_key="test_key")
    adapter._resumption_handle = "opaque-handle-abc123"

    cfg = adapter._build_live_config(settings)

    assert cfg["session_resumption"] == {"handle": "opaque-handle-abc123"}
    assert adapter.get_resumption_handle() == "opaque-handle-abc123"


# ---------------------------------------------------------------------------
# 4. Receive loop captures a handle from a synthetic SessionResumptionUpdate
# ---------------------------------------------------------------------------


class _DummyContextManager:
    """Async context manager returning the supplied session (mirrors
    test_live_ai_gemini.py's own helper of the same name)."""

    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_run_session_loop_captures_resumption_handle():
    """A resumable SessionResumptionUpdate event in the receive stream stores
    its new_handle on the adapter, retrievable via get_resumption_handle().

    Mirrors the existing on_go_away receive-loop test pattern
    (test_run_session_loop_invokes_on_go_away in test_live_ai_gemini.py):
    fake the SDK event shape with SimpleNamespace attributes matching the
    verified google-genai 2.8.0 LiveServerSessionResumptionUpdate fields
    (new_handle, resumable).
    """
    import asyncio as _asyncio

    from backend.adapters.live_ai_gemini import LiveAIGemini
    from unittest.mock import MagicMock

    adapter = LiveAIGemini()
    adapter._log = MagicMock()
    adapter._audio_queue = _asyncio.Queue()
    adapter._text_queue = _asyncio.Queue()

    class _ResumptionSession:
        def __init__(self):
            self._generator = None

        async def send_realtime_input(self, **_kwargs):
            return None

        async def send_tool_response(self, **_kwargs):
            return None

        async def send_client_content(self, **_kwargs):
            return None

        def receive(self):
            if self._generator is None:
                async def gen():
                    yield SimpleNamespace(
                        session_resumption_update=SimpleNamespace(
                            new_handle="fresh-handle-xyz",
                            resumable=True,
                            last_consumed_client_message_index=None,
                        )
                    )
                self._generator = gen()
            return self._generator

    session = _ResumptionSession()
    ctx = _DummyContextManager(session)
    fake_live = MagicMock()
    fake_live.connect.return_value = ctx
    adapter._client = SimpleNamespace(aio=SimpleNamespace(live=fake_live))

    await _asyncio.wait_for(adapter._run_session_loop(), timeout=1.0)

    assert adapter.get_resumption_handle() == "fresh-handle-xyz"
    await adapter.finalize()


@pytest.mark.asyncio
async def test_run_session_loop_ignores_unresumable_update():
    """A SessionResumptionUpdate with resumable=False (the server marking this
    point as NOT safe to resume from -- e.g. mid function-call/generation, per
    the SDK's own field docstring) must NOT overwrite a previously-stored
    handle. Presenting a handle the server already said would lose data is
    worse than presenting the last known-good one."""
    import asyncio as _asyncio

    from backend.adapters.live_ai_gemini import LiveAIGemini
    from unittest.mock import MagicMock

    adapter = LiveAIGemini()
    adapter._log = MagicMock()
    adapter._audio_queue = _asyncio.Queue()
    adapter._text_queue = _asyncio.Queue()
    adapter._resumption_handle = "prior-good-handle"

    class _UnresumableSession:
        def __init__(self):
            self._generator = None

        async def send_realtime_input(self, **_kwargs):
            return None

        async def send_tool_response(self, **_kwargs):
            return None

        async def send_client_content(self, **_kwargs):
            return None

        def receive(self):
            if self._generator is None:
                async def gen():
                    yield SimpleNamespace(
                        session_resumption_update=SimpleNamespace(
                            new_handle="",
                            resumable=False,
                            last_consumed_client_message_index=None,
                        )
                    )
                self._generator = gen()
            return self._generator

    session = _UnresumableSession()
    ctx = _DummyContextManager(session)
    fake_live = MagicMock()
    fake_live.connect.return_value = ctx
    adapter._client = SimpleNamespace(aio=SimpleNamespace(live=fake_live))

    await _asyncio.wait_for(adapter._run_session_loop(), timeout=1.0)

    assert adapter.get_resumption_handle() == "prior-good-handle"
    await adapter.finalize()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
