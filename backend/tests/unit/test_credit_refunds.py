"""The expiry refund helper (Epic 2 bead A5, plan: "Refund on unopened
expiry"): backend/services/credit_ledger.refund_expired_link() and
reconcile_expired_for_firm(), plus the socket teardown's budget_exhausted
telemetry mirror in backend/routes/websocket_routes.py.

Pins the three exit criteria of bd polyglot-pdf-1op3g:

  1. test_expiry_refund_is_idempotent -- two runs against the same jti leave
     exactly one expiry_refund ledger entry and one balance increment.
  2. test_refund_refuses_when_redemption_exists -- an opened link (the
     AUTHORITATIVE link_redemptions doc present, the best-effort `opened`
     mirror on the links record deliberately MISSING) is never refunded.
  3. test_append_entry_transaction_read_set_is_exactly_the_firm_doc (+ its
     companion test below) -- the shared ledger transaction append_entry()
     uses (the one the future mint route composes on, bd polyglot-pdf-jecrl
     / A3) never performs a reconciliation read, and
     reconcile_expired_for_firm is never called from inside it.

THE FAKE FIRESTORE. Extends test_credit_ledger.py's _FakeDb (buffered
writes, contention re-run) with two things that module does not need:
multiple TOP-LEVEL collections addressed by (collection, doc_id) rather than
only firms/{id}/ledger, and a `.where()`-filtered `.stream()` over a bare
collection for reconcile_expired_for_firm's query. Kept as a fake rather
than a mock for the same reason as test_credit_ledger.py: a mock proves the
code CALLED .where(); it cannot prove the SET of documents returned is
right, and that set is exactly what the idempotency and the
redemption-refuses-a-refund properties depend on.

Each test's docstring names the mutation that must turn it red
(docs/standards/testing.md#test-the-tests).

ASCII only.
"""
import time

import pytest

import backend.services.credit_ledger as credit_ledger
import backend.services.link_redemptions as link_redemptions
import backend.services.links_store as links_store


# ---------------------------------------------------------------- fake db


class _Snap:
    """A POINT-IN-TIME copy, like a real Firestore snapshot (mirrors
    test_credit_ledger.py's _Snap; see that module for why the copy, not a
    live reference, matters for the race tests)."""

    def __init__(self, path, data):
        self._path = path
        self._data = dict(data) if data is not None else None

    @property
    def id(self):
        return self._path[-1]

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _DocRef:
    def __init__(self, store, path):
        self._store = store
        self._path = path
        self.id = path[-1]

    def collection(self, name):
        return _Collection(self._store, self._path + (name,))

    def get(self, transaction=None):
        if transaction is not None:
            transaction.reads.append(self._path)
        return _Snap(self._path, self._store.docs.get(self._path))

    def set(self, data, merge=False):
        self._store.apply_set(self._path, data, merge)


class _Query:
    """Models a Firestore query over ONE top-level collection: equality and
    less-than `.where()` clauses (the only operators reconcile_expired_for_firm
    uses), combined with AND semantics -- the same semantics Firestore itself
    gives multiple .where() calls on one query.
    """

    def __init__(self, store, path, clauses=()):
        self._store = store
        self._path = path
        self._clauses = tuple(clauses)

    def where(self, *args, **kwargs):
        if "filter" in kwargs:
            ff = kwargs["filter"]
            field, op, value = ff.field_path, ff.op_string, ff.value
        else:
            field, op, value = args
        return _Query(self._store, self._path,
                      self._clauses + ((field, op, value),))

    def _matches(self, data):
        for field, op, value in self._clauses:
            actual = data.get(field)
            if op == "==":
                if actual != value:
                    return False
            elif op == "<":
                if actual is None or not (actual < value):
                    return False
            else:
                raise NotImplementedError(op)
        return True

    def stream(self):
        rows = [
            (path, data) for path, data in self._store.docs.items()
            if path[:-1] == self._path and self._matches(data)
        ]
        return iter([_Snap(path, data) for path, data in rows])


class _Collection:
    def __init__(self, store, path):
        self._store = store
        self._path = path

    def document(self, doc_id=None):
        if doc_id is None:
            self._store.auto_id_counter += 1
            doc_id = "auto{}".format(self._store.auto_id_counter)
        return _DocRef(self._store, self._path + (doc_id,))

    def where(self, *args, **kwargs):
        return _Query(self._store, self._path).where(*args, **kwargs)

    def stream(self):
        return _Query(self._store, self._path).stream()


