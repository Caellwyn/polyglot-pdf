"""Firms datastore service (bd polyglot-pdf-lo88).

Pins the two load-bearing contracts of backend/services/firms.py:

- FAIL-CLOSED reads: get_allowed_kits returns [] on EVERY failure branch
  (disabled store, missing firm, non-active firm, malformed doc, read error)
  -- bd polyglot-pdf-vccy will gate PRIVATE kit visibility on this call, so
  any fail-open branch here becomes an information-disclosure bug there.
- Idempotent upserts: re-running the bootstrap must not corrupt created_at,
  must merge (not clobber), and upsert failures RAISE (the operator script
  maps them to exit 2 -- an admin tool must never silently no-op).

The fakes extend test_confirmation_firestore_sink.py's _FakeDB shape (that
one has no document-get()/snapshot support, which a read-modify-write needs),
kept local to this file like the precedent.

Each test's docstring names the mutation that must turn it red
(docs/standards/testing.md#test-the-tests).

ASCII only.
"""
import threading
import time
import pytest
from firebase_admin import firestore as fb_firestore

import backend.services.firms as firms


class _FakeSnap:
    def __init__(self, data):
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _FakeDocRef:
    def __init__(self, store, doc_id):
        self._store = store
        self._doc_id = doc_id
        self.set_calls = []  # list of (payload, merge)

    def get(self):
        return _FakeSnap(self._store.get(self._doc_id))

    def set(self, payload, merge=False):
        self.set_calls.append((dict(payload), merge))
        if merge and self._doc_id in self._store:
            self._store[self._doc_id].update(payload)
        else:
            self._store[self._doc_id] = dict(payload)


class _FakeCollection:
    def __init__(self):
        self.store = {}
        self.doc_refs = {}
        self.stream_docs = []
        self.limit_calls = []

    def document(self, doc_id):
        return self.doc_refs.setdefault(
            doc_id, _FakeDocRef(self.store, doc_id)
        )

    def limit(self, n):
        self.limit_calls.append(n)
        return self

    def stream(self):
        return iter(self.stream_docs)


class _FakeDB:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        return self.collections.setdefault(name, _FakeCollection())


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDB()
    monkeypatch.setenv("FIRMS_FIRESTORE_ENABLED", "true")
    monkeypatch.setattr("backend.services.auth.get_db", lambda: db)
    return db


def _firm_doc(**over):
    doc = {
        "name": "Acme Legal Aid",
        "contact_email": "intake@acme.example",
        "allowed_kits": ["w7", "i-90"],
        "status": "active",
    }
    doc.update(over)
    return doc


def _exploding_get_db():
    raise AssertionError("get_db must not be touched on this path")


# ---------------------------------------------------------------- reads


def test_get_allowed_kits_is_inert_when_disabled(monkeypatch):
    """Mutation: invert the _firms_enabled() gate -- the explode-mock fires."""
    monkeypatch.delenv("FIRMS_FIRESTORE_ENABLED", raising=False)
    monkeypatch.setattr("backend.services.auth.get_db", _exploding_get_db)
    assert firms.get_allowed_kits("acme") == []


@pytest.mark.parametrize(
    "case",
    [
        "missing_firm",
        "suspended",
        "kits_not_a_list",
        "kits_mixed_types",
        "read_raises",
    ],
)
def test_get_allowed_kits_fails_closed_to_empty_list(fake_db, monkeypatch, case):
    """Every failure branch resolves to [] -- a list, never None, never a
    raise (a None leaking into `kit_id in allowed` raises instead of
    denying). A list with ANY non-string entry is malformed and fails the
    WHOLE doc closed -- no partial filtering (round-2 fresh-eyes: the code
    contradicted its own every-failure-to-[] docstring). Mutation per
    branch: delete that branch's guard in get_allowed_kits (the not-exists
    early return, the status gate, the isinstance/all check -- for
    kits_mixed_types, revert it to a per-entry isinstance filter -- the
    try/except) -- the corresponding parametrization goes red."""
    col = fake_db.collection(firms._FIRMS_COLLECTION)
    if case == "suspended":
        col.store["acme"] = _firm_doc(status="suspended")
    elif case == "kits_not_a_list":
        col.store["acme"] = _firm_doc(allowed_kits="w7")
    elif case == "kits_mixed_types":
        col.store["acme"] = _firm_doc(allowed_kits=["w7", 123, None])
    elif case == "read_raises":
        def _boom():
            raise RuntimeError("iam drift")

        monkeypatch.setattr("backend.services.auth.get_db", _boom)
    # missing_firm: store stays empty on purpose.

    result = firms.get_allowed_kits("acme")

    assert isinstance(result, list)
    assert result == []


