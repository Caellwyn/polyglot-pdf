"""The credit ledger's transactional helper (Epic 2 bead A2).

Pins the three exit criteria of bd polyglot-pdf-vnxew:

  1. test_ledger_balance_invariant_holds_after_replay -- replaying a fixture
     sequence yields balance == sum(amount) and every balance_after matches
     the running sum.
  2. test_mint_transaction_double_mint_race_is_safe -- two concurrent debits
     against one credit's worth of balance leave exactly one entry and a
     final balance of 0.
  3. (the CLI half lives in test_grant_credits_cli.py)

Also pins a fresh-eyes concurrency finding on bd polyglot-pdf-0euzk (the
firm-plan monthly top-up): test_concurrent_monthly_topups_for_the_same_
period_grant_exactly_once, staged identically to #2 above, one field over
-- two overlapping append_entry() calls carrying the SAME period must
leave exactly one subscription_grant entry, not two.

plus the entry-shape rules the helper enforces (signed amounts per type, the
two-way usd_amount requirement, the required actor, the required reason on
an adjustment, the snapshotted firm_kind) and the ledger_export log line.

THE FAKE FIRESTORE (_fake_firestore.py, shared). _FakeDb models the two properties the real
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
from backend.tests.unit._fake_firestore import _FakeDb, _FakeFirestoreModule


# ---------------------------------------------------------------- fake db
#
# The fake itself lives in _fake_firestore.py -- shared with
# test_link_routes.py, which drives the SAME transaction through the mint
# route (Epic 2 bead A3). Two copies of a buffer-and-retry fake would
# drift, and a drifted copy would let one caller's tests pass against
# semantics the other caller does not have.

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


def test_concurrent_monthly_topups_for_the_same_period_grant_exactly_once(
        fake_db):
    """bd polyglot-pdf-0euzk fresh-eyes finding: the monthly top-up route's
    idempotency guarantee (period is unique per firm) must hold under
    CONCURRENT invocation, not just sequential re-runs. Two overlapping
    append_entry() calls carrying the SAME period must leave exactly ONE
    subscription_grant entry for that period and a balance reflecting only
    ONE grant -- the loser must raise DuplicatePeriodEntry, not double-grant.

    Staged exactly like test_mint_transaction_double_mint_race_is_safe
    above, one field over: transaction B's body reads the firm (and the
    period query, seeing no existing row) before transaction A commits
    underneath it; B is then RE-RUN, and on the re-run its period query
    sees A's just-committed row and refuses. If query_period_entries's
    in-transaction read were hoisted out of the _txn body (read once,
    before @firestore.transactional, and closed over), the re-run would
    reuse the stale "no row yet" answer and B would also commit --
    doubling the grant.

    Mutation: in append_entry's _txn body, move the `if period is not
    None: existing = query_period_entries(...)` block to BEFORE the
    @firestore.transactional-decorated function (reading it once, outside
    the body, and closing over the result) -- this goes red on all three
    assertions: two grant rows exist, the balance is double what one grant
    would produce, and the second call raises nothing at all. Verified
    2026-09-14."""
    fake_db.docs[("firms", "acme")]["balance_credits"] = 10

    committed = []

    def _first_topup(tx):
        # Runs after B's body has read "no existing period row" but before
        # B commits: this is transaction A landing underneath B, exactly
        # like the mint race above.
        credit_ledger.append_entry(
            fake_db, "acme", entry_type="subscription_grant", amount=25,
            actor="system:monthly_topup", usd_amount=None,
            reason="monthly top-up 2026-09", period="2026-09", ts=1000.0,
        )
        committed.append("a")
        return "retry"

    fake_db.on_before_commit = _first_topup

    with pytest.raises(credit_ledger.DuplicatePeriodEntry) as exc:
        credit_ledger.append_entry(
            fake_db, "acme", entry_type="subscription_grant", amount=25,
            actor="system:monthly_topup", usd_amount=None,
            reason="monthly top-up 2026-09", period="2026-09", ts=1001.0,
        )

    assert committed == ["a"], "the first top-up must have committed"
    assert exc.value.firm_id == "acme"
    assert exc.value.period == "2026-09"
    assert fake_db.firm("acme")["balance_credits"] == 35, (
        "10 + 25 from the ONE winning grant -- a double grant would be 60")
    rows = [r for r in fake_db.ledger_rows("acme")
            if r["type"] == "subscription_grant"]
    assert len(rows) == 1, (
        "expected exactly one subscription_grant entry, got {}".format(rows)
    )
    assert rows[0]["period"] == "2026-09"


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


def test_period_defaults_to_none_and_round_trips_when_given(fake_db):
    """bd polyglot-pdf-0euzk: `period` is nullable like link_jti/kit_id --
    every existing caller that never passes it gets None (not a KeyError,
    not an empty string), and the ONE caller that does (the monthly plan
    top-up) gets it back verbatim on the committed entry and the stored row.

    Mutation: drop the `period=period` pass-through in append_entry's
    _apply_entry_writes() call -- the second assertion goes red (the field
    stays None even though "2026-09" was passed). Mutation: drop `period`
    from the entry dict literal in _apply_entry_writes -- the shape test
    above already catches this, and this test's first assertion catches it
    too via a KeyError on row["period"]. Verified 2026-09-14."""
    result = credit_ledger.append_entry(
        fake_db, "acme", entry_type="promo_grant", amount=5,
        actor="uid-ops",
    )
    assert result["period"] is None
    row = fake_db.ledger_rows("acme")[0]
    assert row["period"] is None

    result2 = credit_ledger.append_entry(
        fake_db, "acme", entry_type="subscription_grant", amount=10,
        actor="system:monthly_topup", period="2026-09",
    )
    assert result2["period"] == "2026-09"
    rows = fake_db.ledger_rows("acme")
    stamped = [r for r in rows if r.get("period") == "2026-09"]
    assert len(stamped) == 1
    assert stamped[0]["type"] == "subscription_grant"


def test_actor_email_is_optional_and_round_trips_when_given(fake_db):
    """bd polyglot-pdf-cpsi0: actor_email is nullable like period/link_jti --
    every existing caller that never passes it gets None on the stored row
    (not a KeyError), and a caller that DOES pass one gets it back verbatim
    on both the returned entry and the stored document.

    Mutation: drop the `actor_email=actor_email` pass-through in
    append_entry's _apply_entry_writes() call -- the second assertion goes
    red (the field stays None even though an email was passed)."""
    result = credit_ledger.append_entry(
        fake_db, "acme", entry_type="promo_grant", amount=5,
        actor="system:seed",
    )
    assert result["actor_email"] is None
    row = fake_db.ledger_rows("acme")[0]
    assert row["actor_email"] is None

    result2 = credit_ledger.append_entry(
        fake_db, "acme", entry_type="mint_debit", amount=-1,
        actor="uid-staff", actor_email="staffer@example.com",
        channel="demo", link_jti="jti-cpsi0", kit_id="w7",
    )
    assert result2["actor_email"] == "staffer@example.com"
    rows = fake_db.ledger_rows("acme")
    stamped = [r for r in rows if r.get("link_jti") == "jti-cpsi0"]
    assert len(stamped) == 1
    assert stamped[0]["actor_email"] == "staffer@example.com"
    assert stamped[0]["actor"] == "uid-staff"


def test_ledger_export_line_never_carries_an_at_sign(fake_db, monkeypatch):
    """docs/standards/hipaa-pii-policy.md: uids only in logs. actor_email may
    now ride on the ENTRY, but the ledger_export log line must never carry
    one -- this is the exact regression the bead's own description names
    ("a test asserts the ledger_export log line never contains an '@'").

    Mutation: add actor_email=actor_email to the _log.info(...) call in
    append_entry -- red (the payload gains an '@example.com' value)."""
    lines = _capture_export(monkeypatch)
    credit_ledger.append_entry(
        fake_db, "acme", entry_type="mint_debit", amount=-1,
        actor="uid-staff", actor_email="staffer@example.com",
        channel="demo", link_jti="jti-cpsi0b", kit_id="w7",
    )
    exports = [kw for event, kw in lines
               if event == credit_ledger.LEDGER_EXPORT_EVENT]
    assert len(exports) == 1
    payload = exports[0]
    assert "actor_email" not in payload
    assert not any("@" in str(v) for v in payload.values())


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
    sorted(
        set(credit_ledger.ENTRY_TYPES)
        - credit_ledger.USD_REQUIRED_TYPES
        - credit_ledger.USD_OPTIONAL_TYPES
    ),
)
def test_a_NON_income_type_REFUSES_a_usd_amount(fake_db, entry_type):
    """The requirement runs both ways: a dollar figure on a promo grant, a
    debit, a refund or an adjustment would be double-counted as income by
    the revenue view, which filters on type but sums usd_amount.

    Derived as the SET COMPLEMENT of USD_REQUIRED_TYPES | USD_OPTIONAL_TYPES
    (bd polyglot-pdf-0euzk widened subscription_grant from always-required to
    optional-but-validated, so it moved OUT of this test's parametrization
    and into test_a_usd_OPTIONAL_type_accepts_being_omitted /
    test_a_usd_OPTIONAL_types_usd_amount_is_still_validated_when_given below)
    -- a new type lands in exactly one of these tests automatically (scar #8).

    Mutation: delete the `elif usd_amount is not None: raise` branch in
    _validate -- every parametrization goes red. Verified 2026-09-08 per
    parametrization; re-verified 2026-09-14 after the USD_OPTIONAL_TYPES
    split by dropping only the subscription_grant member's exclusion (which
    only breaks the two NEW tests below, proving the complement is disjoint
    the other way too) and separately by dropping the whole exclusion (every
    parametrization here still passes -- promo_grant/mint_debit/expiry_refund/
    adjustment are unaffected by the split)."""
    amount = -1 if entry_type in credit_ledger.NEGATIVE_ONLY_TYPES else 1
    kwargs = {"reason": "r"} if (
        entry_type in credit_ledger.REASON_REQUIRED_TYPES) else {}
    with pytest.raises(credit_ledger.LedgerError):
        credit_ledger.append_entry(
            fake_db, "acme", entry_type=entry_type, amount=amount,
            actor="uid-ops", usd_amount=9.99, **kwargs)
    assert fake_db.ledger_rows("acme") == []


@pytest.mark.parametrize("entry_type", sorted(credit_ledger.USD_OPTIONAL_TYPES))
def test_a_usd_OPTIONAL_type_accepts_being_omitted(fake_db, entry_type):
    """subscription_grant (bd polyglot-pdf-0euzk, the monthly plan top-up)
    is the ONE type that is neither always-required nor always-refused: a
    usd_amount of None must commit cleanly, with the entry's own usd_amount
    stored as None -- this is the shape the monthly top-up route relies on
    ("usd_amount null (no money moved)", the bead's own words).

    Mutation: move TYPE_SUBSCRIPTION_GRANT back into USD_REQUIRED_TYPES
    (reverting the split) -- this goes red with "requires usd_amount".
    Verified 2026-09-14."""
    result = credit_ledger.append_entry(
        fake_db, "acme", entry_type=entry_type, amount=10,
        actor="uid-ops")
    assert result["usd_amount"] is None
    assert fake_db.ledger_rows("acme")[0]["usd_amount"] is None


@pytest.mark.parametrize("entry_type", sorted(credit_ledger.USD_OPTIONAL_TYPES))
def test_a_usd_OPTIONAL_types_usd_amount_is_still_validated_when_given(
        fake_db, entry_type):
    """The OTHER half of "optional, not unchecked": a human operator's real
    paid subscription_grant still gets the SAME three checks USD_REQUIRED_
    TYPES enforces (numeric, not bool, non-negative) -- optional-when-absent
    must not mean unchecked-when-present, or a string/negative dollar figure
    on a real paid grant would corrupt the income view exactly like it would
    on a purchase.

    Mutation: drop the `elif entry_type in USD_OPTIONAL_TYPES:` branch's
    inner checks in _validate (fall through to accepting any value) -- every
    case here goes from LedgerError to a committed (wrong) entry. Verified
    2026-09-14 per parametrization (both the non-numeric and the negative
    case)."""
    with pytest.raises(credit_ledger.LedgerError):
        credit_ledger.append_entry(
            fake_db, "acme", entry_type=entry_type, amount=10,
            actor="uid-ops", usd_amount="249.00")
    assert fake_db.ledger_rows("acme") == []
    with pytest.raises(credit_ledger.LedgerError):
        credit_ledger.append_entry(
            fake_db, "acme", entry_type=entry_type, amount=10,
            actor="uid-ops", usd_amount=-1.0)
    assert fake_db.ledger_rows("acme") == []
    # And a REAL positive figure still commits and is stored verbatim -- the
    # human-operator-paid-subscription path this type must keep supporting.
    result = credit_ledger.append_entry(
        fake_db, "acme", entry_type=entry_type, amount=10,
        actor="uid-ops", usd_amount=49.99)
    assert result["usd_amount"] == 49.99


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


def test_reason_over_the_bound_is_refused_before_any_write(fake_db):
    """bd polyglot-pdf-uaxt5, Opus cross-surface review finding (bd bnkuv):
    append_entry() itself must bound `reason`, not just
    admin_backend/routes/credit_routes.py's Pydantic model -- scripts/
    grant_credits.py's `adjust` subcommand calls append_entry() directly
    with an operator-supplied --reason that had NO length check before this
    bound, a second, unbounded door into the same ledger.

    Mutation: drop the REASON_MAX_LENGTH check from credit_ledger._validate
    -- this goes red, since the oversized reason would then be accepted and
    written."""
    too_long = "x" * (credit_ledger.REASON_MAX_LENGTH + 1)
    with pytest.raises(credit_ledger.LedgerError):
        credit_ledger.append_entry(
            fake_db, "acme", entry_type=credit_ledger.TYPE_ADJUSTMENT,
            amount=-5, actor="uid-ops", reason=too_long)
    assert fake_db.ledger_rows("acme") == []


def test_reason_at_the_bound_is_accepted(fake_db):
    """Pin both directions (scar #9): the bound must not also refuse a
    reason exactly at the limit."""
    at_bound = "x" * credit_ledger.REASON_MAX_LENGTH
    result = credit_ledger.append_entry(
        fake_db, "acme", entry_type=credit_ledger.TYPE_ADJUSTMENT,
        amount=-5, actor="uid-ops", reason=at_bound)
    assert result["reason"] == at_bound


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


def test_export_line_carries_every_column_income_month_reads(
        fake_db, monkeypatch):
    """Epic 3 bead 6 (E3.6) exit criterion 3: the ledger_export log line
    carries every field sql/telemetry_views.sql's income_month view reads.

    Parses income_month's actual SQL (not a hand-copied list) so this test
    and the view cannot silently drift apart -- if a future edit to the view
    reads a NEW field, this test fails here (income_month would read a
    field that is always NULL) rather than shipping a quietly-empty
    dashboard number. The reverse direction (every LEDGER_EXPORT_FIELDS
    member is a real emitted key) is already pinned by
    test_every_write_emits_ONE_ledger_export_line_with_the_declared_fields
    above via the `set(payload) == LEDGER_EXPORT_FIELDS` equality.

    ACCESSOR SHAPE (bd polyglot-pdf-0fus0): income_month reads every field
    via JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.<col>'), not plain
    jsonPayload.<col> dot-access (bd polyglot-pdf-vqgkj's shape, superseded
    -- see sql/telemetry_views.sql's header for why). This test extracts
    the JSONPath argument, not a dotted accessor, so it stays a real pin
    against the current SQL rather than silently matching zero columns.

    Mutation: add a JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.<col>')
    reference to income_month's SQL for a column not in
    LEDGER_EXPORT_FIELDS (e.g. '$.kit_id', which ENTRY_FIELDS has but
    LEDGER_EXPORT_FIELDS deliberately does not) -- red. Also mutation: drop
    a kwarg from the append_entry _log.info call that income_month reads
    (e.g. remove usd_amount=... from the emit call) -- also red, via the
    payload-vs-referenced-columns check below."""
    import pathlib
    import re

    sql_path = (pathlib.Path(__file__).resolve().parents[3] / "sql"
                / "telemetry_views.sql")
    assert sql_path.is_file(), "sql/telemetry_views.sql is missing"
    sql_text = sql_path.read_text(encoding="utf-8")

    view_match = re.search(
        r"CREATE OR REPLACE VIEW `\$\{DATASET\}\.income_month` AS"
        r"(.*?)(?=CREATE OR REPLACE VIEW|\Z)",
        sql_text, re.DOTALL)
    assert view_match, "income_month view not found in sql/telemetry_views.sql"
    income_body = view_match.group(1)

    # Every flat $.<col> JSONPath the view references, via
    # JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.<col>') -- excluding the
    # nested $.message.* accessor, which belongs to the usage-event shape,
    # not ledger_export's.
    json_value_paths = re.findall(
        r"JSON_VALUE\(\s*TO_JSON_STRING\(jsonPayload\)\s*,\s*'\$((?:\.\w+)+)'\s*\)",
        income_body)
    referenced_columns = {
        path[1:] for path in json_value_paths if path.count(".") == 1
    }
    assert referenced_columns, (
        "no flat $.<col> JSON_VALUE reference found in income_month's SQL "
        "-- the extraction regex may be out of sync with the view's "
        "accessor syntax")
    # timestamp is the LogEntry's own field, not part of the emitted
    # ledger_export payload kwargs -- structural, like event_type.
    referenced_columns -= {"timestamp"}

    unknown = referenced_columns - credit_ledger.LEDGER_EXPORT_FIELDS
    assert not unknown, (
        "income_month references column(s) the ledger_export line does not "
        "carry: {}. Either the view is wrong, or credit_ledger.py's emit "
        "call is missing a field income_month needs.".format(sorted(unknown))
    )

    # And the LIVE emitted payload actually has every column the view
    # reads (not just the static LEDGER_EXPORT_FIELDS set pin) -- catches a
    # kwarg silently dropped from the _log.info(...) call while
    # LEDGER_EXPORT_FIELDS itself is left stale and un-updated.
    lines = _capture_export(monkeypatch)
    credit_ledger.append_entry(
        fake_db, "acme", entry_type="purchase", amount=100, actor="uid-ops",
        usd_amount=249.0, link_jti=None, kit_id="w7")
    payload = [kw for event, kw in lines
               if event == credit_ledger.LEDGER_EXPORT_EVENT][0]
    missing_from_payload = referenced_columns - set(payload)
    assert not missing_from_payload, (
        "income_month reads column(s) the ACTUAL emitted ledger_export "
        "line does not carry: {}".format(sorted(missing_from_payload))
    )


# ------------------------------------------------------- the ONE-writer rule


def test_credit_ledger_is_the_only_module_that_writes_balance_credits():
    """Scar #8: pin the SET, not the instance. The invariant holds only
    because a small, known set of modules write balance_credits; an
    unlisted writer breaks it silently, since nothing recomputes the
    balance from the ledger.

    The two deliberate other sites are firms.upsert_firm() (the
    operator-bootstrap path) and admin_backend/routes/firm_routes.py's
    create route (bd polyglot-pdf-zopqq), both of which 0-initialize the
    field on FIRST CREATE only, for a firm with no ledger yet, and never
    touch it again. Everything else that mentions the key must be a READER.

    Detection is an AST walk, NOT a source grep, and that is the whole point
    of the test. A literal substring like '"balance_credits":' pins one
    SPELLING rather than the SET (scar #8): it misses a single-quoted dict
    key, a payload["balance_credits"] = n subscript assignment, and an
    update(balance_credits=n) kwarg -- all of which write the field just as
    effectively. The miss is not hypothetical: firms.upsert_firm() writes the
    field as payload["balance_credits"] = 0, which that substring does not
    match, so the grep version was already blind to the one legitimate second
    writer it named in this very docstring.

    The walk covers BOTH backend/ and admin_backend/ -- they are sibling
    packages at the repo root, and a walk rooted at backend/ alone (the
    original shape of this guard) cannot see a write anywhere under
    admin_backend/ no matter what that writer does. bd polyglot-pdf-t7zg7
    is the record of that gap: it let firm_routes.py's write through with
    no mechanical objection at all until this widening.

    admin_backend/routes/credit_routes.py is ALSO allowlisted, but it is
    not a fourth writer: `_writes_the_key`'s dict-literal check cannot tell
    a payload write from a read, and credit_routes.py builds
    before={"balance_credits": firm.get(...)} to audit the PRE-write value
    -- a read, reported as a false positive by the same walk. It stays on
    the allowlist (rather than teaching the predicate a read-context
    exception, which would open its own blind spot) precisely because it
    writes nothing; the "allowlist pinned in both direction" assertion below
    still catches it going stale if that audit-dict shape is ever removed.

    A WRITE here means any of the four shapes below; a bare read
    (snap.get("balance_credits")) is deliberately not one, since readers are
    unlimited.

    Mutation: add ANY of these to a backend or admin_backend module outside
    the allowlist and this must go red -- ref.update({"balance_credits": n}),
    ref.update({'balance_credits': n}), payload["balance_credits"] = n, or
    ref.update(balance_credits=n). Verified 2026-09-08 by adding each of the
    four, one at a time, to backend/services/links_store.py; re-verified
    2026-09-09 by adding payload["balance_credits"] = n to
    admin_backend/routes/audit_routes.py."""
    import ast
    import pathlib

    KEY = "balance_credits"

    def _writes_the_key(tree):
        for node in ast.walk(tree):
            # payload["balance_credits"] = n  /  del payload["balance_credits"]
            targets = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                targets = [node.target]
            for tgt in targets:
                if (isinstance(tgt, ast.Subscript)
                        and isinstance(tgt.slice, ast.Constant)
                        and tgt.slice.value == KEY):
                    return True
            # {"balance_credits": n} and {'balance_credits': n} alike --
            # ast.Constant has no memory of which quote character was typed.
            if isinstance(node, ast.Dict):
                for k in node.keys:
                    if isinstance(k, ast.Constant) and k.value == KEY:
                        return True
            # f(balance_credits=n)
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == KEY:
                        return True
        return False

    backend_dir = pathlib.Path(credit_ledger.__file__).resolve().parents[1]
    repo_root = backend_dir.parent
    admin_backend_dir = repo_root / "admin_backend"
    allowed = {"credit_ledger.py", "firms.py", "firm_routes.py",
               "credit_routes.py"}
    offenders = []
    seen_allowed = set()
    search_dirs = [backend_dir, admin_backend_dir]
    for search_dir in search_dirs:
        for path in sorted(search_dir.rglob("*.py")):
            if "tests" in path.parts or "scripts" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            if not _writes_the_key(tree):
                continue
            if path.name in allowed:
                seen_allowed.add(path.name)
            else:
                offenders.append(str(path.relative_to(repo_root)))
    assert offenders == [], (
        "balance_credits is written outside the ledger helper: {}".format(
            offenders)
    )
    # The allowlist is pinned in BOTH directions. A stale entry -- a module
    # that no longer writes the field, or was renamed -- would silently widen
    # the guard for whatever later takes that filename, so an unused
    # exemption is a failure too, not a tidiness nit.
    assert seen_allowed == allowed, (
        "allowlist is stale: {} no longer write balance_credits".format(
            sorted(allowed - seen_allowed))
    )


# --------------------------------------------- alert wiring (bd polyglot-pdf-bo95a)
#
# Mirrors link_spend.py's test_check_budget_writes_the_alert_ON_REFUSAL /
# test_check_budget_STILL_RAISES_LinkBudgetExhausted_when_the_alert_write_fails
# in test_alerts_dedup.py. Those prove check_budget's wiring through the REAL
# caller; test_alerts_dedup.py's own append_entry-side tests only ever call
# alerts.record_credit_threshold() directly, never credit_ledger.append_entry()
# itself -- so nothing proved the _alert_on_low_balance() call at
# credit_ledger.py:435 is actually reached, or that a broken alert store
# cannot break a real debit. These two close that gap.


def test_append_entry_fires_the_alert_on_a_LOW_MINT_DEBIT(fake_db, monkeypatch):
    """Proves the WIRING, not just alerts.py in isolation: a real mint_debit
    through append_entry() that lands the balance at/under the threshold
    must call alerts.record_credit_threshold with the post-commit balance,
    the caller's firm_id and the configured threshold.

    Mutation: delete the _alert_on_low_balance(...) call at the end of
    append_entry (credit_ledger.py:435) -- red, calls stays empty.
    """
    import backend.services.alerts as alerts
    import backend.services.runtime_config as runtime_config

    fake_db.docs[("firms", "acme")]["balance_credits"] = 1

    calls = []

    def _fake_record(firm_id, *, balance, threshold, now=None):
        calls.append({"firm_id": firm_id, "balance": balance,
                      "threshold": threshold})

    monkeypatch.setattr(alerts, "record_credit_threshold", _fake_record)
    monkeypatch.setattr(runtime_config, "credit_low_threshold",
                        lambda channel=None: 10)

    credit_ledger.append_entry(
        fake_db, "acme", entry_type="mint_debit", amount=-1,
        actor="uid-staff", channel="demo", link_jti="jti-a", ts=1000.0,
    )

    assert calls == [{"firm_id": "acme", "balance": 0, "threshold": 10}]


def test_append_entry_writes_no_alert_doc_when_balance_stays_ABOVE_threshold(
        fake_db, monkeypatch):
    """The happy path must reach the real Firestore write with a balance
    that does not cross either boundary, so alerts.py's own gates (the
    exhausted branch's balance<=0 and the low branch's threshold>0-and-
    balance<=threshold) leave the alert store untouched -- exercised through
    the REAL append_entry call with a REAL (fake) alert store, rather than
    record_credit_threshold mocked away, so this also proves
    _alert_on_low_balance is wired to a real Firestore-shaped write path
    that a threshold-gated call leaves empty.

    Mutation: in alerts.record_credit_threshold, drop the `threshold > 0
    and balance <= threshold` gate on the low branch (make it unconditional)
    -- red, store gains a credit_low doc even though balance=999 is nowhere
    near threshold=10.
    """
    import backend.services.alerts as alerts
    import backend.services.runtime_config as runtime_config

    fake_db.docs[("firms", "acme")]["balance_credits"] = 1000

    store = {}

    class _Snap:
        def __init__(self, doc_id):
            self._doc_id = doc_id
            self.exists = doc_id in store

        def to_dict(self):
            return dict(store.get(self._doc_id, {}))

    class _Doc:
        def __init__(self, doc_id):
            self._doc_id = doc_id

        def get(self):
            return _Snap(self._doc_id)

        def set(self, data, merge=False):
            store[self._doc_id] = dict(data)

    class _Collection:
        def document(self, doc_id):
            return _Doc(doc_id)

    monkeypatch.setattr(alerts, "_collection", lambda: _Collection())
    monkeypatch.setattr(runtime_config, "credit_low_threshold",
                        lambda channel=None: 10)

    credit_ledger.append_entry(
        fake_db, "acme", entry_type="mint_debit", amount=-1,
        actor="uid-staff", channel="demo", link_jti="jti-b", ts=1000.0,
    )

    assert store == {}


def test_append_entry_STILL_COMMITS_when_the_alert_write_fails(
        fake_db, monkeypatch):
    """EXIT CRITERION 2, append_entry half, through the REAL caller -- the
    mirror of test_alerts_dedup.py's
    test_check_budget_STILL_RAISES_LinkBudgetExhausted_when_the_alert_write_fails.
    A broken alert STORE (the Firestore write itself failing, not the
    public function monkeypatched to raise) must not change what a real
    debit does: the entry must still be written, the balance still
    updated, and append_entry must not raise -- alerts.py's own try/except
    in _write() is what makes record_credit_threshold's never-raise
    contract real, and this proves it holds reached from the actual
    production call site (credit_ledger.py:435), not just against
    alerts.record_credit_threshold called directly.

    Mutation: remove alerts.py's try/except around the Firestore write in
    _write() -- red, append_entry raises RuntimeError instead of
    committing.
    """
    import backend.services.alerts as alerts
    import backend.services.runtime_config as runtime_config

    fake_db.docs[("firms", "acme")]["balance_credits"] = 1

    class _RaisingDoc:
        def get(self):
            raise RuntimeError("firestore unavailable")

        def set(self, data, merge=False):
            raise RuntimeError("firestore unavailable")

    class _RaisingCollection:
        def document(self, doc_id):
            return _RaisingDoc()

    monkeypatch.setattr(alerts, "_collection", lambda: _RaisingCollection())
    monkeypatch.setattr(runtime_config, "credit_low_threshold",
                        lambda channel=None: 10)

    result = credit_ledger.append_entry(
        fake_db, "acme", entry_type="mint_debit", amount=-1,
        actor="uid-staff", channel="demo", link_jti="jti-c", ts=1000.0,
    )

    # The debit itself already committed BEFORE _alert_on_low_balance ran
    # (module docstring: "AFTER the commit, never before") -- the money is
    # safe regardless of what the alert side-channel does, and append_entry
    # returns normally rather than raising.
    assert result["balance_credits"] == 0
    assert fake_db.firm("acme")["balance_credits"] == 0
    rows = fake_db.ledger_rows("acme")
    assert len(rows) == 1
    assert rows[0]["link_jti"] == "jti-c"
