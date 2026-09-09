"""Integration-style tests for WebSocket `/ws/fill` handshake logic."""

from __future__ import annotations

import json

from backend.services.link_spend import (
    LinkBudgetExhausted as _LinkBudgetExhausted,
)
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocket

from backend.routes.websocket_routes import fill_form_from_schema


def _stub_link_gates(monkeypatch, opened_at=None):
    """Clear the two STORE gates the socket runs before the check under test.

    The socket's client-link path REDEEMS (link_redemptions.open_link) and,
    since Epic 2 bead A3, also requires a MINT RECORD
    (links_store.get_link). Both fail closed when unstubbed, which is the
    correct behaviour and is pinned separately -- but a test aiming at a
    LATER gate (the kit mismatch, the spend ceiling, the completion window)
    must clear them first or it passes for the wrong reason.

    One helper rather than an inline stub per test: A3 added a second gate,
    and eight hand-written copies of "clear the gates" is eight places for
    the next one to be forgotten in.
    """
    import time as _clock

    from backend.services import links_store

    stamp = opened_at if opened_at is not None else int(_clock.time())
    monkeypatch.setattr(
        "backend.services.link_redemptions.open_link",
        lambda jti, firm_id, kit_id, now=None: dict(
            jti=jti, firm_id=firm_id, kit_id=kit_id,
            opened_at=stamp, completed_at=None,
        ),
    )
    monkeypatch.setattr(
        links_store, "get_link",
        lambda jti, channel=None: dict(jti=jti,
                                       status=links_store.STATUS_MINTED),
    )


@pytest.fixture
def mock_websocket():
    """Provide a WebSocket double with the methods used by the handler."""
    ws = MagicMock(spec=WebSocket)
    ws.accept = AsyncMock()
    ws.receive_text = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.fixture
def mock_service():
    """Service dependency injected via Depends in production."""
    return MagicMock(name="form_filling_service")


@pytest.fixture
def handshake_message():
    return {
        "type": "handshake",
        "schema": {
            "source": "web",
            "form_metadata": {"title": "Contact Form", "url": "https://example.com"},
            "fields": [
                {"id": "email", "name": "Email", "type": "email", "required": True},
                {"id": "name", "name": "Full Name", "type": "text", "required": True},
            ],
        },
        "current_values": {}
    }


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes.verify_token")
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_handshake_sends_session_ready(mock_fill_session, mock_verify_token, mock_websocket, mock_service, handshake_message):
    """Happy-path handshake should acknowledge and invoke the fill session helper."""
    mock_websocket.receive_text.return_value = json.dumps(handshake_message)

    await fill_form_from_schema(mock_websocket, service=mock_service, token="test-token")

    # Validate session_ready payload
    mock_websocket.send_json.assert_awaited()
    payloads = [args.args[0] for args in mock_websocket.send_json.await_args_list]
    session_ready = next((p for p in payloads if p.get("type") == "session_ready"), None)
    assert session_ready is not None
    assert session_ready["ephemeral"] is True
    assert session_ready["session_id"].startswith("web_")
    # bd polyglot-pdf-v1m8g: session_ready no longer advertises a VAD mode --
    # push-to-talk is the only input mode, so there is nothing for the frontend to
    # match against. The key must be ABSENT, not false: a false would still read
    # as "a mode was negotiated" to a client that checks for presence.
    assert "native_vad" not in session_ready

    # Ensure helper is invoked with parsed handshake data
    mock_fill_session.assert_awaited_once()
    helper_args, helper_kwargs = mock_fill_session.await_args
    assert helper_args[0] is mock_websocket
    assert helper_args[2] is mock_service
    assert helper_kwargs["schema"] == handshake_message["schema"]
    assert helper_kwargs["current_values"] == handshake_message["current_values"]




