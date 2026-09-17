"""/ws/fill takes its credential from the FIRST FRAME (sprint 23 C2, bd
polyglot-pdf-bwevj) -- the PF-1 root cause fix: a credential on the URL lands
in Cloud Run's request log for every session.

Pins, each red before the change:
- a handshake carrying a valid token proceeds (accept + the session handler);
- a handshake with a bad token, or none, closes 1008 BEFORE the session
  handler (no Gemini session);
- the deprecated ?token= still works for one deploy cycle and logs a
  deprecation line; a bad URL token is refused BEFORE accept;
- an accepted socket that never sends its first frame is closed 1008 after
  WS_AUTH_TIMEOUT_SEC;
- a browser Origin outside the CORS list is refused before accept; no Origin
  (non-browser client) and an allowed Origin pass;
- a text frame over WS_MAX_TEXT_FRAME_BYTES closes 1009;
- /ws/echo and /ws/audio refuse before accept with K_SERVICE set, marker or
  not;
- the token is popped from the handshake before anything reads it.
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

import backend.routes.websocket_routes as wsr

_HANDSHAKE = {
    "type": "handshake",
    "schema": {
        "source": "web",
        "form_metadata": {"title": "Contact", "url": "https://example.com"},
        "fields": [{"id": "name", "name": "Full Name", "type": "text"}],
    },
    "current_values": {},
}
_STAFF = {"uid": "u1", "firm_id": "firm-a", "firm_role": "employee"}


def _ws(first_frame=None, origin=None, frames=None):
    ws = MagicMock()
    ws.headers = {} if origin is None else {"origin": origin}
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    ws.send_json = AsyncMock()
    if frames is not None:
        ws.receive_text = AsyncMock(side_effect=frames)
    else:
        ws.receive_text = AsyncMock(return_value=first_frame)
    return ws


def _run(ws, token=None, service=None):
    handler = AsyncMock()
    asyncio.run(wsr.fill_form_from_schema(ws, token=token, service=service or AsyncMock()))
    return handler


def _closes(ws, code):
    return [c for c in ws.close.await_args_list if c.kwargs.get("code") == code]


@pytest.fixture(autouse=True)
def _stub_session_and_verifier(monkeypatch):
    # The session handler is stubbed: these tests are about what happens
    # BEFORE it. verify_token accepts exactly one token.
    monkeypatch.setattr(wsr, "_handle_fill_session", AsyncMock())

    def _verify(tok, **_kw):
        if tok == "good.staff.token":
            return dict(_STAFF)
        raise ValueError("bad token")

    monkeypatch.setattr(wsr, "verify_token", _verify)
    monkeypatch.setattr(wsr.settings, "WS_AUTH_TIMEOUT_SEC", 0.2, raising=False)


def test_a_valid_credential_in_the_first_frame_opens_the_session():
    frame = dict(_HANDSHAKE, token="good.staff.token")
    ws = _ws(json.dumps(frame))
    _run(ws)
    ws.accept.assert_awaited_once()
    assert not _closes(ws, 1008)
    wsr._handle_fill_session.assert_awaited()


def test_a_bad_credential_in_the_first_frame_closes_1008_before_any_session():
    frame = dict(_HANDSHAKE, token="forged.token")
    ws = _ws(json.dumps(frame))
    _run(ws)
    ws.accept.assert_awaited_once()  # accepted, then refused on the frame
    assert _closes(ws, 1008), ws.close.await_args_list
    wsr._handle_fill_session.assert_not_awaited()
    # The wire reason is the fixed phrase, never the exception text.
    assert _closes(ws, 1008)[0].kwargs.get("reason") == "Authentication failed"


def test_no_credential_anywhere_closes_1008_before_any_session():
    ws = _ws(json.dumps(dict(_HANDSHAKE)))
    _run(ws)
    assert _closes(ws, 1008)
    wsr._handle_fill_session.assert_not_awaited()


def test_the_deprecated_url_token_still_works_and_is_logged(monkeypatch):
    seen = []
    monkeypatch.setattr(wsr, "_log", MagicMock(bind=lambda **kw: MagicMock(
        warning=lambda event, **kw: seen.append(event), error=lambda *a, **k: None, info=lambda *a, **k: None)))
    ws = _ws(json.dumps(dict(_HANDSHAKE)))
    _run(ws, token="good.staff.token")
    ws.accept.assert_awaited_once()
    assert not _closes(ws, 1008)
    wsr._handle_fill_session.assert_awaited()
    assert "ws_token_in_url_deprecated" in seen


def test_a_bad_url_token_is_refused_BEFORE_accept():
    ws = _ws(json.dumps(dict(_HANDSHAKE)))
    _run(ws, token="forged.token")
    ws.accept.assert_not_awaited()
    assert _closes(ws, 1008)
    wsr._handle_fill_session.assert_not_awaited()


def test_a_silent_accepted_socket_is_closed_1008_after_the_auth_timeout():
    async def _never():
        await asyncio.sleep(5)
    ws = _ws()
    ws.receive_text = _never
    _run(ws)
    ws.accept.assert_awaited_once()
    assert _closes(ws, 1008)
    assert _closes(ws, 1008)[0].kwargs.get("reason") == "Authentication failed"
    wsr._handle_fill_session.assert_not_awaited()


def test_the_token_is_popped_from_the_handshake_before_it_is_read(monkeypatch):
    """The parsed handshake dict must not carry the credential once the route
    has verified it (the dict feeds the handshake log/telemetry paths).
    Mutation: pop -> get -- red."""
    held = {}
    real_loads = json.loads

    def _loads(text):
        held.clear()
        held.update(real_loads(text))
        return held

    monkeypatch.setattr(wsr.json, "loads", _loads)
    frame = dict(_HANDSHAKE, token="good.staff.token")
    ws = _ws(json.dumps(frame))
    _run(ws)
    wsr._handle_fill_session.assert_awaited()
    assert "token" not in held, sorted(held)


# --- Origin allowlist ----------------------------------------------------------------

def test_a_disallowed_browser_origin_is_refused_before_accept(monkeypatch):
    monkeypatch.setattr(wsr, "_allowed_ws_origins", lambda: frozenset({"https://polyglot-demo-aa709.web.app"}))
    ws = _ws(json.dumps(dict(_HANDSHAKE, token="good.staff.token")), origin="https://evil.example")
    _run(ws)
    ws.accept.assert_not_awaited()
    assert _closes(ws, 1008)
    assert _closes(ws, 1008)[0].kwargs.get("reason") == "Origin not allowed"


def test_an_allowed_origin_and_a_missing_origin_both_pass(monkeypatch):
    monkeypatch.setattr(wsr, "_allowed_ws_origins", lambda: frozenset({"https://polyglot-demo-aa709.web.app"}))
    for origin in ("https://polyglot-demo-aa709.web.app", None):
        ws = _ws(json.dumps(dict(_HANDSHAKE, token="good.staff.token")), origin=origin)
        _run(ws)
        ws.accept.assert_awaited_once()
        assert not _closes(ws, 1008), origin


def test_the_origin_allowlist_is_the_cors_list(monkeypatch):
    """One list: what CORS allows, the socket allows; nothing else."""
    from backend.config import LOCAL_BROWSER_ORIGINS
    monkeypatch.setattr(wsr.get_settings(), "CORS_EXTRA_ORIGINS", "https://a.web.app;https://b.web.app", raising=False)
    allowed = wsr._allowed_ws_origins()
    assert set(LOCAL_BROWSER_ORIGINS) <= allowed
    assert {"https://a.web.app", "https://b.web.app"} <= allowed


def test_the_deployed_channel_origin_lists_include_the_voice_app_sites():
    """The socket is opened from the voice app's Hosting site DIRECTLY (no
    rewrite for WebSockets), so each channel's CORS_EXTRA_ORIGINS must name
    that channel's app site or every production session is refused."""
    import pathlib
    root = pathlib.Path(wsr.__file__).resolve().parents[2]
    from backend.config import parse_extra_origins

    def origins(channel):
        text = (root / "deploy" / "channels" / f"{channel}.env").read_text(encoding="utf-8")
        line = next(l for l in text.splitlines() if l.startswith("CORS_EXTRA_ORIGINS="))
        return set(parse_extra_origins(line.split("=", 1)[1]))

    assert {"https://polyglot-demo-aa709.web.app", "https://polyglot-demo-aa709.firebaseapp.com"} <= origins("demo")
    assert {"https://polyglot-app-staging.web.app", "https://polyglot-app-staging.firebaseapp.com"} <= origins("staging")
    # And NOT the other's: staging and demo share the project, so a backend
    # accepting the other channel's app site would let a browser on one
    # channel open a session on the other.
    assert not any("polyglot-app-staging" in o for o in origins("demo")), origins("demo")
    assert not any("polyglot-demo-aa709" in o for o in origins("staging")), origins("staging")


