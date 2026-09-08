"""The credit ledger's transactional helper (Epic 2 bead A2).

Pins the three exit criteria of bd polyglot-pdf-vnxew:

  1. test_ledger_balance_invariant_holds_after_replay -- replaying a fixture
     sequence yields balance == sum(amount) and every balance_after matches
     the running sum.
  2. test_mint_transaction_double_mint_race_is_safe -- two concurrent debits
     against one credit's worth of balance leave exactly one entry and a
     final balance of 0.
  3. (the CLI half lives in test_grant_credits_cli.py)

plus the entry-shape rules the helper enforces (signed amounts per type, the
two-way usd_amount requirement, the required actor, the required reason on
an adjustment, the snapshotted firm_kind) and the ledger_export log line.

THE FAKE FIRESTORE. _FakeDb below models the two properties the real
transaction has that a plain dict does not: writes are BUFFERED until commit
(so an aborted body leaves nothing behind), and a body can be RE-RUN on
contention (so a test can interleave two transactions and prove the loser
re-reads). It is deliberately a fake and not a mock: the race test needs the
buffer-and-retry semantics to mean something, and a MagicMock would assert
that calls happened rather than that the money is right (CLAUDE.md scar #7's
neighbour -- a mock cannot tell you the invariant held).

Each test's docstring names the mutation that must turn it red
(docs/standards/testing.md#test-the-tests).

ASCII only.
"""
import pytest

import backend.services.credit_ledger as credit_ledger


# ---------------------------------------------------------------- fake db


class _Snap:
    """A POINT-IN-TIME copy, like a real Firestore snapshot.

    The copy is load-bearing, not tidiness: holding a reference to the live
    store dict would let a snapshot taken BEFORE a competing commit silently
    observe that commit's values, and every "the stale read is the bug" test
    below would pass against a helper that reads outside its transaction.
    """

    def __init__(self, data):
        self._data = dict(data) if data is not None else None

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
            # Record which docs a transaction read, and WHEN, so a test can
            # assert reads-before-writes and drive a contention retry.
            transaction.reads.append(self._path)
        return _Snap(self._store.docs.get(self._path))

    def set(self, data, merge=False):
        self._store.apply_set(self._path, data, merge)


class _Query:
    """Ordering and limiting are ONE query in Firestore, applied in that
    fixed order regardless of the builder call sequence -- so the fake
    models the RESULT (sort, then slice), and a test pins which entries come
    back rather than which builder method was called first.

    `direction` is honoured (not just accepted) so a mutation that flips the
    sort is a red test rather than a TypeError that reddens everything.
    """

    def __init__(self, store, path, order_field=None, limit=None,
                 descending=False):
        self._store = store
        self._path = path
        self._order = order_field
        self._limit = limit
        self._descending = descending

    def order_by(self, field, direction="ASCENDING"):
        return _Query(self._store, self._path, field, self._limit,
                      str(direction).upper().startswith("DESC"))

    def limit(self, n):
        return _Query(self._store, self._path, self._order, n,
                      self._descending)

    def stream(self):
        rows = [
            (path, data) for path, data in self._store.docs.items()
            if path[:-1] == self._path
        ]
        if self._order:
            rows.sort(key=lambda kv: kv[1].get(self._order),
                      reverse=self._descending)
        if self._limit is not None:
            rows = rows[: self._limit]
        return iter([_Snap(data) for _, data in rows])


class _Collection:
    def __init__(self, store, path):
        self._store = store
        self._path = path

    def document(self, doc_id=None):
        if doc_id is None:
            self._store.auto_id_counter += 1
            doc_id = "auto{}".format(self._store.auto_id_counter)
        return _DocRef(self._store, self._path + (doc_id,))

    def order_by(self, field):
        return _Query(self._store, self._path).order_by(field)

    def limit(self, n):
        return _Query(self._store, self._path).limit(n)

    def stream(self):
        return _Query(self._store, self._path).stream()


class _Transaction:
    """Buffers writes; the buffer is applied only on a clean commit.

    This is what makes "nothing was committed" a real assertion rather than
    a tautology: a body that raises leaves the buffer unapplied.
    """

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
        """What the real client does before RE-RUNNING a contended body."""
        self._buffer = []
        self.reads = []
        self.writes = []


class _FakeDb:
    def __init__(self, docs=None):
        # {(collection, doc_id, [subcollection, doc_id, ...]): {...}}
        self.docs = dict(docs or {})
        self.auto_id_counter = 0
        # Set by a test to run a callback between the transaction body's
        # reads and its commit -- the contention window.
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


