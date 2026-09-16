"""POST /admin/credits/monthly-topup (bd polyglot-pdf-0euzk; DEFAULT_PLAN's
rollover default flipped True by bd polyglot-pdf-hnlj3, 2026-09-15,
maintainer decision: credits roll over, no real reason not to).

Pins the bead's exit criterion 1: "three firms (balance 10 no-rollover,
balance 40 no-rollover, balance 10 rollover=true) get exactly [+25, nothing,
+35] with period stamped; a second run in the same month writes nothing."
Every scenario below still constructs its OWN explicit plan dict (never
plans.DEFAULT_PLAN) so a future default change cannot silently alter what
these prove -- test_a_firm_on_the_actual_default_plan_rolls_over below is
the ONE test that reads plans.DEFAULT_PLAN directly, pinning that the
DEFAULT is now the rollover=True row of this same scenario table (bd
polyglot-pdf-hnlj3 exit criterion 1: "the top-up scenario table's default
row adds the full amount").

IDEMPOTENCY IS TWO LAYERS, SEQUENTIAL AND CONCURRENT (fresh-eyes finding
added post-review): _already_topped_up_this_period is a pre-transaction
fast path covering the sequential re-run case (mutation-verified here by
disabling it ALONE and confirming the transactional layer still catches
it -- test_dropping_the_fast_path_check_alone_does_not_double_grant), and
credit_ledger.append_entry()'s own in-transaction re-check
(DuplicatePeriodEntry) is what actually makes two OVERLAPPING invocations
safe (pinned directly, with a staged concurrent commit, by
test_concurrent_monthly_topups_for_the_same_period_grant_exactly_once in
test_credit_ledger.py). test_dropping_both_period_checks_breaks_idempotency
below proves the pair together, not either alone, is what the guarantee
rests on.

THE FAKE FIRESTORE mirrors test_sweep_routes.py's _FakeDb (tuple-path
documents, a real all-or-nothing transaction, and a `.where()`-filtered
`.stream()`/`.get()` over a bare collection) -- this route's Firestore
surface is a plain firms iteration plus the ledger-subcollection
idempotency query, both shapes that fake already proves out. It has NO
contention/retry model (unlike backend/tests/unit/_fake_firestore.py,
which is what the concurrent race test above uses) -- this file's own
_FakeDb is for the route's per-firm outcome-shape tests, not for staging a
race.

ASCII only.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import backend.services.credit_ledger as credit_ledger
import backend.services.plans as plans
from admin_backend.main import app
from admin_backend.routes import credit_routes
from admin_backend.services import admin_auth, audit_log


# --------------------------------------------------------------------------
# The fake Firestore: identical shape to test_sweep_routes.py's _FakeDb.
# --------------------------------------------------------------------------

class _Snap:
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
        return _Snap(self._path, self._store.docs.get(self._path))


class _Query:
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

    def limit(self, n):
        return self

    def _matches(self, data):
        for field, op, value in self._clauses:
            actual = data.get(field)
            if op == "==":
                if actual != value:
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

    def get(self, transaction=None):
        # credit_ledger.py's query_period_entries uses .get(transaction=...)
        # (the real Admin SDK's transactional query read; .stream() does
        # not accept a transaction) -- this fake has no contention/retry
        # model (unlike _fake_firestore.py's _FakeDb, which is what the
        # dedicated race test in test_credit_ledger.py drives), so `get`
        # here is just `stream` as a list.
        return list(self.stream())


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

    def set(self, ref, data, merge=False):
        if self._store.audit_write_error is not None and \
                ref._path[0] == audit_log.COLLECTION:
            raise self._store.audit_write_error
        self._buffer.append((ref._path, dict(data), merge))

    def commit(self):
        for path, data, merge in self._buffer:
            self._store.apply_set(path, data, merge)
        self._buffer = []


class _FakeDb:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})
        self.auto_id_counter = 0
        self.audit_write_error = None

    def collection(self, name):
        return _Collection(self, (name,))

    def transaction(self):
        return _Transaction(self)

    def apply_set(self, path, data, merge):
        if merge and path in self.docs:
            self.docs[path].update(data)
        else:
            self.docs[path] = dict(data)

    # test helpers ----------------------------------------------------
    def firm(self, firm_id):
        return self.docs.get(("firms", firm_id))

    def ledger_rows(self, firm_id):
        return [data for path, data in self.docs.items()
                if path[:3] == ("firms", firm_id, "ledger")]

    def audit_rows(self):
        return [v for path, v in self.docs.items()
                if path[0] == audit_log.COLLECTION]


class _FakeTransactionalDecorator:
    def __call__(self, fn):
        def wrapper(transaction):
            fn(transaction)
            transaction.commit()
        return wrapper


class _FakeFirestoreModule:
    transactional = _FakeTransactionalDecorator()


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDb()
    import firebase_admin
    monkeypatch.setattr(firebase_admin, "firestore", _FakeFirestoreModule(),
                        raising=False)
    monkeypatch.setattr("backend.services.auth.get_db", lambda: db)
    return db


def _seed_firm(fake_db, firm_id, *, balance, plan, status="active",
               kind="live"):
    fake_db.docs[("firms", firm_id)] = {
        "name": firm_id, "contact_email": "ops@example.com",
        "status": status, "kind": kind, "balance_credits": balance,
        "plan": plan,
    }


# --------------------------------------------------------------------------
# OIDC gate plumbing -- identical shape to test_sweep_routes.py's
# scheduler_env fixture, one route/env-var pair over.
# --------------------------------------------------------------------------

SCHEDULER_EMAIL = "monthly-topup-scheduler-sa@test-project.iam.gserviceaccount.com"
ADMIN_SERVICE_URL = "https://polyglot-admin-test.a.run.app"
AUDIENCE = ADMIN_SERVICE_URL + "/admin/credits/monthly-topup"


@pytest.fixture
def scheduler_env(monkeypatch):
    monkeypatch.setenv("ADMIN_SERVICE_URL", ADMIN_SERVICE_URL)
    monkeypatch.setenv("MONTHLY_TOPUP_SCHEDULER_SA_EMAIL", SCHEDULER_EMAIL)

    def _fake_verify(token, audience):
        if token == "valid-scheduler-token":
            return {"email": SCHEDULER_EMAIL, "email_verified": True,
                    "aud": audience}
        if token == "valid-other-caller-token":
            return {"email": "someone-else@other-project.iam.gserviceaccount.com",
                    "email_verified": True, "aud": audience}
        raise ValueError("invalid token: {}".format(token))

    monkeypatch.setattr(admin_auth, "_verify_google_id_token", _fake_verify)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _auth(token):
    return {"Authorization": "Bearer {}".format(token)} if token else {}


def _post_topup(client):
    return client.post(
        "/admin/credits/monthly-topup",
        headers=_auth("valid-scheduler-token"))


# --------------------------------------------------------------------------
# EXIT CRITERION 1: the three-firm scenario, verbatim.
# --------------------------------------------------------------------------

def test_three_firms_get_exactly_the_bead_scenarios_amounts(
        client, fake_db, scheduler_env, monkeypatch):
    """balance 10 no-rollover -> +25 (tops up to the 35-credit cap);
    balance 40 no-rollover -> nothing (already over the cap);
    balance 10 rollover=true -> +35 (adds the full monthly_credits).

    Mutation: change the no-rollover amount formula from
    `monthly_credits - balance` to `monthly_credits` -- firm-a's expected
    balance goes from 35 to 45, this test's first assertion goes red.
    Mutation: change the rollover branch to `monthly_credits - balance`
    (the no-rollover formula) -- firm-c's expected balance goes from 45 to
    25, this test's third assertion goes red. Verified 2026-09-14."""
    monkeypatch.setattr(
        credit_routes, "_current_period", lambda now: "2026-09")

    plan_no_rollover = {"tier": "starter", "monthly_credits": 35,
                        "rollover": False}
    plan_rollover = {"tier": "starter", "monthly_credits": 35,
                     "rollover": True}
    _seed_firm(fake_db, "firm-a", balance=10, plan=plan_no_rollover)
    _seed_firm(fake_db, "firm-b", balance=40, plan=plan_no_rollover)
    _seed_firm(fake_db, "firm-c", balance=10, plan=plan_rollover)

    resp = _post_topup(client)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert fake_db.firm("firm-a")["balance_credits"] == 35  # +25
    assert fake_db.firm("firm-b")["balance_credits"] == 40  # nothing
    assert fake_db.firm("firm-c")["balance_credits"] == 45  # +35

    assert sorted(body["topped_up"]) == ["firm-a", "firm-c"]
    assert body["skipped_at_cap"] == ["firm-b"]

    a_rows = [r for r in fake_db.ledger_rows("firm-a")
              if r["type"] == "subscription_grant"]
    assert len(a_rows) == 1
    assert a_rows[0]["amount"] == 25
    assert a_rows[0]["period"] == "2026-09"
    assert a_rows[0]["usd_amount"] is None
    # bd polyglot-pdf-cpsi0: a scheduled job is a system actor with no
    # human behind it at write time -- actor stays the "system:" string,
    # and actor_email stays None, exactly as before this bead.
    assert a_rows[0]["actor"] == credit_routes.MONTHLY_TOPUP_ACTOR
    assert a_rows[0]["actor_email"] is None

    c_rows = [r for r in fake_db.ledger_rows("firm-c")
              if r["type"] == "subscription_grant"]
    assert len(c_rows) == 1
    assert c_rows[0]["amount"] == 35
    assert c_rows[0]["period"] == "2026-09"

    # firm-b got NO subscription_grant row at all -- already at the cap.
    assert [r for r in fake_db.ledger_rows("firm-b")
            if r["type"] == "subscription_grant"] == []