# --- staff kit gate: publish + visibility, like the HTTP kit reads ------------------

def test_a_staff_token_naming_an_unpublished_kit_is_refused_1008(monkeypatch):
    """require_published runs before require_visible on the socket, as on
    every HTTP kit read: a draft/reverted kit must not open a voice session.
    Mutation: drop the _require_published call -- red."""
    from backend.services.form_kits import FormKitNotFound
    monkeypatch.setattr(wsr, "_load_live_metadata", AsyncMock(return_value={"status": "draft"}))
    monkeypatch.setattr(wsr, "_require_published", MagicMock(side_effect=FormKitNotFound("Kit not published: k")))
    monkeypatch.setattr(wsr, "_require_visible", AsyncMock(return_value=None))
    frame = dict(_HANDSHAKE, token="good.staff.token", kit_id="k")
    ws = _ws(json.dumps(frame))
    _run(ws)
    assert _closes(ws, 1008) and _closes(ws, 1008)[0].kwargs.get("reason") == "Kit not available"
    wsr._handle_fill_session.assert_not_awaited()


def test_a_transient_kit_store_failure_is_1013_not_the_terminal_1008(monkeypatch):
    """A GCS blip on the metadata read must not end a staff session for good:
    1013 kit_unavailable (the client's ordinary retry path, like
    budget_unavailable), never 1008. Mutation: collapse to 1008 -- red."""
    from backend.services.form_kits import FormKitStoreError
    monkeypatch.setattr(wsr, "_load_live_metadata", AsyncMock(side_effect=FormKitStoreError("gcs 503")))
    frame = dict(_HANDSHAKE, token="good.staff.token", kit_id="k")
    ws = _ws(json.dumps(frame))
    _run(ws)
    assert not _closes(ws, 1008)
    assert _closes(ws, 1013) and _closes(ws, 1013)[0].kwargs.get("reason") == "kit_unavailable"
    wsr._handle_fill_session.assert_not_awaited()