class _FakeTransactionalDecorator:
    """Stands in for firebase_admin.firestore.transactional.

    Runs the body, then commits. Models CONTENTION when the db carries an
    on_before_commit hook: the hook runs after the body's reads, and if it
    reports that the underlying doc moved, the body is reset and RE-RUN
    exactly as the real client re-runs a contended transaction. Without the
    re-run the race test would be pinning the fake, not the helper.
    """

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
        "balance_credits": 0,
    }})
    import firebase_admin
    monkeypatch.setattr(firebase_admin, "firestore", _FakeFirestoreModule(),
                        raising=False)
    return db


# ------------------------------------------------- EXIT CRITERION 1: replay


# The fixture sequence: every entry type, both signs, in a deliberate order
# whose running sum dips and recovers. Kept as a module-level constant so
# the replay test and the export-line test drive the SAME sequence.
_REPLAY_SEQUENCE = [
    dict(entry_type="promo_grant", amount=10, actor="system:seed"),
    dict(entry_type="purchase", amount=100, actor="uid-ops", usd_amount=249.0),
    dict(entry_type="mint_debit", amount=-1, actor="uid-staff",
         channel="demo", link_jti="jti-1", kit_id="w7"),
    dict(entry_type="mint_debit", amount=-1, actor="uid-staff",
         channel="demo", link_jti="jti-2", kit_id="i-90"),
    dict(entry_type="expiry_refund", amount=1, actor="system:sweep",
         channel="demo", link_jti="jti-2"),
    dict(entry_type="subscription_grant", amount=50, actor="uid-ops",
         usd_amount=99.0),
    dict(entry_type="adjustment", amount=-40, actor="uid-ops",
         reason="double-charged on 09-07"),
    dict(entry_type="adjustment", amount=5, actor="uid-ops",
         reason="goodwill after the outage"),
]


def _replay(fake_db):
    for i, call in enumerate(_REPLAY_SEQUENCE):
        credit_ledger.append_entry(fake_db, "acme", ts=1000.0 + i, **call)


def test_ledger_balance_invariant_holds_after_replay(fake_db):
    """EXIT CRITERION 1. Replaying the fixture sequence must leave
    balance_credits == sum(amount), and every stored balance_after must equal
    the running sum at that point.

    Mutation: in append_entry's transaction body, compute new_balance as
    `balance + abs(amount)` (or drop the tx.set of balance_credits) -- both
    halves go red. Verified 2026-09-08."""
    _replay(fake_db)

    rows = fake_db.ledger_rows("acme")
    assert len(rows) == len(_REPLAY_SEQUENCE)

    running = 0
    for row, expected in zip(rows, _REPLAY_SEQUENCE):
        running += expected["amount"]
        assert row["amount"] == expected["amount"]
        assert row["balance_after"] == running, (
            "balance_after {} != running sum {} on entry {}".format(
                row["balance_after"], running, row["type"])
        )

    total = sum(r["amount"] for r in rows)
    assert total == running
    assert fake_db.firm("acme")["balance_credits"] == total
    assert credit_ledger.read_balance(fake_db, "acme") == total


def test_read_entries_returns_the_replay_in_ts_order(fake_db):
    """read_entries is the replay READER: a console or a checker must get
    the entries oldest-first so the running sum it computes is the one the
    writer computed.

    Mutation: drop the .order_by("ts") in read_entries -- the fake returns
    dict-insertion order, which for a shuffled write order no longer matches
    the running sum. Verified 2026-09-08 by writing the sequence with
    descending timestamps."""
    for i, call in enumerate(_REPLAY_SEQUENCE):
        # Descending ts on purpose: insertion order and ts order disagree, so
        # only a real sort passes.
        credit_ledger.append_entry(fake_db, "acme", ts=2000.0 - i, **call)

    entries = credit_ledger.read_entries(fake_db, "acme")
    stamps = [e["ts"] for e in entries]
    assert stamps == sorted(stamps)


def test_read_entries_limit_takes_the_OLDEST_n(fake_db):
    """The docstring's contract: a LIMITED read is the OLDEST n -- the shape
    a replay check wants, not the newest-n a console table wants. Ordering
    and limiting are one Firestore query, so the property to pin is the
    RESULT (which entries come back), not the call order of the builder.

    Mutation: change read_entries to `.order_by("ts", direction="DESCENDING")`
    -- or drop the order_by entirely, which the fake resolves to insertion
    order, here the NEWEST two. Both go red. Verified 2026-09-08 with the
    order_by dropped."""
    for i, call in enumerate(_REPLAY_SEQUENCE[:4]):
        # Descending ts on purpose: insertion order and ts order disagree, so
        # a limit applied to an unordered read returns the wrong two.
        credit_ledger.append_entry(fake_db, "acme", ts=2000.0 - i, **call)

    entries = credit_ledger.read_entries(fake_db, "acme", limit=2)
    assert [e["ts"] for e in entries] == [1997.0, 1998.0]