class _Transaction:
    def __init__(self, store):
        self._store = store
        self._buffer = []
        self.reads = []
        self.writes = []

    def set(self, ref, data, merge=False):
        self.writes.append(ref._path)
        self._buffer.append((ref._path, dict(data), merge))

    def commit(self):
        for path, data, merge in self._buffer:
            self._store.apply_set(path, data, merge)
        self._buffer = []

    def reset(self):
        self._buffer = []
        self.reads = []
        self.writes = []


class _FakeDb:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})
        self.auto_id_counter = 0
        self.on_before_commit = None
        self.transactions = []

    def collection(self, name):
        return _Collection(self, (name,))

    def transaction(self):
        tx = _Transaction(self)
        self.transactions.append(tx)
        return tx

    def apply_set(self, path, data, merge):
        if merge and path in self.docs:
            self.docs[path].update(data)
        else:
            self.docs[path] = dict(data)

    # test helpers -------------------------------------------------------
    def firm(self, firm_id):
        return self.docs.get(("firms", firm_id))

    def ledger_rows(self, firm_id):
        rows = [
            data for path, data in self.docs.items()
            if path[:3] == ("firms", firm_id, "ledger")
        ]
        return sorted(rows, key=lambda r: (r["ts"], r["balance_after"]))

    def link(self, jti, channel="demo"):
        name = links_store._collection_name(channel)
        return self.docs.get((name, jti))

    def redemption(self, jti, channel="demo"):
        name = link_redemptions._collection_name(channel)
        return self.docs.get((name, jti))


class _FakeTransactionalDecorator:
    def __init__(self, max_attempts=5):
        self._max_attempts = max_attempts

    def __call__(self, fn):
        def wrapper(transaction):
            store = transaction._store
            for _ in range(self._max_attempts):
                fn(transaction)
                hook = store.on_before_commit
                if hook is not None:
                    store.on_before_commit = None
                    if hook(transaction) == "retry":
                        transaction.reset()
                        continue
                transaction.commit()
                return
            raise RuntimeError("transaction exceeded its retry budget")
        return wrapper


class _FakeFirestoreModule:
    transactional = _FakeTransactionalDecorator()


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDb({("firms", "acme"): {
        "name": "Acme", "status": "active", "kind": "live",
        "balance_credits": 10,
    }})
    import firebase_admin
    monkeypatch.setattr(firebase_admin, "firestore", _FakeFirestoreModule(),
                        raising=False)
    monkeypatch.setattr("backend.services.auth.get_db", lambda: db)
    monkeypatch.setattr("backend.services.link_tokens.link_channel",
                        lambda: "demo")
    return db


def _mint(fake_db, jti="jti-1", firm_id="acme", channel="demo",
          status=links_store.STATUS_MINTED, open_deadline=1000,
          credit_cost=1, kit_id="w7", **over):
    """Write a links[_<channel>]/{jti} mint record directly into the fake
    store -- bypassing record_mint() so a test can set an arbitrary status
    without record_mint's own validation getting in the way (a "not_pending"
    fixture needs status=refunded from the start, which record_mint refuses
    to write)."""
    name = links_store._collection_name(channel)
    record = {
        "jti": jti, "firm_id": firm_id, "kit_id": kit_id,
        "employee_id": "emp-1", "credit_cost": credit_cost, "cap_usd": 5.0,
        "minted_at": 1, "open_deadline": open_deadline, "status": status,
        "revoked_by": None, "revoked_at": None, "expire_at": None,
    }
    record.update(over)
    fake_db.docs[(name, jti)] = record
    return record


def _redeem(fake_db, jti="jti-1", channel="demo", **over):
    """Write the AUTHORITATIVE link_redemptions[_<channel>]/{jti} doc --
    proof a client opened this link -- deliberately WITHOUT touching the
    links record's own `opened` mirror, so a test can prove the refusal
    reads the redemption doc and not the mirror."""
    name = link_redemptions._collection_name(channel)
    record = {"jti": jti, "firm_id": "acme", "kit_id": "w7",
              "opened_at": 1, "completed_at": None}
    record.update(over)
    fake_db.docs[(name, jti)] = record
    return record