# --- frame cap ------------------------------------------------------------------------

def test_the_frame_cap_counts_utf8_bytes_not_code_points(monkeypatch):
    """Under the cap by characters, over it by bytes (a translated handshake
    is up to ~3x its code points in UTF-8). Mutation: len(text) -- red."""
    monkeypatch.setattr(wsr.settings, "WS_MAX_TEXT_FRAME_BYTES", 450, raising=False)
    frame = dict(_HANDSHAKE, token="good.staff.token", padding="\u4e2d" * 120)  # 120 chars, 360 bytes
    text = json.dumps(frame, ensure_ascii=False)
    assert len(text) < 450 < len(text.encode("utf-8"))
    ws = _ws(text)
    _run(ws)
    assert _closes(ws, 1009)


def test_an_oversized_first_frame_closes_1009(monkeypatch):
    monkeypatch.setattr(wsr.settings, "WS_MAX_TEXT_FRAME_BYTES", 100, raising=False)
    frame = dict(_HANDSHAKE, token="good.staff.token", padding="x" * 200)
    ws = _ws(json.dumps(frame))
    _run(ws)
    assert _closes(ws, 1009)
    wsr._handle_fill_session.assert_not_awaited()


# --- the dev sockets --------------------------------------------------------------------

@pytest.mark.parametrize("route", [wsr.ws_echo, wsr.ws_audio])
def test_the_dev_sockets_refuse_before_accept_on_cloud_run_even_with_the_marker(route, monkeypatch):
    monkeypatch.setattr(wsr, "DEV_LOGGING_ENABLED", True)
    monkeypatch.setenv("K_SERVICE", "polyglot-backend")
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    asyncio.run(route(ws))
    ws.accept.assert_not_awaited()
    assert _closes(ws, 1008)