@pytest.mark.asyncio
@patch("backend.routes.websocket_routes.verify_token")
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_handshake_passes_reconnect_values(mock_fill_session, mock_verify_token, mock_websocket, mock_service, handshake_message):
    reconnect = handshake_message | {
        "current_values": {
            "email": {"value": "reconnect@example.com", "confirmed": True}
        }
    }
    mock_websocket.receive_text.return_value = json.dumps(reconnect)

    await fill_form_from_schema(mock_websocket, service=mock_service, token="test-token")

    mock_fill_session.assert_awaited_once()
    _, helper_kwargs = mock_fill_session.await_args
    assert helper_kwargs["current_values"]["email"]["value"] == "reconnect@example.com"
    assert helper_kwargs["current_values"]["email"]["confirmed"] is True


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes.verify_token")
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_missing_schema_returns_error(mock_fill_session, mock_verify_token, mock_websocket, mock_service):
    mock_websocket.receive_text.return_value = json.dumps({"type": "handshake"})

    await fill_form_from_schema(mock_websocket, service=mock_service, token="test-token")

    mock_fill_session.assert_not_called()
    mock_websocket.send_json.assert_awaited()
    error_payload = mock_websocket.send_json.await_args_list[0].args[0]
    assert error_payload["type"] == "error"
    assert error_payload["code"] == "invalid_schema"
    mock_websocket.close.assert_awaited()


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes.verify_token")
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_missing_current_values_defaults_to_empty(mock_fill_session, mock_verify_token, mock_websocket, mock_service, handshake_message):
    handshake = dict(handshake_message)
    handshake.pop("current_values", None)
    mock_websocket.receive_text.return_value = json.dumps(handshake)

    await fill_form_from_schema(mock_websocket, service=mock_service, token="test-token")

    _, helper_kwargs = mock_fill_session.await_args
    assert helper_kwargs["current_values"] == {}