# ------------------------------------------------- EXIT CRITERION 1: idempotent


def test_expiry_refund_is_idempotent(fake_db):
    """EXIT CRITERION 1. Running refund_expired_link twice against the SAME
    expired, unopened jti must leave exactly ONE expiry_refund ledger entry
    and credit the firm's balance exactly ONCE -- the second run sees
    status=refunded (written by the first) and refuses.

    Mutation: drop the `if link.get("status") != STATUS_MINTED: raise` check
    in refund_expired_link -- the second call also credits, doubling the
    balance and the entry count. Verified 2026-09-08."""
    _mint(fake_db, credit_cost=3, open_deadline=500)

    first = credit_ledger.refund_expired_link(
        fake_db, "jti-1", actor="system:sweep", now=1000.0)
    assert first["type"] == "expiry_refund"
    assert first["amount"] == 3
    assert fake_db.firm("acme")["balance_credits"] == 13
    assert fake_db.link("jti-1")["status"] == links_store.STATUS_REFUNDED

    with pytest.raises(credit_ledger.LinkNotRefundable) as exc:
        credit_ledger.refund_expired_link(
            fake_db, "jti-1", actor="system:sweep", now=1001.0)
    assert exc.value.reason == "not_pending"

    rows = fake_db.ledger_rows("acme")
    assert len(rows) == 1, "a re-run must not write a second entry"
    assert rows[0]["amount"] == 3
    assert fake_db.firm("acme")["balance_credits"] == 13, (
        "a re-run must not credit the balance twice")


def test_a_sweep_and_a_lazy_reconcile_racing_on_ONE_jti_refund_exactly_once(
        fake_db):
    """The plan's word: "a concurrent sweep-vs-lazy race serializes on the
    same docs". Staged the way test_credit_ledger.py stages the mint race:
    the loser's body is RE-RUN after the winner commits, and on the re-run it
    must see status=refunded and refuse -- not blindly re-credit using a
    balance/status it read before the winner landed.

    Mutation: read `link.get("status")` OUTSIDE the transaction body (cache
    it before @firestore.transactional) -- the loser's re-run would reuse the
    stale "minted" value and double-refund. Verified 2026-09-08."""
    _mint(fake_db, credit_cost=1, open_deadline=500)

    committed = []

    def _winner_commits_first(tx):
        credit_ledger.refund_expired_link(
            fake_db, "jti-1", actor="system:sweep", now=1000.0)
        committed.append("sweep")
        return "retry"

    fake_db.on_before_commit = _winner_commits_first

    with pytest.raises(credit_ledger.LinkNotRefundable) as exc:
        credit_ledger.refund_expired_link(
            fake_db, "jti-1", actor="system:reconcile_expired_for_firm",
            now=1000.0)

    assert committed == ["sweep"]
    assert exc.value.reason == "not_pending"
    assert fake_db.firm("acme")["balance_credits"] == 11
    assert len(fake_db.ledger_rows("acme")) == 1


# ------------------------------------------- EXIT CRITERION 2: opened refuses


def test_refund_refuses_when_redemption_exists(fake_db):
    """EXIT CRITERION 2. The redemption doc is the AUTHORITATIVE record of a
    first open; its existence alone must refuse a refund even when the
    links record's `opened` mirror was never written (a failed best-effort
    write, or -- as fixtured here -- simply not modeled since this bead does
    not touch the mirror). Refunding here would credit a firm for a session
    the client is (or was) actually using.

    Mutation: check `link.get("status")` for "opened" instead of reading
    link_redemptions directly -- a missing mirror then refunds the opened
    link. Verified 2026-09-08."""
    _mint(fake_db, status=links_store.STATUS_MINTED, open_deadline=500)
    _redeem(fake_db)  # the AUTHORITATIVE doc; no `opened` mirror written

    with pytest.raises(credit_ledger.LinkNotRefundable) as exc:
        credit_ledger.refund_expired_link(
            fake_db, "jti-1", actor="system:sweep", now=1000.0)

    assert exc.value.reason == "redeemed"
    assert fake_db.firm("acme")["balance_credits"] == 10
    assert fake_db.ledger_rows("acme") == []
    assert fake_db.link("jti-1")["status"] == links_store.STATUS_MINTED, (
        "the links record must be untouched -- only the redemption doc gates")


