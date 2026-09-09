"""Session-end Firestore usage rollups (Epic 3 bead E3.4, bd
polyglot-pdf-w828m).

Pins the bead's three exit criteria:

  1. A completed link session and a staff session each write exactly one
     batched update with the right attribution (by_employee from the link's
     employee for link sessions, the uid for staff), completed vs abandoned
     counted separately.
  2. A hyphenated kit id and language code increment the intended nested
     field (through the REAL FieldPath/nested-dict construction, not a
     hand-typed dotted string).
  3. (the rules deny blocks + set test live in
     test_firestore_rules_text.py)

Each test's docstring names the mutation that must turn it red
(docs/standards/testing.md#test-the-tests).

ASCII only.
"""
from __future__ import annotations

import pytest

from backend.services import usage_rollups


# ---------------------------------------------------------------- fake db
#
# A minimal but FAITHFUL Firestore-merge simulation: set(data, merge=True)
# on a batch, committed, actually merges nested dicts and resolves
# firestore.Increment against the PRIOR stored value the way real Firestore
# does. This is the only way to prove the hyphenated-key exit criterion --
# a fake that just recorded the raw dict passed to set() would pass even if
# usage_rollups.py handed it a flat dotted-string key that a real Firestore
# server would silently mis-nest (see the module docstring's account of
# set(merge=True) NOT dot-expanding). Deliberately a FAKE, not a mock
# (CLAUDE.md scar #7's neighbour, mirroring test_alerts_dedup.py).


def _is_increment(value):
    return type(value).__name__ == "Increment" and hasattr(value, "value")


def _merge_value(existing, incoming):
    """Merge ONE value the way Firestore's set(merge=True) does: a nested
    dict merges key-by-key (recursively), an Increment resolves against the
    prior numeric value (0 if absent or non-numeric), anything else
    overwrites.
    """
    if _is_increment(incoming):
        base = existing if isinstance(existing, (int, float)) else 0
        return base + incoming.value
    if isinstance(incoming, dict):
        merged = dict(existing) if isinstance(existing, dict) else {}
        for k, v in incoming.items():
            merged[k] = _merge_value(merged.get(k), v)
        return merged
    return incoming


class _DocRef:
    def __init__(self, store, path):
        self._store = store
        self._path = path

    def collection(self, name):
        return _Collection(self._store, self._path + "/" + name)

    def set(self, data, merge=False):
        """record_link_opened/_completed write directly through the doc ref
        (no batch) -- mirrors alerts.py's own single-doc write shape.
        """
        if self._store.commit_error:
            raise RuntimeError(self._store.commit_error)
        existing = self._store.docs.get(self._path, {})
        if merge:
            merged = dict(existing)
            for k, v in data.items():
                merged[k] = _merge_value(merged.get(k), v)
            self._store.docs[self._path] = merged
        else:
            self._store.docs[self._path] = dict(data)
        self._store.commit_count += 1


class _Collection:
    def __init__(self, store, path):
        self._store = store
        self._path = path

    def document(self, doc_id):
        return _DocRef(self._store, self._path + "/" + doc_id)


class _WriteBatch:
    def __init__(self, store):
        self._store = store
        self._pending = []  # [(path, data, merge)]

    def set(self, ref, data, merge=False):
        self._pending.append((ref._path, data, merge))

    def commit(self):
        if self._store.commit_error:
            raise RuntimeError(self._store.commit_error)
        for path, data, merge in self._pending:
            existing = self._store.docs.get(path, {})
            if merge:
                merged = dict(existing)
                for k, v in data.items():
                    merged[k] = _merge_value(merged.get(k), v)
                self._store.docs[path] = merged
            else:
                self._store.docs[path] = dict(data)
        self._store.commit_count += 1
        self._pending = []


class _FakeDb:
    def __init__(self):
        self.docs: dict[str, dict] = {}
        self.commit_count = 0
        self.commit_error = None
        self.get_error = None

    def collection(self, name):
        return _Collection(self, name)

    def batch(self):
        return _WriteBatch(self)