def test_a_firm_on_the_actual_default_plan_rolls_over(
        client, fake_db, scheduler_env, monkeypatch):
    """bd polyglot-pdf-hnlj3 exit criterion 1: "the top-up scenario table's
    default row adds the full amount." Every other scenario in this file
    hand-writes its own plan dict; this is the one test that seeds a firm
    with plans.DEFAULT_PLAN ITSELF (the object admin_backend/routes/
    firm_routes.py's create route and scripts/backfill_firm_kind.py's
    backfill both actually apply to a real firm with no stored plan), so a
    firm that gets no plan editor visit at all -- the common case -- rolls
    over, exactly like firm-c above.

    Mutation: flip plans.DEFAULT_PLAN["rollover"] back to False -- this
    goes red (firm-a would land at 35, the no-rollover to-the-cap amount,
    instead of 45). Verified 2026-09-15."""
    monkeypatch.setattr(
        credit_routes, "_current_period", lambda now: "2026-09")
    _seed_firm(fake_db, "firm-a", balance=10, plan=dict(plans.DEFAULT_PLAN))

    resp = _post_topup(client)
    assert resp.status_code == 200, resp.text
    assert resp.json()["topped_up"] == ["firm-a"]
    assert fake_db.firm("firm-a")["balance_credits"] == 45  # 10 + 35


