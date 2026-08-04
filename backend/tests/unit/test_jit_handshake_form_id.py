"""form_id must survive the manifest-first (JIT) handshake (bd polyglot-pdf-n0em).

FOUND IN PRODUCTION: the first real deployed W-7 voice run wrote 31
`field_confirmed` events to the durable Firestore sink, every one carrying
`form_id="unknown"` instead of "W-7". The confirmation trail exists for
liability protection, and a record that cannot name the form is materially
weaker evidence -- field ids alone do not identify the form to a third party,
and cross-form field-id collisions grow with the kit catalogue.

Root cause: `FormFillingService.start_session` derives
`form_id = schema["form_metadata"]["form_number"]`, but on the manifest-first
transport (the SHIPPED DEFAULT -- USE_DTI/CONTINUOUS_SESSION default true) the
handshake carries a manifest + first_field_schema, NOT the full schema, so
`form_metadata` was absent and the "unknown" fallback fired.

These tests drive the REAL `/ws/fill` route over a TestClient websocket and
assert the id that actually reaches the CallbackHandler -- the object that
writes the audit record. An earlier cut of this module tested a local
REPRODUCTION of the route's schema construction instead; an Opus review proved
that vacuous by reverting the route and watching 6 of 7 tests still pass, and
then defeated the accompanying `inspect.getsource` guard with a realistic
one-token mutation (`if jit_form_title or jit_form_number:` -> `if
jit_form_title:`) that left both guarded substrings intact. Route-level
assertions are the only ones that actually pin this.

No real Gemini call is reached: `start_session` only registers callbacks on the
injected adapter (same property `TestLiveHandshakeFlow` in
backend/tests/contract/test_websocket_protocol.py relies on).

ASCII only (CLAUDE.md scar #6).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.form_filling_service import FormFillingService


@pytest.fixture
def ws_client() -> TestClient:
    return TestClient(app)


def _jit_handshake(**overrides) -> dict:
    """A minimal valid manifest-first handshake; override per test."""
    handshake = {
        "type": "handshake_jit",
        "manifest": {
            "current_section": {
                "section_id": "s1",
                "fields": [{"id": "name", "name": "Full Name", "type": "text"}],
            },
            "previous_sections": [],
            "parts": [],
        },
        "first_field_schema": {"id": "name", "name": "Full Name", "type": "text"},
        "loaded_field_ids": [],
        "form_title": "Application for IRS Individual Taxpayer Identification Number",
        "form_number": "W-7",
        "current_values": {},
    }
    handshake.update(overrides)
    return handshake


def _run_handshakes(ws_client: TestClient, handshakes: list[dict]) -> list[str]:
    """Drive the real route once per handshake; return each session's form_id.

    Spies on start_session so the assertion reads the id the CallbackHandler was
    actually constructed with -- the value `log_field_confirmation` writes into
    the audit record -- rather than re-deriving it in the test.
    """
    captured: list[str] = []
    real_start = FormFillingService.start_session

    async def spy(self, *args, **kwargs):
        result = await real_start(self, *args, **kwargs)
        handler = getattr(self, "_callback_handler", None)
        captured.append(getattr(handler, "_form_id", None))
        return result

    with patch("backend.routes.websocket_routes.verify_token",
               return_value={"uid": "test_user"}), \
         patch.object(FormFillingService, "start_session", spy):
        for handshake in handshakes:
            with ws_client.websocket_connect("/ws/fill?token=test-token") as ws:
                ws.send_json(handshake)
                response = ws.receive_json()
                assert response["type"] == "session_ready", response
    return captured


def test_jit_session_logs_the_real_form_id(ws_client):
    """The regression: a W-7 session must reach the audit trail as 'W-7'."""
    assert _run_handshakes(ws_client, [_jit_handshake()]) == ["W-7"]


def test_form_number_only_handshake_still_yields_real_form_id(ws_client):
    """A title-less-but-numbered handshake must NOT lose the id.

    This is the case the pre-fix code broke by keying form_metadata construction
    on the title alone -- and the exact mutation that defeated the earlier
    source-substring guard. Asserted through the route, so the `or` condition is
    genuinely pinned.
    """
    handshake = _jit_handshake()
    handshake.pop("form_title")
    assert _run_handshakes(ws_client, [handshake]) == ["W-7"]


def test_form_id_survives_reconnect_and_section_switch(ws_client):
    """One form-session spanning SEVERAL Gemini sessions keeps the real id.

    The production run that surfaced this bug reconnected mid-form (Gemini's
    ~10-minute session cap), so one form_session_id spanned three Gemini
    sessions -- each re-handshaking and re-deriving form_id. A fix that only
    worked on the FIRST connect would still poison most of the trail. Three real
    round-trips: cold connect, resume, then a section-switch-shaped resume.
    """
    fss = "fss_reconnect_test"
    handshakes = [
        _jit_handshake(form_session_id=fss),
        _jit_handshake(form_session_id=fss, resume=True,
                       current_values={"name": "Linh"}),
        _jit_handshake(form_session_id=fss, resume=True, section_id="s2"),
    ]
    assert _run_handshakes(ws_client, handshakes) == ["W-7", "W-7", "W-7"]


def test_older_client_without_form_number_degrades_to_unknown(ws_client):
    """A deployed client predating the fix must still connect.

    Clients update independently of the backend, so the pre-fix handshake shape
    has to keep working -- degrading to the old 'unknown' audit value rather
    than erroring.
    """
    handshake = _jit_handshake()
    handshake.pop("form_number")
    assert _run_handshakes(ws_client, [handshake]) == ["unknown"]