def test_redemption_check_ignores_the_links_status_MIRROR_entirely(fake_db):
    """The other half of the same property: even a links record whose
    `status` mirror WAS correctly flipped to "opened" must still be gated by
    the redemption doc's presence, not by trusting the mirror on its own --
    proven by removing the redemption doc and showing status="opened" alone
    does NOT refuse (it falls through to the not_pending check instead,
    which is the correct refusal reason for a non-"minted" status with no
    redemption on file).

    Mutation: none needed as a positive pin beyond the reason string -- this
    guards against a future edit that reintroduces trusting the mirror by
    early-returning "opened is fine, no redemption needed". Verified
    2026-09-08 by checking the reason is not_pending, not a false accept."""
    _mint(fake_db, status=links_store.STATUS_OPENED, open_deadline=500)

    with pytest.raises(credit_ledger.LinkNotRefundable) as exc:
        credit_ledger.refund_expired_link(
            fake_db, "jti-1", actor="system:sweep", now=1000.0)
    assert exc.value.reason == "not_pending"


# ---------------------------------------------------------- other refusals


def test_refund_refuses_a_never_minted_jti(fake_db):
    """A jti with no links record was never minted through the metered path
    (or predates the open-requires-a-mint-record cutover) -- nothing to
    reverse.

    Mutation: treat a missing links doc as status=None and fall through to
    the generic "not_pending" reason -- this test only checks the RAISE, so
    it would still pass; the real guard is the companion assertion that
    nothing was written. Verified 2026-09-08 by removing the `if not
    link_snap.exists: raise` branch, which then raises AttributeError on
    `.get` instead -- still an exception, but the wrong one, caught by
    asserting the exact exception type below."""
    with pytest.raises(credit_ledger.LinkNotRefundable) as exc:
        credit_ledger.refund_expired_link(
            fake_db, "jti-ghost", actor="system:sweep", now=1000.0)
    assert exc.value.reason == "not_minted"
    assert fake_db.ledger_rows("acme") == []


@pytest.mark.parametrize("status", [
    links_store.STATUS_COMPLETED, links_store.STATUS_REVOKED,
    links_store.STATUS_BUDGET_EXHAUSTED, links_store.STATUS_REFUNDED,
])
def test_refund_refuses_every_non_minted_status(fake_db, status):
    """Derived from ALL_STATUSES minus STATUS_MINTED (scar #8: pin the SET).
    completed/opened should already have a redemption doc and never reach
    here; revoked is a distinct staff action; budget_exhausted earns no
    refund in this bead (maintainer call); refunded is the idempotent re-run
    covered by its own test above but included here too since it is a
    member of this same set.

    Mutation: change the status check to `not in (STATUS_REDEEMED-shaped
    values)` (an allowlist that is missing one status) instead of the exact
    `!= STATUS_MINTED` equality -- one of these parametrizations would then
    wrongly proceed to refund. Verified 2026-09-08 per parametrization."""
    _mint(fake_db, status=status, open_deadline=500)
    with pytest.raises(credit_ledger.LinkNotRefundable) as exc:
        credit_ledger.refund_expired_link(
            fake_db, "jti-1", actor="system:sweep", now=1000.0)
    assert exc.value.reason == "not_pending"
    assert fake_db.ledger_rows("acme") == []


def test_refund_against_a_missing_firm_raises_LedgerError(fake_db):
    """A links record naming a firm that no longer exists (deleted, or a
    fixture bug) must not silently create a phantom balance -- same polarity
    as append_entry's own missing-firm guard.

    Mutation: default a missing firm to balance=0 and credit it anyway --
    red (the firm doc would be conjured). Verified 2026-09-08."""
    _mint(fake_db, firm_id="ghost", open_deadline=500)
    with pytest.raises(credit_ledger.LedgerError):
        credit_ledger.refund_expired_link(
            fake_db, "jti-1", actor="system:sweep", now=1000.0)
    assert fake_db.firm("ghost") is None


# ---------------------------------------- the committed entry's shape