def test_a_second_run_the_same_month_writes_nothing(
        client, fake_db, scheduler_env, monkeypatch):
    """EXIT CRITERION 1's idempotency half. A re-run (a retried Scheduler
    call, or a second manual invocation) in the SAME period must top up
    NOTHING for a firm it already topped up.

    Mutation-verified below (test_dropping_both_period_checks_breaks_
    idempotency) by disabling BOTH idempotency layers' shared query and
    watching this exact scenario double-grant; the fast-path-only case is
    covered separately by
    test_dropping_the_fast_path_check_alone_does_not_double_grant, which
    proves the transactional layer alone is already enough."""
    monkeypatch.setattr(
        credit_routes, "_current_period", lambda now: "2026-09")
    _seed_firm(fake_db, "firm-a", balance=10, plan={
        "tier": "starter", "monthly_credits": 35, "rollover": False})

    first = _post_topup(client)
    assert first.status_code == 200, first.text
    assert first.json()["topped_up"] == ["firm-a"]
    assert fake_db.firm("firm-a")["balance_credits"] == 35

    second = _post_topup(client)
    assert second.status_code == 200, second.text
    assert second.json()["topped_up"] == []
    assert second.json()["skipped_already_run"] == ["firm-a"]
    assert fake_db.firm("firm-a")["balance_credits"] == 35

    grant_rows = [r for r in fake_db.ledger_rows("firm-a")
                  if r["type"] == "subscription_grant"]
    assert len(grant_rows) == 1