def test_get_allowed_kits_returns_stored_list_for_active_firm(fake_db):
    """The positive case. Mutation: return [] unconditionally -- red."""
    fake_db.collection(firms._FIRMS_COLLECTION).store["acme"] = _firm_doc()
    assert firms.get_allowed_kits("acme") == ["w7", "i-90"]


# ------------------------------------------------------------- firm_kind


def test_firm_kind_is_live_when_disabled(monkeypatch):
    """Mutation: invert the _firms_enabled() gate -- the explode-mock fires
    instead of the fail-closed-to-live default."""
    monkeypatch.delenv("FIRMS_FIRESTORE_ENABLED", raising=False)
    monkeypatch.setattr("backend.services.auth.get_db", _exploding_get_db)
    assert firms.firm_kind("acme") == firms.FIRM_KIND_LIVE


@pytest.mark.parametrize(
    "case",
    ["missing_firm", "no_kind_key", "malformed_kind", "read_raises"],
)
def test_firm_kind_fails_closed_to_live(fake_db, monkeypatch, case):
    """Every failure branch resolves to "live" -- the OPPOSITE polarity from
    get_allowed_kits' fail-closed-to-[]: widening kit visibility is the risk
    there, minting for free without the live-firm gate is the risk here, and
    "live" is what SUBJECTS a firm to that gate. A doc with no `kind` key at
    all (the pre-backfill window, bd polyglot-pdf-d4wdi) gets the same
    treatment on purpose -- that is exit criterion 3's "missing kind is
    live" requirement. Mutation per branch: delete that branch's guard in
    firm_kind (the not-exists early return, the kind-membership check, the
    try/except) -- the corresponding parametrization goes red."""
    col = fake_db.collection(firms._FIRMS_COLLECTION)
    if case == "no_kind_key":
        doc = _firm_doc()
        doc.pop("kind", None)
        col.store["acme"] = doc
    elif case == "malformed_kind":
        col.store["acme"] = _firm_doc(kind="trial")
    elif case == "read_raises":
        def _boom():
            raise RuntimeError("iam drift")

        monkeypatch.setattr("backend.services.auth.get_db", _boom)
    # missing_firm: store stays empty on purpose.

    assert firms.firm_kind("acme") == firms.FIRM_KIND_LIVE


def test_firm_kind_returns_stored_mock(fake_db):
    """The positive case for the OTHER value: a doc explicitly marked mock
    must not be swept into the live fail-closed default. Mutation: return
    FIRM_KIND_LIVE unconditionally -- red."""
    fake_db.collection(firms._FIRMS_COLLECTION).store["acme"] = _firm_doc(
        kind="mock"
    )
    assert firms.firm_kind("acme") == firms.FIRM_KIND_MOCK


def test_firm_kind_returns_stored_live(fake_db):
    """The positive case for an explicitly-live doc, so the mock test above
    is not the only positive path exercised. Mutation: return
    FIRM_KIND_MOCK unconditionally -- red."""
    fake_db.collection(firms._FIRMS_COLLECTION).store["acme"] = _firm_doc(
        kind="live"
    )
    assert firms.firm_kind("acme") == firms.FIRM_KIND_LIVE


# --------------------------------------------------------------- upserts


def test_upsert_first_write_sets_created_at_server_timestamp(fake_db):
    """POSITIVE pin on the first write: created_at present and IS the
    SERVER_TIMESTAMP sentinel (key-existence alone would pass with any
    garbage value). Mutation: drop created_at from the first-write payload
    -- red."""
    firms.upsert_firm("acme", "Acme", "a@x.example", ["w7"], "live")

    ref = fake_db.collection(firms._FIRMS_COLLECTION).document("acme")
    payload, merge = ref.set_calls[0]
    assert merge is False
    assert payload["created_at"] is fb_firestore.SERVER_TIMESTAMP
    assert payload["updated_at"] is fb_firestore.SERVER_TIMESTAMP
    assert payload["allowed_kits"] == ["w7"]
    assert payload["status"] == "active"
    assert payload["kind"] == "live"


def test_upsert_rerun_omits_created_at_and_merges(fake_db):
    """The idempotency pin: the SECOND call's payload must carry NO
    created_at key (a SERVER_TIMESTAMP there would overwrite the original
    creation time on every re-run) AND must use merge=True (a bare set()
    would wipe fields the doc gained elsewhere). Mutation (named in the
    plan): make upsert_firm unconditionally include created_at -> the
    no-created_at assertion goes red; drop merge=True -> the merge
    assertion goes red."""
    firms.upsert_firm("acme", "Acme", "a@x.example", ["w7"], "live")
    firms.upsert_firm("acme", "Acme Legal", "a@x.example", ["w7", "i-90"], "live")

    ref = fake_db.collection(firms._FIRMS_COLLECTION).document("acme")
    assert len(ref.set_calls) == 2
    payload2, merge2 = ref.set_calls[1]
    assert merge2 is True
    assert "created_at" not in payload2
    assert payload2["updated_at"] is fb_firestore.SERVER_TIMESTAMP
    assert payload2["allowed_kits"] == ["w7", "i-90"]
    # balance_credits and balance_updated_at belong to the ledger helper
    # (Epic 2 bead A2) alone from the SECOND write onward -- re-including
    # them here would zero out a real balance on every re-bootstrap.
    assert "balance_credits" not in payload2
    assert "balance_updated_at" not in payload2


