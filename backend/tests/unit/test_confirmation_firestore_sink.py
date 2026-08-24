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
    cl._probe_in_flight = None
    yield
    cl.flush_confirmation_sink()
    cl._probe_cache = None
    cl._probe_in_flight = None


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
        firm_id="firm-a",
    )
    cl.flush_confirmation_sink()  # drain the background writer

    added = fake_db.collections[cl._FIRESTORE_COLLECTION].added
    assert len(added) == 1
    doc = added[0]
    # ALLOWLIST: exactly these keys, nothing else -- a `value` key appearing
    # here would be a PII regression (pin-with-allowlist, never a blacklist).
    # kit_id + edition_date joined under bd polyglot-pdf-47r3: both are form
    # METADATA (which kit, which government edition), never user data.
    # firm_id joined under bd polyglot-pdf-xwlt: it names the CUSTOMER FIRM
    # (our paying customer), never the client filling the form -- the firm
    # tier deliberately has no client identifier anywhere in this record.
    assert set(doc) == {
        "timestamp",
        "event",
        "form_id",
        "kit_id",
        "edition_date",
        "firm_id",
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
    assert doc["firm_id"] == "firm-a"


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


def test_strict_read_without_firestore_enabled_raises_instead_of_no_events(
    monkeypatch,
):
    """bd polyglot-pdf-k3v7: an operator who forgets --firestore (or has
    CONFIRMATION_FIRESTORE_ENABLED unset, the normal laptop case) must NOT
    see the same 'no events found' result a genuinely empty durable trail
    would produce -- the durable sink was never even consulted. strict=True
    must raise here exactly as it does for a FAILED query, since both are
    'I did not check', not 'the record does not exist'."""
    monkeypatch.delenv("CONFIRMATION_FIRESTORE_ENABLED", raising=False)

    def _explode():
        raise AssertionError(
            "get_db must not be called when the sink is not enabled"
        )

    monkeypatch.setattr("backend.services.auth.get_db", _explode)

    with pytest.raises(cl.ConfirmationReadError):
        cl.read_confirmation_log("fss_no_sink_1", strict=True)

    # Non-strict keeps the never-raise contract (degrades to the local file,
    # which is empty/absent here) -- this bug is specifically about strict.
    assert cl.read_confirmation_log("fss_no_sink_1") == []


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


def test_concurrent_probes_on_a_cold_cache_coalesce_to_one_round_trip(
    fake_db, monkeypatch
):
    """bd polyglot-pdf-fzwp: /health has no auth, so an unauthenticated caller
    can drive confirmation_sink_status() at their own request rate. Without
    coalescing, N concurrent callers racing in on a cold/stale cache each fall
    through to their OWN Firestore write+delete round trip -- write churn
    against the collection that holds the legal audit trail. This pins that
    only ONE round trip happens no matter how many callers race in."""
    import threading as _threading
    import time as _time

    call_count = {"n": 0}
    # Wrap the fake collection's document() to count calls AND to slow the
    # probe down, widening the race window so concurrent callers actually
    # overlap rather than running sequentially.
    coll = fake_db.collection(cl._FIRESTORE_COLLECTION)
    real_document_method = coll.document

    def slow_document(doc_id):
        if doc_id == "_health_probe":
            call_count["n"] += 1
            _time.sleep(0.05)
        return real_document_method(doc_id)

    monkeypatch.setattr(coll, "document", slow_document)

    results = []
    errors = []

    def worker():
        try:
            results.append(cl.confirmation_sink_status())
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [_threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert not errors, "concurrent probes raised: %r" % (errors,)
    assert call_count["n"] == 1, (
        "confirmation_sink_status made %d Firestore round trips for 10 "
        "concurrent callers on a cold cache; expected exactly 1 (coalescing "
        "must serialize concurrent probes onto a single round trip)"
        % call_count["n"]
    )
    assert results == ["ok"] * 10, "every caller must see the SAME result"


def test_a_waiter_times_out_honestly_when_the_prober_stalls(fake_db, monkeypatch):
    """bd polyglot-pdf-fzwp round 2 (Opus cross-surface review): a genuinely
    STALLED prober (the exact IAM-drift/outage scenario this probe exists to
    detect) must not hang a coalesced waiter forever. The waiter's internal
    timeout is bounded well under /health's own 3.0s asyncio.wait_for budget
    (backend/main.py) -- a wait longer than the only real caller's own
    deadline can never usefully return to that caller anyway. This path is
    REACHABLE, not dead defensive code: pin it directly rather than trusting
    only the "should be unreachable" comment that used to describe it."""
    import threading as _threading

    prober_may_finish = _threading.Event()
    prober_started = _threading.Event()

    coll = fake_db.collection(cl._FIRESTORE_COLLECTION)
    real_document_method = coll.document

    def blocking_document(doc_id):
        if doc_id == "_health_probe":
            prober_started.set()
            prober_may_finish.wait(timeout=5)
        return real_document_method(doc_id)

    monkeypatch.setattr(coll, "document", blocking_document)

    results = []

    def prober():
        results.append(("prober", cl.confirmation_sink_status()))

    def waiter():
        results.append(("waiter", cl.confirmation_sink_status()))

    t_prober = _threading.Thread(target=prober)
    t_prober.start()
    assert prober_started.wait(timeout=5), "prober never started its probe"

    t_waiter = _threading.Thread(target=waiter)
    t_waiter.start()
    t_waiter.join(timeout=5)  # the waiter's own internal wait is ~2s

    assert not t_waiter.is_alive(), "the waiter must not hang past its own timeout"
    waiter_result = dict(results)["waiter"]
    assert waiter_result == (
        "error: probe coalescing timed out waiting for another in-flight probe"
    )

    # Let the still-running prober finish so the test leaves no live thread.
    prober_may_finish.set()
    t_prober.join(timeout=5)
    assert not t_prober.is_alive()


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


def test_disclaimer_acceptance_reaches_the_durable_sink(fake_db, monkeypatch):
    """The acceptance is written to Firestore, not just to a log line.

    bd polyglot-pdf-0dsv4: the record that a user accepted the LEGAL TERMS
    used to be a structlog line only, while the record of what they TYPED
    went to Firestore. That is backwards for an evidence trail.
    """
    cl.log_disclaimer_acceptance(
        form_session_id="fss_test_1",
        language="Spanish",
        timestamp_unix_ms=1755000000000,
        script_version="deadbeefcafe0001",
        user_agent="Mozilla/5.0 (test)",
        firm_id=None,
    )
    cl.flush_confirmation_sink()

    added = fake_db.collections[cl._FIRESTORE_COLLECTION].added
    assert len(added) == 1
    doc = added[0]
    # ALLOWLIST: exactly these keys, nothing else. A `value`, `client_ip`, or
    # any client identifier appearing here would be a PII regression
    # (pin-with-allowlist, never a blacklist -- banning one word is a synonym
    # away from defeat). script_version is a HASH of copy that ships in the
    # client bundle, so it names WHICH text was agreed to without carrying
    # user content. firm_id names our CUSTOMER FIRM, never the person filling
    # the form.
    assert set(doc) == {
        "timestamp",
        "event",
        "form_session_id",
        "firm_id",
        "language",
        "timestamp_unix_ms",
        "script_version",
        "user_agent",
    }
    assert doc["event"] == "disclaimer_accepted"
    assert doc["form_session_id"] == "fss_test_1"
    assert doc["script_version"] == "deadbeefcafe0001"
    # firm_id is present-but-None today (the route is unauthenticated). The
    # KEY must exist so the collection has one shape and no migration is
    # needed when firm auth reaches this route.
    assert doc["firm_id"] is None


def test_acceptance_and_confirmations_form_ONE_session_record(fake_db, monkeypatch):
    """The whole point: both event kinds are retrievable together.

    Keyed on form_session_id, so read_confirmation_log() returns the
    acceptance and the field confirmations as one timestamp-ordered record --
    "this session accepted this text, then confirmed these fields".
    """
    cl.log_disclaimer_acceptance(
        form_session_id="fss_join_1",
        language="English",
        timestamp_unix_ms=1755000000000,
        script_version="abc123def4567890",
        user_agent="ua",
        firm_id=None,
    )
    cl.log_field_confirmation(
        form_id="I-90",
        form_session_id="fss_join_1",
        field_id="p1_line1_aliennumber",
        field_name=None,
        confirmation_method="verbal",
        kit_id="i-90",
        edition_date="01/20/25",
        firm_id="firm-a",
    )
    cl.flush_confirmation_sink()

    added = fake_db.collections[cl._FIRESTORE_COLLECTION].added
    session = [d for d in added if d.get("form_session_id") == "fss_join_1"]
    assert len(session) == 2
    assert {d["event"] for d in session} == {"disclaimer_accepted", "field_confirmed"}


def test_acceptance_does_NOT_match_the_kit_deletion_guard(fake_db, monkeypatch):
    """A new event kind must not make a kit undeletable.

    The deletion guard's own history is the reason this test exists: an
    UNSCOPED kit query once matched session-lifecycle events, so a single
    voice session made a kit permanently undeletable (bd polyglot-pdf-68s2q /
    u66ka). Every guard query is now scoped to event == "field_confirmed".
    The acceptance record carries NO kit_id at all, so it cannot match -- but
    pin it, because the failure mode is silent and expensive.
    """
    cl.log_disclaimer_acceptance(
        form_session_id="fss_guard_1",
        language="English",
        timestamp_unix_ms=1755000000000,
        script_version="abc123def4567890",
        user_agent="ua",
        firm_id=None,
    )
    cl.flush_confirmation_sink()

    doc = fake_db.collections[cl._FIRESTORE_COLLECTION].added[0]
    assert "kit_id" not in doc
    assert doc["event"] != "field_confirmed"


def test_firm_attribution_recovers_the_firm_from_sibling_records():
    """The JOIN fallback: the acceptance has no firm, its siblings do."""
    events = [
        {"event": "disclaimer_accepted", "firm_id": None},
        {"event": "field_confirmed", "firm_id": "firm-a"},
    ]
    assert cl.firm_of_events(events) == "firm-a"


def test_firm_attribution_is_None_when_the_session_has_no_firm():
    """A session that accepted and abandoned before confirming a field has no
    firm ANYWHERE. Report that honestly rather than inventing one."""
    assert cl.firm_of_events([{"event": "disclaimer_accepted", "firm_id": None}]) is None
    assert cl.firm_of_events([]) is None


def test_firm_attribution_REFUSES_to_guess_when_records_disagree():
    """Two firms on one session means something is wrong upstream.

    Returning the first would launder a data problem into a confident wrong
    answer on a legal-evidence path. "We do not know" is the honest result.
    """
    events = [
        {"event": "field_confirmed", "firm_id": "firm-a"},
        {"event": "field_confirmed", "firm_id": "firm-b"},
    ]
    assert cl.firm_of_events(events) is None


# --- path traversal: form_session_id becomes a FILENAME -------------------
#
# POST /api/disclaimer-acceptance is UNAUTHENTICATED (Agree fires before any
# session exists), and bd polyglot-pdf-0dsv4 made its client-supplied
# form_session_id reach the filesystem. "../../PWNED" wrote a file two
# directories outside CONFIRMATION_LOG_DIR and returned 200 -- reproduced in
# the cross-surface review of that bead, before this guard existed.
#
# Validated at the SINK, not in the route, so every caller is covered --
# including ones added later that forget.

@pytest.mark.parametrize("unsafe", [
    "../../PWNED",
    ".." + chr(92) + ".." + chr(92) + "PWNED",   # Windows separators
    "..",
    "a/b",
    "a" + chr(92) + "b",
    "/etc/passwd",
    "C:" + chr(92) + "evil",                            # drive-qualified
    chr(92) + chr(92) + "server" + chr(92) + "share",   # UNC
    "%2e%2e%2fPWNED",                                   # url-encoded
    "%252e%252e%252f",                                  # double-encoded
    "fss_x" + chr(0),                                   # NUL byte
    "fss_x\n",   # the fullmatch-vs-match trap (bd polyglot-pdf-sbfk)
    # Windows RESERVED DEVICE NAMES. "NUL.jsonl" opens the null device and
    # discards every byte -- SILENT evidence loss, worse than a noisy failure.
    # These passed the first version of this validator; found by attacking it
    # rather than reasoning about it.
    "CON", "con", "NUL", "nul.jsonl", "COM1", "LPT9", "PRN", "AUX",
    "fss_x.",           # Windows strips trailing dots: "x." and "x" collide
    ".",
    "...",
    "",
    "x" * 129,          # length bound
])
def test_an_unsafe_session_id_is_refused_as_a_filename(unsafe):
    assert cl._is_safe_session_id(unsafe) is False


@pytest.mark.parametrize("safe", [
    "fss_abc123_xyz789",   # the real shape from schemaFormState.ts
    "fss_1755000000_ab12cd34",
    "fss_a_b",
    "a",
    "A-Z_0.9",
    "x" * 128,             # at the bound, not over it
    # NEAR-MISSES on the device list: ordinary names that must NOT be refused.
    # Silently dropping a legitimate id is WORSE than the traversal -- it is
    # evidence loss with no error at all.
    "CONSOLE", "NULLABLE", "COM10", "AUXILIARY",
])
def test_a_legitimate_session_id_is_accepted(safe):
    assert cl._is_safe_session_id(safe) is True


def test_an_unsafe_session_id_writes_NO_file(tmp_path, monkeypatch):
    """The guard must actually prevent the write, not just return False.

    NOTE THE DEPTH. "../../PWNED" escapes TWO levels above the log dir, so a
    check that only globs the log dir -- or even its parent -- passes while
    the file lands somewhere else entirely. My first version of this test did
    exactly that and stayed green with the guard disabled. Nest the log dir
    deep enough that every escape target is still inside tmp_path, then assert
    NOTHING was written anywhere beneath it.
    """
    log_dir = tmp_path / "a" / "b" / "c" / "confirmations"
    log_dir.mkdir(parents=True)
    monkeypatch.setenv("CONFIRMATION_LOG_DIR", str(log_dir))

    for unsafe in ("../../PWNED", "../ESCAPED", "..", "a/b"):
        cl._write_confirmation_to_file(unsafe, {"event": "disclaimer_accepted"})

    written = list(tmp_path.rglob("*.jsonl"))
    assert written == [], f"files escaped the log dir: {written}"


def test_a_legitimate_session_id_STILL_writes(tmp_path, monkeypatch):
    """The guard must not break the normal path -- pin both directions."""
    log_dir = tmp_path / "confirmations"
    log_dir.mkdir()
    monkeypatch.setenv("CONFIRMATION_LOG_DIR", str(log_dir))

    cl._write_confirmation_to_file("fss_good_1", {"event": "disclaimer_accepted"})

    assert (log_dir / "fss_good_1.jsonl").exists()
