"""Telemetry alert docs: deterministic-id dedup (Epic 3 bead E3.5, bd
polyglot-pdf-bo95a).

Pins the bead's three exit criteria:

  1. test_alerts_dedup.py itself -- a second refusal for the same jti writes
     nothing NEW; a firm crossing the low threshold twice in one day yields
     one doc; crossing to zero yields the exhausted doc.
  2. an alert write failure never propagates into check_budget or
     append_entry.
  3. (the rules deny block + set test live in test_firestore_rules_text.py)

Each test's docstring names the mutation that must turn it red
(docs/standards/testing.md#test-the-tests).

ASCII only.
"""
from __future__ import annotations

import pytest

from backend.services import alerts, link_spend, runtime_config


# ---------------------------------------------------------------- fake db
#
# A minimal Firestore-shaped document store: .document(id).get()/.set(merge).
# Deliberately a FAKE, not a mock (CLAUDE.md scar #7's neighbour) -- the
# dedup property being pinned is "a second write does not create a second
# document and does not clobber acknowledged/emailed fields", which only a
# store that actually MERGES can prove.


class _Snap:
    def __init__(self, data):
        self._data = dict(data) if data is not None else None

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _Doc:
    def __init__(self, store, doc_id):
        self._store = store
        self._doc_id = doc_id

    def get(self):
        if self._store.read_error:
            raise RuntimeError(self._store.read_error)
        return _Snap(self._store.docs.get(self._doc_id))

    def set(self, data, merge=False):
        if self._store.write_error:
            raise RuntimeError(self._store.write_error)
        self._store.write_count += 1
        if merge and self._doc_id in self._store.docs:
            self._store.docs[self._doc_id].update(data)
        else:
            self._store.docs[self._doc_id] = dict(data)


class _Collection:
    def __init__(self, store):
        self._store = store

    def document(self, doc_id):
        return _Doc(self._store, doc_id)


class _Store:
    def __init__(self):
        self.docs: dict[str, dict] = {}
        self.write_count = 0
        self.read_error = None
        self.write_error = None

    def collection(self, name):
        assert name == alerts.COLLECTION
        return _Collection(self)


@pytest.fixture
def store(monkeypatch):
    s = _Store()
    monkeypatch.setattr(alerts, "_collection", lambda: _Collection(s))
    runtime_config.clear_cache()
    return s


# ---------------------------------------------------------------------------
# 1a. link_exhausted dedup
# ---------------------------------------------------------------------------


def test_a_second_refusal_for_the_SAME_jti_writes_no_new_doc(store):
    """EXIT CRITERION 1. Two refusals, same jti -> ONE document.

    Mutation: change record_link_exhausted's doc_id from
    "link_exhausted_{jti}" to include a counter or timestamp -- this test
    goes red because len(store.docs) becomes 2.
    """
    alerts.record_link_exhausted("jti-a", firm_id="acme", spend_usd=10.5,
                                  ceiling_usd=10.0, now=1000.0)
    alerts.record_link_exhausted("jti-a", firm_id="acme", spend_usd=11.0,
                                  ceiling_usd=10.0, now=2000.0)

    assert len(store.docs) == 1
    doc = store.docs["link_exhausted_jti-a"]
    assert doc["kind"] == alerts.KIND_LINK_EXHAUSTED
    assert doc["ts"] == 2000.0, "the doc must reflect the LATEST crossing"
    assert doc["context"]["spend_usd"] == pytest.approx(11.0)


def test_a_DIFFERENT_jti_gets_its_OWN_doc(store):
    alerts.record_link_exhausted("jti-a", firm_id="acme", spend_usd=10.0,
                                  ceiling_usd=10.0)
    alerts.record_link_exhausted("jti-b", firm_id="acme", spend_usd=10.0,
                                  ceiling_usd=10.0)
    assert len(store.docs) == 2