def test_dropping_the_fast_path_check_alone_does_not_double_grant(
        client, fake_db, scheduler_env, monkeypatch):
    """TEST THE TEST (docs/standards/testing.md#test-the-tests), UPDATED
    after the fresh-eyes concurrency finding on bd polyglot-pdf-0euzk: this
    route's idempotency is now TWO layers, not one --
    _already_topped_up_this_period (a pre-transaction fast path, pure
    optimization) and credit_ledger.append_entry()'s own in-transaction
    re-check (raises DuplicatePeriodEntry -- the RACE-SAFE layer; see
    test_concurrent_monthly_topups_for_the_same_period_grant_exactly_once
    in test_credit_ledger.py, which pins THAT layer directly against a
    staged concurrent commit).

    This test now proves the fast path is REDUNDANT with the transactional
    layer for a plain sequential re-run, not that it is the only thing
    standing between here and a double grant: with ONLY the fast path
    disabled, a second run still writes nothing, because
    topup_firm catches the transactional layer's
    DuplicatePeriodEntry and reports skipped_already_run.

    Uses rollover=True (which always grants monthly_credits regardless of
    balance, see test_rollover_true_always_adds_even_when_already_over_cap)
    so the at-cap skip cannot mask a broken idempotency check the way it
    would for a no-rollover plan.

    Mutation: this test's own assertions were the ones that changed --
    before the fix, a disabled fast path with no transactional backstop
    let a second run reach balance 80 (45 + 35) with 2 grant rows; now it
    correctly stays at 45 with 1 row. Verified 2026-09-14 by reverting the
    _apply_entry_writes call to skip the DuplicatePeriodEntry check (see
    test_concurrent_monthly_topups_for_the_same_period_grant_exactly_once's
    own mutation for the direct version of this)."""
    monkeypatch.setattr(
        credit_routes, "_current_period", lambda now: "2026-09")
    monkeypatch.setattr(
        credit_routes, "_already_topped_up_this_period",
        lambda db, firm_id, period: False)
    _seed_firm(fake_db, "firm-a", balance=10, plan={
        "tier": "starter", "monthly_credits": 35, "rollover": True})

    first = _post_topup(client)
    assert first.json()["topped_up"] == ["firm-a"]
    assert fake_db.firm("firm-a")["balance_credits"] == 45  # 10 + 35

    second = _post_topup(client)
    assert second.status_code == 200, second.text
    assert second.json()["topped_up"] == [], (
        "the fast path was disabled, but append_entry's own in-transaction "
        "re-check must still catch this and report skipped_already_run")
    assert second.json()["skipped_already_run"] == ["firm-a"]
    assert fake_db.firm("firm-a")["balance_credits"] == 45, (
        "must NOT be 80 (45 + 35) -- the transactional layer is the "
        "backstop, not just the fast path")

    grant_rows = [r for r in fake_db.ledger_rows("firm-a")
                  if r["type"] == "subscription_grant"]
    assert len(grant_rows) == 1, (
        "expected exactly one subscription_grant entry even with the fast "
        "path disabled, got {}".format(grant_rows)
    )


