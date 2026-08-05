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
        # The real client ALWAYS sends full_schema on both handshake shapes
        # (schemaFormState.ts:953 legacy / :1028 JIT) -- it is the secretary's
        # whole-form catalog (bd p68s). The edition marker is resolved from it,
        # so a fixture omitting it does not represent production traffic.
        "full_schema": {
            "form_metadata": {
                "title": "Application for IRS Individual Taxpayer Identification Number",
                "form_number": "W-7",
                "edition_date": "12/2024",
            },
            "fields": [
                {"id": "name", "name": "Full Name", "type": "text"},
                {"id": "reason", "type": "select",
                 "options": [{"value": "a"}, {"value": "b"}]},
            ],
        },
        "loaded_field_ids": [],
        "form_title": "Application for IRS Individual Taxpayer Identification Number",
        "form_number": "W-7",
        "kit_id": "w7",
        "edition_date": "12/2024",
        "current_values": {},
    }
    handshake.update(overrides)
    return handshake


def _with_edition(edition_date, **overrides) -> dict:
    """A handshake whose FULL SCHEMA carries the given edition (or none).

    The marker is resolved from full_schema (the whole-form catalog), never the
    per-section schema -- a section-derived fingerprint would change as the user
    moves through the form. Tests that vary the edition must therefore vary it
    here, not in the top-level handshake key.
    """
    handshake = _jit_handshake(**overrides)
    metadata = dict(handshake["full_schema"]["form_metadata"])
    if edition_date is None:
        metadata.pop("edition_date", None)
    else:
        metadata["edition_date"] = edition_date
    handshake["full_schema"] = {
        **handshake["full_schema"], "form_metadata": metadata,
    }
    handshake["edition_date"] = edition_date
    return handshake


def _run_handshakes(ws_client: TestClient, handshakes: list[dict]) -> list[str]:
    """Drive the real route once per handshake; return each session's form_id.

    Spies on start_session so the assertion reads the id the CallbackHandler was
    actually constructed with -- the value `log_field_confirmation` writes into
    the audit record -- rather than re-deriving it in the test.
    """
    return [ident["form_id"] for ident in _run_handshakes_identity(ws_client, handshakes)]


def _run_handshakes_identity(ws_client: TestClient, handshakes: list[dict]) -> list[dict]:
    """As above, but returns the FULL audit identity per session.

    bd polyglot-pdf-47r3 added kit_id + edition_date alongside form_id: a form
    NUMBER identifies neither which kit was used (two kits can share one) nor
    which government edition the client confirmed against.
    """
    captured: list[dict] = []
    real_start = FormFillingService.start_session

    async def spy(self, *args, **kwargs):
        result = await real_start(self, *args, **kwargs)
        handler = getattr(self, "_callback_handler", None)
        captured.append({
            "form_id": getattr(handler, "_form_id", None),
            "kit_id": getattr(handler, "_kit_id", None),
            "edition_date": getattr(handler, "_edition_date", None),
        })
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


def test_jit_session_records_kit_id_and_edition_date(ws_client):
    """bd polyglot-pdf-47r3: the audit identity is kit + form + EDITION.

    form_number alone identifies neither the kit (two kits can share one -- a
    standard W-7 and a firm-specific variant) nor the government edition
    (agencies revise forms and enforce edition dates). All three must reach the
    CallbackHandler, which is what writes them into the confirmation record.
    """
    identity = _run_handshakes_identity(ws_client, [_jit_handshake()])
    assert identity == [{
        "form_id": "W-7",
        "kit_id": "w7",
        "edition_date": "12/2024",
    }]


def test_kit_id_distinguishes_two_kits_sharing_a_form_number(ws_client):
    """Two kits, same form_number, different kit_id -- the collision case.

    This is the scenario form_number cannot resolve on its own and the reason
    kit_id is recorded: a firm-specific W-7 variant must be distinguishable from
    the standard one in a liability record.
    """
    standard = _jit_handshake(kit_id="w7")
    variant = _jit_handshake(kit_id="w7-acme-variant")

    identity = _run_handshakes_identity(ws_client, [standard, variant])

    assert [i["form_id"] for i in identity] == ["W-7", "W-7"]  # indistinguishable
    assert [i["kit_id"] for i in identity] == ["w7", "w7-acme-variant"]  # resolved


def test_edition_date_distinguishes_revisions_of_one_form(ws_client):
    """Same kit, different government edition -- the revision case.

    A form filled against the 12/2024 edition and one filled after a 2026
    revision must not read identically in the trail.
    """
    old = _with_edition("12/2024")
    revised = _with_edition("03/2026")

    identity = _run_handshakes_identity(ws_client, [old, revised])

    assert [i["edition_date"] for i in identity] == ["12/2024", "03/2026"]


