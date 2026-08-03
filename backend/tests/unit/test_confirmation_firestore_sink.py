"""Durable Firestore mirror for the confirmation audit trail (bd polyglot-pdf-z2is).

Cloud Run's filesystem is ephemeral tmpfs, so the file-only confirmation trail
did not survive production. When CONFIRMATION_FIRESTORE_ENABLED=true every
event is mirrored to the `confirmation_events` collection via a fire-and-forget
background writer. These tests pin:
- events land in Firestore with EXACTLY the metadata keys (allowlist -- never a
  value field);
- the sink is inert when disabled;
- a Firestore failure is logged loudly and never raised into the caller;
- CONFIRMATION_RETENTION_DAYS stamps expire_at (TTL feed);
- read_confirmation_log prefers Firestore (sorted) and falls back to the file.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

import backend.utils.confirmation_logger as cl


class _FakeQuery:
    def __init__(self, docs):
        self._docs = docs

    def stream(self):
        for d in self._docs:
            m = MagicMock()
            m.to_dict.return_value = d
            yield m


class _FakeCollection:
    def __init__(self):
        self.added = []
        self.query_docs = []

    def add(self, doc):
        self.added.append(doc)
        return (None, None)

    def where(self, *args, **kwargs):
        return _FakeQuery(self.query_docs)


class _FakeDB:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        return self.collections.setdefault(name, _FakeCollection())


@pytest.fixture(autouse=True)
def _fresh_sink():
    """Each test starts and ends with no live background writer."""
    cl.flush_confirmation_sink()
    yield
    cl.flush_confirmation_sink()


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDB()
    monkeypatch.setenv("CONFIRMATION_FIRESTORE_ENABLED", "true")
    monkeypatch.setattr("backend.services.auth.get_db", lambda: db)
    return db


def test_confirmation_event_mirrors_to_firestore(fake_db):
    cl.log_field_confirmation(
        form_id="I-90",
        form_session_id="fss_test_1",
        field_id="p1_line1_aliennumber",
        field_name=None,
        confirmation_method="verbal",
    )
    cl.flush_confirmation_sink()  # drain the background writer

    added = fake_db.collections[cl._FIRESTORE_COLLECTION].added
    assert len(added) == 1
    doc = added[0]
    # ALLOWLIST: exactly these keys, nothing else -- a `value` key appearing
    # here would be a PII regression (pin-with-allowlist, never a blacklist).
    assert set(doc) == {
        "timestamp",
        "event",
        "form_id",
        "form_session_id",
        "field_id",
        "field_name",
        "confirmation_method",
    }
    assert doc["event"] == "field_confirmed"
    assert doc["form_session_id"] == "fss_test_1"
    assert doc["confirmation_method"] == "verbal"


def test_session_lifecycle_events_mirror_too(fake_db):
    cl.log_form_session_start(form_id="I-90", form_session_id="fss_test_2")
    cl.log_form_session_end(
        form_id="I-90",
        form_session_id="fss_test_2",
        completion_status="completed",
        total_fields_confirmed=3,
    )
    cl.flush_confirmation_sink()

    added = fake_db.collections[cl._FIRESTORE_COLLECTION].added
    assert [d["event"] for d in added] == [
        "form_session_started",
        "form_session_ended",
    ]
    assert added[1]["total_fields_confirmed"] == 3


def test_sink_is_inert_when_disabled(monkeypatch):
    monkeypatch.delenv("CONFIRMATION_FIRESTORE_ENABLED", raising=False)

    def _explode():
        raise AssertionError("get_db must not be called when the sink is off")

    monkeypatch.setattr("backend.services.auth.get_db", _explode)
    cl.log_field_confirmation(
        form_id="I-90",
        form_session_id="fss_test_3",
        field_id="f1",
        field_name=None,
        confirmation_method="manual",
    )
    cl.flush_confirmation_sink()  # would surface the AssertionError if queued


def test_firestore_failure_is_loud_but_never_raises(monkeypatch):
    monkeypatch.setenv("CONFIRMATION_FIRESTORE_ENABLED", "true")

    def _broken():
        raise RuntimeError("firestore down")

    monkeypatch.setattr("backend.services.auth.get_db", _broken)
    mock_log = MagicMock()
    monkeypatch.setattr(cl, "_log", mock_log)

    cl.log_field_confirmation(
        form_id="I-90",
        form_session_id="fss_test_4",
        field_id="f1",
        field_name=None,
        confirmation_method="verbal",
    )
    cl.flush_confirmation_sink()  # must not raise

    error_events = [c.args[0] for c in mock_log.error.call_args_list]
    assert "confirmation_firestore_write_failed" in error_events


def test_retention_days_stamps_expire_at(fake_db, monkeypatch):
    monkeypatch.setenv("CONFIRMATION_RETENTION_DAYS", "90")
    cl.log_field_confirmation(
        form_id="I-90",
        form_session_id="fss_test_5",
        field_id="f1",
        field_name=None,
        confirmation_method="verbal",
    )
    cl.flush_confirmation_sink()

    doc = fake_db.collections[cl._FIRESTORE_COLLECTION].added[0]
    assert "expire_at" in doc
    expected = datetime.now(timezone.utc) + timedelta(days=90)
    assert abs((doc["expire_at"] - expected).total_seconds()) < 60


def test_read_prefers_firestore_and_sorts_by_timestamp(fake_db):
    coll = fake_db.collection(cl._FIRESTORE_COLLECTION)
    coll.query_docs = [
        {"event": "b", "form_session_id": "fss_r", "timestamp": "2026-08-03T02:00:00"},
        {"event": "a", "form_session_id": "fss_r", "timestamp": "2026-08-03T01:00:00"},
    ]
    events = cl.read_confirmation_log("fss_r")
    assert [e["event"] for e in events] == ["a", "b"]


def test_read_falls_back_to_file_when_firestore_empty(fake_db, tmp_path, monkeypatch):
    # Firestore query returns nothing; the local JSONL (written by the same
    # call) must still be readable -- dev-mode behavior preserved.
    monkeypatch.setenv("CONFIRMATION_LOG_DIR", str(tmp_path / "conf"))
    cl.log_field_confirmation(
        form_id="I-90",
        form_session_id="fss_test_6",
        field_id="f1",
        field_name=None,
        confirmation_method="verbal",
    )
    cl.flush_confirmation_sink()
    events = cl.read_confirmation_log("fss_test_6")
    assert len(events) == 1
    assert events[0]["event"] == "field_confirmed"