def test_dropping_both_period_checks_breaks_idempotency(
        client, fake_db, scheduler_env, monkeypatch):
    """The genuine "both layers gone" case, for completeness: patching OUT
    the shared credit_ledger.query_period_entries() helper that BOTH the
    fast path and the in-transaction re-check call removes the guarantee
    entirely and a second run in the same period double-grants -- proving
    the fast path and the transactional check are not each independently
    redundant window-dressing, they are the ONLY two places this guarantee
    is enforced, and removing what both of them call under the hood is
    what it actually takes to lose it.

    Mutation: this IS the mutation -- there is no further code change to
    apply; patching query_period_entries to always report "no existing
    entry" is the direct simulation of both checks' shared read failing to
    see the prior entry."""
    monkeypatch.setattr(
        credit_routes, "_current_period", lambda now: "2026-09")
    monkeypatch.setattr(
        credit_ledger, "query_period_entries",
        lambda db, firm_id, entry_type, period, transaction=None: [])
    _seed_firm(fake_db, "firm-a", balance=10, plan={
        "tier": "starter", "monthly_credits": 35, "rollover": True})

    _post_topup(client)
    assert fake_db.firm("firm-a")["balance_credits"] == 45  # 10 + 35
    _post_topup(client)
    assert fake_db.firm("firm-a")["balance_credits"] == 80  # 45 + 35 (!)

    grant_rows = [r for r in fake_db.ledger_rows("firm-a")
                  if r["type"] == "subscription_grant"]
    assert len(grant_rows) == 2, (
        "with BOTH layers' shared query stubbed out, a second run in the "
        "SAME period double-granted -- this is the exact bug the two "
        "checks together prevent")


def test_rollover_true_always_adds_even_when_already_over_cap(
        client, fake_db, scheduler_env, monkeypatch):
    """rollover=True never skips at-cap -- it is an accumulating allotment,
    not a ceiling. Mutation: apply the no-rollover at-cap skip to the
    rollover branch too -- this goes red (firm-a would get skipped_at_cap
    instead of topped_up)."""
    monkeypatch.setattr(
        credit_routes, "_current_period", lambda now: "2026-09")
    _seed_firm(fake_db, "firm-a", balance=100, plan={
        "tier": "starter", "monthly_credits": 35, "rollover": True})

    resp = _post_topup(client)
    assert resp.status_code == 200, resp.text
    assert resp.json()["topped_up"] == ["firm-a"]
    assert fake_db.firm("firm-a")["balance_credits"] == 135


def test_no_rollover_exactly_at_the_cap_is_skipped_not_failed(
        client, fake_db, scheduler_env, monkeypatch):
    """Pins the exact `balance == monthly_credits` boundary of the
    no-rollover at-cap check (fresh-eyes finding on bd polyglot-pdf-0euzk:
    every existing scenario used a balance strictly under the cap (10) or
    strictly over it (40), never exactly AT it, so a one-character `>=` ->
    `>` regression would slip through green).

    At exactly the cap there is nothing to grant: amount would compute to
    monthly_credits - balance == 0, and credit_ledger._validate rejects a
    zero amount with LedgerError("amount must be non-zero") -- a
    LedgerError, not DuplicatePeriodEntry, which topup_firm does not
    catch, so it would propagate to _run_monthly_topup's generic
    except Exception and silently misclassify this firm as "failed"
    instead of "skipped_at_cap".

    Mutation: change `if balance >= monthly_credits:` to
    `if balance > monthly_credits:` in topup_firm -- this goes red:
    firm-a moves from skipped_at_cap/no ledger row to failed/(still) no
    ledger row, both assertions below flip. Verified 2026-09-14."""
    monkeypatch.setattr(
        credit_routes, "_current_period", lambda now: "2026-09")
    _seed_firm(fake_db, "firm-a", balance=35, plan={
        "tier": "starter", "monthly_credits": 35, "rollover": False})

    resp = _post_topup(client)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["skipped_at_cap"] == ["firm-a"]
    assert body["failed"] == []
    assert body["topped_up"] == []
    assert fake_db.firm("firm-a")["balance_credits"] == 35

    assert [r for r in fake_db.ledger_rows("firm-a")
            if r["type"] == "subscription_grant"] == []


