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


class _FakeDocRef:
    def __init__(self):
        self.set_calls = []
        self.delete_calls = 0

    def set(self, doc):
        self.set_calls.append(doc)

    def delete(self):
        self.delete_calls += 1


class _FakeCollection:
    def __init__(self):
        self.added = []
        self.query_docs = []
        self.doc_refs = {}

    def add(self, doc):
        self.added.append(doc)
        return (None, None)

    def document(self, doc_id):
        return self.doc_refs.setdefault(doc_id, _FakeDocRef())

    def where(self, *args, **kwargs):
        return _FakeQuery(self.query_docs)


class _FakeDB:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        return self.collections.setdefault(name, _FakeCollection())


@pytest.fixture(autouse=True)
def _fresh_sink():
    """Each test starts and ends with no live background writer or probe cache."""
    cl.flush_confirmation_sink()
    cl._probe_cache = None
    yield
    cl.flush_confirmation_sink()
    cl._probe_cache = None


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
        kit_id="i-90",
        edition_date="01/20/25",
    )
    cl.flush_confirmation_sink()  # drain the background writer

    added = fake_db.collections[cl._FIRESTORE_COLLECTION].added
    assert len(added) == 1
    doc = added[0]
    # ALLOWLIST: exactly these keys, nothing else -- a `value` key appearing
    # here would be a PII regression (pin-with-allowlist, never a blacklist).
    # kit_id + edition_date joined under bd polyglot-pdf-47r3: both are form
    # METADATA (which kit, which government edition), never user data.
    assert set(doc) == {
        "timestamp",
        "event",
        "form_id",
        "kit_id",
        "edition_date",
        "form_session_id",
        "field_id",
        "field_name",
        "confirmation_method",
    }
    assert doc["event"] == "field_confirmed"
    assert doc["form_session_id"] == "fss_test_1"
    assert doc["confirmation_method"] == "verbal"
    assert doc["kit_id"] == "i-90"
    assert doc["edition_date"] == "01/20/25"


def test_confirmation_event_keys_present_even_when_unset(fake_db):
    """An older client omitting kit_id/edition_date still yields a uniform shape.

    The keys are always written (as None) so every record has the same shape and
    a query cannot silently skip pre-47r3 sessions -- and so a missing edition
    reads as 'not recorded', never as a different edition.
    """
    cl.log_field_confirmation(
        form_id="I-90",
        form_session_id="fss_legacy_1",
        field_id="f1",
        field_name=None,
        confirmation_method="verbal",
    )
    cl.flush_confirmation_sink()

    doc = fake_db.collections[cl._FIRESTORE_COLLECTION].added[0]
    assert doc["kit_id"] is None
    assert doc["edition_date"] is None


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


def test_shutdown_race_falls_back_to_synchronous_write(fake_db, monkeypatch):
    """Submit-after-shutdown must WRITE synchronously, never drop (fresh-eyes
    on bd z2is): flush_confirmation_sink() can shut the executor between
    _get_executor() returning and submit() running -- exactly Cloud Run's
    SIGTERM drain window, when a liability event most matters."""
    from concurrent.futures import ThreadPoolExecutor

    dead = ThreadPoolExecutor(max_workers=1)
    dead.shutdown(wait=True)  # submit() on this now raises RuntimeError
    monkeypatch.setattr(cl, "_get_executor", lambda: dead)

    cl.log_field_confirmation(
        form_id="I-90",
        form_session_id="fss_race_1",
        field_id="f1",
        field_name=None,
        confirmation_method="verbal",
    )
    # No flush needed -- the fallback path writes synchronously.
    added = fake_db.collections[cl._FIRESTORE_COLLECTION].added
    assert len(added) == 1
    assert added[0]["form_session_id"] == "fss_race_1"