# --- firm identity from the TOKEN, not the handshake (bd polyglot-pdf-xwlt) ---


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes.verify_token")
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_firm_id_comes_from_the_verified_token_claim(
    mock_fill_session, mock_verify_token, mock_websocket, mock_service, handshake_message
):
    """The firm_id custom claim on the verified token reaches the session.

    Before bd xwlt the WS gate CALLED verify_token and threw the decoded
    claims away, so the voice path could not see firm identity at all.
    Mutation: revert `claims = verify_token(token)` to a bare call, or drop
    firm_id from the _handle_fill_session kwargs -- red.
    """
    mock_verify_token.return_value = {"uid": "staff-a", "firm_id": "firm-a"}
    mock_websocket.receive_text.return_value = json.dumps(handshake_message)

    await fill_form_from_schema(mock_websocket, service=mock_service, token="tok")

    assert mock_fill_session.await_args.kwargs["firm_id"] == "firm-a"


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes.verify_token")
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_a_handshake_supplied_firm_id_is_IGNORED(
    mock_fill_session, mock_verify_token, mock_websocket, mock_service, handshake_message
):
    """A firm id a CLIENT can type is not an identity.

    The handshake is client-controlled, so a firm_id there must never become
    the telemetry key -- otherwise any signed-in user could bill their usage
    to another firm (or hide their own). Mutation: read firm_id from the
    handshake instead of the claims -- red.
    """
    mock_verify_token.return_value = {"uid": "legacy-user"}  # NO firm claim
    spoofed = dict(handshake_message, firm_id="firm-victim")
    mock_websocket.receive_text.return_value = json.dumps(spoofed)

    await fill_form_from_schema(mock_websocket, service=mock_service, token="tok")

    assert mock_fill_session.await_args.kwargs["firm_id"] is None


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes.verify_token")
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_a_session_with_no_firm_claim_still_runs(
    mock_fill_session, mock_verify_token, mock_websocket, mock_service, handshake_message
):
    """A caller who CLEARED verify_token but carries no firm_id runs with
    firm_id None -- the dev-bypass stub, and a dev-claim account.

    SUPERSEDED IN PART by bd polyglot-pdf-hn0jq. This began as bd
    polyglot-pdf-xwlt's EXIT CRITERION 2 ("a legacy authed user connects
    unchanged"), and its mutation note read "require a firm claim to proceed --
    red". Enrolment IS now required: verify_token refuses an account carrying
    neither firm_id nor the dev claim ("2 separate auth lists", maintainer
    2026-08-22).

    What this route must still do is the part that survives: not INVENT a firm
    for a caller who has none. The enrolment gate lives in verify_token and is
    pinned in test_editor_identity.py; this test mocks verify_token, so it
    covers the route's handling, not the gate.
    """
    mock_verify_token.return_value = {"uid": "dev_user", "email": "dev@example.com",
                                      "vff_dev": True}
    mock_websocket.receive_text.return_value = json.dumps(handshake_message)

    await fill_form_from_schema(mock_websocket, service=mock_service, token="tok")

    mock_fill_session.assert_awaited()
    assert mock_fill_session.await_args.kwargs["firm_id"] is None


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_a_client_link_CANNOT_fill_a_form_it_does_not_name(
    mock_fill_session, mock_websocket, mock_service, handshake_message, monkeypatch
):
    """A LINK NAMES ONE FORM (bd polyglot-pdf-ugm6).

    The handshake is client-controlled, so a link holder who edits `kit_id`
    could otherwise fill a DIFFERENT form of the same firm -- one they were
    never sent -- and produce a confirmation record naming it. The token's
    kit_id wins, and a mismatch is REFUSED rather than silently substituted:
    quietly swapping the form would mean the record names a form the client
    never saw.

    Found unpinned by mutation: disabling the mismatch check left every other
    test in this bead green.
    """
    monkeypatch.setenv("LINK_TOKEN_SECRET", "w" * 40)
    from backend.services.link_tokens import mint_link_token

    token, _jti = mint_link_token("firm-a", "i-90", "u-emp-7")
    # Stub the store so this test proves the KIT MISMATCH refusal specifically,
    # not an unstubbed-store fail-closed that would pass for the wrong reason.
    import time as _t
    _stub_link_gates(monkeypatch)
    hostile = dict(handshake_message)
    hostile["kit_id"] = "n-400"          # NOT the form the link names
    mock_websocket.receive_text.return_value = json.dumps(hostile)

    await fill_form_from_schema(mock_websocket, service=mock_service, token=token)

    mock_websocket.close.assert_awaited()
    assert mock_websocket.close.await_args.kwargs.get("code") == 1008
    mock_fill_session.assert_not_awaited()


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_a_client_link_session_carries_the_links_firm_and_form(
    mock_fill_session, mock_websocket, mock_service, handshake_message, monkeypatch
):
    """The telemetry requirement for a CLIENT session: firm + form come from
    the signed link, with no account anywhere in the picture. The matching
    handshake kit_id is accepted."""
    monkeypatch.setenv("LINK_TOKEN_SECRET", "w" * 40)
    from backend.services.link_tokens import mint_link_token

    token, _jti = mint_link_token("firm-a", "i-90", "u-emp-7")
    # The socket REDEEMS the link (not just verifies the signature), so a
    # session test must supply the redemption store -- an unstubbed store
    # fails closed, which is the correct behavior and is pinned separately
    # below.
    import time as _t
    _stub_link_gates(monkeypatch)
    ok = dict(handshake_message)
    ok["kit_id"] = "i-90"
    mock_websocket.receive_text.return_value = json.dumps(ok)

    await fill_form_from_schema(mock_websocket, service=mock_service, token=token)

    mock_fill_session.assert_awaited()
    kwargs = mock_fill_session.await_args.kwargs
    assert kwargs.get("firm_id") == "firm-a"
    # THE CLAIMS -> TELEMETRY WIRING, at the REAL entry point. Asserting only
    # firm_id left the jti/employee extraction unpinned: replacing both with
    # literal None passed 104 tests (Opus cross-surface r5), which silently
    # kills THREE guarantees at once -- the split-key join (link_jti on every
    # record), the originating-employee requirement, and link burning (the
    # completion guard is `if session_completed and link_jti`, so a None jti
    # means no link is ever used up).
    #
    # The earlier test for this lives in test_proactive_complete_events and
    # INJECTS link_jti as a parameter, so it proves _handle_fill_session
    # forwards what it is handed -- one layer above the extraction, and blind
    # to whether fill_form_from_schema ever hands it over. Same
    # one-layer-removed shape this bead has now hit six times.
    # THE FORM, which this test's own title and docstring promise and which
    # it did not check (Opus r10). The token's kit is authoritative: with the
    # substitution deleted, a client-link session runs kit_id=None and every
    # audit record names no form.
    assert kwargs.get("kit_id") == "i-90"
    assert kwargs.get("link_jti") == _jti
    assert kwargs.get("link_employee_id") == "u-emp-7"


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_a_link_at_its_SPEND_CEILING_is_refused_a_new_voice_session(
    mock_fill_session, mock_websocket, mock_service, handshake_message, monkeypatch
):
    """THE CEILING ACTUALLY STOPS A SESSION (bd polyglot-pdf-ik7e).

    Refused BEFORE any Gemini session exists -- the point is to refuse the
    session, not to discover afterwards that it should have been refused.

    And refused with 1013 + `budget_exhausted`, deliberately NOT the 1008
    "Authentication failed" the other refusals use: a client who used their
    allowance has a perfectly good link, and telling them authentication
    failed sends them to the firm with the wrong problem.
    """
    monkeypatch.setenv("LINK_TOKEN_SECRET", "w" * 40)
    from backend.services.link_tokens import mint_link_token

    token, _jti = mint_link_token("firm-a", "i-90", "u-emp-7")
    import time as _t
    _stub_link_gates(monkeypatch)
    # This link has already spent its whole ceiling.
    monkeypatch.setattr(
        "backend.routes.websocket_routes.check_budget",
        lambda jti, *a, **k: (_ for _ in ()).throw(
            _LinkBudgetExhausted("spent 10.0000 of its 10.00 ceiling")
        ),
    )
    mock_websocket.receive_text.return_value = json.dumps(handshake_message)

    await fill_form_from_schema(mock_websocket, service=mock_service, token=token)

    mock_fill_session.assert_not_awaited()          # no paid session started
    mock_websocket.close.assert_awaited()
    kwargs = mock_websocket.close.await_args.kwargs
    assert kwargs.get("code") == 1013, "a spent link is not an auth failure"
    assert kwargs.get("reason") == "budget_exhausted"