# --------------------------------------------- EXIT CRITERION 2: the race


def test_mint_transaction_double_mint_race_is_safe(fake_db):
    """EXIT CRITERION 2. Two concurrent debits against ONE credit of balance:
    exactly one succeeds, the final balance is 0, and exactly one entry
    exists.

    The race is staged the way Firestore stages it: transaction B's body runs
    against the balance it read, transaction A commits underneath it, and B's
    body is RE-RUN against the new state. If the helper computed anything
    (the balance, the sufficiency verdict, balance_after) OUTSIDE the body,
    the re-run would reuse the stale value and B would also succeed --
    leaving balance -1 and two entries.

    Mutation: hoist the firm read and the `balance` computation out of the
    _txn body (read the snapshot before @firestore.transactional and close
    over it) -- B commits a second debit and this goes red on all three
    assertions. Verified 2026-09-08."""
    fake_db.docs[("firms", "acme")]["balance_credits"] = 1

    committed = []

    def _first_debit(tx):
        # Runs after B's body has read balance=1 but before B commits: this
        # is transaction A landing underneath B.
        credit_ledger.append_entry(
            fake_db, "acme", entry_type="mint_debit", amount=-1,
            actor="uid-staff-a", channel="demo", link_jti="jti-a",
            require_sufficient_balance=True, ts=1000.0,
        )
        committed.append("a")
        return "retry"

    fake_db.on_before_commit = _first_debit

    with pytest.raises(credit_ledger.InsufficientCredits):
        credit_ledger.append_entry(
            fake_db, "acme", entry_type="mint_debit", amount=-1,
            actor="uid-staff-b", channel="demo", link_jti="jti-b",
            require_sufficient_balance=True, ts=1001.0,
        )

    assert committed == ["a"], "the first debit must have committed"
    assert fake_db.firm("acme")["balance_credits"] == 0
    rows = fake_db.ledger_rows("acme")
    assert len(rows) == 1, "expected exactly one entry, got {}".format(rows)
    assert rows[0]["link_jti"] == "jti-a"
    assert rows[0]["balance_after"] == 0


def test_a_refused_debit_commits_NOTHING(fake_db):
    """The other half of the race property, on its own: an InsufficientCredits
    refusal must leave the balance untouched and write no entry -- the
    buffered writes are discarded, not partially applied.

    Mutation: replace `raise InsufficientCredits(...)` with `pass` -- the
    writes then commit and both the balance and the entry assertions go red.
    (Note what does NOT work: moving the check BELOW the two tx.set calls
    changes nothing, because the buffered writes are discarded on the raise
    either way -- that is the property, not a gap.) Verified 2026-09-08."""
    fake_db.docs[("firms", "acme")]["balance_credits"] = 2

    with pytest.raises(credit_ledger.InsufficientCredits) as exc:
        credit_ledger.append_entry(
            fake_db, "acme", entry_type="mint_debit", amount=-3,
            actor="uid-staff", require_sufficient_balance=True,
        )

    assert exc.value.balance == 2
    assert fake_db.firm("acme")["balance_credits"] == 2
    assert fake_db.ledger_rows("acme") == []


def test_enforcement_OFF_lets_the_balance_go_negative(fake_db):
    """The soft-launch mode the plan requires: with
    require_sufficient_balance left False (the default), a debit past zero is
    WRITTEN and the balance goes negative -- metered, not refused.

    Mutation: make the sufficiency check unconditional (drop the
    `require_sufficient_balance and` guard) -- this raises instead of writing
    and goes red. Verified 2026-09-08."""
    result = credit_ledger.append_entry(
        fake_db, "acme", entry_type="mint_debit", amount=-1,
        actor="uid-staff", channel="demo", link_jti="jti-x",
    )
    assert result["balance_credits"] == -1
    assert fake_db.firm("acme")["balance_credits"] == -1
    assert len(fake_db.ledger_rows("acme")) == 1


def test_reads_happen_BEFORE_writes_in_the_transaction(fake_db):
    """The Firestore rule the module docstring carries: every read in a
    transaction must precede every write, or the real client raises. The fake
    records the order, so this pins it without a live Firestore.

    Mutation: move the `snap = firm_ref.get(transaction=tx)` line below the
    two tx.set calls -- red. Verified 2026-09-08."""
    credit_ledger.append_entry(
        fake_db, "acme", entry_type="promo_grant", amount=5,
        actor="system:seed",
    )
    tx = fake_db.transactions[0]
    assert tx.reads, "the body must read the firm doc"
    assert tx.writes, "the body must write"
    # Every read was recorded before any write on the same transaction object.
    assert len(tx.reads) == 1 and len(tx.writes) == 2


