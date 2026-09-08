"""scripts/grant_credits.py CLI contract (Epic 2 bead A2).

EXIT CRITERION 3: the CLI grants and adjusts THROUGH the one transactional
helper -- a dry run prints and writes nothing, a real run writes one entry
plus one ledger_export log line.

Pins the operator-facing safety properties:
- grant refuses a negative --credits (removing credits needs the adjust
  verb, which requires a reason);
- adjust requires --reason (argparse-level, so it cannot be skipped);
- --usd is required for purchase/subscription_grant and refused for
  promo_grant, both ways;
- a mismatched resolved project ABORTS with exit 2 before anything is
  written, and the dead project is refused outright;
- --dry-run reads the balance and writes nothing;
- every write goes through credit_ledger.append_entry, never a direct
  Firestore set -- so the CLI cannot become a second writer of the balance;
- the literal choice lists match the service's constants.

The CLI is driven as main([...]) -- grant_credits.main takes argv, matching
bootstrap_firm.py, so no module-reload/argv-monkeypatch fixture is needed.

Each test's docstring names the mutation that must turn it red.

ASCII only.
"""
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import backend.services.credit_ledger as credit_ledger  # noqa: E402
import scripts.grant_credits as grant_credits  # noqa: E402

PROJECT = "polyglot-demo-aa709"


class _FakeApp:
    def __init__(self, project_id):
        self.project_id = project_id


@pytest.fixture
def firebase_stub(monkeypatch):
    """Pretend firebase_admin is already initialized for PROJECT.

    Patching _apps non-empty keeps main() from calling the real
    initialize_app; get_app returns an object whose project_id the script
    asserts against --project.
    """
    import firebase_admin
    monkeypatch.setattr(firebase_admin, "_apps", {"[DEFAULT]": object()},
                        raising=False)
    monkeypatch.setattr(firebase_admin, "get_app",
                        lambda: _FakeApp(PROJECT), raising=False)
    return firebase_admin


class _LedgerSpy:
    """Records append_entry calls; returns a plausible result."""

    def __init__(self, balance=0, raises=None):
        self.calls = []
        self.balance = balance
        self.raises = raises

    def append_entry(self, db, firm_id, **kwargs):
        self.calls.append((firm_id, kwargs))
        if self.raises is not None:
            raise self.raises
        self.balance += kwargs["amount"]
        return {
            "doc_id": "auto1",
            "firm_id": firm_id,
            "balance_credits": self.balance,
            "type": kwargs["entry_type"],
            "amount": kwargs["amount"],
        }


@pytest.fixture
def ledger_spy(monkeypatch):
    spy = _LedgerSpy()
    monkeypatch.setattr(credit_ledger, "append_entry", spy.append_entry)
    monkeypatch.setattr(credit_ledger, "read_balance",
                        lambda db, firm_id: spy.balance)
    monkeypatch.setattr("backend.services.auth.get_db", lambda: object())
    return spy


# ------------------------------------------------- EXIT CRITERION 3: writes


def test_grant_writes_ONE_entry_through_the_ledger_helper(
        firebase_stub, ledger_spy, capsys):
    """EXIT CRITERION 3, the real-run half. The CLI must call
    credit_ledger.append_entry exactly once, with the arguments the flags
    describe -- not a direct Firestore write.

    Mutation: change the append_entry call to a direct db.collection(...)
    .set(...) -- ledger_spy records nothing and this goes red. Verified
    2026-09-08."""
    rc = grant_credits.main(
        ["grant", "acme", "--credits", "500", "--project", PROJECT,
         "--actor", "josh"])
    assert rc == 0
    assert len(ledger_spy.calls) == 1
    firm_id, kwargs = ledger_spy.calls[0]
    assert firm_id == "acme"
    assert kwargs["entry_type"] == "promo_grant"
    assert kwargs["amount"] == 500
    assert kwargs["usd_amount"] is None
    assert kwargs["actor"] == "system:grant_credits_cli:josh"
    out = capsys.readouterr().out
    assert "firms/acme/ledger/auto1" in out
    assert "500" in out


def test_a_purchase_grant_carries_the_usd_amount(
        firebase_stub, ledger_spy):
    """The income figure Epic 5's revenue view sums has to reach the entry.

    Mutation: drop `usd_amount=usd` from the append_entry call -- red.
    Verified 2026-09-08."""
    rc = grant_credits.main(
        ["grant", "acme", "--credits", "100", "--type", "purchase",
         "--usd", "249.00", "--project", PROJECT])
    assert rc == 0
    _, kwargs = ledger_spy.calls[0]
    assert kwargs["entry_type"] == "purchase"
    assert kwargs["usd_amount"] == 249.00