@pytest.mark.asyncio
async def test_a_finished_session_BANKS_its_spend_against_the_link(monkeypatch):
    """The gate is useless unless spend is actually RECORDED.

    Without banking, every link sits at $0 forever and the ceiling never fires
    -- while both refusal tests stay green, because they stub check_budget and
    never reach a teardown. That is the one-layer-removed trap this project has
    paid for repeatedly.

    Tests the extracted helper rather than driving the whole receive loop; the
    test below pins that the teardown actually CALLS it, which is the other
    half of the same guarantee.
    """
    from backend.routes import websocket_routes as wr

    banked = []
    monkeypatch.setattr(wr, "record_spend",
                        lambda j, cost, *a, **k: banked.append((j, cost)))

    class _AI:
        def session_cost_usd(self):
            return 1.75

    class _Svc:
        live_ai = _AI()

    got = await wr._bank_link_spend("jti-under-test", _Svc(), wr._log)

    assert banked, "the session's cost never reached the spend store"
    assert banked[0] == ("jti-under-test", pytest.approx(1.75))
    assert got == pytest.approx(1.75)


@pytest.mark.asyncio
async def test_a_STAFF_session_banks_nothing(monkeypatch):
    """No jti, no link, nothing to bank. Staff are not the abuse surface."""
    from backend.routes import websocket_routes as wr

    banked = []
    monkeypatch.setattr(wr, "record_spend",
                        lambda j, cost, *a, **k: banked.append((j, cost)))

    class _AI:
        def session_cost_usd(self):
            return 9.99

    class _Svc:
        live_ai = _AI()

    assert await wr._bank_link_spend(None, _Svc(), wr._log) == 0.0
    assert banked == []