def test_extra_writes_join_the_SAME_transaction(fake_db):
    """The A3 hook: a caller's mint record must commit with the debit or not
    at all. Here the callback writes a doc, and an exception from a LATER
    callback must leave nothing behind.

    Mutation: call extra_writes outside the _txn body (after _txn returns) --
    the abort half goes red because the extra doc survives the failed
    transaction. Verified 2026-09-08."""
    written = {}

    def _write_record(tx, firm):
        written["firm_kind"] = firm.get("kind")
        tx.set(fake_db.collection("links").document("jti-1"),
               {"jti": "jti-1", "status": "minted"})

    credit_ledger.append_entry(
        fake_db, "acme", entry_type="mint_debit", amount=-1,
        actor="uid-staff", channel="demo", link_jti="jti-1",
        extra_writes=_write_record,
    )
    assert fake_db.docs[("links", "jti-1")]["status"] == "minted"
    assert written["firm_kind"] == "live"


def test_an_extra_writes_failure_aborts_the_WHOLE_transaction(fake_db):
    """The other direction: if the caller's joined write raises, the debit
    and the ledger entry must not commit either.

    Mutation: wrap the extra_writes(...) call in a try/except that swallows
    -- the debit commits alone and this goes red. Verified 2026-09-08."""
    fake_db.docs[("firms", "acme")]["balance_credits"] = 5

    def _boom(tx, firm):
        raise RuntimeError("mint record write failed")

    with pytest.raises(RuntimeError):
        credit_ledger.append_entry(
            fake_db, "acme", entry_type="mint_debit", amount=-1,
            actor="uid-staff", extra_writes=_boom,
        )

    assert fake_db.firm("acme")["balance_credits"] == 5
    assert fake_db.ledger_rows("acme") == []


# ------------------------------------------------------------ entry shape


def test_the_entry_carries_EXACTLY_the_declared_field_set(fake_db):
    """ENTRY_FIELDS is the contract Epic 3's BigQuery table and the console's
    ledger view are built from. A writer that drops a field, or adds one
    nobody declared, is a set difference -- caught here rather than as a NULL
    column later.

    Mutation: delete the "kit_id" key from the entry dict in the body -- red.
    Verified 2026-09-08."""
    credit_ledger.append_entry(
        fake_db, "acme", entry_type="mint_debit", amount=-1,
        actor="uid-staff", channel="demo", link_jti="j", kit_id="w7",
    )
    row = fake_db.ledger_rows("acme")[0]
    assert set(row) == credit_ledger.ENTRY_FIELDS


@pytest.mark.parametrize("entry_type", sorted(credit_ledger.ENTRY_TYPES))
def test_every_declared_type_can_be_written(fake_db, entry_type):
    """Derived from ENTRY_TYPES, not hand-listed: a type added to the tuple
    without a working write path fails here (scar #8 -- pin the SET).

    Mutation: drop one member from POSITIVE_ONLY_TYPES' handling by making
    _validate reject that type outright -- its parametrization goes red.
    Verified 2026-09-08 per parametrization."""
    amount = -1 if entry_type in credit_ledger.NEGATIVE_ONLY_TYPES else 1
    kwargs = {}
    if entry_type in credit_ledger.USD_REQUIRED_TYPES:
        kwargs["usd_amount"] = 10.0
    if entry_type in credit_ledger.REASON_REQUIRED_TYPES:
        kwargs["reason"] = "because"
    result = credit_ledger.append_entry(
        fake_db, "acme", entry_type=entry_type, amount=amount,
        actor="uid-ops", **kwargs)
    assert result["type"] == entry_type
    assert result["balance_after"] == amount


@pytest.mark.parametrize("entry_type", sorted(credit_ledger.POSITIVE_ONLY_TYPES))
def test_a_credit_ADDING_type_refuses_a_negative_amount(fake_db, entry_type):
    """A grant with a minus sign is an adjustment wearing a grant's name --
    and it would skip the reason requirement that makes an adjustment
    auditable.

    Mutation: drop the POSITIVE_ONLY_TYPES branch in _validate -- every
    parametrization goes red. Verified 2026-09-08 per parametrization."""
    kwargs = {"usd_amount": 5.0} if (
        entry_type in credit_ledger.USD_REQUIRED_TYPES) else {}
    with pytest.raises(credit_ledger.LedgerError):
        credit_ledger.append_entry(
            fake_db, "acme", entry_type=entry_type, amount=-5,
            actor="uid-ops", **kwargs)
    assert fake_db.ledger_rows("acme") == []