def test_adjust_writes_an_adjustment_with_the_reason(
        firebase_stub, ledger_spy):
    """The rollback half of "credits can be granted and rolled back before
    the console exists": a signed correction, carrying its justification.

    Mutation: hardcode entry_type="promo_grant" in the adjust branch -- red.
    Verified 2026-09-08."""
    rc = grant_credits.main(
        ["adjust", "acme", "--credits", "-50", "--reason",
         "double-charged on 09-07", "--project", PROJECT])
    assert rc == 0
    _, kwargs = ledger_spy.calls[0]
    assert kwargs["entry_type"] == "adjustment"
    assert kwargs["amount"] == -50
    assert kwargs["reason"] == "double-charged on 09-07"
    assert kwargs["usd_amount"] is None


def test_a_grant_carries_NO_channel(firebase_stub, ledger_spy):
    """An operator grant is not a channel action, and the balance is not
    channel-partitioned. Only a mint DEBIT (bead A3) fills in a channel.

    Mutation: pass channel="demo" in the CLI's append_entry call -- red.
    Verified 2026-09-08."""
    grant_credits.main(
        ["grant", "acme", "--credits", "5", "--project", PROJECT])
    _, kwargs = ledger_spy.calls[0]
    assert kwargs.get("channel") is None


def test_a_refused_ledger_write_exits_1_and_names_the_reason(
        firebase_stub, ledger_spy, monkeypatch, capsys):
    """An unknown firm, a malformed entry, or an insufficient balance must
    surface as a non-zero exit with the helper's message -- not a traceback
    and not a silent success.

    Mutation: swallow the exception and `return 0` -- red. Verified
    2026-09-08."""
    ledger_spy.raises = credit_ledger.LedgerError("firm ghost does not exist")
    rc = grant_credits.main(
        ["grant", "ghost", "--credits", "5", "--project", PROJECT])
    assert rc == 1
    assert "ghost does not exist" in capsys.readouterr().err


# ------------------------------------------------------------ the dry run


def test_dry_run_prints_the_entry_and_writes_NOTHING(
        firebase_stub, ledger_spy, capsys):
    """EXIT CRITERION 3, the dry-run half. --dry-run must read the balance
    and print what it would do, calling append_entry zero times.

    Mutation: remove the `if args.dry_run: ... return 0` block -- the write
    happens and this goes red. Verified 2026-09-08."""
    ledger_spy.balance = 120
    rc = grant_credits.main(
        ["grant", "acme", "--credits", "500", "--project", PROJECT,
         "--dry-run"])
    assert rc == 0
    assert ledger_spy.calls == []
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "120" in out, "the current balance must be shown"
    assert "620" in out, "the resulting balance must be shown"
    assert "promo_grant" in out