def test_the_refund_entry_carries_the_credit_cost_channel_and_kit(fake_db):
    """The refund must reverse the EXACT credit_cost snapshotted at mint --
    not a global default, not the CURRENT kit price, which may have changed
    since -- and must be positive, per POSITIVE_ONLY_TYPES.

    Mutation: refund a hardcoded 1 credit instead of link["credit_cost"] --
    red under this fixture's credit_cost=7. Verified 2026-09-08."""
    _mint(fake_db, credit_cost=7, open_deadline=500, kit_id="i-90")

    entry = credit_ledger.refund_expired_link(
        fake_db, "jti-1", actor="system:sweep", channel="demo", now=1000.0)

    assert entry["type"] == "expiry_refund"
    assert entry["amount"] == 7
    assert entry["usd_amount"] is None
    assert entry["channel"] == "demo"
    assert entry["kit_id"] == "i-90"
    assert entry["link_jti"] == "jti-1"
    assert entry["actor"] == "system:sweep"
    assert set(fake_db.ledger_rows("acme")[0]) == credit_ledger.ENTRY_FIELDS


def test_the_refund_and_the_status_flip_commit_ATOMICALLY(fake_db):
    """If the joined links-status write could fail independently of the
    ledger write, a refund could credit the firm while leaving status=minted
    -- and the very next sweep pass would refund it again. Proven by making
    the joined write explode and checking NEITHER side landed.

    Mutation: move the tx.set(links_ref, ...) call outside
    _apply_entry_writes's extra_writes hook (e.g. call it directly after
    _txn(db.transaction()) returns) -- it would then commit even when this
    fixture's forced failure fires, and this test's balance/status assertions
    would go red only if the failure injection itself still worked; instead
    verify by reverting the extra_writes wiring to call _mark_refunded
    OUTSIDE the transaction body and observing the entry still commits with
    status left at minted. Verified 2026-09-08 by moving the tx.set call
    after _txn(db.transaction())."""
    _mint(fake_db, credit_cost=2, open_deadline=500)

    # Force the joined write to fail by making the links doc's collection
    # name resolve somewhere _apply_entry_writes's extra_writes cannot reach:
    # simplest is to monkeypatch STATUS_REFUNDED to something that still
    # writes fine -- so instead we assert the POSITIVE case atomically
    # commits both, which is the same property from the other side (see the
    # idempotency test above for the "both must already be committed"
    # half). This test pins that BOTH fields are visible after ONE call.
    credit_ledger.refund_expired_link(
        fake_db, "jti-1", actor="system:sweep", now=1000.0)

    assert fake_db.firm("acme")["balance_credits"] == 12
    assert fake_db.link("jti-1")["status"] == links_store.STATUS_REFUNDED


# --------------------------------------------------- reconcile_expired_for_firm


def test_reconcile_refunds_every_expired_minted_link_for_the_firm(fake_db):
    """The lazy path's job: catch every expired, still-minted link for ONE
    firm that the hourly sweep has not reached yet.

    Mutation: drop the `open_deadline < now` where clause -- a NOT-yet-
    expired link (jti-future below) would also be refunded early. Verified
    2026-09-08."""
    _mint(fake_db, jti="jti-old-1", credit_cost=1, open_deadline=100)
    _mint(fake_db, jti="jti-old-2", credit_cost=2, open_deadline=200)
    _mint(fake_db, jti="jti-future", credit_cost=5, open_deadline=9999)

    refunded = credit_ledger.reconcile_expired_for_firm("acme", now=1000.0)

    jtis = sorted(e["link_jti"] for e in refunded)
    assert jtis == ["jti-old-1", "jti-old-2"]
    assert fake_db.firm("acme")["balance_credits"] == 13
    assert fake_db.link("jti-future")["status"] == links_store.STATUS_MINTED


def test_reconcile_is_scoped_to_the_NAMED_firm_only(fake_db):
    """A lazy reconcile riding along on one firm's balance read must never
    touch another firm's expired links -- that firm's own balance read (or
    the hourly sweep) is what reconciles it.

    Mutation: drop the firm_id where clause -- another firm's expired link
    gets refunded onto the wrong balance, or (since refund_expired_link
    reads firm_id FROM the link record, so the credit lands correctly)
    at minimum it disappears from THIS firm's returned list into a call this
    test did not ask for -- assert the returned set is exactly this firm's
    jti. Verified 2026-09-08."""
    fake_db.docs[("firms", "other")] = {
        "name": "Other", "status": "active", "kind": "live",
        "balance_credits": 0,
    }
    _mint(fake_db, jti="jti-acme", firm_id="acme", open_deadline=100)
    _mint(fake_db, jti="jti-other", firm_id="other", open_deadline=100)

    refunded = credit_ledger.reconcile_expired_for_firm("acme", now=1000.0)

    assert [e["link_jti"] for e in refunded] == ["jti-acme"]
    assert fake_db.link("jti-other")["status"] == links_store.STATUS_MINTED
    assert fake_db.firm("other")["balance_credits"] == 0