@pytest.fixture
def db(monkeypatch):
    fake = _FakeDb()
    monkeypatch.setattr(usage_rollups, "_get_db", lambda: fake)
    return fake


_NOW = 1_788_955_200.0  # 2026-09-09 12:00:00 UTC
_FIRM_DOC = "firms/acme/usage/2026-09"
_KIT_DOC = "kits/i-90/usage/2026-09"


# ---------------------------------------------------------------------------
# Exit criterion 1: staff vs link attribution, completed vs abandoned
# ---------------------------------------------------------------------------


def test_a_completed_link_session_writes_one_batched_update_with_link_attribution(db):
    """EXIT CRITERION 1. A completed client-link session writes ONE commit,
    bumping connections_ended, sessions_completed, cost_usd_total, and
    by_employee keyed on the LINK's employee_id.

    Mutation: change record_session_end to call batch.commit() once per doc
    ref update inside the loop instead of once at the end -- this test
    would still pass (commit_count counts calls, and there are legitimately
    two set() calls for two docs) UNLESS commit_count is asserted as
    exactly 1: a per-doc-commit refactor breaks the "one batched set of
    updates" contract even though the DATA would still look right, so this
    assertion is the one that catches it.
    """
    ok = usage_rollups.record_session_end(
        firm_id="acme",
        kit_id="i-90",
        employee_id="employee-77",
        language="en-US",
        channel="demo",
        kind="live",
        completion_status="completed",
        cost_usd=1.25,
        now=_NOW,
    )
    assert ok is True
    assert db.commit_count == 1, "must be ONE batched commit, not per-doc"

    firm = db.docs[_FIRM_DOC]
    assert firm["connections_ended"] == 1
    assert firm["sessions_completed"] == 1
    assert firm["cost_usd_total"] == pytest.approx(1.25)
    assert firm["by_employee"]["employee-77"]["sessions"] == 1
    assert firm["by_employee"]["employee-77"]["cost_usd"] == pytest.approx(1.25)


def test_a_staff_session_writes_with_STAFF_UID_attribution(db):
    """A staff session (no link) attributes by_employee to the passed
    employee_id the SAME WAY -- this module does not distinguish staff vs
    link; the caller resolves which id to pass (usage_employee_id in
    websocket_routes.py). Proves the function itself is attribution-source
    agnostic.
    """
    usage_rollups.record_session_end(
        firm_id="acme",
        kit_id="i-90",
        employee_id="staff-uid-42",
        language="en-US",
        channel="demo",
        kind="live",
        completion_status="completed",
        cost_usd=0.0,
        now=_NOW,
    )
    firm = db.docs[_FIRM_DOC]
    assert firm["by_employee"]["staff-uid-42"]["sessions"] == 1
    assert "cost_usd" not in firm["by_employee"]["staff-uid-42"], (
        "zero cost must not write a cost_usd Increment(0) entry"
    )


def test_an_ABANDONED_session_does_NOT_increment_sessions_completed(db):
    """EXIT CRITERION 1: completed vs abandoned counted separately.

    Mutation: drop the `if completed:` guard around sessions_completed's
    Increment in record_session_end -- red, sessions_completed becomes 1.
    """
    usage_rollups.record_session_end(
        firm_id="acme",
        kit_id="i-90",
        employee_id="employee-77",
        language="en-US",
        channel="demo",
        kind="live",
        completion_status="abandoned",
        cost_usd=0.5,
        now=_NOW,
    )
    firm = db.docs[_FIRM_DOC]
    assert firm["connections_ended"] == 1
    assert "sessions_completed" not in firm


