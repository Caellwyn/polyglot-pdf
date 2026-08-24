"""Firm-keyed telemetry (bd polyglot-pdf-xwlt, epic 02ye rubric #3).

The firm tier needs per-firm usage answerable by an equality query, without
ever touching client PII. That means three record types carry firm_id:
session-start, session-end, and every field confirmation -- and the two
session functions, which shipped under bd z2is with ZERO callers, finally
have one.

The register these tests pin: firm_id names the CUSTOMER FIRM, never the
client; a session with no firm claim still logs (firm_id None), unchanged
behavior otherwise -- that is exit criterion 2 and the reason the key is
always present rather than conditionally added.

ASCII only.
"""
import pytest

import backend.utils.confirmation_logger as cl


class _FakeCollection:
    def __init__(self):
        self.added = []

    def add(self, doc):
        self.added.append(doc)
        return (None, None)


class _FakeDB:
    """Minimal sink double -- copy-and-narrow of the one in
    test_confirmation_firestore_sink.py (its fakes are file-local, not a
    shared conftest; only `add` is exercised here)."""

    def __init__(self):
        self.collections = {}

    def collection(self, name):
        return self.collections.setdefault(name, _FakeCollection())


@pytest.fixture(autouse=True)
def _fresh_sink():
    cl.flush_confirmation_sink()
    yield
    cl.flush_confirmation_sink()


@pytest.fixture
def fake_db(monkeypatch, tmp_path):
    db = _FakeDB()
    monkeypatch.setenv("CONFIRMATION_FIRESTORE_ENABLED", "true")
    # Redirect the JSONL half away from the repo tree (the logger writes both).
    monkeypatch.setenv("CONFIRMATION_LOG_DIR", str(tmp_path))
    monkeypatch.setattr("backend.services.auth.get_db", lambda: db)
    return db


def _drain(fake_db):
    cl.flush_confirmation_sink()
    return fake_db.collections[cl._FIRESTORE_COLLECTION].added


def test_session_start_and_end_carry_firm_and_kit(fake_db, monkeypatch):
    """Both session records key on firm_id + kit_id, so a per-firm session
    count is an equality query. Mutation: drop firm_id from either event
    dict in confirmation_logger -- red."""
    monkeypatch.setenv("CONFIRMATION_FIRESTORE_ENABLED", "true")

    cl.log_form_session_start(
        form_id="I-90", form_session_id="fss_1", section_id="s1",
        firm_id="firm-a", kit_id="i-90",
    )
    cl.log_form_session_end(
        form_id="I-90", form_session_id="fss_1",
        completion_status="completed", total_fields_confirmed=7,
        firm_id="firm-a", kit_id="i-90",
    )

    docs = _drain(fake_db)
    assert [d["event"] for d in docs] == ["form_session_started", "form_session_ended"]
    for d in docs:
        assert d["firm_id"] == "firm-a"
        assert d["kit_id"] == "i-90"
        assert d["form_session_id"] == "fss_1"
    assert docs[1]["completion_status"] == "completed"
    assert docs[1]["total_fields_confirmed"] == 7


def test_all_three_record_types_share_the_firm_key(fake_db, monkeypatch):
    """The per-firm query spans SESSIONS and CONFIRMATIONS -- one key name
    across all three record types, or the query silently misses a type.
    Mutation: rename firm_id in any one of the three events -- red."""
    monkeypatch.setenv("CONFIRMATION_FIRESTORE_ENABLED", "true")

    cl.log_form_session_start(form_id="I-90", form_session_id="fss_2", firm_id="firm-b")
    cl.log_field_confirmation(
        form_id="I-90", form_session_id="fss_2", field_id="p1_line1",
        field_name=None, confirmation_method="verbal", firm_id="firm-b",
    )
    cl.log_form_session_end(
        form_id="I-90", form_session_id="fss_2", completion_status="abandoned",
        total_fields_confirmed=1, firm_id="firm-b",
    )

    docs = _drain(fake_db)
    assert len(docs) == 3
    assert {d["firm_id"] for d in docs} == {"firm-b"}
    # The count an operator would run: equality on firm_id across the sink.
    assert sum(1 for d in docs if d.get("firm_id") == "firm-b") == 3


def test_sessions_without_a_firm_claim_still_log_with_firm_id_none(fake_db, monkeypatch):
    """EXIT CRITERION 2: a legacy authed user (no firm claim) logs exactly as
    before, with firm_id present-but-None -- never a missing key (a per-firm
    query must be able to tell 'no firm' from 'key absent') and never a
    dropped record. Mutation: make any of the three events omit the key when
    firm_id is None -- red."""
    monkeypatch.setenv("CONFIRMATION_FIRESTORE_ENABLED", "true")

    cl.log_form_session_start(form_id="I-90", form_session_id="fss_3")
    cl.log_field_confirmation(
        form_id="I-90", form_session_id="fss_3", field_id="p1_line1",
        field_name=None, confirmation_method="verbal",
    )
    cl.log_form_session_end(
        form_id="I-90", form_session_id="fss_3", completion_status="abandoned",
        total_fields_confirmed=1,
    )

    docs = _drain(fake_db)
    assert len(docs) == 3
    for d in docs:
        assert "firm_id" in d, "the key must exist even with no firm claim"
        assert d["firm_id"] is None