def test_link_exhausted_never_touches_ack_or_email_fields_on_a_repeat(store):
    """A re-trigger must not silently un-acknowledge or un-email a doc an
    operator (or the future dispatcher) already handled.

    Mutation: drop the "already exists" read-before-write check in
    alerts._write and always seed the three fields to None -- red.
    """
    alerts.record_link_exhausted("jti-a", firm_id="acme", spend_usd=10.0,
                                  ceiling_usd=10.0)
    store.docs["link_exhausted_jti-a"]["acknowledged_by"] = "operator-1"
    store.docs["link_exhausted_jti-a"]["emailed_at"] = 555.0

    alerts.record_link_exhausted("jti-a", firm_id="acme", spend_usd=12.0,
                                  ceiling_usd=10.0)

    doc = store.docs["link_exhausted_jti-a"]
    assert doc["acknowledged_by"] == "operator-1"
    assert doc["emailed_at"] == 555.0


def test_link_exhausted_carries_the_expected_context_and_no_field_values(
        store):
    alerts.record_link_exhausted("jti-a", firm_id="acme", spend_usd=10.25,
                                  ceiling_usd=10.0, now=42.0)
    doc = store.docs["link_exhausted_jti-a"]
    assert set(doc) == alerts.ALERT_FIELDS
    assert doc["firm_id"] == "acme"
    assert doc["level"] == alerts.LEVEL_CRITICAL
    assert doc["acknowledged_by"] is None
    assert doc["acknowledged_at"] is None
    assert doc["emailed_at"] is None
    assert set(doc["context"]) == {"jti", "spend_usd", "ceiling_usd"}
    assert doc["context"]["jti"] == "jti-a"


# ---------------------------------------------------------------------------
# 1b. credit_low / credit_exhausted dedup
# ---------------------------------------------------------------------------


_SAME_DAY = 1_757_000_000.0        # an arbitrary UTC instant
_SAME_DAY_LATER = _SAME_DAY + 3600  # +1h, same UTC calendar day
_NEXT_DAY = _SAME_DAY + 86400 + 3600  # unambiguously the next UTC day


def test_a_firm_crossing_the_LOW_threshold_TWICE_in_one_day_yields_ONE_doc(
        store):
    """EXIT CRITERION 1. Two low-threshold crossings, same UTC day -> ONE doc.

    Mutation: key the doc id on a per-call counter or on `ts` directly
    instead of the calendar day -- red, because len(store.docs) becomes 2.
    """
    alerts.record_credit_threshold("acme", balance=8, threshold=10,
                                    now=_SAME_DAY)
    alerts.record_credit_threshold("acme", balance=5, threshold=10,
                                    now=_SAME_DAY_LATER)

    low_docs = {k: v for k, v in store.docs.items()
                if v["kind"] == alerts.KIND_CREDIT_LOW}
    assert len(low_docs) == 1
    doc = next(iter(low_docs.values()))
    assert doc["context"]["balance"] == 5, "must reflect the LATEST crossing"


def test_crossing_to_ZERO_yields_the_EXHAUSTED_doc(store):
    """EXIT CRITERION 1. balance <= 0 writes credit_exhausted (in ADDITION
    to credit_low -- zero is also at-or-below a positive threshold).

    Mutation: change the exhausted branch's condition from `balance <= 0` to
    `balance < 0` -- red, because a balance of exactly 0 stops firing it.
    """
    alerts.record_credit_threshold("acme", balance=0, threshold=10,
                                    now=_SAME_DAY)

    kinds = {v["kind"] for v in store.docs.values()}
    assert alerts.KIND_CREDIT_EXHAUSTED in kinds
    assert alerts.KIND_CREDIT_LOW in kinds, (
        "zero is also <= a positive threshold -- both alerts fire"
    )