def test_TWO_connections_one_completed_one_abandoned_COUNT_SEPARATELY(db):
    """The real regression shape: a reconnect (abandoned) followed by the
    real finish (completed) must leave connections_ended=2,
    sessions_completed=1 -- not both counters equal.
    """
    usage_rollups.record_session_end(
        firm_id="acme", kit_id="i-90", employee_id="e1", language=None,
        channel="demo", kind="live", completion_status="abandoned",
        cost_usd=0.3, now=_NOW,
    )
    usage_rollups.record_session_end(
        firm_id="acme", kit_id="i-90", employee_id="e1", language=None,
        channel="demo", kind="live", completion_status="completed",
        cost_usd=0.7, now=_NOW + 10,
    )
    firm = db.docs[_FIRM_DOC]
    assert firm["connections_ended"] == 2
    assert firm["sessions_completed"] == 1
    assert firm["cost_usd_total"] == pytest.approx(1.0)


def test_writes_BOTH_the_firm_and_the_kit_doc_in_ONE_commit(db):
    """The kit-side doc mirrors by_firm, and both land in the SAME commit.

    Mutation: move the kit batch.set() call after batch.commit() -- red,
    the kit doc never appears (commit() clears the pending list).
    """
    usage_rollups.record_session_end(
        firm_id="acme", kit_id="i-90", employee_id="e1", language=None,
        channel="demo", kind="live", completion_status="completed",
        cost_usd=2.0, now=_NOW,
    )
    assert db.commit_count == 1
    kit = db.docs[_KIT_DOC]
    assert kit["connections_ended"] == 1
    assert kit["sessions_completed"] == 1
    assert kit["cost_usd_total"] == pytest.approx(2.0)
    assert kit["by_firm"]["acme"]["sessions"] == 1
    assert kit["by_firm"]["acme"]["cost_usd"] == pytest.approx(2.0)


def test_NO_kit_id_writes_ONLY_the_firm_doc(db):
    """A session with no kit_id (should not normally happen, but the
    function must degrade gracefully) writes the firm doc and skips the
    kit doc entirely -- no kit ref with an empty/None document id.
    """
    usage_rollups.record_session_end(
        firm_id="acme", kit_id=None, employee_id="e1", language=None,
        channel="demo", kind="live", completion_status="completed",
        cost_usd=1.0, now=_NOW,
    )
    assert _FIRM_DOC in db.docs
    assert not any(k.startswith("kits/") for k in db.docs), (
        "no kit_id must mean NO kit-side write at all"
    )


def test_NO_firm_id_writes_NOTHING_and_returns_False(db):
    """EXIT CRITERION: both target documents are firm/kit-keyed; a firm-less
    session has no document to bump at all.

    Mutation: remove the `if not firm_id: return False` early return --
    this test's ok/docs/commit_count assertions alone do NOT catch it (a
    real/fake Firestore client raises "component is not a string or is
    empty" on .document(None), which the function's own broad except
    Exception then catches -- so the OUTWARD behavior "returns False,
    writes nothing" looks identical whether the guard exists or the call
    crashed and was swallowed). The get_db spy below is what actually
    distinguishes the two: an intentional early return never reaches
    _get_db() at all; a caught crash calls it first. Confirmed by mutation
    (removing the guard leaves ok/docs/commit_count all still green, but
    turns get_db_calls from [] into a non-empty list).
    """
    calls = []
    real_get_db = usage_rollups._get_db
    import unittest.mock as _mock
    with _mock.patch.object(
        usage_rollups, "_get_db",
        side_effect=lambda: (calls.append(1), real_get_db())[1],
    ):
        ok = usage_rollups.record_session_end(
            firm_id=None, kit_id="i-90", employee_id="e1", language=None,
            channel="demo", kind="live", completion_status="completed",
            cost_usd=1.0, now=_NOW,
        )
    assert ok is False
    assert db.docs == {}
    assert db.commit_count == 0
    assert calls == [], (
        "a firm-less session must return early WITHOUT ever reaching "
        "_get_db() -- reaching it (even if the resulting write then fails "
        "and is caught) is the guard being removed, not the guard working"
    )


# ---------------------------------------------------------------------------
# Exit criterion 2: hyphenated kit id and language code nest correctly
# ---------------------------------------------------------------------------


