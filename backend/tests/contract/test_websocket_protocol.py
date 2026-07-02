"""WebSocket protocol CONTRACT tests (bd polyglot-pdf-ceyt).

Pins the /ws/fill wire contract documented in docs/standards/ws-protocol.md
against the REAL implementation in backend/routes/websocket_routes.py (plus the
backend->frontend senders in callback_handler.py, request_coordinator.py, and
form_filling_service.py). The goal is a set of tests that FAIL the moment a wire
key or message `type` string is renamed or dropped on either side of the union --
so the future part_* -> section_* wire rename (bd polyglot-pdf-zun) is
test-driven from here rather than discovered live.

Scope note (CLAUDE.md scar #5): `part_*` keys in the handshake manifest
(`manifest.parts`) and the token-log payload are CURRENT wire format as of this
writing. These tests pin what IS -- they do not take a position on the rename.

Style: doc-vs-code string contracts (extract literals from the doc and the code,
diff the sets) are preferred over mocking the world, per uov.14's
test_tool_contracts.py precedent. One live TestClient websocket_connect flow is
included (handshake -> session_ready) since it is feasible without touching
Gemini -- start_session only registers callbacks, it does not open a live
connection (verified against the existing
backend/tests/unit/test_websocket_fill_web.py::test_websocket_schema_initializes_session
pattern, which passes with a real (non-mocked) LiveAIGemini adapter instance).

No @pytest.mark.external: no real Gemini calls anywhere in this module.

ASCII only (CLAUDE.md scar #6).
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocket
from fastapi.testclient import TestClient

from backend.main import app
from backend.routes import websocket_routes
from backend.routes.websocket_routes import _handle_fill_session, fill_form_from_schema

REPO_ROOT = Path(__file__).resolve().parents[3]
DOC_PATH = REPO_ROOT / "docs" / "standards" / "ws-protocol.md"
ROUTES_SRC = Path(inspect.getsourcefile(websocket_routes)).read_text(encoding="utf-8")

# The doc-vs-code helpers below intentionally re-derive the "ground truth" sets
# from source text rather than importing enums, because there ARE no enums --
# the wire protocol is untyped `{"type": "..."}` dicts on both sides. Reading the
# literals out of the .py source is the only way to pin what the CODE actually
# does (as opposed to what a docstring claims it does).


def _doc_text() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def _doc_table_rows(section_heading: str) -> list[str]:
    """Return the first-column cell text of every `| \\`type\\` | ... |` row in the
    markdown table that immediately follows the given `### heading` in
    ws-protocol.md, up to the next `###` heading or a blank line ending the
    table. Handles cells with `` \\`a\\` \\| \\`b\\` `` multi-value alternatives
    (e.g. `` `handshake` \\| `handshake_jit` ``) by splitting on the markdown
    `\\|` escape.
    """
    text = _doc_text()
    heading_idx = text.index(section_heading)
    tail = text[heading_idx:]
    # Stop at the next heading of the same or higher level.
    next_heading = re.search(r"\n#{1,3} ", tail[1:])
    table_block = tail[: next_heading.start() + 1] if next_heading else tail

    rows: list[str] = []
    for line in table_block.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not cells:
            continue
        first = cells[0]
        if first.startswith("Type") or first.startswith("Key") or first.startswith(
            "---"
        ) or set(first) <= {"-"}:
            continue
        if "`" not in first:
            continue
        # Split multi-value alternatives escaped as \| inside a single cell,
        # e.g. "`handshake`" or "`handshake` \\| `handshake_jit`".
        for alt in re.split(r"\\\|", first):
            m = re.findall(r"`([a-zA-Z0-9_]+)`", alt)
            rows.extend(m)
    return rows


def doc_backend_to_frontend_types() -> set[str]:
    return set(_doc_table_rows("### Backend -> frontend"))


def doc_frontend_to_backend_types() -> set[str]:
    return set(_doc_table_rows("### Frontend -> backend"))


def doc_handshake_mode_types() -> set[str]:
    # The mode-selector table's `type` row lists `handshake` and `handshake_jit`.
    return {"handshake", "handshake_jit"}


# ---------------------------------------------------------------------------
# Code-side extraction: literal `"type": "..."` sends and `mtype == "..."`
# dispatch arms, scoped to the /ws/fill route only (the /ws/echo and /ws/audio
# debug sockets, gated dev-only per test_debug_socket_gate.py, are a DIFFERENT
# protocol and must not leak into this diff).
# ---------------------------------------------------------------------------

_FILL_ROUTE_START = ROUTES_SRC.index("async def _handle_fill_session")


def _fill_route_src() -> str:
    return ROUTES_SRC[_FILL_ROUTE_START:]


def code_fill_route_send_types() -> set[str]:
    """`{"type": "..."}` literals sent from websocket_routes.py's /ws/fill code
    path (both the ack path in fill_form_from_schema and the control loop in
    _handle_fill_session)."""
    return set(re.findall(r'"type":\s*"([a-zA-Z0-9_]+)"', _fill_route_src()))


def code_fill_route_dispatch_types() -> set[str]:
    """`mtype == "..."` inbound dispatch arms in the /ws/fill control loop."""
    return set(re.findall(r'mtype == "([a-zA-Z0-9_]+)"', _fill_route_src()))


def code_service_send_types() -> set[str]:
    """`{"type": "..."}` literals sent via websocket.send_json from the service
    layer (callback_handler.py, request_coordinator.py, form_filling_service.py)
    -- the backend->frontend push/request messages that do not originate in
    websocket_routes.py itself."""
    types: set[str] = set()
    for mod in ("callback_handler.py", "request_coordinator.py", "form_filling_service.py"):
        src = (REPO_ROOT / "backend" / "services" / mod).read_text(encoding="utf-8")
        types |= set(re.findall(r'"type":\s*"([a-zA-Z0-9_]+)"', src))
    return types


# ---------------------------------------------------------------------------
# 1. Handshake shape: required/optional keys the backend reads.
# ---------------------------------------------------------------------------


class TestHandshakeShape:
    """Pins the handshake keys /ws/fill's route function actually reads via
    `handshake.get(...)`, both mode-shared and mode-specific, against the doc's
    "Current state: the /ws/fill handshake" tables."""

    def _handshake_get_keys(self) -> set[str]:
        # Only the top-level `handshake.get("...")` reads in fill_form_from_schema
        # (the route function itself) -- these are the keys the FIRST text frame
        # must carry. Excludes nested reads on `manifest`/`schema` sub-objects.
        fn_src = inspect.getsource(fill_form_from_schema)
        return set(re.findall(r'handshake\.get\(\s*"([a-zA-Z0-9_]+)"', fn_src))

    def test_shared_handshake_keys_are_read_by_the_route(self):
        """Every mode-shared key the doc documents (type, form_session_id,
        current_values, full_schema, fill_language, section_number,
        section_label, total_sections, section_id, previous_spoken_names,
        initial_field_hint, resume) is actually read via handshake.get(...)."""
        documented_shared_keys = {
            "type",
            "form_session_id",
            "current_values",
            "full_schema",
            "fill_language",
            "section_number",
            "section_label",
            "total_sections",
            "section_id",
            "previous_spoken_names",
            "initial_field_hint",
            "resume",
        }
        code_keys = self._handshake_get_keys()
        missing = documented_shared_keys - code_keys
        assert not missing, (
            f"doc documents handshake keys the route no longer reads: {missing}"
        )

    def test_legacy_mode_requires_schema_key(self):
        """type != 'handshake_jit' -> legacy mode; schema is REQUIRED (missing/
        invalid schema closes the socket with invalid_schema), per the doc's
        legacy-mode table."""
        fn_src = inspect.getsource(fill_form_from_schema)
        assert 'schema = handshake.get("schema")' in fn_src
        assert '"code": "invalid_schema"' in fn_src

    def test_jit_mode_keys_are_read(self):
        """type == 'handshake_jit' reads manifest, first_field_schema,
        loaded_field_ids, form_title (per the JIT-mode key table)."""
        fn_src = inspect.getsource(fill_form_from_schema)
        for key in ("manifest", "first_field_schema", "loaded_field_ids", "form_title"):
            assert f'handshake.get("{key}"' in fn_src, (
                f"JIT-mode key '{key}' documented in ws-protocol.md but not read "
                f"via handshake.get(...) in fill_form_from_schema"
            )

    def test_mode_selector_is_handshake_jit_string(self):
        """The mode selector is exactly the literal 'handshake_jit' -- anything
        else (including a missing type) falls back to legacy, per the doc."""
        fn_src = inspect.getsource(fill_form_from_schema)
        assert 'is_jit_mode = handshake_type == "handshake_jit"' in fn_src

    def test_source_must_be_web_or_pdf(self):
        """schema.source is validated against exactly {"web", "pdf"}."""
        fn_src = inspect.getsource(fill_form_from_schema)
        assert 'source not in ("web", "pdf")' in fn_src


class TestSessionReadyShape:
    """Pins the session_ready ack payload keys."""

    def test_session_ready_carries_documented_keys(self):
        fn_src = inspect.getsource(fill_form_from_schema)
        # The session_ready send_json call site.
        m = re.search(r'"type":\s*"session_ready".*?\}\)', fn_src, re.DOTALL)
        assert m, "session_ready send_json call not found in fill_form_from_schema"
        block = m.group(0)
        for key in ("session_id", "ephemeral", "jit_mode_enabled", "native_vad"):
            assert f'"{key}"' in block, (
                f"doc documents session_ready.{key} but it is missing from the "
                f"send_json call"
            )

    def test_session_ready_dti_mode_enabled_sent_and_documented(self):
        """session_ready carries dti_mode_enabled (websocket_routes.py, consumed
        by the frontend's handleSessionReady destructure). The key was
        sent-but-undocumented until these contract tests caught it; the
        ws-protocol.md session_ready table now lists it -- this test pins BOTH
        sides so neither can drift again (bd polyglot-pdf-ceyt)."""
        fn_src = inspect.getsource(fill_form_from_schema)
        m = re.search(r'"type":\s*"session_ready".*?\}\)', fn_src, re.DOTALL)
        assert m
        assert '"dti_mode_enabled"' in m.group(0)
        assert "`dti_mode_enabled`" in DOC_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 2. Message-type unions, both directions.
# ---------------------------------------------------------------------------


class TestBackendToFrontendUnion:
    """Every backend->frontend `type` the doc documents must have a real send
    site somewhere in the /ws/fill code path (route + service layer), and every
    type the CODE actually sends for /ws/fill must be documented -- a rename or
    drop on either side fails one of these."""

    def _all_code_send_types(self) -> set[str]:
        return code_fill_route_send_types() | code_service_send_types()

    def test_every_documented_backend_to_frontend_type_is_sent_by_code(self):
        documented = doc_backend_to_frontend_types()
        code_types = self._all_code_send_types()
        missing = documented - code_types
        assert not missing, (
            f"ws-protocol.md documents backend->frontend types with no matching "
            f"send_json(...) call found in the /ws/fill code path: {missing}"
        )

    def test_every_code_sent_type_is_documented(self):
        """The reverse direction: a NEW backend->frontend type introduced in code
        without a doc update must fail here (catches silent additions, not just
        drops/renames)."""
        documented = doc_backend_to_frontend_types()
        code_types = self._all_code_send_types()
        # dti_mode_enabled is a KEY on session_ready, not a message `type` -- not
        # applicable here. error codes are not separate `type`s (all "error").
        undocumented = code_types - documented
        assert not undocumented, (
            f"code sends backend->frontend types not documented in "
            f"ws-protocol.md: {undocumented}"
        )

    @pytest.mark.parametrize(
        "wire_type",
        sorted(doc_backend_to_frontend_types()),
    )
    def test_documented_backend_to_frontend_type_pinned(self, wire_type):
        """Per-type pin (parametrized) so a single dropped/renamed type reports
        by name in the failing test ID, rather than only inside a combined set
        diff."""
        assert wire_type in self._all_code_send_types(), (
            f"'{wire_type}' is documented in ws-protocol.md's backend->frontend "
            f"table but no send_json call for it was found"
        )


class TestFrontendToBackendUnion:
    """Same diff, inbound direction: every documented frontend->backend type has
    a dispatch arm (`mtype == "..."`) in the /ws/fill control loop, and every
    dispatch arm is documented."""

    def test_every_documented_type_has_a_dispatch_arm(self):
        documented = doc_frontend_to_backend_types() - doc_handshake_mode_types()
        code_types = code_fill_route_dispatch_types()
        missing = documented - code_types
        assert not missing, (
            f"ws-protocol.md documents frontend->backend types with no "
            f"'mtype == ...' dispatch arm in the /ws/fill control loop: {missing}"
        )

    def test_every_dispatch_arm_is_documented(self):
        documented = doc_frontend_to_backend_types() - doc_handshake_mode_types()
        code_types = code_fill_route_dispatch_types()
        undocumented = code_types - documented
        assert not undocumented, (
            f"the /ws/fill control loop dispatches on types not documented in "
            f"ws-protocol.md's frontend->backend table: {undocumented}"
        )

    @pytest.mark.parametrize(
        "wire_type",
        sorted(doc_frontend_to_backend_types() - doc_handshake_mode_types()),
    )
    def test_documented_frontend_to_backend_type_pinned(self, wire_type):
        assert wire_type in code_fill_route_dispatch_types(), (
            f"'{wire_type}' is documented in ws-protocol.md's frontend->backend "
            f"table but no 'mtype == \"{wire_type}\"' dispatch arm was found in "
            f"the /ws/fill control loop"
        )

    def test_unhandled_inbound_type_is_provably_outside_the_union(self):
        """A message type the backend does not handle at all (neither
        documented nor dispatched) must fall through to the generic
        unknown_control error arm, not silently match some other branch."""
        bogus = "totally_bogus_message_type_ceyt"
        assert bogus not in doc_frontend_to_backend_types()
        assert bogus not in code_fill_route_dispatch_types()
        assert "unknown_control" in _fill_route_src()


class TestHandshakeTypesInFrontendToBackendTable:
    """handshake / handshake_jit are documented as the FIRST message on the
    socket (not part of the post-handshake control loop dispatch), but the doc
    also lists them in the frontend->backend union table. Pin that they are at
    least present in the doc's inbound table even though they are consumed by
    fill_form_from_schema's own handshake_type read, not the mtype dispatch
    loop."""

    def test_handshake_types_present_in_doc_table(self):
        assert doc_handshake_mode_types() <= doc_frontend_to_backend_types()

    def test_handshake_types_are_the_mode_selector_in_code(self):
        fn_src = inspect.getsource(fill_form_from_schema)
        assert 'handshake.get("type", "handshake")' in fn_src
        assert '"handshake_jit"' in fn_src


# ---------------------------------------------------------------------------
# 3. Live TestClient handshake -> session_ready flow (no real Gemini).
# ---------------------------------------------------------------------------


@pytest.fixture()
def ws_client() -> TestClient:
    return TestClient(app)


class TestLiveHandshakeFlow:
    """A real ASGI websocket round-trip through /ws/fill, exercising the actual
    route + accept + first-frame parse + session_ready reply. No Gemini call is
    reached on this path: start_session only registers callbacks on the
    injected LiveAIGemini adapter (set_session_context / set_callbacks), it does
    not open a live connection -- mirrors
    test_websocket_fill_web.py::test_websocket_schema_initializes_session, which
    already passes this way without mocking the adapter."""

    @patch("backend.routes.websocket_routes.verify_token", return_value={"uid": "test_user"})
    def test_legacy_handshake_to_session_ready(self, _mock_verify, ws_client):
        handshake = {
            "type": "handshake",
            "schema": {
                "source": "web",
                "form_metadata": {"title": "Contact", "url": "https://example.com"},
                "fields": [{"id": "name", "name": "Full Name", "type": "text"}],
            },
            "current_values": {},
        }
        with ws_client.websocket_connect("/ws/fill?token=test-token") as ws:
            ws.send_json(handshake)
            response = ws.receive_json()

        assert response["type"] == "session_ready"
        assert response["session_id"].startswith("web_")
        assert response["ephemeral"] is True
        assert "jit_mode_enabled" in response
        assert "native_vad" in response
        assert "dti_mode_enabled" in response  # see the undocumented-key test above

    @patch("backend.routes.websocket_routes.verify_token", return_value={"uid": "test_user"})
    def test_jit_handshake_to_session_ready(self, _mock_verify, ws_client):
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
            "form_title": "Contact",
            "current_values": {},
        }
        with ws_client.websocket_connect("/ws/fill?token=test-token") as ws:
            ws.send_json(handshake)
            response = ws.receive_json()

        assert response["type"] == "session_ready"
        assert response["session_id"].startswith("web_")

    @patch("backend.routes.websocket_routes.verify_token", return_value={"uid": "test_user"})
    def test_missing_schema_in_legacy_mode_closes_with_invalid_schema(self, _mock_verify, ws_client):
        with ws_client.websocket_connect("/ws/fill?token=test-token") as ws:
            ws.send_json({"type": "handshake"})
            response = ws.receive_json()

        assert response["type"] == "error"
        assert response["code"] == "invalid_schema"


# ---------------------------------------------------------------------------
# 4. Control-loop dispatch: unhandled type falls outside the union (mocked
#    service, mirrors test_proactive_complete_events.py's _handle_fill_session
#    harness so no real Gemini/websocket accept is needed).
# ---------------------------------------------------------------------------


def _mock_service(verdict=None):
    svc = MagicMock(name="form_filling_service")
    svc.start_session = AsyncMock()
    svc.end_session = AsyncMock()
    svc.stream_audio = AsyncMock()
    svc.handle_validation_boundary = AsyncMock(return_value=verdict or {"conflicts": []})
    return svc


def _ws_yielding(messages: list[dict]):
    ws = MagicMock(spec=WebSocket)
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    queue = list(messages) + [{"type": "websocket.disconnect"}]
    ws.receive = AsyncMock(side_effect=queue)
    return ws


async def _run_control_loop(messages: list[dict]):
    ws = _ws_yielding(messages)
    svc = _mock_service()
    await _handle_fill_session(
        ws,
        session_id="web_test",
        service=svc,
        send_transcript=False,
        accept_connection=False,
        schema=None,
    )
    sent = [c.args[0] for c in ws.send_json.await_args_list]
    return sent


class TestControlLoopUnknownType:
    @pytest.mark.asyncio
    async def test_unhandled_type_gets_unknown_control_error(self):
        sent = await _run_control_loop(
            [{"text": json.dumps({"type": "totally_bogus_message_type_ceyt"})}]
        )
        assert {"type": "error", "code": "unknown_control"} in sent

    @pytest.mark.asyncio
    async def test_ping_gets_pong_with_echoed_ts(self):
        sent = await _run_control_loop([{"text": json.dumps({"type": "ping", "ts": 12345})}])
        assert {"type": "pong", "ts": 12345} in sent

    @pytest.mark.asyncio
    async def test_stats_gets_ok_reply(self):
        sent = await _run_control_loop([{"text": json.dumps({"type": "stats"})}])
        assert {"type": "stats", "message": "ok"} in sent