def test_threshold_ZERO_writes_ONLY_the_EXHAUSTED_doc(store):
    """threshold=0 is the documented carve-out (runtime_config.py's
    KEY_CREDIT_LOW_THRESHOLD coercion comment and
    test_credit_low_threshold_accepts_zero): an operator who sets the
    threshold to 0 wants ONLY the zero-balance/exhausted alert, never a
    separate credit_low doc, since both would trip on the identical
    balance<=0 boundary.

    Mutation: drop the `threshold > 0` guard from the low branch's `if` in
    record_credit_threshold -- red, because credit_low would also be
    written here.
    """
    alerts.record_credit_threshold("acme", balance=0, threshold=0,
                                    now=_SAME_DAY)

    kinds = {v["kind"] for v in store.docs.values()}
    assert kinds == {alerts.KIND_CREDIT_EXHAUSTED}, (
        "threshold=0 must suppress the separate credit_low doc"
    )


def test_crossing_to_exhausted_TWICE_in_one_day_yields_ONE_doc(store):
    alerts.record_credit_threshold("acme", balance=-2, threshold=10,
                                    now=_SAME_DAY)
    alerts.record_credit_threshold("acme", balance=-5, threshold=10,
                                    now=_SAME_DAY_LATER)

    exhausted_docs = {k: v for k, v in store.docs.items()
                       if v["kind"] == alerts.KIND_CREDIT_EXHAUSTED}
    assert len(exhausted_docs) == 1
    assert next(iter(exhausted_docs.values()))["context"]["balance"] == -5


def test_a_NEW_UTC_day_gets_a_FRESH_doc(store):
    """The reset an operator would expect: still-low-today is one alert per
    day, not one forever."""
    alerts.record_credit_threshold("acme", balance=5, threshold=10,
                                    now=_SAME_DAY)
    alerts.record_credit_threshold("acme", balance=5, threshold=10,
                                    now=_NEXT_DAY)

    low_docs = [v for v in store.docs.values()
                if v["kind"] == alerts.KIND_CREDIT_LOW]
    assert len(low_docs) == 2


def test_a_balance_ABOVE_threshold_writes_nothing(store):
    alerts.record_credit_threshold("acme", balance=50, threshold=10,
                                    now=_SAME_DAY)
    assert store.docs == {}


def test_a_DIFFERENT_firm_gets_its_own_doc_the_same_day(store):
    alerts.record_credit_threshold("acme", balance=5, threshold=10,
                                    now=_SAME_DAY)
    alerts.record_credit_threshold("beta", balance=5, threshold=10,
                                    now=_SAME_DAY)
    low_docs = [v for v in store.docs.values()
                if v["kind"] == alerts.KIND_CREDIT_LOW]
    assert len(low_docs) == 2
    assert {d["firm_id"] for d in low_docs} == {"acme", "beta"}


# ---------------------------------------------------------------------------
# 2. An alert write failure never propagates into the callers.
# ---------------------------------------------------------------------------


def test_a_store_failure_never_raises_out_of_record_link_exhausted(store):
    """EXIT CRITERION 2, half A.

    Mutation: remove the try/except around the Firestore .set() call in
    alerts._write -- red, this test raises RuntimeError instead of passing.
    """
    store.write_error = "firestore unavailable"
    alerts.record_link_exhausted("jti-a", firm_id="acme", spend_usd=10.0,
                                  ceiling_usd=10.0)  # must not raise


def test_a_store_failure_never_raises_out_of_record_credit_threshold(store):
    store.write_error = "firestore unavailable"
    alerts.record_credit_threshold("acme", balance=0, threshold=10)  # no raise


def test_get_db_itself_RAISING_never_propagates(monkeypatch):
    """The regression this module actually shipped with once, caught by the
    full credit_ledger suite: `_collection()` was called OUTSIDE `_write`'s
    try/except, so a broken firebase_admin app (get_db() raising, not just
    returning None) crashed straight through record_credit_threshold ->
    append_entry.

    Mutation: move the `ref = _collection().document(doc_id)` line back
    outside the try block in alerts._write -- red, AttributeError instead
    of a clean return.
    """
    def _broken_get_db():
        raise AttributeError("'_FakeFirestoreModule' object has no attribute 'client'")

    monkeypatch.setattr("backend.services.auth.get_db", _broken_get_db)
    alerts.record_link_exhausted("jti-a", firm_id="acme", spend_usd=10.0,
                                  ceiling_usd=10.0)  # must not raise
    alerts.record_credit_threshold("acme", balance=0, threshold=10)  # no raise