def test_a_HYPHENATED_kit_id_increments_the_INTENDED_nested_field(db):
    """EXIT CRITERION 2. kit_id="i-90" must land at
    firm.by_kit["i-90"]["sessions"], a REAL nested dict entry under the
    single key "i-90" -- not a top-level field literally named
    "by_kit.i-90.sessions" (the failure mode a flat dotted string produces
    under set(merge=True), and not two levels ("i" and "90") from a naive
    split on "-").

    Mutation: replace usage_rollups._nest_increment's FieldPath(*parts).parts
    walk with a hand-built ".".join(parts) dotted STRING key handed straight
    to set(merge=True) -- red, because this fake (which faithfully mirrors
    Firestore's own non-dot-expanding merge extractor) would store that
    string as one flat top-level key instead of nesting under by_kit ->
    "i-90" -> sessions, and this assertion's KeyError/lookup fails.
    """
    usage_rollups.record_session_end(
        firm_id="acme", kit_id="i-90", employee_id=None, language=None,
        channel="demo", kind="live", completion_status="completed",
        cost_usd=3.0, now=_NOW,
    )
    firm = db.docs[_FIRM_DOC]
    assert isinstance(firm["by_kit"], dict)
    assert set(firm["by_kit"].keys()) == {"i-90"}, (
        "the hyphen must not split into separate map levels"
    )
    assert firm["by_kit"]["i-90"] == {"sessions": 1, "cost_usd": pytest.approx(3.0)}
    # And no flat dotted-string field leaked in at the top level.
    assert not any("." in k for k in firm if isinstance(k, str) and k != "by_kit"), (
        "no literal dotted-string top-level key should exist"
    )
    assert "by_kit.i-90.sessions" not in firm


def test_a_SLASHED_kit_id_is_DROPPED_not_written_as_a_path_segment(db):
    """Opus cross-surface finding 1 (bd polyglot-pdf-w828m): a STAFF
    session's handshake kit_id is raw client input (websocket_routes.py's
    client-link branch is the only guard, and it does not run for staff).
    firestore.Client.document() does not reject embedded slashes, so
    kit_id="a/b/c" would otherwise commit to kits/a/b/c/usage/... -- a path
    this module never intended to touch -- instead of being refused.

    Mutation: delete the `kit_id = _safe_kit_id(kit_id)` line in
    record_session_end -- red, because this fake's _Collection.document()
    naively concatenates the raw id into the path (exactly like real
    Firestore does NOT validate it either), so kits/a/b/c/usage/2026-09
    would appear in db.docs and this test's absence assertions fail.
    """
    ok = usage_rollups.record_session_end(
        firm_id="acme", kit_id="a/b/c", employee_id=None, language=None,
        channel="demo", kind="live", completion_status="completed",
        cost_usd=1.0, now=_NOW,
    )
    assert ok is True, "the firm-side write must still happen"
    assert "kits/a/b/c/usage/2026-09" not in db.docs
    assert not any(path.startswith("kits/a/b/c") for path in db.docs), (
        "no document under the attacker-chosen path should be written"
    )
    firm = db.docs[_FIRM_DOC]
    assert "by_kit" not in firm, (
        "an invalid kit_id must be dropped, not used as a by_kit map key"
    )


def test_a_PATH_TRAVERSAL_kit_id_is_DROPPED(db):
    """kit_id=".." must never reach .document() or a by_kit map key.

    Mutation: same as above -- delete the _safe_kit_id call -- red because
    the fake would happily record kits/../usage/2026-09.
    """
    ok = usage_rollups.record_session_end(
        firm_id="acme", kit_id="..", employee_id=None, language=None,
        channel="demo", kind="live", completion_status="completed",
        cost_usd=1.0, now=_NOW,
    )
    assert ok is True
    assert not any(".." in path for path in db.docs)
    assert "by_kit" not in db.docs[_FIRM_DOC]