@pytest.mark.asyncio
async def test_a_broken_adapter_does_not_break_the_TEARDOWN(monkeypatch):
    """Accounting must never take down a session teardown."""
    from backend.routes import websocket_routes as wr

    class _AI:
        def session_cost_usd(self):
            raise RuntimeError("adapter exploded")

    class _Svc:
        live_ai = _AI()

    assert await wr._bank_link_spend("jti-a", _Svc(), wr._log) == 0.0


def test_the_TEARDOWN_actually_calls_the_banking_helper():
    """Pins the WIRING, not just the helper.

    A perfectly-tested helper nobody calls banks nothing. Derived from the
    shipped source so deleting the call reddens here.
    """
    from pathlib import Path as _P

    src = _P(__file__).resolve().parents[2] / "routes" / "websocket_routes.py"
    body = src.read_text(encoding="utf-8")
    assert "await _bank_link_spend(link_jti, service, log)" in body, (
        "the teardown no longer banks link spend -- every ceiling would sit "
        "at $0 forever and never fire"
    )
    # ...and it must run BEFORE end_session finalises the adapter.
    assert body.index("await _bank_link_spend(") < body.index("await service.end_session()")


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_a_link_WITH_headroom_still_connects_normally(
    mock_fill_session, mock_websocket, mock_service, handshake_message, monkeypatch
):
    """The other half: the gate must not refuse a client who has room.

    Without this, a gate that refused EVERYTHING would pass the test above.
    """
    monkeypatch.setenv("LINK_TOKEN_SECRET", "w" * 40)
    from backend.services.link_tokens import mint_link_token

    token, _jti = mint_link_token("firm-a", "i-90", "u-emp-7")
    import time as _t
    _stub_link_gates(monkeypatch)
    monkeypatch.setattr(
        "backend.routes.websocket_routes.check_budget", lambda jti, *a, **k: 7.5
    )
    mock_websocket.receive_text.return_value = json.dumps(handshake_message)

    await fill_form_from_schema(mock_websocket, service=mock_service, token=token)

    mock_fill_session.assert_awaited()


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_a_COMPLETED_link_cannot_open_a_second_socket(
    mock_fill_session, mock_websocket, mock_service, handshake_message, monkeypatch
):
    """ONE COMPLETION PER LINK, ENFORCED WHERE IT MATTERS (bd
    polyglot-pdf-ugm6, fresh-eyes r1 finding 2).

    The signature check alone cannot know a link was used -- that lives in the
    redemption store. Before this, the socket only verified the signature, so
    anyone holding the raw token (a forwarded URL, a screenshot) could start
    UNLIMITED paid Gemini sessions for the full ~48h window by connecting
    directly and never calling /api/links/open. The one-time guarantee was
    enforced only on a route an attacker need not call.

    Mutation: drop the open_link call in _verify_ws_credential's caller --
    red.
    """
    monkeypatch.setenv("LINK_TOKEN_SECRET", "w" * 40)
    from backend.services.link_redemptions import LinkAlreadyUsed
    from backend.services.link_tokens import mint_link_token

    token, _jti = mint_link_token("firm-a", "i-90", "u-emp-7")

    def _already_used(jti, firm_id, kit_id, now=None):
        raise LinkAlreadyUsed("already completed")

    monkeypatch.setattr("backend.services.link_redemptions.open_link",
                        _already_used)
    ok = dict(handshake_message)
    ok["kit_id"] = "i-90"
    mock_websocket.receive_text.return_value = json.dumps(ok)

    await fill_form_from_schema(mock_websocket, service=mock_service, token=token)

    mock_websocket.close.assert_awaited()
    assert mock_websocket.close.await_args.kwargs.get("code") == 1008
    mock_fill_session.assert_not_awaited()


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_an_UNREACHABLE_redemption_store_refuses_the_socket(
    mock_fill_session, mock_websocket, mock_service, handshake_message, monkeypatch
):
    """FAIL CLOSED at the socket too. Unable to confirm a link is unredeemed
    means we must not start a paid session -- the same polarity as /open.

    Mutation: treat RedemptionUnavailable as "proceed" -- red.
    """
    monkeypatch.setenv("LINK_TOKEN_SECRET", "w" * 40)
    from backend.services.link_redemptions import RedemptionUnavailable
    from backend.services.link_tokens import mint_link_token

    token, _jti = mint_link_token("firm-a", "i-90", "u-emp-7")

    def _down(jti, firm_id, kit_id, now=None):
        raise RedemptionUnavailable("firestore down")

    monkeypatch.setattr("backend.services.link_redemptions.open_link", _down)
    ok = dict(handshake_message)
    ok["kit_id"] = "i-90"
    mock_websocket.receive_text.return_value = json.dumps(ok)

    await fill_form_from_schema(mock_websocket, service=mock_service, token=token)

    mock_websocket.close.assert_awaited()
    assert mock_websocket.close.await_args.kwargs.get("code") == 1008
    mock_fill_session.assert_not_awaited()


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_the_COMPLETION_WINDOW_is_enforced_at_the_socket(
    mock_fill_session, mock_websocket, mock_service, handshake_message, monkeypatch
):
    """verify_link_token knows only the OPEN deadline (~48h). The COMPLETION
    clock (7 days by default) starts at first open and lives in the store, so
    the socket has to check it or a link opened long ago still works. This
    test passes its own short window, so it is independent of the default.

    Mutation: drop the opened_at + cw check -- red.
    """
    monkeypatch.setenv("LINK_TOKEN_SECRET", "w" * 40)
    import time as _t

    from backend.services.link_tokens import mint_link_token

    token, _jti = mint_link_token("firm-a", "i-90", "u-emp-7",
                                  complete_window_s=3600)
    opened_long_ago = int(_t.time()) - 10_000     # past the 1h window
    _stub_link_gates(monkeypatch, opened_at=opened_long_ago)
    ok = dict(handshake_message)
    ok["kit_id"] = "i-90"
    mock_websocket.receive_text.return_value = json.dumps(ok)

    await fill_form_from_schema(mock_websocket, service=mock_service, token=token)

    mock_websocket.close.assert_awaited()
    assert mock_websocket.close.await_args.kwargs.get("code") == 1008
    mock_fill_session.assert_not_awaited()


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes.verify_token")
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_a_STAFF_session_carries_NO_link_identity(
    mock_fill_session, mock_verify_token, mock_websocket, mock_service,
    handshake_message
):
    """The other half of the wiring: a Firebase session must pass None for
    both, or a staff session would be attributed to a link that does not
    exist -- and worse, a non-None jti would make the completion guard try to
    burn one.

    Mutation: pass claims.get("jti") unconditionally (dropping the
    is_client_link check) -- red.
    """
    mock_verify_token.return_value = {
        "uid": "u-staff", "firm_id": "firm-a", "firm_role": "manager",
        # A Firebase token could carry its OWN jti claim; it must not be
        # mistaken for a link's.
        "jti": "firebase-jti", "employee_id": "not-a-link",
    }
    mock_websocket.receive_text.return_value = json.dumps(handshake_message)

    await fill_form_from_schema(mock_websocket, service=mock_service,
                                token="header.payload.signature")

    mock_fill_session.assert_awaited()
    kwargs = mock_fill_session.await_args.kwargs
    assert kwargs.get("link_jti") is None
    assert kwargs.get("link_employee_id") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("handshake_kit", [None, ""],
                         ids=["absent", "blank"])
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
async def test_the_TOKENS_kit_is_used_when_the_handshake_omits_one(
    mock_fill_session, mock_websocket, mock_service, handshake_message,
    monkeypatch, handshake_kit
):
    """The token is authoritative when the handshake carries no kit.

    `kit_id = _link_kit` exists for exactly this case, and deleting it left
    332 tests green (Opus r10): every WS link test supplies a MATCHING
    handshake kit, so the substitution the line performs was never exercised.
    The consequence is not cosmetic -- a client-link session would run with
    kit_id=None, and every session + confirmation record would name no form,
    defeating the "firm + form + originating employee" requirement for
    exactly the client whose handshake omitted it.

    Mutation: replace `kit_id = _link_kit` with `pass` -- red, both cases.
    """
    monkeypatch.setenv("LINK_TOKEN_SECRET", "w" * 40)
    import time as _t

    from backend.services.link_tokens import mint_link_token

    token, _jti = mint_link_token("firm-a", "i-90", "u-emp-7")
    _stub_link_gates(monkeypatch)
    hs = dict(handshake_message)
    if handshake_kit is None:
        hs.pop("kit_id", None)
    else:
        hs["kit_id"] = handshake_kit
    mock_websocket.receive_text.return_value = json.dumps(hs)

    await fill_form_from_schema(mock_websocket, service=mock_service, token=token)

    mock_fill_session.assert_awaited()
    assert mock_fill_session.await_args.kwargs.get("kit_id") == "i-90", (
        "the token's kit must fill in for an absent handshake kit, or the "
        "audit trail names no form"
    )