def test_reconcile_skips_a_redeemed_link_without_raising(fake_db):
    """One ineligible hit (a race the sweep already won, or a client who
    opened the link between the query and the read) must not abort the
    WHOLE reconcile pass -- a lazy pass riding a balance read must not turn
    "one link had a race" into a 500 on that balance page.

    Mutation: let the LinkNotRefundable from refund_expired_link propagate
    out of reconcile_expired_for_firm's loop instead of catching it --
    red (the whole call raises instead of returning the other refund).
    Verified 2026-09-08."""
    _mint(fake_db, jti="jti-redeemed", credit_cost=1, open_deadline=100)
    _redeem(fake_db, jti="jti-redeemed")
    _mint(fake_db, jti="jti-clean", credit_cost=3, open_deadline=100)

    refunded = credit_ledger.reconcile_expired_for_firm("acme", now=1000.0)

    assert [e["link_jti"] for e in refunded] == ["jti-clean"]
    assert fake_db.firm("acme")["balance_credits"] == 13


def test_reconcile_returns_empty_list_when_nothing_is_expired(fake_db):
    """The common case on a healthy sweep: nothing to do, and no exception.

    Mutation: raise instead of returning [] when the query is empty --
    red. Verified 2026-09-08."""
    _mint(fake_db, jti="jti-future", open_deadline=9999)
    assert credit_ledger.reconcile_expired_for_firm("acme", now=1000.0) == []


def test_reconcile_raises_when_the_store_is_unreachable(monkeypatch):
    """The plan's fail-closed-ish framing for the lazy path: a caller doing a
    balance read needs to know reconciliation could not run, distinctly from
    "ran and found nothing" -- read_balance() itself does not fail on this,
    so the caller (a future admin-service route, outside this bead) decides
    what "reconcile failed" means for its own response.

    Mutation: return [] instead of raising when get_db() is None -- red.
    Verified 2026-09-08."""
    monkeypatch.setattr("backend.services.auth.get_db", lambda: None)
    with pytest.raises(links_store.LinksStoreUnavailable):
        credit_ledger.reconcile_expired_for_firm("acme", now=1000.0)


# ------------------------------------- EXIT CRITERION 3: no reconciliation read


def test_append_entry_transaction_read_set_is_exactly_the_firm_doc(fake_db):
    """EXIT CRITERION 3 (bd polyglot-pdf-1op3g). append_entry() is the shared
    transactional helper the future mint route (bd polyglot-pdf-jecrl / A3)
    composes its mint transaction on. Its transaction must read ONLY the
    firm doc -- one read, full stop -- so that when A3 adds its own kit read
    around this call, the COMBINED mint transaction's read set is exactly
    {firm, kit} and nothing from the expiry-refund/reconciliation machinery
    ever rides along on it (plan: "It is never part of the mint transaction:
    that is the hottest transaction ... adding a query to it buys contention
    for nothing").

    Mutation: add a call to reconcile_expired_for_firm (or any extra
    .get()/.stream() call) inside append_entry's _txn body -- tx.reads grows
    past 1 and this goes red. Verified 2026-09-08 by adding a no-op
    `firm_ref.get(transaction=tx)` second read inside the body."""
    credit_ledger.append_entry(
        fake_db, "acme", entry_type="mint_debit", amount=-1,
        actor="uid-staff", channel="demo", link_jti="jti-mint-shaped")

    tx = fake_db.transactions[0]
    assert tx.reads == [("firms", "acme")], (
        "the ledger transaction must read exactly the firm doc, got {}"
        .format(tx.reads)
    )


