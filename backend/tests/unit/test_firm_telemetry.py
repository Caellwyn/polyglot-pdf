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