def test_a_VALID_kit_id_still_writes_the_kit_doc(db):
    """Sanity check the guard is not overbroad: a genuinely valid kit id
    (matching form_kit_routes.py's own charset) must still write both docs.

    Mutation: tighten _KIT_ID_RE to reject hyphens -- red, because "i-90"
    (an existing real kit id used throughout this file) would then be
    dropped and kits/i-90/usage/2026-09 would never appear.
    """
    ok = usage_rollups.record_session_end(
        firm_id="acme", kit_id="i-90", employee_id=None, language=None,
        channel="demo", kind="live", completion_status="completed",
        cost_usd=1.0, now=_NOW,
    )
    assert ok is True
    assert _KIT_DOC in db.docs
    assert db.docs[_FIRM_DOC]["by_kit"]["i-90"]["sessions"] == 1


def test_a_NON_STRING_kit_id_is_DROPPED_not_raised(db):
    """A dict/list/int kit_id (e.g. a malformed handshake payload) must
    degrade to kit-less, matching this module's never-raise contract --
    not raise TypeError out of .document() or _nest_increment.

    Mutation: remove the isinstance(kit_id, str) check from _safe_kit_id --
    red, because _KIT_ID_RE.fullmatch(kit_id) raises TypeError on a
    non-string and the whole record_session_end call would then be caught
    by the module's broad except and return False, silently dropping the
    FIRM-side write too (not just the kit-side one).
    """
    ok = usage_rollups.record_session_end(
        firm_id="acme", kit_id={"bad": "shape"}, employee_id=None,
        language=None, channel="demo", kind="live",
        completion_status="completed", cost_usd=1.0, now=_NOW,
    )
    assert ok is True, "a bad kit_id shape must not sink the firm-side write"
    assert db.docs[_FIRM_DOC]["connections_ended"] == 1
    assert "by_kit" not in db.docs[_FIRM_DOC]


def test_a_HYPHENATED_language_code_increments_the_INTENDED_nested_field(db):
    """EXIT CRITERION 2, the language half. language="zh-CN" must land at
    firm.by_language["zh-CN"]["sessions"], not mis-nested or split on the
    hyphen.
    """
    usage_rollups.record_session_end(
        firm_id="acme", kit_id=None, employee_id=None, language="zh-CN",
        channel="demo", kind="live", completion_status="completed",
        cost_usd=0.0, now=_NOW,
    )
    firm = db.docs[_FIRM_DOC]
    assert set(firm["by_language"].keys()) == {"zh-CN"}
    assert firm["by_language"]["zh-CN"]["sessions"] == 1


def test_TWO_hyphenated_kit_ids_ACCUMULATE_INDEPENDENTLY(db):
    """Two different hyphenated kit ids must not collide or overwrite each
    other's counters -- proves the nesting is truly per-key, not a shared
    bucket the hyphen happens to route into.
    """
    usage_rollups.record_session_end(
        firm_id="acme", kit_id="i-90", employee_id=None, language=None,
        channel="demo", kind="live", completion_status="completed",
        cost_usd=1.0, now=_NOW,
    )
    usage_rollups.record_session_end(
        firm_id="acme", kit_id="n-400", employee_id=None, language=None,
        channel="demo", kind="live", completion_status="completed",
        cost_usd=2.0, now=_NOW + 5,
    )
    firm = db.docs[_FIRM_DOC]
    assert firm["by_kit"]["i-90"]["sessions"] == 1
    assert firm["by_kit"]["n-400"]["sessions"] == 1
    assert firm["by_kit"]["i-90"]["cost_usd"] == pytest.approx(1.0)
    assert firm["by_kit"]["n-400"]["cost_usd"] == pytest.approx(2.0)


def test_a_hyphenated_kit_id_ACCUMULATES_ACROSS_TWO_CONNECTIONS(db):
    """The map-nested Increment must actually ACCUMULATE across writes (not
    just work once) -- proves the merge, not just the first insert.
    """
    usage_rollups.record_session_end(
        firm_id="acme", kit_id="i-90", employee_id=None, language=None,
        channel="demo", kind="live", completion_status="completed",
        cost_usd=1.0, now=_NOW,
    )
    usage_rollups.record_session_end(
        firm_id="acme", kit_id="i-90", employee_id=None, language=None,
        channel="demo", kind="live", completion_status="abandoned",
        cost_usd=0.5, now=_NOW + 5,
    )
    firm = db.docs[_FIRM_DOC]
    assert firm["by_kit"]["i-90"]["sessions"] == 2
    assert firm["by_kit"]["i-90"]["cost_usd"] == pytest.approx(1.5)