def test_upsert_first_write_sets_balance_credits_zero(fake_db):
    """POSITIVE pin: a brand-new firm starts at balance_credits=0 with
    balance_updated_at stamped, so the ledger invariant
    (balance_credits == sum(amount)) holds from doc creation, before any
    ledger entry exists. Mutation: drop the balance_credits=0 seed from the
    first-write payload -- red."""
    firms.upsert_firm("acme", "Acme", "a@x.example", ["w7"], "live")

    ref = fake_db.collection(firms._FIRMS_COLLECTION).document("acme")
    payload, _ = ref.set_calls[0]
    assert payload["balance_credits"] == 0
    assert payload["balance_updated_at"] is fb_firestore.SERVER_TIMESTAMP


def test_upsert_rejects_unknown_status(fake_db):
    """The write layer validates status against the closed set (the CLI's
    argparse choices are a separate layer; a future non-CLI caller passing
    junk would store a status that silently fail-closes the firm).
    Mutation: remove the status guard in upsert_firm -- red."""
    with pytest.raises(ValueError):
        firms.upsert_firm(
            "acme", "Acme", "a@x.example", [], "live", status="bogus"
        )
    assert fake_db.collection(firms._FIRMS_COLLECTION).store == {}


def test_upsert_rejects_unknown_kind(fake_db):
    """The write layer validates kind against the closed set, mirroring the
    status guard: a future non-CLI caller passing junk (or a typo) must not
    silently write an unrecognized kind that firm_kind() would then treat as
    its fail-closed default. Mutation: remove the kind guard in upsert_firm
    -- red."""
    with pytest.raises(ValueError):
        firms.upsert_firm("acme", "Acme", "a@x.example", [], "trial")
    assert fake_db.collection(firms._FIRMS_COLLECTION).store == {}


def test_upsert_writes_the_given_kind(fake_db):
    """POSITIVE pin: kind lands verbatim in the doc, and is re-written on
    every merge (unlike balance_credits) -- a re-bootstrap with a different
    --kind is how an operator corrects a mis-classified firm before the
    admin console's PATCH .../kind route exists. Mutation: hardcode
    FIRM_KIND_LIVE in the payload instead of the kind param -- red."""
    firms.upsert_firm("acme", "Acme", "a@x.example", [], "mock")

    ref = fake_db.collection(firms._FIRMS_COLLECTION).document("acme")
    payload, _ = ref.set_calls[0]
    assert payload["kind"] == "mock"


def test_upsert_is_ungated_by_the_env_var(monkeypatch):
    """upsert_firm is the operator path and must work with the read gate
    off (the script would otherwise silently no-op). Mutation: add a
    _firms_enabled() early return to upsert_firm -- red."""
    monkeypatch.delenv("FIRMS_FIRESTORE_ENABLED", raising=False)
    db = _FakeDB()
    monkeypatch.setattr("backend.services.auth.get_db", lambda: db)

    firms.upsert_firm("acme", "Acme", "a@x.example", [], "live")

    assert "acme" in db.collection(firms._FIRMS_COLLECTION).store


def test_upsert_raises_on_store_failure(monkeypatch):
    """Upsert failures RAISE (loud admin tool), unlike the fail-closed
    reads. Mutation: wrap upsert_firm's body in try/except-return -- red."""
    monkeypatch.setenv("FIRMS_FIRESTORE_ENABLED", "true")

    def _boom():
        raise RuntimeError("no creds")

    monkeypatch.setattr("backend.services.auth.get_db", _boom)
    with pytest.raises(RuntimeError):
        firms.upsert_firm("acme", "Acme", "a@x.example", [], "live")


# ----------------------------------------------------------------- probe


@pytest.fixture(autouse=True)
def _reset_probe_cache():
    """Clear the firms probe cache around EVERY test in this file.

    firms_store_status() gained a process-wide cache + in-flight Event
    when it was wired into /health (bd polyglot-pdf-vq5wd /
    polyglot-pdf-e4dt8). Without this reset the tests below leak into each
    other: the 'ok' this file probes first is still cached when the error
    test runs, so the error test passes on a STALE 'ok' and asserts
    nothing (observed -- it went red for exactly this reason before the
    fixture existed).
    """
    firms._probe_cache = None
    firms._probe_in_flight = None
    yield
    firms._probe_cache = None
    firms._probe_in_flight = None