def test_a_negative_balance_is_brought_up_to_the_cap(
        client, fake_db, scheduler_env, monkeypatch):
    """The metered soft-launch mode can leave a firm's balance negative
    (CREDITS_ENFORCED off) -- the top-up must bring it UP TO the cap, a
    bigger grant than a from-zero top-up would be.

    Mutation: clamp `balance` to 0 before computing amount -- this goes red
    (firm-a would get +35 landing at 35, not +45 landing at 35 from -10...
    wait: -10 + 45 = 35, and 0 + 35 = 35 -- both land at the SAME final
    balance, so the real regression this guards is a formula that instead
    computes amount from a CLAMPED balance while still adding it to the
    UNCLAMPED one, e.g. `monthly_credits - max(balance, 0)` applied to the
    real balance -- that would grant only 35 and land at 25, which this
    assertion catches)."""
    monkeypatch.setattr(
        credit_routes, "_current_period", lambda now: "2026-09")
    _seed_firm(fake_db, "firm-a", balance=-10, plan={
        "tier": "starter", "monthly_credits": 35, "rollover": False})

    resp = _post_topup(client)
    assert resp.status_code == 200, resp.text
    assert resp.json()["topped_up"] == ["firm-a"]
    assert fake_db.firm("firm-a")["balance_credits"] == 35


def test_a_suspended_firm_is_not_topped_up(client, fake_db, scheduler_env,
                                            monkeypatch):
    """Mutation: drop the `status != FIRM_STATUS_ACTIVE` skip -- this goes
    red (the suspended firm would be topped up too)."""
    monkeypatch.setattr(
        credit_routes, "_current_period", lambda now: "2026-09")
    _seed_firm(fake_db, "firm-a", balance=10, status="suspended", plan={
        "tier": "starter", "monthly_credits": 35, "rollover": False})

    resp = _post_topup(client)
    assert resp.status_code == 200, resp.text
    assert resp.json()["topped_up"] == []
    assert fake_db.firm("firm-a")["balance_credits"] == 10


def test_a_firm_with_no_plan_is_skipped_not_failed(
        client, fake_db, scheduler_env, monkeypatch):
    """A firm predating this bead (or a fresh doc backfill_firm_kind.py has
    not reached yet) has no `plan` key -- skipped cleanly, never a 500 for
    the whole batch.

    Mutation: change `isinstance(plan, dict)` to accept None too -- this
    goes red with a KeyError/TypeError on plan["monthly_credits"]."""
    monkeypatch.setattr(
        credit_routes, "_current_period", lambda now: "2026-09")
    fake_db.docs[("firms", "firm-a")] = {
        "name": "firm-a", "status": "active", "kind": "live",
        "balance_credits": 10,
    }

    resp = _post_topup(client)
    assert resp.status_code == 200, resp.text
    assert resp.json()["skipped_no_plan"] == ["firm-a"]
    assert resp.json()["failed"] == []


def test_mock_firms_are_topped_up_too(client, fake_db, scheduler_env,
                                      monkeypatch):
    """Plan: 'Mock firms are topped up too (staging needs credits)' --
    kind is never read or filtered on by this route.

    Mutation: add a `kind == "live"` filter to _run_monthly_topup -- this
    goes red."""
    monkeypatch.setattr(
        credit_routes, "_current_period", lambda now: "2026-09")
    _seed_firm(fake_db, "firm-mock", balance=10, kind="mock", plan={
        "tier": "starter", "monthly_credits": 35, "rollover": False})

    resp = _post_topup(client)
    assert resp.status_code == 200, resp.text
    assert resp.json()["topped_up"] == ["firm-mock"]
    assert fake_db.firm("firm-mock")["balance_credits"] == 35
    grant_row = [r for r in fake_db.ledger_rows("firm-mock")
                if r["type"] == "subscription_grant"][0]
    assert grant_row["firm_kind"] == "mock"