# ---------------------------------------------------------------------------
# Channel partitioning (Opus cross-surface, bd polyglot-pdf-w828m finding 2)
# ---------------------------------------------------------------------------


def test_a_STAGING_session_does_NOT_touch_the_DEMO_months_totals(db):
    """Staging and demo share one Firestore project (CLAUDE.md "Deployment /
    promotion"). Before the channel-suffixed doc id, both channels wrote
    the SAME firms/{firm_id}/usage/{YYYY-MM} document, so a staging
    test-drive would inflate the demo firm's connections_ended and
    cost_usd_total -- the numbers bd polyglot-pdf-mpebj's admin console
    reads as per-firm billing input.

    Mutation: hard-code the demo doc id in _month_key (drop the channel
    suffix) -- red, because the staging call's increment lands on
    _FIRM_DOC instead of a separate document and this assertion fails.
    """
    usage_rollups.record_session_end(
        firm_id="acme", kit_id=None, employee_id=None, language=None,
        channel="demo", kind="live", completion_status="completed",
        cost_usd=5.0, now=_NOW,
    )
    usage_rollups.record_session_end(
        firm_id="acme", kit_id=None, employee_id=None, language=None,
        channel="staging", kind="live", completion_status="completed",
        cost_usd=9.0, now=_NOW,
    )
    demo_doc = db.docs[_FIRM_DOC]
    assert demo_doc["connections_ended"] == 1
    assert demo_doc["cost_usd_total"] == pytest.approx(5.0)
    assert demo_doc["channel"] == "demo"

    staging_doc = db.docs["firms/acme/usage/2026-09_staging"]
    assert staging_doc["connections_ended"] == 1
    assert staging_doc["cost_usd_total"] == pytest.approx(9.0)
    assert staging_doc["channel"] == "staging"


def test_a_STAGING_session_does_NOT_touch_the_DEMO_kit_doc_either(db):
    """Same partitioning, kit side."""
    usage_rollups.record_session_end(
        firm_id="acme", kit_id="i-90", employee_id=None, language=None,
        channel="demo", kind="live", completion_status="completed",
        cost_usd=1.0, now=_NOW,
    )
    usage_rollups.record_session_end(
        firm_id="acme", kit_id="i-90", employee_id=None, language=None,
        channel="staging", kind="live", completion_status="completed",
        cost_usd=2.0, now=_NOW,
    )
    demo_kit_doc = db.docs[_KIT_DOC]
    assert demo_kit_doc["cost_usd_total"] == pytest.approx(1.0)

    staging_kit_doc = db.docs["kits/i-90/usage/2026-09_staging"]
    assert staging_kit_doc["cost_usd_total"] == pytest.approx(2.0)


def test_the_demo_channel_keeps_the_BARE_month_id(db):
    """The demo channel is the pre-existing default: its doc id must stay
    the bare "YYYY-MM" so nothing already written under it is orphaned
    (mirrors bd polyglot-pdf-3q9qn's link_redemptions/links_store
    convention exactly).
    """
    usage_rollups.record_session_end(
        firm_id="acme", kit_id=None, employee_id=None, language=None,
        channel="demo", kind="live", completion_status="completed",
        cost_usd=1.0, now=_NOW,
    )
    assert _FIRM_DOC in db.docs
    assert "firms/acme/usage/2026-09_demo" not in db.docs


def test_link_opened_and_completed_counters_are_ALSO_channel_partitioned(
    db, monkeypatch,
):
    """record_link_opened/record_link_completed share the SAME rollup
    document as record_session_end (_increment_firm_counter), so they must
    resolve the same channel-suffixed doc id -- via this process's own
    link_channel(), since neither open_link() nor complete_link() is ever
    called with an explicit channel argument (both run only on the public
    backend, which has exactly one channel of its own).
    """
    monkeypatch.setenv("LINK_CHANNEL", "staging")
    usage_rollups.record_link_opened("acme", now=_NOW)
    usage_rollups.record_link_completed("acme", now=_NOW)

    assert _FIRM_DOC not in db.docs
    staging_doc = db.docs["firms/acme/usage/2026-09_staging"]
    assert staging_doc["links_opened"] == 1
    assert staging_doc["links_completed"] == 1