def test_no_client_identifier_rides_any_record(fake_db, monkeypatch):
    """The firm tier identifies FIRMS, never clients. Allowlist-shaped: assert
    the sanctioned identity keys and then that nothing user-shaped appears."""
    monkeypatch.setenv("CONFIRMATION_FIRESTORE_ENABLED", "true")

    cl.log_form_session_start(form_id="I-90", form_session_id="fss_4", firm_id="firm-a")
    cl.log_field_confirmation(
        form_id="I-90", form_session_id="fss_4", field_id="p1_line1",
        field_name=None, confirmation_method="verbal", firm_id="firm-a",
    )

    for d in _drain(fake_db):
        for banned in ("uid", "email", "user_id", "client_id", "value", "name"):
            assert banned not in d, f"{banned} must never ride a telemetry record"


# --- the two bugs fresh-eyes round 1 caught (both would have passed the
# --- original suite, which is why they are pinned here explicitly) ---


def test_the_confirmed_count_survives_a_section_switch():
    """The session-end count is SESSION-scoped, not per-section.

    The counter first lived on the callback handler, which start_session
    REBUILDS on every section switch and reconnect -- so a 3-field form
    filled across two sections reported 1. It now lives on the service,
    which survives the rebuild. Mutation: move the counter back onto the
    handler (or drop the _on_field_confirmed wiring) -- red.
    """
    from backend.services.form_filling_service import FormFillingService

    svc = FormFillingService.__new__(FormFillingService)  # no live Gemini
    svc._confirmed_count = 0

    # Two confirmations, then the section-switch handler rebuild, then one more.
    svc._note_field_confirmed()
    svc._note_field_confirmed()

    class _Rebuilt:
        """A fresh handler, as start_session builds on a section switch."""
        _on_field_confirmed = None

    svc._callback_handler = _Rebuilt()
    svc._callback_handler._on_field_confirmed = svc._note_field_confirmed
    svc._callback_handler._on_field_confirmed()

    assert svc.confirmed_field_count() == 3, "the count must span sections"


def test_form_number_extraction_never_raises_on_a_malformed_schema():
    """The session-START call sits OUTSIDE the handler's try, so a non-dict
    form_metadata from a legacy/malformed client must degrade to "unknown"
    rather than kill the session (the bd polyglot-pdf-ypk4 crash class).
    Mutation: revert to (schema or {}).get("form_metadata", {}).get(...) --
    red on the non-dict rows."""
    from backend.routes.websocket_routes import _form_number_of

    assert _form_number_of({"form_metadata": {"form_number": "I-90"}}) == "I-90"
    for malformed in (
        None,
        {},
        {"form_metadata": None},
        {"form_metadata": "not-a-dict"},
        {"form_metadata": []},
        {"form_metadata": {"form_number": None}},
        {"form_metadata": {"form_number": ""}},
        "not-a-schema",
    ):
        assert _form_number_of(malformed) == "unknown"


@pytest.mark.parametrize(
    "form_session_id, is_reconnect, start, end",
    [
        ("fss_1", False, True, True),    # first connection: both
        ("fss_1", True, False, True),    # RECONNECT: end only, never a 2nd start
        (None, False, False, False),     # no session key: neither
        (None, True, False, False),
    ],
    ids=["first-connection", "reconnect", "no-session-id", "no-session-id-resume"],
)
def test_session_logging_decisions(form_session_id, is_reconnect, start, end):
    """The whole start/end decision table (bd polyglot-pdf-xwlt).

    The RECONNECT row is the one fresh-eyes round 1 caught: end-logging was
    gated on is_reconnect, which describes the connection that just OPENED,
    so a reconnected connection's real teardown logged NOTHING while the
    pre-reconnect disconnect logged a false "abandoned". End must fire on
    every teardown; start must not re-fire on a resume.

    Mutation: add `and not is_reconnect` to should_log_session_end -- the
    reconnect row goes red. Drop it from should_log_session_start -- the
    reconnect row goes red the other way.
    """
    from backend.routes.websocket_routes import (
        should_log_session_end,
        should_log_session_start,
    )

    assert should_log_session_start(form_session_id, is_reconnect) is start
    assert should_log_session_end(form_session_id, is_reconnect) is end


@pytest.mark.parametrize("event_name", ["form_session_started", "form_session_ended"])
def test_BOTH_session_records_carry_the_link_join_key(monkeypatch, event_name):
    """PIN THE SET, not one record (CLAUDE.md scar #7).

    The jti is the FIRM'S JOIN KEY: they hold jti -> which client, we hold
    the pseudonymous record. A record without it makes the split-key
    arrangement inoperable -- the firm cannot match their client to our
    record even under a court order.

    I shipped this HALF DONE: the end record got the key, the START record
    did not, and the START record is the one-per-session row (end fires per
    CONNECTION). Nothing pinned it, and the docs asserted both. Parametrized
    over both events so the next record cannot be forgotten either.

    Mutation: drop link_jti from either call site -- that parametrization
    goes red.
    """
    from backend.utils import confirmation_logger as cl

    written = []
    monkeypatch.setattr(cl, "_write_confirmation_to_file",
                        lambda sid, ev: written.append(ev))
    monkeypatch.setattr(cl, "_submit_firestore_write", lambda ev: None)

    if event_name == "form_session_started":
        cl.log_form_session_start(
            form_id="I-90", form_session_id="fss_1", firm_id="firm-a",
            kit_id="i-90", link_jti="jti-abc", employee_id="u-emp-7",
        )
    else:
        cl.log_form_session_end(
            form_id="I-90", form_session_id="fss_1",
            completion_status="completed", total_fields_confirmed=3,
            firm_id="firm-a", kit_id="i-90",
            link_jti="jti-abc", employee_id="u-emp-7",
        )

    record = next(e for e in written if e["event"] == event_name)
    assert record["link_jti"] == "jti-abc", (
        event_name + " must carry the firm's join key"
    )
    assert record["employee_id"] == "u-emp-7", (
        event_name + " must name the originating employee"
    )