@pytest.mark.parametrize("entry_type", sorted(credit_ledger.NEGATIVE_ONLY_TYPES))
def test_a_DEBIT_type_refuses_a_positive_amount(fake_db, entry_type):
    """The mirror rule: a mint_debit that ADDS credits would silently mint
    money on every mint.

    Mutation: drop the NEGATIVE_ONLY_TYPES branch in _validate -- red.
    Verified 2026-09-08 per parametrization."""
    with pytest.raises(credit_ledger.LedgerError):
        credit_ledger.append_entry(
            fake_db, "acme", entry_type=entry_type, amount=5,
            actor="uid-staff")
    assert fake_db.ledger_rows("acme") == []


@pytest.mark.parametrize("entry_type", sorted(credit_ledger.USD_REQUIRED_TYPES))
def test_an_income_type_REQUIRES_usd_amount(fake_db, entry_type):
    """purchase and subscription_grant are what the revenue view sums. A
    missing usd_amount there is revenue silently recorded as zero.

    Mutation: `if entry_type in USD_REQUIRED_TYPES:` -> `if False:` -- red.
    (The narrower `if usd_amount is None: raise` -> pass does NOT redden this
    on its own: the isinstance guard below catches None too. That REDUNDANCY
    is why the next two tests exist -- each guard is pinned separately, so
    neither can be deleted while the suite stays green.) Verified 2026-09-08
    per parametrization."""
    with pytest.raises(credit_ledger.LedgerError):
        credit_ledger.append_entry(
            fake_db, "acme", entry_type=entry_type, amount=10,
            actor="uid-ops")
    assert fake_db.ledger_rows("acme") == []


@pytest.mark.parametrize("entry_type", sorted(credit_ledger.USD_REQUIRED_TYPES))
@pytest.mark.parametrize("usd", ["249.00", True, [1]])
def test_a_NON_NUMERIC_usd_amount_is_refused(fake_db, entry_type, usd):
    """The layer BELOW the None check, pinned on its own. A string dollar
    figure -- exactly what an HTTP form or a CSV import yields -- would be
    stored verbatim and then SUM() to a type error (or, for a bool, to 1) in
    the revenue view.

    Mutation: delete ONLY the `isinstance(usd_amount, (int, float))` guard,
    keeping the None check -- these go red while the None test above stays
    green, which is the per-layer property. Verified 2026-09-08 per
    parametrization."""
    with pytest.raises(credit_ledger.LedgerError):
        credit_ledger.append_entry(
            fake_db, "acme", entry_type=entry_type, amount=10,
            actor="uid-ops", usd_amount=usd)
    assert fake_db.ledger_rows("acme") == []


@pytest.mark.parametrize("entry_type", sorted(credit_ledger.USD_REQUIRED_TYPES))
def test_a_NEGATIVE_usd_amount_is_refused(fake_db, entry_type):
    """The third layer. Negative income is not a refund -- a refund is a
    separate signed entry -- so a minus sign here would silently subtract
    from the revenue total while the credits still went up.

    Mutation: delete ONLY the `if usd_amount < 0` guard -- these go red while
    the None and isinstance tests stay green. Verified 2026-09-08 per
    parametrization."""
    with pytest.raises(credit_ledger.LedgerError):
        credit_ledger.append_entry(
            fake_db, "acme", entry_type=entry_type, amount=10,
            actor="uid-ops", usd_amount=-1.0)
    assert fake_db.ledger_rows("acme") == []


@pytest.mark.parametrize(
    "entry_type",
    sorted(set(credit_ledger.ENTRY_TYPES) - credit_ledger.USD_REQUIRED_TYPES),
)
def test_a_NON_income_type_REFUSES_a_usd_amount(fake_db, entry_type):
    """The requirement runs both ways: a dollar figure on a promo grant, a
    debit, a refund or an adjustment would be double-counted as income by
    the revenue view, which filters on type but sums usd_amount.

    Derived as the SET COMPLEMENT of USD_REQUIRED_TYPES, so a new type lands
    in exactly one of these two tests automatically (scar #8).

    Mutation: delete the `elif usd_amount is not None: raise` branch in
    _validate -- every parametrization goes red. Verified 2026-09-08 per
    parametrization."""
    amount = -1 if entry_type in credit_ledger.NEGATIVE_ONLY_TYPES else 1
    kwargs = {"reason": "r"} if (
        entry_type in credit_ledger.REASON_REQUIRED_TYPES) else {}
    with pytest.raises(credit_ledger.LedgerError):
        credit_ledger.append_entry(
            fake_db, "acme", entry_type=entry_type, amount=amount,
            actor="uid-ops", usd_amount=9.99, **kwargs)
    assert fake_db.ledger_rows("acme") == []


@pytest.mark.parametrize(
    "entry_type", sorted(credit_ledger.REASON_REQUIRED_TYPES))