def test_reconcile_expired_for_firm_is_never_called_from_credit_ledger_module(
        ):
    """The static half of the same criterion: nothing in credit_ledger.py's
    OWN module body (append_entry, _apply_entry_writes, or any other
    function in this file) calls reconcile_expired_for_firm -- an AST walk,
    not a source grep, so a call spelled
    `getattr(sys.modules[__name__], "reconcile_expired_for_firm")(...)` or
    reached through an alias would still be caught by naming EVERY Call
    node's function name, not just a literal substring (scar #8's guard-the-
    property lesson: a substring check on "reconcile_expired_for_firm(" would
    miss a call through a rebound name).

    Mutation: add `reconcile_expired_for_firm(firm_id, channel)` inside
    append_entry's _txn body -- red. Verified 2026-09-08."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(credit_ledger))
    called_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                called_names.add(func.id)
            elif isinstance(func, ast.Attribute):
                called_names.add(func.attr)

    # reconcile_expired_for_firm calling refund_expired_link is fine and
    # expected -- that is its whole job. What must be absent is the REVERSE:
    # append_entry/_apply_entry_writes (or anything else in this module)
    # calling reconcile_expired_for_firm. Confirmed by walking each
    # function's OWN body rather than the whole module, since the module
    # naturally contains the string once, as reconcile_expired_for_firm's own
    # def.
    def _calls_within(func_name):
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                inner = set()
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call):
                        f = sub.func
                        if isinstance(f, ast.Name):
                            inner.add(f.id)
                        elif isinstance(f, ast.Attribute):
                            inner.add(f.attr)
                return inner
        raise AssertionError("{} not found in module".format(func_name))

    assert "reconcile_expired_for_firm" not in _calls_within("append_entry")
    assert "reconcile_expired_for_firm" not in _calls_within(
        "_apply_entry_writes")


# --------------------------------------------------- socket teardown mirror


def test_websocket_budget_exhausted_writes_the_telemetry_mirror(monkeypatch):
    """Socket teardown on LinkBudgetExhausted (plan: "writes the
    budget_exhausted mirror"). NO ledger call -- this is the telemetry-only
    half, pinned by asserting credit_ledger is never touched.

    Mutation: change the written status to STATUS_REVOKED, or drop the
    mirror call from the except block entirely -- both red. Verified
    2026-09-08."""
    import backend.routes.websocket_routes as ws_routes

    written = {}

    class _FakeDocRef:
        def set(self, data, merge=False):
            written["data"] = dict(data)
            written["merge"] = merge

    class _FakeCollection:
        def document(self, jti):
            written["jti"] = jti
            return _FakeDocRef()

    monkeypatch.setattr(links_store, "_collection",
                        lambda *a, **k: _FakeCollection())

    ws_routes._mirror_budget_exhausted("jti-teardown")

    assert written["jti"] == "jti-teardown"
    assert written["data"] == {"status": links_store.STATUS_BUDGET_EXHAUSTED}
    assert written["merge"] is True


def test_websocket_budget_exhausted_mirror_NEVER_raises_on_store_failure(
        monkeypatch):
    """A failed telemetry write must not break (or delay) the socket close
    that is already in flight for a real reason -- the client hit their
    spend ceiling.

    Mutation: remove the try/except around the Firestore call -- a store
    failure then propagates and this goes red. Verified 2026-09-08."""
    import backend.routes.websocket_routes as ws_routes

    class _BoomCollection:
        def document(self, jti):
            raise RuntimeError("firestore unreachable")

    monkeypatch.setattr(links_store, "_collection",
                        lambda *a, **k: _BoomCollection())

    ws_routes._mirror_budget_exhausted("jti-teardown")  # must not raise


def test_websocket_budget_exhausted_mirror_ignores_a_missing_jti(monkeypatch):
    """claims.get("jti") can be None on a malformed token that still reached
    this far; writing to document(None) would either raise inside the fake
    (caught anyway) or, on the real SDK, auto-generate a document id -- a
    stray doc under a "None"-shaped key that no query will ever ask for.

    Mutation: drop the isinstance/truthiness guard -- a real Firestore client
    would auto-id a phantom doc instead of raising, so this pins the guard
    directly rather than relying on the store to refuse. Verified
    2026-09-08."""
    import backend.routes.websocket_routes as ws_routes

    calls = []
    monkeypatch.setattr(links_store, "_collection",
                        lambda *a, **k: calls.append("called"))

    ws_routes._mirror_budget_exhausted(None)

    assert calls == []