def test_dry_run_says_a_MISSING_firm_would_be_refused(
        firebase_stub, ledger_spy, monkeypatch, capsys):
    """read_balance returns None for a firm that does not exist; the dry run
    must say so rather than print a confident "would become N credits" for a
    write the real run will refuse.

    Mutation: treat None as 0 in the dry-run branch -- red. Verified
    2026-09-08."""
    monkeypatch.setattr(credit_ledger, "read_balance", lambda db, f: None)
    rc = grant_credits.main(
        ["grant", "ghost", "--credits", "5", "--project", PROJECT,
         "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "NO document" in out
    assert "REFUSED" in out
    assert ledger_spy.calls == []


# ----------------------------------------------------- argument refusals


def test_grant_REFUSES_a_negative_credits(firebase_stub, ledger_spy, capsys):
    """Removing credits must go through the adjust verb, which requires a
    reason. A minus sign in the everyday command would skip that control.

    Mutation: drop the `if args.credits < 0` branch -- the write happens and
    this goes red. Verified 2026-09-08."""
    rc = grant_credits.main(
        ["grant", "acme", "--credits", "-50", "--project", PROJECT])
    assert rc == 2
    assert ledger_spy.calls == []
    assert "adjust" in capsys.readouterr().err


@pytest.mark.parametrize("entry_type", sorted(grant_credits.USD_REQUIRED_TYPES))
def test_an_income_type_REQUIRES_usd_at_the_CLI(
        firebase_stub, ledger_spy, entry_type, capsys):
    """Caught at the CLI as well as in the helper so the operator sees it
    before a Firestore round trip -- and so --dry-run refuses it too.

    Mutation: delete the `--usd is required` branch -- both parametrizations
    go red (the helper would still refuse a real run, but the dry run would
    silently print a bad entry). Verified 2026-09-08 per parametrization."""
    rc = grant_credits.main(
        ["grant", "acme", "--credits", "10", "--type", entry_type,
         "--project", PROJECT])
    assert rc == 2
    assert ledger_spy.calls == []
    assert "--usd" in capsys.readouterr().err


def test_a_promo_grant_REFUSES_usd(firebase_stub, ledger_spy, capsys):
    """The requirement runs both ways: a dollar figure on a promotional grant
    would be double-counted as income.

    Mutation: delete the `--usd must not be passed` branch -- red. Verified
    2026-09-08."""
    rc = grant_credits.main(
        ["grant", "acme", "--credits", "10", "--usd", "5.00",
         "--project", PROJECT])
    assert rc == 2
    assert ledger_spy.calls == []
    assert "--usd" in capsys.readouterr().err


def test_adjust_without_a_reason_is_an_ARGPARSE_error(firebase_stub):
    """--reason is required=True on the adjust subparser, so it cannot be
    skipped even by a caller who never reaches the helper.

    Mutation: change required=True to required=False on adjust's --reason --
    SystemExit is no longer raised and this goes red. Verified 2026-09-08."""
    with pytest.raises(SystemExit):
        grant_credits.main(
            ["adjust", "acme", "--credits", "-5", "--project", PROJECT])


@pytest.mark.parametrize("command", ["grant", "adjust"])
def test_a_zero_credits_delta_is_REFUSED(
        firebase_stub, ledger_spy, command, capsys):
    """A zero-credit entry moves nothing and would still consume a balance
    write -- always a caller bug.

    Mutation: drop the `if args.credits == 0` branch -- the grant case
    reaches the helper (which also refuses, exit 1 not 2) and the assertion
    on rc == 2 goes red. Verified 2026-09-08 per parametrization."""
    argv = [command, "acme", "--credits", "0", "--project", PROJECT]
    if command == "adjust":
        argv += ["--reason", "r"]
    rc = grant_credits.main(argv)
    assert rc == 2
    assert ledger_spy.calls == []
    assert "non-zero" in capsys.readouterr().err


def test_the_DEAD_project_is_refused_before_anything_is_touched(
        ledger_spy, capsys):
    """The former prod project is unreachable; a stale muscle-memory
    invocation must not hang or half-write against it.

    Mutation: empty the DEAD_PROJECTS set -- the run proceeds past the guard
    and this goes red. Verified 2026-09-08."""
    rc = grant_credits.main(
        ["grant", "acme", "--credits", "5", "--project",
         "polyglot-forms-919f2"])
    assert rc == 2
    assert ledger_spy.calls == []
    assert "DEAD" in capsys.readouterr().err


def test_a_MISMATCHED_resolved_project_aborts_with_exit_2(
        monkeypatch, ledger_spy, capsys):
    """Credits granted into the wrong project are invisible until someone
    goes looking. The assertion that the resolved app project equals
    --project is what makes --project deterministic.

    Mutation: delete the `if resolved != args.project` block -- the write
    proceeds against the wrong project and this goes red. Verified
    2026-09-08."""
    import firebase_admin
    monkeypatch.setattr(firebase_admin, "_apps", {"[DEFAULT]": object()},
                        raising=False)
    monkeypatch.setattr(firebase_admin, "get_app",
                        lambda: _FakeApp("some-other-project"), raising=False)
    rc = grant_credits.main(
        ["grant", "acme", "--credits", "5", "--project", PROJECT])
    assert rc == 2
    assert ledger_spy.calls == []
    assert "refusing to write into the wrong project" in capsys.readouterr().err


def test_project_is_a_REQUIRED_flag(firebase_stub):
    """Without it firebase_admin resolves the project from the operator's ADC
    credential -- the trap bootstrap_firm.py documents.

    Mutation: give --project a default -- SystemExit is not raised and this
    goes red. Verified 2026-09-08."""
    with pytest.raises(SystemExit):
        grant_credits.main(["grant", "acme", "--credits", "5"])


# ----------------------------------------------------------- the actor stamp


def test_the_actor_defaults_to_the_OS_USERNAME_and_is_never_blank(
        firebase_stub, ledger_spy, monkeypatch):
    """The helper refuses a blank actor. The CLI must therefore always
    produce one, and it must be distinguishable from a console grant's
    Firebase uid.

    Mutation: return args.actor directly from _actor (no prefix, no
    fallback) -- red on both assertions. Verified 2026-09-08."""
    monkeypatch.setattr(grant_credits.getpass, "getuser", lambda: "operator1")
    grant_credits.main(
        ["grant", "acme", "--credits", "5", "--project", PROJECT])
    _, kwargs = ledger_spy.calls[0]
    assert kwargs["actor"] == "system:grant_credits_cli:operator1"


def test_the_actor_survives_a_failing_getuser(
        firebase_stub, ledger_spy, monkeypatch):
    """Some hosts have no resolvable username. An unattributable entry is
    still better than a refused correction, but it must look conspicuously
    unattributable rather than blank (which the helper refuses outright).

    Mutation: drop the try/except around getpass.getuser -- the call raises
    and this goes red. Verified 2026-09-08."""
    def _boom():
        raise OSError("no username")
    monkeypatch.setattr(grant_credits.getpass, "getuser", _boom)
    grant_credits.main(
        ["grant", "acme", "--credits", "5", "--project", PROJECT])
    _, kwargs = ledger_spy.calls[0]
    assert kwargs["actor"] == "system:grant_credits_cli:unknown"


@pytest.mark.parametrize("blank", ["   ", "\t", "\n", " \t\n ", ""])
def test_a_whitespace_only_actor_falls_back_instead_of_stamping_a_blank(
        firebase_stub, ledger_spy, monkeypatch, blank):
    """The helper's blank-actor guard cannot catch this one, so the CLI must.

    credit_ledger._validate tests actor.strip() on the WHOLE stamped string,
    and "system:grant_credits_cli:   " is non-blank after strip purely
    because of the literal prefix. So a whitespace-only --actor would commit
    an entry whose OPERATOR SEGMENT -- the half that says who moved the
    credits -- is empty, which is precisely the unattributable movement the
    module docstring calls the one thing the ledger exists to make
    impossible. Whitespace must therefore be treated as absent and take the
    same fallback path as an omitted flag.

    Parametrized over the whole blank dimension rather than one sample:
    a fix that stripped only " " would leave tabs and newlines through.

    Mutation: drop the .strip() in _actor (who = explicit) -- every case
    except "" goes red, since argparse's own default already handles "".
    Verified 2026-09-08 per parametrization."""
    monkeypatch.setattr(grant_credits.getpass, "getuser", lambda: "operator1")
    grant_credits.main(
        ["grant", "acme", "--credits", "5", "--project", PROJECT,
         "--actor", blank])
    _, kwargs = ledger_spy.calls[0]
    assert kwargs["actor"] == "system:grant_credits_cli:operator1"
    operator_segment = kwargs["actor"].split(":")[-1]
    assert operator_segment.strip(), (
        "the operator segment is blank: {!r}".format(kwargs["actor"]))


# --------------------------------------------- literals match the service


def test_grant_type_choices_match_service_constants():
    """The CLI keeps its type list as LITERALS (a backend.* import at module
    scope would run before initialize_app -- the ordering trap
    bootstrap_firm.py documents). This pins them against the service so the
    drift fails CI instead of silently offering a type the helper rejects.

    Mutation: add "mint_debit" to GRANT_TYPE_CHOICES -- red. Verified
    2026-09-08."""
    assert set(grant_credits.GRANT_TYPE_CHOICES) == {
        credit_ledger.TYPE_PROMO_GRANT,
        credit_ledger.TYPE_PURCHASE,
        credit_ledger.TYPE_SUBSCRIPTION_GRANT,
    }
    # Every listed choice is a real entry type the helper accepts.
    assert set(grant_credits.GRANT_TYPE_CHOICES) <= set(
        credit_ledger.ENTRY_TYPES)


def test_usd_required_types_match_service_constants():
    """Same drift guard for the usd_amount rule: if the service ever adds a
    third income type, the CLI's --usd requirement must move with it.

    Mutation: remove "subscription_grant" from the CLI's set -- red.
    Verified 2026-09-08."""
    assert grant_credits.USD_REQUIRED_TYPES == set(
        credit_ledger.USD_REQUIRED_TYPES)


def test_the_adjustment_type_matches_the_service_constant():
    """Mutation: change ADJUSTMENT_TYPE to "adjust" -- red (and the real CLI
    would then write an entry type the helper rejects). Verified
    2026-09-08."""
    assert grant_credits.ADJUSTMENT_TYPE == credit_ledger.TYPE_ADJUSTMENT