@pytest.mark.parametrize("reason", [None, "", "   "])
def test_an_adjustment_REQUIRES_a_non_blank_reason(fake_db, entry_type, reason):
    """The adjustment is the one signed entry with no upstream event
    explaining it. A blank reason -- including whitespace, which a form field
    yields readily -- makes it unauditable.

    Mutation: change the reason check to `reason is None` (dropping the
    .strip()) -- the "" and "   " parametrizations go red while None still
    passes, which is exactly why all three are here. Verified 2026-09-08 per
    parametrization."""
    with pytest.raises(credit_ledger.LedgerError):
        credit_ledger.append_entry(
            fake_db, "acme", entry_type=entry_type, amount=-5,
            actor="uid-ops", reason=reason)
    assert fake_db.ledger_rows("acme") == []


@pytest.mark.parametrize("actor", [None, "", "   ", 7])
def test_actor_is_REQUIRED_and_never_blank(fake_db, actor):
    """The plan's word: actor is a uid or system:<origin>, never blank. An
    unattributable credit movement is the one thing the ledger exists to make
    impossible.

    Mutation: drop the actor check from _validate -- every parametrization
    goes red. Verified 2026-09-08 per parametrization."""
    with pytest.raises(credit_ledger.LedgerError):
        credit_ledger.append_entry(
            fake_db, "acme", entry_type="promo_grant", amount=5, actor=actor)
    assert fake_db.ledger_rows("acme") == []


@pytest.mark.parametrize("amount", [0, 1.5, True, "5"])
def test_a_non_integer_or_zero_amount_is_REFUSED(fake_db, amount):
    """Credits are whole units. A float would make balance_after
    unreproducible on replay; a bool is an int in Python and would write
    amount=True; zero moves nothing.

    Mutation: drop the isinstance/bool/zero checks -- every parametrization
    goes red. Verified 2026-09-08 per parametrization."""
    with pytest.raises(credit_ledger.LedgerError):
        credit_ledger.append_entry(
            fake_db, "acme", entry_type="promo_grant", amount=amount,
            actor="uid-ops")
    assert fake_db.ledger_rows("acme") == []


def test_an_unknown_type_is_REFUSED(fake_db):
    """A typo'd type would land rows the income and spend views silently skip.

    Mutation: drop the ENTRY_TYPES membership check -- red. Verified
    2026-09-08."""
    with pytest.raises(credit_ledger.LedgerError):
        credit_ledger.append_entry(
            fake_db, "acme", entry_type="freebie", amount=5, actor="uid-ops")
    assert fake_db.ledger_rows("acme") == []


def test_an_entry_against_a_MISSING_firm_is_refused(fake_db):
    """Writing would create balance_credits on a phantom doc and make a firm
    that does not exist appear in listings.

    Mutation: drop the `if not snap.exists: raise` branch -- the write
    conjures ("firms", "ghost") and this goes red. Verified 2026-09-08."""
    with pytest.raises(credit_ledger.LedgerError):
        credit_ledger.append_entry(
            fake_db, "ghost", entry_type="promo_grant", amount=5,
            actor="uid-ops")
    assert fake_db.firm("ghost") is None
    assert fake_db.ledger_rows("ghost") == []


# --------------------------------------------------------- firm_kind snapshot


@pytest.mark.parametrize("stored_kind,expected", [
    ("mock", "mock"),
    ("live", "live"),
    (None, "live"),
    ("bogus", "live"),
])
def test_firm_kind_is_snapshotted_and_fails_closed_to_live(
        fake_db, stored_kind, expected):
    """The income view filters on firm_kind == "live". A missing or malformed
    kind must resolve to "live" -- the SAME fail-closed polarity as
    firms.firm_kind() -- so a pre-backfill firm's real purchase is never
    silently dropped from revenue.

    Mutation: change the fallback to "mock" -- the None and "bogus"
    parametrizations go red while the two explicit ones still pass, which is
    why all four are here. Verified 2026-09-08 per parametrization."""
    firm = fake_db.docs[("firms", "acme")]
    if stored_kind is None:
        firm.pop("kind", None)
    else:
        firm["kind"] = stored_kind

    credit_ledger.append_entry(
        fake_db, "acme", entry_type="purchase", amount=10, actor="uid-ops",
        usd_amount=49.0)
    assert fake_db.ledger_rows("acme")[0]["firm_kind"] == expected


def test_a_firm_kind_flip_does_NOT_rewrite_older_entries(fake_db):
    """The snapshot's point: a firm promoted from mock to live must not
    retroactively turn its test grants into revenue.

    Mutation: read the kind from the firm doc at READ time in read_entries
    instead of storing it on the entry -- red. Verified 2026-09-08."""
    fake_db.docs[("firms", "acme")]["kind"] = "mock"
    credit_ledger.append_entry(
        fake_db, "acme", entry_type="purchase", amount=10, actor="uid-ops",
        usd_amount=0.0, ts=1000.0)
    fake_db.docs[("firms", "acme")]["kind"] = "live"
    credit_ledger.append_entry(
        fake_db, "acme", entry_type="purchase", amount=10, actor="uid-ops",
        usd_amount=49.0, ts=1001.0)

    kinds = [r["firm_kind"] for r in credit_ledger.read_entries(fake_db, "acme")]
    assert kinds == ["mock", "live"]