@pytest.mark.asyncio
@patch("backend.routes.websocket_routes._handle_fill_session", new_callable=AsyncMock)
@pytest.mark.parametrize("record", [None, {"jti": "x", "status": "revoked"}],
                         ids=["never-minted", "revoked"])
async def test_the_socket_refuses_a_link_with_no_usable_mint_record(
    mock_fill_session, mock_websocket, mock_service, handshake_message,
    monkeypatch, record
):
    """Epic 2 bead A3 AT THE SOCKET, not only at /api/links/open.

    The socket is the door that actually starts the paid Gemini session, so
    a mint-record gate that only guarded the HTTP open route would leave the
    expensive door open: a client whose link was revoked mid-session, or a
    pre-cutover token, could reconnect straight to the socket. This pins
    that the socket's paid gate inherits the refusal.

    It inherits it through the SHARED helper (enforce_link_redemption) and
    through LinkNotMinted subclassing RedemptionUnavailable, which the
    socket's except-tuple already names -- so the mechanism being pinned is
    that no separate wiring is needed at this call site, and that it works.

    Mutation: delete the _require_mint_record call in
    enforce_link_redemption -- red. Mutation: make LinkNotMinted subclass
    Exception directly -- red (the refusal escapes the handler).
    """
    monkeypatch.setenv("LINK_TOKEN_SECRET", "w" * 40)
    from backend.services import links_store
    from backend.services.link_tokens import mint_link_token

    token, _jti = mint_link_token("firm-a", "i-90", "u-emp-7")
    # The redemption store itself is HEALTHY and would admit this link --
    # so a pass here cannot be the unstubbed-store fail-closed passing for
    # the wrong reason.
    _stub_link_gates(monkeypatch)
    monkeypatch.setattr(links_store, "get_link",
                        lambda jti, channel=None: record)
    ok = dict(handshake_message)
    ok["kit_id"] = "i-90"
    mock_websocket.receive_text.return_value = json.dumps(ok)

    await fill_form_from_schema(mock_websocket, service=mock_service,
                                token=token)

    mock_websocket.close.assert_awaited()
    assert mock_websocket.close.await_args.kwargs.get("code") == 1008
    mock_fill_session.assert_not_awaited()