def test_edition_date_survives_a_title_and_number_less_handshake(ws_client):
    """edition_date must reach the record even as the ONLY form_metadata key.

    The route builds form_metadata from `title or number or edition_date`. Every
    other test here sends a title, so that final `or` clause is never
    load-bearing for them -- I verified by mutation that dropping
    `or jit_edition_date` leaves them ALL green. This test is the one that
    fails, which is the point: it covers the branch, not just the happy path.
    (Same lesson as bd n0em's post-mortem -- pick the mutation that MATTERS.)
    """
    handshake = _jit_handshake()
    handshake.pop("form_title")
    handshake.pop("form_number")

    identity = _run_handshakes_identity(ws_client, [handshake])

    assert identity == [{
        "form_id": "unknown",  # no number sent -- correct fallback
        "kit_id": "w7",  # kit_id rides its own argument, not form_metadata
        "edition_date": "12/2024",  # survives as the sole form_metadata key
    }]


def test_edition_marker_is_stable_across_a_reconnect(ws_client):
    """A reconnect must not DRIFT the marker (Opus review on 47r3).

    Each (re)connect supplies full_schema and so recomputes the marker. That is
    only safe if the same full schema yields the same value -- otherwise a
    mid-form reconnect (Gemini's ~10-minute session cap makes these routine)
    would silently record two different 'revisions' for one sitting. Uses a
    FINGERPRINT kit (no government edition), which is the case that recomputes
    rather than echoing a literal date.
    """
    fss = "fss_reconnect_marker"
    handshakes = [
        _with_edition(None, form_session_id=fss),
        _with_edition(None, form_session_id=fss, resume=True),
        _with_edition(None, form_session_id=fss, resume=True),
    ]

    markers = [i["edition_date"] for i in _run_handshakes_identity(ws_client, handshakes)]

    assert all(m is not None and m.startswith("sha256:") for m in markers), markers
    assert len(set(markers)) == 1, f"marker drifted across reconnects: {markers}"


def test_older_client_still_yields_the_REAL_edition_from_full_schema(ws_client):
    """A pre-47r3 client's real edition must be USED, not discarded (bd kdrz).

    Clients update independently of the backend, so the pre-47r3 handshake shape
    -- no top-level kit_id / edition_date, but full_schema present -- keeps
    working. Crucially, that full_schema CARRIES the government edition
    ("12/2024" on the shipped W-7), so reading only the top-level key threw away
    an agency edition we had been handed and recorded a content fingerprint
    instead: strictly weaker evidence in a liability record.

    An earlier cut of this test asserted the fingerprint here and thereby PINNED
    the degradation as correct -- caught by review.

    kit_id genuinely has no server-side fallback (only the client knows which
    kit was picked), so it stays None; that half is bd polyglot-pdf-d95y.
    """
    handshake = _jit_handshake()
    handshake.pop("kit_id")
    handshake.pop("edition_date")

    identity = _run_handshakes_identity(ws_client, [handshake])

    assert len(identity) == 1
    assert identity[0]["form_id"] == "W-7"  # unchanged: n0em's fix still applies
    assert identity[0]["kit_id"] is None  # no server-side fallback exists
    assert identity[0]["edition_date"] == "12/2024"  # from full_schema, NOT a digest


def test_fingerprint_is_used_only_when_no_edition_exists_anywhere(ws_client):
    """The digest is the LAST resort, not the first (bd kdrz).

    With no edition in the handshake key AND none in full_schema -- a genuine
    custom form -- the fingerprint is correct and must still appear.
    """
    handshake = _with_edition(None)
    handshake.pop("kit_id")
    handshake.pop("edition_date")

    identity = _run_handshakes_identity(ws_client, [handshake])

    assert identity[0]["edition_date"].startswith("sha256:")


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
    """EVERY connect in a form-session derives the real id, not just the first.

    The production run that surfaced this bug reconnected mid-form (Gemini's
    ~10-minute session cap), so one form_session_id spanned three Gemini
    sessions -- each re-handshaking and re-deriving form_id. A fix that only
    worked on the FIRST connect would still poison most of the trail.

    SCOPE, stated precisely: the backend is stateless by design (CLAUDE.md scar
    #4), and `form_session_id` is only ever threaded (log binding, start_session,
    CallbackHandler, token-log context) -- nothing keys, caches, or branches on
    it, and `resume`/`section_id` only pick a greeting template and a log field.
    So these three round-trips are three INDEPENDENT sessions carrying the same
    string: the test pins PER-CONNECT derivation, which is the real risk here,
    NOT cross-connect state (of which the backend has none to break). If
    reconnect logic ever gains server-side state, this test does not cover it.
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