def test_strict_read_distinguishes_failure_from_empty(monkeypatch):
    """A FAILED Firestore query must never read as 'no events' (fresh-eyes on
    bd z2is): for a legal-retrieval surface those are opposite answers.
    strict=True raises ConfirmationReadError; the default degrades as before."""
    monkeypatch.setenv("CONFIRMATION_FIRESTORE_ENABLED", "true")

    def _broken():
        raise RuntimeError("403 Permission denied")

    monkeypatch.setattr("backend.services.auth.get_db", _broken)

    with pytest.raises(cl.ConfirmationReadError):
        cl.read_confirmation_log("fss_strict_1", strict=True)

    # Non-strict keeps the never-raise contract for in-app callers.
    assert cl.read_confirmation_log("fss_strict_1") == []


def test_flush_drains_sibling_executor_created_mid_drain(fake_db):
    """bd polyglot-pdf-wv3j: shutdown(wait=True) runs outside the lock, so a
    concurrent submit can lazily create a SIBLING executor while the swapped
    one drains. The flush loop must drain that sibling too and leave no live
    executor behind."""
    cl.log_field_confirmation(
        form_id="I-90",
        form_session_id="fss_sib_1",
        field_id="f1",
        field_name=None,
        confirmation_method="verbal",
    )
    ex1 = cl._executor
    assert ex1 is not None

    real_shutdown = ex1.shutdown

    def hijacked_shutdown(wait=True, **kw):
        # Simulate the concurrent producer landing after the swap, before the
        # drain completes: this lazily creates a fresh sibling executor.
        cl.log_field_confirmation(
            form_id="I-90",
            form_session_id="fss_sib_2",
            field_id="f2",
            field_name=None,
            confirmation_method="verbal",
        )
        real_shutdown(wait=wait, **kw)

    ex1.shutdown = hijacked_shutdown  # instance attr shadows the method

    cl.flush_confirmation_sink()

    # The deterministic pin: a single-pass flush would leave the sibling as
    # the live module executor; the loop must end with none.
    assert cl._executor is None
    ids = {
        d["form_session_id"]
        for d in fake_db.collections[cl._FIRESTORE_COLLECTION].added
    }
    assert ids == {"fss_sib_1", "fss_sib_2"}


def test_sink_status_disabled_ok_and_error(fake_db, monkeypatch):
    """confirmation_sink_status (round-3 fresh-eyes): IAM drift must be
    visible on /health, not only via a manual retrieval run."""
    # ok: probe write+delete against the fake
    assert cl.confirmation_sink_status() == "ok"
    probe_ref = fake_db.collections[cl._FIRESTORE_COLLECTION].doc_refs["_health_probe"]
    assert probe_ref.set_calls and probe_ref.delete_calls == 1

    # error: broken client -> "error: ..." (fresh cache)
    cl._probe_cache = None

    def _broken():
        raise RuntimeError("403 Permission denied")

    monkeypatch.setattr("backend.services.auth.get_db", _broken)
    status = cl.confirmation_sink_status()
    assert status.startswith("error:")

    # disabled: sink off -> "disabled" without touching the client
    monkeypatch.delenv("CONFIRMATION_FIRESTORE_ENABLED", raising=False)
    assert cl.confirmation_sink_status() == "disabled"


def test_sink_status_is_cached(fake_db, monkeypatch):
    assert cl.confirmation_sink_status() == "ok"

    def _explode():
        raise AssertionError("probe must be served from cache within max_age")

    monkeypatch.setattr("backend.services.auth.get_db", _explode)
    # Within max_age the cached "ok" is returned; no second Firestore hit.
    assert cl.confirmation_sink_status(max_age_s=300.0) == "ok"


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


# --- revision marker fallback (bd polyglot-pdf-47r3) --------------------------
#
# A disputed filing must pin WHICH revision of the form the client confirmed
# against. A government edition_date is the right answer for an official form,
# but a CUSTOM form (a firm's own intake sheet -- the firm-tier case) has none,
# and recording nothing would leave those confirmations unable to pin anything.


_SCHEMA = {
    "fields": [
        {"id": "a", "type": "text"},
        {"id": "b", "type": "select",
         "options": [{"value": "x"}, {"value": "y"}]},
    ]
}


def test_government_edition_wins_over_the_fingerprint():
    assert cl.resolve_edition_marker("12/2024", _SCHEMA) == "12/2024"