def test_a_read_failure_on_the_existence_check_never_raises(store):
    """The "does this doc already exist" read (used to decide whether to
    seed ack/email fields) is ALSO best-effort -- an unreachable store must
    degrade the same way a write failure does, not surface a different
    exception.
    """
    store.read_error = "firestore unavailable"
    alerts.record_link_exhausted("jti-a", firm_id="acme", spend_usd=10.0,
                                  ceiling_usd=10.0)  # must not raise


def test_check_budget_STILL_RAISES_LinkBudgetExhausted_when_the_alert_write_fails(
        monkeypatch, store):
    """EXIT CRITERION 2, half B -- the REAL caller. A broken alert store must
    not change WHAT check_budget raises: the client must still be refused,
    for the real reason, not for a bookkeeping failure.

    Mutation: let the alerts.record_link_exhausted exception propagate out
    of check_budget (e.g. remove alerts.py's own try/except) -- red, this
    test then raises RuntimeError instead of LinkBudgetExhausted.
    """
    monkeypatch.setattr(link_spend, "_enabled", lambda: True)

    class _Snap:
        exists = True

        def to_dict(self):
            return {link_spend.SPEND_FIELD: 999.0}

    class _Doc:
        def get(self):
            return _Snap()

    class _SpendStore:
        def document(self, jti):
            return _Doc()

    monkeypatch.setattr(link_spend, "_collection", lambda: _SpendStore())
    store.write_error = "firestore unavailable"

    with pytest.raises(link_spend.LinkBudgetExhausted):
        link_spend.check_budget("jti-a", {"link_cost_ceiling_usd": 10.0},
                                 firm_id="acme")


# ---------------------------------------------------------------------------
# Integration: check_budget's refusal branch actually calls alerts.py
# ---------------------------------------------------------------------------


def test_check_budget_writes_the_alert_ON_REFUSAL(store):
    """Proves the WIRING, not just alerts.py in isolation: check_budget's
    LinkBudgetExhausted branch must actually call record_link_exhausted with
    the right jti/firm_id/spend/ceiling.

    Mutation: delete the alerts.record_link_exhausted(...) call from
    check_budget -- red, store.docs stays empty.
    """
    import unittest.mock as _mock

    class _Doc:
        def get(self):
            class _Snap:
                exists = True

                def to_dict(self):
                    return {link_spend.SPEND_FIELD: 10.0}
            return _Snap()

    class _Coll:
        def document(self, jti):
            return _Doc()

    with _mock.patch.object(link_spend, "_enabled", lambda: True), \
         _mock.patch.object(link_spend, "_collection", lambda: _Coll()):
        with pytest.raises(link_spend.LinkBudgetExhausted):
            link_spend.check_budget("jti-a", {"link_cost_ceiling_usd": 10.0},
                                     firm_id="acme")

    assert "link_exhausted_jti-a" in store.docs
    doc = store.docs["link_exhausted_jti-a"]
    assert doc["firm_id"] == "acme"
    assert doc["context"]["spend_usd"] == pytest.approx(10.0)
    assert doc["context"]["ceiling_usd"] == pytest.approx(10.0)


def test_check_budget_UNDER_ceiling_writes_no_alert(store):
    """The happy path must not write telemetry at all."""
    import unittest.mock as _mock

    class _Doc:
        def get(self):
            class _Snap:
                exists = True

                def to_dict(self):
                    return {link_spend.SPEND_FIELD: 1.0}
            return _Snap()

    class _Coll:
        def document(self, jti):
            return _Doc()

    with _mock.patch.object(link_spend, "_enabled", lambda: True), \
         _mock.patch.object(link_spend, "_collection", lambda: _Coll()):
        link_spend.check_budget("jti-a", {"link_cost_ceiling_usd": 10.0},
                                 firm_id="acme")

    assert store.docs == {}