def test_firms_store_status_disabled(monkeypatch):
    """Mutation: invert the gate -- 'disabled' never returned."""
    monkeypatch.delenv("FIRMS_FIRESTORE_ENABLED", raising=False)
    monkeypatch.setattr("backend.services.auth.get_db", _exploding_get_db)
    assert firms.firms_store_status() == "disabled"


def test_firms_store_status_ok_and_read_shaped(fake_db):
    """The probe must be READ-shaped: 'ok' with ZERO document writes (the
    sink probe's write+delete shape would test the wrong permission for a
    read-only path). Mutation: switch the probe to the sink's write+delete
    -- the no-writes assertion goes red."""
    assert firms.firms_store_status() == "ok"

    col = fake_db.collection(firms._FIRMS_COLLECTION)
    assert col.limit_calls == [1]
    assert all(not ref.set_calls for ref in col.doc_refs.values())


def test_firms_store_status_reports_error(monkeypatch):
    """Mutation: swallow the exception into 'ok' -- red."""
    monkeypatch.setenv("FIRMS_FIRESTORE_ENABLED", "true")

    def _boom():
        raise RuntimeError("iam drift")

    monkeypatch.setattr("backend.services.auth.get_db", _boom)
    assert firms.firms_store_status().startswith("error:")

def test_firms_store_status_caches_within_max_age(fake_db):
    """A second call inside the window does NOT hit Firestore again.

    /health is UNAUTHENTICATED, so any caller can poll it at their own
    rate; without the cache each poll is a Firestore round trip. Mutation:
    delete the cache read at the top of firms_store_status -- limit_calls
    grows to [1, 1] and this goes red.
    """
    assert firms.firms_store_status() == "ok"
    assert firms.firms_store_status() == "ok"

    col = fake_db.collection(firms._FIRMS_COLLECTION)
    assert col.limit_calls == [1], (
        "the probe ran twice inside the cache window: " + repr(col.limit_calls))


def test_firms_store_status_reprobes_after_the_window(fake_db):
    """max_age_s=0 forces a fresh probe -- the cache expires, it does not
    pin the first answer forever. Without this, a cache that never expired
    would pass the test above and report a long-dead 'ok' in production.
    """
    assert firms.firms_store_status() == "ok"
    assert firms.firms_store_status(max_age_s=0) == "ok"

    col = fake_db.collection(firms._FIRMS_COLLECTION)
    assert col.limit_calls == [1, 1], (
        "an expired cache did not re-probe: " + repr(col.limit_calls))


def test_firms_store_status_coalesces_concurrent_callers(monkeypatch):
    """N concurrent callers on a cold cache produce ONE Firestore round trip.

    The cache alone does not give this: N threads arriving together all see
    an empty cache and all fall through. The in-flight Event is what makes
    the second through Nth wait for the first.

    THE PROBE IS DELIBERATELY SLOW (a 0.3s sleep inside get_db). With the
    fake_db fixture's instant probe the threads never actually overlap: the
    first finishes and populates the cache before the others reach the
    check, so they hit the CACHE and the test passes even with coalescing
    removed -- verified by mutation, it did exactly that. The sleep is what
    makes the window real, so this test measures coalescing rather than
    scheduling luck.
    """
    monkeypatch.setenv("FIRMS_FIRESTORE_ENABLED", "true")

    probe_count = []
    count_lock = threading.Lock()

    class _SlowCollection:
        def limit(self, n):
            return self

        def stream(self):
            with count_lock:
                probe_count.append(1)
            time.sleep(0.3)
            return iter([])

    class _SlowDB:
        def collection(self, name):
            return _SlowCollection()

    monkeypatch.setattr("backend.services.auth.get_db", lambda: _SlowDB())

    barrier = threading.Barrier(4)
    results = []
    results_lock = threading.Lock()

    def _call():
        barrier.wait(timeout=5)
        r = firms.firms_store_status()
        with results_lock:
            results.append(r)

    threads = [threading.Thread(target=_call) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert results == ["ok"] * 4, repr(results)
    assert len(probe_count) == 1, (
        "concurrent callers each ran their own Firestore probe ({} of them) -- the in-flight coalescing is not working".format(len(probe_count)))

def test_firms_store_status_disabled_is_not_cached(monkeypatch, fake_db):
    """The disabled short-circuit returns BEFORE the cache is consulted.

    So flipping FIRMS_FIRESTORE_ENABLED on does not leave /health reporting
    a cached 'disabled' for five minutes after the store came up.
    """
    monkeypatch.delenv("FIRMS_FIRESTORE_ENABLED", raising=False)
    assert firms.firms_store_status() == "disabled"

    monkeypatch.setenv("FIRMS_FIRESTORE_ENABLED", "true")
    assert firms.firms_store_status() == "ok"