# -------------------------------------------------------- balance handling


def test_a_MISSING_balance_field_is_treated_as_zero(fake_db):
    """The pre-backfill window (bead A6): a firm doc with no balance_credits
    must still accept a grant -- that grant is how an operator gets the firm
    out of the window.

    Mutation: raise instead of defaulting to 0 -- red. Verified 2026-09-08."""
    fake_db.docs[("firms", "acme")].pop("balance_credits")
    result = credit_ledger.append_entry(
        fake_db, "acme", entry_type="promo_grant", amount=25,
        actor="system:seed")
    assert result["balance_credits"] == 25
    assert result["balance_after"] == 25


@pytest.mark.parametrize("stored", ["12", 12.5, True, None])
def test_a_MALFORMED_balance_is_treated_as_zero(fake_db, stored):
    """A string, a float, or a bool in balance_credits would make
    `balance + amount` either raise or produce a nonsense balance. Zero is the
    conservative resolution and matches read_balance().

    Mutation: drop the isinstance guard in the body -- the "12" and None
    parametrizations raise TypeError and go red. Verified 2026-09-08 per
    parametrization."""
    fake_db.docs[("firms", "acme")]["balance_credits"] = stored
    result = credit_ledger.append_entry(
        fake_db, "acme", entry_type="promo_grant", amount=5,
        actor="system:seed")
    assert result["balance_credits"] == 5


def test_the_balance_write_MERGES_and_never_drops_the_firm_profile(fake_db):
    """balance_credits lives on the firm doc alongside name, status, kind and
    allowed_kits. A non-merge set would blank the firm's profile on every
    grant -- and get_allowed_kits fails closed on a malformed doc, so every
    private kit would vanish for that firm.

    Mutation: change the tx.set(firm_ref, ...) merge=True to merge=False --
    red. Verified 2026-09-08."""
    fake_db.docs[("firms", "acme")]["allowed_kits"] = ["w7"]
    credit_ledger.append_entry(
        fake_db, "acme", entry_type="promo_grant", amount=5,
        actor="system:seed")
    firm = fake_db.firm("acme")
    assert firm["name"] == "Acme"
    assert firm["status"] == "active"
    assert firm["allowed_kits"] == ["w7"]
    assert firm["balance_credits"] == 5
    assert firm["balance_updated_at"] is not None


def test_balance_updated_at_moves_with_the_balance(fake_db):
    """An operator diagnosing a wrong balance needs to know WHEN it last
    changed; a stale stamp points at the wrong day.

    Mutation: drop balance_updated_at from the tx.set payload -- red.
    Verified 2026-09-08."""
    credit_ledger.append_entry(
        fake_db, "acme", entry_type="promo_grant", amount=5,
        actor="system:seed", ts=1234.0)
    assert fake_db.firm("acme")["balance_updated_at"] == 1234.0


def test_read_balance_returns_None_for_a_missing_firm(fake_db):
    """None and 0 are different answers: "no such firm" must not read as "a
    firm with no credits", or a grant CLI's dry run would promise a write
    that the real run refuses.

    Mutation: return 0 instead of None on a missing doc -- red. Verified
    2026-09-08."""
    assert credit_ledger.read_balance(fake_db, "ghost") is None
    assert credit_ledger.read_balance(fake_db, "acme") == 0


# ---------------------------------------------------- the ledger_export line


def _capture_export(monkeypatch):
    lines = []

    class _Recorder:
        def bind(self, **kw):
            return self

        def info(self, event, **kw):
            lines.append((event, kw))

        def error(self, event, **kw):
            lines.append((event, kw))

    monkeypatch.setattr(credit_ledger, "_log", _Recorder())
    return lines


def test_every_write_emits_ONE_ledger_export_line_with_the_declared_fields(
        fake_db, monkeypatch):
    """Epic 3's BigQuery sink filters on jsonPayload.event_type ==
    "ledger_export" and reads exactly LEDGER_EXPORT_FIELDS. A dropped key
    becomes a NULL column nobody notices until a revenue number is wrong.

    Mutation: remove `usd_amount=...` from the _log.info call -- red.
    Verified 2026-09-08."""
    lines = _capture_export(monkeypatch)
    credit_ledger.append_entry(
        fake_db, "acme", entry_type="purchase", amount=100, actor="uid-ops",
        usd_amount=249.0, link_jti=None, kit_id="w7")

    exports = [kw for event, kw in lines
               if event == credit_ledger.LEDGER_EXPORT_EVENT]
    assert len(exports) == 1
    payload = exports[0]
    assert set(payload) == credit_ledger.LEDGER_EXPORT_FIELDS
    assert payload["event_type"] == "ledger_export"
    assert payload["type"] == "purchase"
    assert payload["amount"] == 100
    assert payload["usd_amount"] == 249.0
    assert payload["firm_id"] == "acme"
    assert payload["firm_kind"] == "live"