def test_the_route_audits_in_the_same_transaction_as_the_grant(
        client, fake_db, scheduler_env, monkeypatch):
    """Exit criterion 2's audit half, extended to this route: a forced
    audit-write failure must abort the whole grant, leaving no ledger entry
    and no balance change -- the SAME property test_credit_routes.py's
    grant/adjust tests prove over append_entry's extra_writes hook.

    Mutation: pass extra_writes=None instead of _audit to append_entry --
    this goes red (the balance would change with zero audit rows, instead
    of neither changing)."""
    monkeypatch.setattr(
        credit_routes, "_current_period", lambda now: "2026-09")
    _seed_firm(fake_db, "firm-a", balance=10, plan={
        "tier": "starter", "monthly_credits": 35, "rollover": False})
    fake_db.audit_write_error = RuntimeError("audit sink refused")

    resp = _post_topup(client)
    assert resp.status_code == 200, resp.text
    assert resp.json()["failed"] == ["firm-a"]
    assert fake_db.firm("firm-a")["balance_credits"] == 10
    assert fake_db.ledger_rows("firm-a") == []
    assert fake_db.audit_rows() == []


# --------------------------------------------------------------------------
# OIDC gate (mirrors test_sweep_routes.py's gate tests, one route over).
# --------------------------------------------------------------------------

def test_no_token_is_401(client, scheduler_env):
    resp = client.post("/admin/credits/monthly-topup")
    assert resp.status_code == 401


def test_right_audience_wrong_email_is_403(client, fake_db, scheduler_env):
    resp = client.post(
        "/admin/credits/monthly-topup",
        headers=_auth("valid-other-caller-token"))
    assert resp.status_code == 403


def test_route_refuses_with_503_when_unconfigured(client, monkeypatch):
    """No ADMIN_SERVICE_URL / MONTHLY_TOPUP_SCHEDULER_SA_EMAIL set at all
    (mirrors test_sweep_routes.py's identical test one route over) -- an
    unconfigured deployment must refuse every caller with 503, never
    silently accept one against an empty audience or empty allowlist.

    Mutation: change the `not resolved_audience or not resolved_allowed_
    emails` guard in require_google_oidc to `and` -- this goes red (an
    unconfigured deployment, both empty, would fall through to token
    verification instead of 503ing)."""
    monkeypatch.delenv("ADMIN_SERVICE_URL", raising=False)
    monkeypatch.delenv("MONTHLY_TOPUP_SCHEDULER_SA_EMAIL", raising=False)
    resp = client.post(
        "/admin/credits/monthly-topup",
        headers=_auth("anything"))
    assert resp.status_code == 503, resp.text


def test_audience_appends_the_route_path_to_the_bare_service_root(
        monkeypatch):
    monkeypatch.setenv("ADMIN_SERVICE_URL", ADMIN_SERVICE_URL)
    assert credit_routes._topup_audience() == AUDIENCE


def test_audience_is_empty_when_admin_service_url_is_unset(monkeypatch):
    monkeypatch.delenv("ADMIN_SERVICE_URL", raising=False)
    assert credit_routes._topup_audience() == ""


def test_allowed_caller_emails_is_empty_when_unset(monkeypatch):
    monkeypatch.delenv("MONTHLY_TOPUP_SCHEDULER_SA_EMAIL", raising=False)
    assert credit_routes._topup_allowed_caller_emails() == tuple()


def test_current_period_formats_as_yyyy_mm_in_utc():
    """Mutation: use time.strftime with a local-time struct instead of
    time.gmtime -- this test alone cannot distinguish local from UTC on a
    UTC-configured CI box, but pins the FORMAT at least; the UTC choice
    itself is defended in the function's own docstring."""
    # 2026-09-14 00:00:00 UTC
    import calendar
    import datetime

    ts = calendar.timegm(
        datetime.datetime(2026, 9, 14, 0, 0, 0).timetuple())
    assert credit_routes._current_period(ts) == "2026-09"