# ---------------------------------------------------------------------------
# Best-effort / never-raises
# ---------------------------------------------------------------------------


def test_a_commit_failure_never_raises(db):
    """Mutation: remove the try/except around batch.commit() in
    record_session_end -- red, RuntimeError propagates instead of a clean
    False return.
    """
    db.commit_error = "firestore unavailable"
    ok = usage_rollups.record_session_end(
        firm_id="acme", kit_id="i-90", employee_id=None, language=None,
        channel="demo", kind="live", completion_status="completed",
        cost_usd=1.0, now=_NOW,
    )
    assert ok is False


def test_get_db_returning_None_never_raises_and_writes_nothing(monkeypatch):
    monkeypatch.setattr(usage_rollups, "_get_db", lambda: None)
    ok = usage_rollups.record_session_end(
        firm_id="acme", kit_id="i-90", employee_id=None, language=None,
        channel="demo", kind="live", completion_status="completed",
        cost_usd=1.0, now=_NOW,
    )
    assert ok is False


def test_get_db_itself_RAISING_never_propagates(monkeypatch):
    """Mirrors alerts.py's own regression test: get_db() can RAISE (a
    broken firebase_admin app), not just return None.
    """
    def _broken_get_db():
        raise AttributeError("'_FakeFirestoreModule' object has no attribute 'client'")

    monkeypatch.setattr("backend.services.auth.get_db", _broken_get_db)
    ok = usage_rollups.record_session_end(
        firm_id="acme", kit_id="i-90", employee_id=None, language=None,
        channel="demo", kind="live", completion_status="completed",
        cost_usd=1.0, now=_NOW,
    )
    assert ok is False


# ---------------------------------------------------------------------------
# links_opened / links_completed hooks (record_link_opened / _completed)
# ---------------------------------------------------------------------------


def test_record_link_opened_increments_the_firm_doc(db):
    ok = usage_rollups.record_link_opened("acme", now=_NOW)
    assert ok is True
    assert db.docs[_FIRM_DOC]["links_opened"] == 1


def test_record_link_completed_increments_the_firm_doc(db):
    ok = usage_rollups.record_link_completed("acme", now=_NOW)
    assert ok is True
    assert db.docs[_FIRM_DOC]["links_completed"] == 1


def test_record_link_opened_with_no_firm_id_writes_nothing(db):
    ok = usage_rollups.record_link_opened(None, now=_NOW)
    assert ok is False
    assert db.docs == {}


def test_record_link_opened_never_raises_on_a_write_failure(monkeypatch):
    class _RaisingDb:
        def collection(self, name):
            raise RuntimeError("boom")

    monkeypatch.setattr(usage_rollups, "_get_db", lambda: _RaisingDb())
    ok = usage_rollups.record_link_opened("acme", now=_NOW)
    assert ok is False


# ---------------------------------------------------------------------------
# Wiring: link_redemptions.py actually calls the rollup hooks
# ---------------------------------------------------------------------------