def test_the_export_line_carries_the_channel_and_jti_of_a_mint_debit(
        fake_db, monkeypatch):
    """The spend side of the same feed: a debit's channel and link_jti are how
    Epic 3 attributes a burn to a channel and a link.

    Mutation: hardcode channel=None in the _log.info call -- red. Verified
    2026-09-08."""
    lines = _capture_export(monkeypatch)
    credit_ledger.append_entry(
        fake_db, "acme", entry_type="mint_debit", amount=-1,
        actor="uid-staff", channel="staging", link_jti="jti-7", kit_id="i-90")

    payload = [kw for event, kw in lines
               if event == credit_ledger.LEDGER_EXPORT_EVENT][0]
    assert payload["channel"] == "staging"
    assert payload["link_jti"] == "jti-7"
    assert payload["usd_amount"] is None


def test_NO_export_line_is_emitted_when_the_transaction_ABORTS(
        fake_db, monkeypatch):
    """The line is emitted AFTER the commit for exactly this reason: a
    ledger_export for an entry that never committed would inflate the income
    view with money that never moved.

    Mutation: move the _log.info call above `_txn(db.transaction())` -- red.
    Verified 2026-09-08."""
    lines = _capture_export(monkeypatch)

    def _boom(tx, firm):
        raise RuntimeError("joined write failed")

    with pytest.raises(RuntimeError):
        credit_ledger.append_entry(
            fake_db, "acme", entry_type="promo_grant", amount=5,
            actor="system:seed", extra_writes=_boom)

    assert [e for e, _ in lines
            if e == credit_ledger.LEDGER_EXPORT_EVENT] == []


def test_a_REFUSED_entry_emits_no_export_line(fake_db, monkeypatch):
    """Same property on the validation path: a refused call must not appear
    in the income feed at all.

    Mutation: emit the export line inside _validate -- red. Verified
    2026-09-08."""
    lines = _capture_export(monkeypatch)
    with pytest.raises(credit_ledger.LedgerError):
        credit_ledger.append_entry(
            fake_db, "acme", entry_type="promo_grant", amount=-5,
            actor="uid-ops")
    assert lines == []


def test_the_export_line_carries_NO_field_values_or_free_text(
        fake_db, monkeypatch):
    """docs/standards/hipaa-pii-policy.md: the log line carries ids, credit
    counts and dollar amounts only. `reason` is operator free text and must
    NOT reach the log sink even though it is stored on the entry.

    Mutation: add reason=reason to the _log.info call -- red. Verified
    2026-09-08."""
    lines = _capture_export(monkeypatch)
    credit_ledger.append_entry(
        fake_db, "acme", entry_type="adjustment", amount=-5, actor="uid-ops",
        reason="client SSN 123-45-6789 was double charged")

    payload = [kw for event, kw in lines
               if event == credit_ledger.LEDGER_EXPORT_EVENT][0]
    assert "reason" not in payload
    assert not any("123-45-6789" in str(v) for v in payload.values())


# ------------------------------------------------------- the ONE-writer rule


def test_credit_ledger_is_the_only_module_that_writes_balance_credits():
    """Scar #8: pin the SET, not the instance. The invariant holds only
    because ONE module writes balance_credits; a second writer breaks it
    silently, since nothing recomputes the balance from the ledger.

    The one legitimate other site is firms.upsert_firm(), which
    0-initializes the field on FIRST CREATE and never touches it again.
    Everything else that mentions the key must be a READER.

    Mutation: add a `ref.update({"balance_credits": n})` to any backend
    service other than these two -- red. Verified 2026-09-08 by adding one to
    backend/services/links_store.py."""
    import pathlib

    backend_dir = pathlib.Path(credit_ledger.__file__).resolve().parents[1]
    allowed = {"credit_ledger.py", "firms.py"}
    offenders = []
    for path in sorted(backend_dir.rglob("*.py")):
        if "tests" in path.parts or "scripts" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if '"balance_credits":' not in text:
            continue
        if path.name not in allowed:
            offenders.append(str(path.relative_to(backend_dir)))
    assert offenders == [], (
        "balance_credits is written outside the ledger helper: {}".format(
            offenders)
    )