# --- author_version: the middle rank (bd polyglot-pdf-xzw5) -----------------
# Three sources, so the precedence has THREE edges to pin, not one. Testing
# only "author beats fingerprint" would leave the government-wins edge free to
# regress (docs/standards/testing.md: pin the dimension, not a sample).


@pytest.mark.parametrize("edition", ["12/2024", " 12/2024 "])
def test_government_edition_outranks_the_author_version(edition):
    """The agency marker is the only one an agency recognizes, so a kit
    carrying BOTH records the official one -- never the author's."""
    assert cl.resolve_edition_marker(edition, _SCHEMA, "2026-08-07") == "12/2024"


def test_author_version_outranks_the_fingerprint():
    """The whole point: a custom form records something a human can read back
    in a dispute instead of sha256:abc123..."""
    assert cl.resolve_edition_marker(None, _SCHEMA, "2026-08-07") == "2026-08-07"


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_a_blank_author_version_falls_through_to_the_fingerprint(blank):
    """Mirrors the blank-edition rule: whitespace is not a revision marker.
    Without this, an empty version box would record "" as the marker -- worse
    than the fingerprint it displaced, because it identifies nothing."""
    marker = cl.resolve_edition_marker(None, _SCHEMA, blank)
    assert marker.startswith("sha256:")


def test_author_version_is_trimmed_like_the_edition():
    assert cl.resolve_edition_marker(None, _SCHEMA, "  2026-08-07  ") == "2026-08-07"


def test_a_non_string_author_version_never_reaches_the_record():
    """The client controls form_metadata, so a malformed payload must fall
    through rather than record a dict/list/number as the revision marker."""
    for bogus in ({"v": 1}, ["2026"], 20260807, True):
        marker = cl.resolve_edition_marker(None, _SCHEMA, bogus)
        assert marker.startswith("sha256:"), bogus


def test_author_version_records_even_when_the_schema_is_unusable():
    """The fingerprint needs a schema; the author version does not. A kit with
    an author version but no readable fields must still name its revision
    rather than returning None (the "no marker at all" case)."""
    assert cl.resolve_edition_marker(None, None, "2026-08-07") == "2026-08-07"
    assert cl.resolve_edition_marker(None, {"fields": []}, "2026-08-07") == "2026-08-07"


def test_blank_edition_falls_back_to_the_fingerprint():
    """A whitespace-only edition must not be recorded AS an edition."""
    marker = cl.resolve_edition_marker("   ", _SCHEMA)
    assert marker.startswith("sha256:")


def test_fingerprint_is_stable_for_one_revision():
    assert (cl.resolve_edition_marker(None, _SCHEMA)
            == cl.resolve_edition_marker(None, _SCHEMA))


def test_fingerprint_moves_when_the_answerable_shape_changes():
    """Adding a field, retyping one, or changing an option VALUE is a revision."""
    base = cl.resolve_edition_marker(None, _SCHEMA)

    added = {"fields": _SCHEMA["fields"] + [{"id": "c", "type": "text"}]}
    retyped = {"fields": [{"id": "a", "type": "date"}, _SCHEMA["fields"][1]]}
    reoptioned = {"fields": [
        _SCHEMA["fields"][0],
        {"id": "b", "type": "select",
         "options": [{"value": "x"}, {"value": "DIFFERENT"}]},
    ]}

    assert cl.resolve_edition_marker(None, added) != base
    assert cl.resolve_edition_marker(None, retyped) != base
    assert cl.resolve_edition_marker(None, reoptioned) != base


def test_fingerprint_ignores_prose_edits():
    """A label/guidance typo fix must NOT read as a new revision.

    Otherwise every copy edit would look like a form change in the audit trail,
    and the marker would stop meaning anything.
    """
    base = cl.resolve_edition_marker(None, _SCHEMA)
    reworded = {"fields": [
        {"id": "a", "type": "text", "label": "Totally rewritten prose",
         "help": {"instructions": "new guidance"}},
        _SCHEMA["fields"][1],
    ]}

    assert cl.resolve_edition_marker(None, reworded) == base


def test_no_edition_and_no_schema_yields_none():
    assert cl.resolve_edition_marker(None, None) is None
    assert cl.resolve_edition_marker(None, {"fields": []}) is None