def test_open_link_calls_record_link_opened_ONLY_on_a_GENUINE_first_open(
        monkeypatch, db):
    """Mutation: move the record_link_opened() call in link_redemptions.
    open_link() so it also fires on the idempotent re-open branch
    (snap.exists) -- red, links_opened would be 2 instead of 1 after the
    second call.
    """
    from backend.services import link_redemptions

    monkeypatch.setattr(link_redemptions, "_enabled", lambda: True)

    class _Snap:
        def __init__(self, data):
            self._data = data

        @property
        def exists(self):
            return self._data is not None

        def to_dict(self):
            return dict(self._data) if self._data else None

    class _Doc:
        def __init__(self):
            self._data = None

        def get(self):
            return _Snap(self._data)

        def set(self, rec):
            self._data = dict(rec)

    class _Coll:
        def __init__(self):
            self._doc = _Doc()

        def document(self, jti):
            return self._doc

    coll = _Coll()
    monkeypatch.setattr(link_redemptions, "_collection", lambda: coll)

    link_redemptions.open_link("jti-a", "acme", "i-90", now=_NOW)
    assert db.docs[_FIRM_DOC]["links_opened"] == 1

    # Re-open the SAME link (idempotent path) -- must NOT increment again.
    link_redemptions.open_link("jti-a", "acme", "i-90", now=_NOW + 100)
    assert db.docs[_FIRM_DOC]["links_opened"] == 1


def test_complete_link_calls_record_link_completed(monkeypatch, db):
    """Mutation: delete the record_link_completed(...) call from
    link_redemptions.complete_link() -- red, links_completed doc never
    appears.
    """
    from backend.services import link_redemptions

    class _Snap:
        exists = True

        def to_dict(self):
            return {"jti": "jti-a", "firm_id": "acme", "kit_id": "i-90"}

    class _Doc:
        def update(self, data):
            pass

        def get(self):
            return _Snap()

    class _Coll:
        def document(self, jti):
            return _Doc()

    monkeypatch.setattr(link_redemptions, "_collection", lambda: _Coll())

    link_redemptions.complete_link("jti-a", now=_NOW)
    assert db.docs[_FIRM_DOC]["links_completed"] == 1


# ---------------------------------------------------------------------------
# websocket_routes.py's teardown-call helpers (_session_cost_usd,
# _rollup_language_key) -- small pure functions this bead adds to wire
# record_session_end's cost and language arguments.
# ---------------------------------------------------------------------------


def test_session_cost_usd_reads_the_live_adapter():
    from backend.routes import websocket_routes as wr

    class _Ai:
        def session_cost_usd(self):
            return 4.5

    class _Service:
        live_ai = _Ai()

    assert wr._session_cost_usd(_Service()) == pytest.approx(4.5)


def test_session_cost_usd_returns_0_when_service_has_no_live_ai():
    """Mutation: drop the `getattr(service, "live_ai", None)` default and
    use `service.live_ai` directly -- red, this raises AttributeError
    instead of returning 0.0 for a service with no adapter attribute at
    all (a plausible pre-connect teardown shape).
    """
    from backend.routes import websocket_routes as wr

    class _Service:
        pass

    assert wr._session_cost_usd(_Service()) == 0.0


def test_session_cost_usd_never_raises_on_a_broken_adapter():
    from backend.routes import websocket_routes as wr

    class _Ai:
        def session_cost_usd(self):
            raise RuntimeError("adapter torn down")

    class _Service:
        live_ai = _Ai()

    assert wr._session_cost_usd(_Service()) == 0.0


def test_rollup_language_key_prefers_the_bcp47_code():
    """Mutation: return the raw name unconditionally (drop the
    bcp47_codes_for_spoken_language call) -- red, this would see "Spanish"
    instead of "es-US".
    """
    from backend.routes import websocket_routes as wr

    class _Service:
        def spoken_language(self):
            return "Spanish"

    assert wr._rollup_language_key(_Service()) == "es-US"


def test_rollup_language_key_falls_back_to_the_raw_name_when_uncoded():
    """A future spoken language not yet in the BCP-47 map must still be
    counted, under its plain name, per the never-pin-a-language doctrine.

    Mutation: change the fallback from `name` to `None` -- red, an
    uncoded language would vanish from by_language entirely.
    """
    from backend.routes import websocket_routes as wr

    class _Service:
        def spoken_language(self):
            return "Klingon"

    assert wr._rollup_language_key(_Service()) == "Klingon"


def test_rollup_language_key_returns_None_for_no_language():
    from backend.routes import websocket_routes as wr

    class _Service:
        def spoken_language(self):
            return ""

    assert wr._rollup_language_key(_Service()) is None
