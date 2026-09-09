"""scripts/backfill_firm_kind.py CLI contract (Epic 2 bead A6).

EXIT CRITERION 1 (backfill_firm_kind half): dry-run, idempotent re-run, the
mock allowlist, the missing required flag, and the seed grant landing as one
ledger entry.

Pins the operator-facing safety properties:
- every firm gets kind=live unless named in --mock;
- kind and balance_credits are backfilled ONLY when the firm doc lacks them
  (a firm that already carries kind is never overwritten);
- --seed-credits writes exactly ONE promo_grant entry through
  credit_ledger.append_entry -- never a second balance writer -- and ONLY
  for firms this run is first assigning a kind to;
- a re-run against already-backfilled+seeded firms is a true no-op (no
  Firestore write attempted at all);
- --dry-run reads and writes nothing;
- a mismatched resolved project ABORTS with exit 2 before anything is
  written, and the dead project is refused outright;
- --seed-credits must be positive.

The CLI is driven as main([...]) -- matching scripts/grant_credits.py and
scripts/bootstrap_firm.py, so no module-reload/argv-monkeypatch fixture is
needed.

Each test's docstring names the mutation that must turn it red.

ASCII only.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import backend.services.credit_ledger as credit_ledger  # noqa: E402
import scripts.backfill_firm_kind as backfill_firm_kind  # noqa: E402

PROJECT = "polyglot-demo-aa709"


class _FakeApp:
    def __init__(self, project_id):
        self.project_id = project_id


@pytest.fixture
def firebase_stub(monkeypatch):
    """Pretend firebase_admin is already initialized for PROJECT."""
    import firebase_admin

    monkeypatch.setattr(
        firebase_admin, "_apps", {"[DEFAULT]": object()}, raising=False
    )
    monkeypatch.setattr(
        firebase_admin, "get_app", lambda: _FakeApp(PROJECT), raising=False
    )
    return firebase_admin


class _FakeDocRef:
    def __init__(self, store, firm_id):
        self._store = store
        self._firm_id = firm_id

    def set(self, payload, merge=False):
        assert merge is True, "backfill writes must merge, never replace"
        current = self._store.setdefault(self._firm_id, {})
        current.update(payload)


class _FakeSnap:
    def __init__(self, firm_id, data, store):
        self.id = firm_id
        self._data = data
        self.reference = _FakeDocRef(store, firm_id)

    def to_dict(self):
        return dict(self._data)


class _FakeCollection:
    def __init__(self, store):
        self._store = store

    def stream(self):
        # Snapshot the keys up front: writes during iteration (this script
        # doesn't do that, but a fake should not assume) must not affect
        # this pass, matching real Firestore query semantics.
        for firm_id in list(self._store.keys()):
            yield _FakeSnap(firm_id, self._store[firm_id], self._store)


class _FakeDb:
    def __init__(self, firms: dict):
        self.firms = firms  # firm_id -> dict, MUTATED in place by .set()

    def collection(self, name):
        assert name == "firms"
        return _FakeCollection(self.firms)


class _LedgerSpy:
    def __init__(self, balances=None):
        self.calls = []
        self.balances = dict(balances or {})

    def append_entry(self, db, firm_id, **kwargs):
        self.calls.append((firm_id, kwargs))
        bal = self.balances.get(firm_id, 0) + kwargs["amount"]
        self.balances[firm_id] = bal
        return {
            "doc_id": "auto1",
            "firm_id": firm_id,
            "balance_credits": bal,
            "type": kwargs["entry_type"],
            "amount": kwargs["amount"],
        }


@pytest.fixture
def ledger_spy(monkeypatch):
    spy = _LedgerSpy()
    monkeypatch.setattr(credit_ledger, "append_entry", spy.append_entry)
    return spy


def _wire_db(monkeypatch, firms: dict):
    db = _FakeDb(firms)
    monkeypatch.setattr("backend.services.auth.get_db", lambda: db)
    return db


def _argv(*extra, project=PROJECT):
    return ["--project", project, *extra]


# --------------------------------------------------- missing required flag


def test_project_is_required(capsys):
    """--project has no default; argparse must refuse with exit 2 and no
    firebase_admin touch. Mutation: make --project optional with a
    default -- this would stop raising SystemExit and go red."""
    with pytest.raises(SystemExit) as exc:
        backfill_firm_kind.main([])
    assert exc.value.code == 2


# --------------------------------------------------------- dead/wrong project


def test_dead_project_is_refused(capsys):
    """The former prod project must be refused before any Firestore touch.
    Mutation: remove the DEAD_PROJECTS check -- would proceed to
    firebase_admin init instead of exit(2) here."""
    rc = backfill_firm_kind.main(_argv(project="polyglot-forms-919f2"))
    assert rc == 2
    assert "DEAD" in capsys.readouterr().err


def test_mismatched_resolved_project_aborts(firebase_stub, monkeypatch, capsys):
    """A resolved project different from --project must abort with exit 2
    and write nothing. Mutation: drop the resolved-vs-requested equality
    check -- would proceed to read/write firms instead of aborting."""
    import firebase_admin

    monkeypatch.setattr(
        firebase_admin, "get_app",
        lambda: _FakeApp("some-other-project"),
    )
    called = {"db": False}

    def _get_db():
        called["db"] = True
        return _FakeDb({})

    monkeypatch.setattr("backend.services.auth.get_db", _get_db)

    rc = backfill_firm_kind.main(_argv())
    assert rc == 2
    assert not called["db"], "must abort before touching Firestore"
    assert "not" in capsys.readouterr().err


# -------------------------------------------------------------- --mock gate


def test_unlisted_firm_becomes_live_listed_firm_becomes_mock(
        firebase_stub, ledger_spy, monkeypatch, capsys):
    """Every firm gets kind=live unless named in --mock. Mutation: invert
    the ternary in main() (mock_allowlist membership) -- would flip which
    firm gets which kind, reddening this test."""
    firms = {"acme-legal": {}, "staging-fixture": {}}
    db = _wire_db(monkeypatch, firms)

    rc = backfill_firm_kind.main(_argv("--mock", "staging-fixture"))

    assert rc == 0
    assert db.firms["acme-legal"]["kind"] == "live"
    assert db.firms["staging-fixture"]["kind"] == "mock"


def test_mock_allowlist_parses_comma_separated_with_whitespace(
        firebase_stub, ledger_spy, monkeypatch):
    """--mock "a, b" must treat both a and b as mock, not just the first
    (or a literal " b" with a leading space). Mutation: split on "," without
    stripping -- "staging-fixture" would fail to match " staging-fixture"
    and this test goes red."""
    firms = {"acme-legal": {}, "staging-fixture": {}}
    db = _wire_db(monkeypatch, firms)

    rc = backfill_firm_kind.main(_argv("--mock", "staging-fixture, unused-id"))

    assert rc == 0
    assert db.firms["staging-fixture"]["kind"] == "mock"


# ------------------------------------------------------ backfill selectivity


def test_firm_with_existing_kind_is_never_overwritten(
        firebase_stub, ledger_spy, monkeypatch):
    """A firm that already carries `kind` must not be touched by this
    script, even if --mock would otherwise select it. Mutation: drop the
    `"kind" not in firm` guard -- would overwrite a deliberately-chosen
    kind, reddening this test."""
    firms = {"acme-legal": {"kind": "mock"}}
    db = _wire_db(monkeypatch, firms)

    rc = backfill_firm_kind.main(_argv())  # no --mock: would be "live" if touched

    assert rc == 0
    assert db.firms["acme-legal"]["kind"] == "mock", "must not be overwritten"


def test_firm_with_existing_balance_is_never_overwritten(
        firebase_stub, ledger_spy, monkeypatch):
    """A firm that already carries balance_credits must not have it reset
    to 0. Mutation: drop the `"balance_credits" not in firm` guard --
    would zero out a real balance, reddening this test."""
    firms = {"acme-legal": {"balance_credits": 500}}
    db = _wire_db(monkeypatch, firms)

    rc = backfill_firm_kind.main(_argv())

    assert rc == 0
    assert db.firms["acme-legal"]["balance_credits"] == 500


def test_true_no_op_rerun_writes_nothing(firebase_stub, ledger_spy, monkeypatch):
    """A firm already fully backfilled (kind + balance_credits present) must
    not trigger ANY Firestore write on a re-run. Mutation: remove the
    `if not payload and not will_seed: continue` early-out -- would call
    .set({}, merge=True) unconditionally, and this test's assertion that
    .set was never invoked would go red."""
    firms = {"acme-legal": {"kind": "live", "balance_credits": 0}}
    db = _wire_db(monkeypatch, firms)

    calls = []
    real_set = _FakeDocRef.set

    def _spy_set(self, payload, merge=False):
        calls.append((self._firm_id, payload))
        return real_set(self, payload, merge=merge)

    monkeypatch.setattr(_FakeDocRef, "set", _spy_set)

    rc = backfill_firm_kind.main(_argv())

    assert rc == 0
    assert calls == []
    assert ledger_spy.calls == []


# --------------------------------------------------------------- seed grant


def test_seed_credits_writes_exactly_one_ledger_entry_per_new_firm(
        firebase_stub, ledger_spy, monkeypatch):
    """--seed-credits N must call credit_ledger.append_entry EXACTLY once
    per firm this run gives a kind to, as a promo_grant, with channel=None.
    Mutation: call append_entry twice, or pass entry_type="adjustment" --
    either reddens this test."""
    firms = {"acme-legal": {}}
    db = _wire_db(monkeypatch, firms)

    rc = backfill_firm_kind.main(_argv("--seed-credits", "500"))

    assert rc == 0
    assert len(ledger_spy.calls) == 1
    firm_id, kwargs = ledger_spy.calls[0]
    assert firm_id == "acme-legal"
    assert kwargs["entry_type"] == "promo_grant"
    assert kwargs["amount"] == 500
    assert kwargs["channel"] is None


def test_seed_credits_skips_firm_that_already_had_a_kind(
        firebase_stub, ledger_spy, monkeypatch):
    """A firm that already carried `kind` before this run must NOT be
    seeded, even on a fresh --seed-credits invocation -- the seed step is
    scoped to firms newly given a kind. Mutation: seed every firm touched
    by --seed-credits regardless of had_kind -- would call append_entry for
    this firm too, reddening the zero-calls assertion."""
    firms = {"acme-legal": {"kind": "live"}}
    db = _wire_db(monkeypatch, firms)

    rc = backfill_firm_kind.main(_argv("--seed-credits", "500"))

    assert rc == 0
    assert ledger_spy.calls == []


def test_seed_credits_must_be_positive(capsys):
    """--seed-credits 0 or negative must be refused with exit 2 before any
    Firestore touch. Mutation: drop the `<= 0` check -- would proceed to
    firebase_admin init and attempt a zero/negative grant."""
    rc = backfill_firm_kind.main(_argv("--seed-credits", "0"))
    assert rc == 2
    assert "positive" in capsys.readouterr().err


# -------------------------------------------------------------------- dry-run


def test_dry_run_writes_nothing(firebase_stub, ledger_spy, monkeypatch, capsys):
    """--dry-run must print what would change but call neither .set() nor
    append_entry(). Mutation: remove the `if args.dry_run: continue` guard
    in the per-firm loop -- would perform the real write despite --dry-run,
    reddening the zero-calls assertions."""
    firms = {"acme-legal": {}}
    db = _wire_db(monkeypatch, firms)

    calls = []
    real_set = _FakeDocRef.set
    monkeypatch.setattr(
        _FakeDocRef, "set",
        lambda self, *a, **kw: (calls.append(1), real_set(self, *a, **kw))[0],
    )

    rc = backfill_firm_kind.main(
        _argv("--seed-credits", "500", "--dry-run")
    )

    assert rc == 0
    assert calls == []
    assert ledger_spy.calls == []
    out = capsys.readouterr().out
    assert "DRY RUN" in out


# ---------------------------------------------------------- resilience: one bad firm


def test_one_failing_firm_does_not_abort_the_sweep(
        firebase_stub, ledger_spy, monkeypatch, capsys):
    """A write failure on one firm must be recorded and reported (exit 1),
    but must not stop the sweep from processing the remaining firms.
    Mutation: remove the try/except around the per-firm write -- an
    exception would propagate and abort main() entirely, and
    "second-firm" would never get processed."""
    firms = {"bad-firm": {}, "second-firm": {}}
    db = _wire_db(monkeypatch, firms)

    def _boom(self, payload, merge=False):
        if self._firm_id == "bad-firm":
            raise RuntimeError("simulated write failure")
        current = self._store.setdefault(self._firm_id, {})
        current.update(payload)

    monkeypatch.setattr(_FakeDocRef, "set", _boom)

    rc = backfill_firm_kind.main(_argv())

    assert rc == 1
    assert "bad-firm" in capsys.readouterr().err
    assert db.firms["second-firm"].get("kind") == "live"


# ----------------------------------------------- drift guard + doc-shape parity


def test_kind_choices_match_service_constants():
    """KIND_MOCK/KIND_LIVE are kept as literals (not imported from
    backend.services.firms) for the same import-ordering reason
    bootstrap_firm.py documents -- but that means nothing catches a rename
    of FIRM_KIND_MOCK/FIRM_KIND_LIVE in firms.py without this test.
    Mutation: rename either service constant without updating this script's
    literal -- this test is the tripwire."""
    from backend.services import firms

    assert backfill_firm_kind.KIND_MOCK == firms.FIRM_KIND_MOCK
    assert backfill_firm_kind.KIND_LIVE == firms.FIRM_KIND_LIVE


def test_balance_backfill_writes_balance_updated_at_with_balance_credits(
        firebase_stub, ledger_spy, monkeypatch):
    """balance_credits and balance_updated_at must be written TOGETHER,
    mirroring upsert_firm()'s first-create payload
    (backend/services/firms.py) -- a firm backfilled by this script must
    end up with the same doc shape as one created through the normal path.
    Mutation: drop the balance_updated_at line from the payload -- this
    test's second assertion goes red."""
    firms = {"acme-legal": {}}
    db = _wire_db(monkeypatch, firms)

    rc = backfill_firm_kind.main(_argv())

    assert rc == 0
    assert db.firms["acme-legal"]["balance_credits"] == 0
    assert "balance_updated_at" in db.firms["acme-legal"]


def test_existing_balance_never_gets_balance_updated_at_added(
        firebase_stub, ledger_spy, monkeypatch):
    """A firm that already has balance_credits must not have
    balance_updated_at added either -- the skip guard covers both fields as
    one unit, matching the never-overwritten selectivity tests above.
    Mutation: write balance_updated_at unconditionally (outside the
    `not had_balance` guard) -- this test goes red."""
    firms = {"acme-legal": {"balance_credits": 500}}
    db = _wire_db(monkeypatch, firms)

    rc = backfill_firm_kind.main(_argv())

    assert rc == 0
    assert "balance_updated_at" not in db.firms["acme-legal"]
