"""scripts/bootstrap_firm.py CLI contract (bd polyglot-pdf-lo88).

Pins the operator-facing safety properties:
- the claims stamp MERGES over existing custom claims (set_custom_user_claims
  REPLACES the whole object -- the read-then-spread is the script's single
  highest-risk line);
- roles land per flag (--manager-email -> manager, --employee-email ->
  employee);
- a mismatched resolved project ABORTS with exit 2 before anything is
  written (a claim stamped into the wrong project fails silently);
- the dead project polyglot-forms-919f2 is refused outright;
- --dry-run does the read-only lookups but writes nothing;
- one unknown email does not abort the batch (exit 1, address named).

The CLI is driven as main([...]) -- bootstrap_firm.main takes argv, a
deliberate improvement over read_confirmations.py's bare main()+sys.argv,
so no module-reload/argv-monkeypatch fixture is needed here.

Each test's docstring names the mutation that must turn it red.

ASCII only.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import firebase_admin
import pytest
from firebase_admin import auth as fb_auth

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.bootstrap_firm as bootstrap_firm  # noqa: E402

PROJECT = "polyglot-demo-aa709"


class _FakeUser:
    def __init__(self, uid, claims=None):
        self.uid = uid
        self.custom_claims = claims


class _AuthStub:
    """Captures the firebase_admin.auth surface the script touches."""

    def __init__(self, users):
        self.users = users  # email -> _FakeUser
        self.lookups = []
        self.stamps = {}  # uid -> claims payload

    def get_user_by_email(self, email):
        self.lookups.append(email)
        user = self.users.get(email)
        if user is None:
            raise fb_auth.UserNotFoundError(f"no user for {email}")
        return user

    def set_custom_user_claims(self, uid, claims):
        self.stamps[uid] = dict(claims)


@pytest.fixture
def wired(monkeypatch):
    """Wire the script's firebase_admin + firms surfaces to fakes: an app
    already 'initialized' on the right project, a capturing auth stub, and
    a recording upsert_firm."""
    auth_stub = _AuthStub(users={})
    upserts = []

    monkeypatch.setattr(firebase_admin, "_apps", {"[DEFAULT]": object()})
    monkeypatch.setattr(
        firebase_admin, "initialize_app",
        lambda *a, **kw: pytest.fail("initialize_app must not run when an app exists"),
    )
    monkeypatch.setattr(
        firebase_admin, "get_app",
        lambda: SimpleNamespace(project_id=PROJECT),
    )
    monkeypatch.setattr(fb_auth, "get_user_by_email", auth_stub.get_user_by_email)
    monkeypatch.setattr(
        fb_auth, "set_custom_user_claims", auth_stub.set_custom_user_claims
    )
    def _fake_upsert(*a, **kw):
        # Mirrors the real contract: created=True only on the first call for
        # a firm_id -- so a mutation that errors on "already exists" reddens
        # the idempotency test instead of hiding behind an always-True fake.
        created = a[0] not in {u[0][0] for u in upserts}
        upserts.append((a, kw))
        return {"firm_id": a[0], "created": created}

    monkeypatch.setattr("backend.services.firms.upsert_firm", _fake_upsert)
    return SimpleNamespace(auth=auth_stub, upserts=upserts)


def _argv(*extra, firm_id="acme-legal", project=PROJECT, kind="live"):
    return [
        firm_id,
        "--name", "Acme Legal Aid",
        "--contact", "intake@acme.example",
        "--project", project,
        "--kind", kind,
        *extra,
    ]


def test_stamps_roles_per_flag_and_exits_0(wired, capsys):
    """--manager-email lands firm_role=manager, --employee-email lands
    firm_role=employee, firm doc upserted once, exit 0. Mutation: swap the
    ROLE_MANAGER/ROLE_EMPLOYEE constants in the staff list build -- red."""
    wired.auth.users["ada@x.example"] = _FakeUser("uid-ada")
    wired.auth.users["bo@x.example"] = _FakeUser("uid-bo")

    rc = bootstrap_firm.main(
        _argv(
            "--allowed-kits", "w7, i-90",
            "--manager-email", "ada@x.example",
            "--employee-email", "bo@x.example",
        )
    )

    assert rc == 0
    assert wired.auth.stamps["uid-ada"]["firm_role"] == "manager"
    assert wired.auth.stamps["uid-bo"]["firm_role"] == "employee"
    assert wired.auth.stamps["uid-ada"]["firm_id"] == "acme-legal"
    assert len(wired.upserts) == 1
    args, _ = wired.upserts[0]
    assert args[0] == "acme-legal"
    assert args[3] == ["w7", "i-90"]  # comma-split + stripped
    assert args[4] == "live"  # --kind, default in _argv()


def test_existing_custom_claims_survive_the_stamp(wired):
    """THE clobber pin: set_custom_user_claims replaces the whole claims
    object, so the script must read-then-spread. Mutation (the one that
    matters): replace {**existing, ...} with a bare {firm_id, firm_role}
    payload in stamp_firm_claims -- the admin key vanishes and this goes
    red."""
    wired.auth.users["ada@x.example"] = _FakeUser(
        "uid-ada", claims={"admin": True}
    )

    rc = bootstrap_firm.main(_argv("--manager-email", "ada@x.example"))

    assert rc == 0
    assert wired.auth.stamps["uid-ada"] == {
        "admin": True,
        "firm_id": "acme-legal",
        "firm_role": "manager",
    }


def test_unknown_email_does_not_abort_batch_and_exits_1(wired, capsys):
    """One unknown address: the OTHER account still gets stamped, exit is 1
    (partial), and the failing address is named in the output. Mutation:
    re-raise UserNotFoundError out of stamp_firm_claims -- the batch dies
    and this goes red."""
    wired.auth.users["bo@x.example"] = _FakeUser("uid-bo")

    rc = bootstrap_firm.main(
        _argv(
            "--manager-email", "ghost@x.example",
            "--employee-email", "bo@x.example",
        )
    )

    out = capsys.readouterr()
    assert rc == 1
    assert wired.auth.stamps["uid-bo"]["firm_role"] == "employee"
    assert "ghost@x.example" in out.out
    assert "unknown_email" in out.out


def test_dry_run_looks_up_emails_but_writes_nothing(wired, monkeypatch, capsys):
    """--dry-run performs the READ-ONLY lookups (unknown addresses surface
    before the real run) but never calls upsert_firm or
    set_custom_user_claims. Mutation: drop the dry-run guard on either
    write -- the explode-mocks fire."""
    wired.auth.users["ada@x.example"] = _FakeUser("uid-ada")
    monkeypatch.setattr(
        "backend.services.firms.upsert_firm",
        lambda *a, **kw: pytest.fail("upsert_firm must not run under --dry-run"),
    )
    monkeypatch.setattr(
        fb_auth, "set_custom_user_claims",
        lambda *a, **kw: pytest.fail("claims must not be stamped under --dry-run"),
    )

    rc = bootstrap_firm.main(
        _argv("--manager-email", "ada@x.example", "--dry-run")
    )

    assert rc == 0
    assert wired.auth.lookups == ["ada@x.example"]
    assert "DRY RUN" in capsys.readouterr().out


def test_mismatched_resolved_project_aborts_with_exit_2(wired, monkeypatch, capsys):
    """The wrong-project abort: if the resolved firebase_admin app project
    differs from --project (a pre-existing app, or a credential resolving
    elsewhere), NOTHING may be written. Mutation: delete the resolved ==
    args.project assertion -- the explode-mock upsert fires and this goes
    red."""
    monkeypatch.setattr(
        firebase_admin, "get_app",
        lambda: SimpleNamespace(project_id="somebody-elses-project"),
    )
    monkeypatch.setattr(
        "backend.services.firms.upsert_firm",
        lambda *a, **kw: pytest.fail("must not write into a mismatched project"),
    )
    wired.auth.users["ada@x.example"] = _FakeUser("uid-ada")

    rc = bootstrap_firm.main(_argv("--manager-email", "ada@x.example"))

    assert rc == 2
    assert wired.auth.stamps == {}
    assert "refusing" in capsys.readouterr().err


def test_dead_project_is_refused_before_any_init(monkeypatch, capsys):
    """polyglot-forms-919f2 is dead (maintainer 2026-08-14): exit 2 before
    firebase_admin is even initialized. Mutation: drop the DEAD_PROJECTS
    check -- the explode-mock init fires."""
    monkeypatch.setattr(firebase_admin, "_apps", {})
    monkeypatch.setattr(
        firebase_admin, "initialize_app",
        lambda *a, **kw: pytest.fail("must not initialize against the dead project"),
    )

    rc = bootstrap_firm.main(_argv(project="polyglot-forms-919f2"))

    assert rc == 2
    assert "DEAD" in capsys.readouterr().err


def test_invalid_firm_slug_is_refused(wired, capsys):
    """Slug validation happens at the CLI layer, before any Firestore path
    is built. Mutation: drop the FIRM_ID_RE check -- red."""
    rc = bootstrap_firm.main(_argv(firm_id="Acme/Legal"))

    assert rc == 2
    assert "not a valid slug" in capsys.readouterr().err
    assert wired.upserts == []


def test_trailing_newline_firm_id_is_refused(wired, capsys):
    """FIRM_ID_RE must be applied with fullmatch: a $-anchored .match still
    accepts a trailing newline (the _KIT_ID_RE / bd sbfk bug class), so
    'acme-legal\\n' would pass and become a Firestore path segment.
    Mutation: revert fullmatch to match -- red."""
    rc = bootstrap_firm.main(_argv(firm_id="acme-legal\n"))

    assert rc == 2
    assert "not a valid slug" in capsys.readouterr().err
    assert wired.upserts == []


def test_email_in_both_role_flags_is_refused(wired, capsys):
    """An address under BOTH --manager-email and --employee-email is an
    ambiguous role assignment: refuse (exit 2, nothing written) rather than
    silently letting the last stamp win. Mutation: drop the duplicate-email
    check -- the address gets stamped and this goes red."""
    wired.auth.users["ada@x.example"] = _FakeUser("uid-ada")

    rc = bootstrap_firm.main(
        _argv(
            "--manager-email", "ada@x.example",
            "--employee-email", "ada@x.example",
        )
    )

    assert rc == 2
    assert "BOTH" in capsys.readouterr().err
    assert wired.auth.stamps == {}
    assert wired.upserts == []


def test_omitted_status_upserts_service_active_constant(wired):
    """--status omitted must write firms.FIRM_STATUS_ACTIVE into the firm
    doc: the argparse default is a literal-drift hazard (round-2 fresh-eyes
    mutation-proved default="bogus" left every test green while silently
    fail-closing every new firm). Mutation: set the --status default to a
    literal not equal to the service constant -- red."""
    import backend.services.firms as firms

    rc = bootstrap_firm.main(_argv())

    assert rc == 0
    assert len(wired.upserts) == 1
    _, kw = wired.upserts[0]
    assert kw["status"] == firms.FIRM_STATUS_ACTIVE


def test_case_mismatched_dual_role_email_is_refused(wired, capsys):
    """Firebase resolves emails case-insensitively, so Ada@x under
    --manager-email and ada@x under --employee-email are the SAME account --
    the duplicate-role refusal must casefold before intersecting. Mutation:
    revert the casefolded sets to exact-string sets -- red."""
    user = _FakeUser("uid-ada")
    wired.auth.users["Ada@x.example"] = user
    wired.auth.users["ada@x.example"] = user

    rc = bootstrap_firm.main(
        _argv(
            "--manager-email", "Ada@x.example",
            "--employee-email", "ada@x.example",
        )
    )

    assert rc == 2
    assert "BOTH" in capsys.readouterr().err
    assert wired.auth.stamps == {}
    assert wired.upserts == []


def test_status_choices_match_service_constants():
    """The CLI's status choices are deliberate literals (a module-scope
    backend import would break main()'s init-ordering trick); this pin turns
    drift between them and the service's FIRM_STATUS_* constants into a CI
    failure. Mutation: change a STATUS_CHOICES literal -- red."""
    import backend.services.firms as firms

    assert bootstrap_firm.STATUS_CHOICES == [
        firms.FIRM_STATUS_ACTIVE,
        firms.FIRM_STATUS_SUSPENDED,
    ]


def test_kind_choices_match_service_constants():
    """Same drift guard as test_status_choices_match_service_constants, for
    the new --kind flag (Epic 2 bead A1). Mutation: change a KIND_CHOICES
    literal -- red."""
    import backend.services.firms as firms

    assert bootstrap_firm.KIND_CHOICES == [
        firms.FIRM_KIND_MOCK,
        firms.FIRM_KIND_LIVE,
    ]


def test_kind_is_required_and_missing_kind_aborts_before_any_write(capsys):
    """--kind has NO default (module docstring: an operator who has not
    decided mock-vs-live must not silently get either). argparse's own
    required=True enforcement means main() never runs at all -- argparse
    calls sys.exit(2) directly. Mutation: drop required=True from the --kind
    argument -- this raises SystemExit(0) or hangs on a missing required
    value instead of the expected usage-error exit, and the assertion below
    goes red."""
    argv = [
        "acme-legal",
        "--name", "Acme Legal Aid",
        "--contact", "intake@acme.example",
        "--project", PROJECT,
        # --kind deliberately omitted
    ]
    with pytest.raises(SystemExit) as exc_info:
        bootstrap_firm.main(argv)
    assert exc_info.value.code == 2
    assert "--kind" in capsys.readouterr().err


@pytest.mark.parametrize("kind", ["mock", "live"])
def test_kind_flows_through_to_upsert_firm(wired, kind):
    """--kind mock and --kind live both reach upsert_firm as the 5th
    positional argument, unchanged. Mutation: hardcode "live" (or any other
    literal) in the upsert_firm call instead of args.kind -- the mock case
    goes red."""
    rc = bootstrap_firm.main(_argv(kind=kind))

    assert rc == 0
    assert len(wired.upserts) == 1
    args, _ = wired.upserts[0]
    assert args[4] == kind


def test_firm_write_failure_exits_2_and_stamps_nobody(wired, monkeypatch, capsys):
    """Exit code 2 means NOTHING was stamped: if the firm-doc write raises,
    the staff loop must never run (a claim stamped for a firm whose doc
    write failed would reference a nonexistent record). Mutation: make the
    upsert except-branch fall through to stamping instead of returning 2 --
    red."""
    wired.auth.users["ada@x.example"] = _FakeUser("uid-ada")

    def _raise(*a, **kw):
        raise RuntimeError("firestore down")

    monkeypatch.setattr("backend.services.firms.upsert_firm", _raise)

    rc = bootstrap_firm.main(_argv("--manager-email", "ada@x.example"))

    assert rc == 2
    assert "firm write FAILED" in capsys.readouterr().err
    assert wired.auth.stamps == {}


def test_rerun_is_idempotent(wired):
    """Running the same invocation twice succeeds twice with the same end
    state (upsert_firm carries the real merge semantics, pinned in
    test_firms_service.py; the claims stamp is naturally idempotent via the
    clobber-pin's read-then-spread). Mutation: make main() error on an
    already-existing firm -- red."""
    wired.auth.users["ada@x.example"] = _FakeUser("uid-ada")
    argv = _argv("--manager-email", "ada@x.example")

    assert bootstrap_firm.main(argv) == 0
    assert bootstrap_firm.main(argv) == 0
    assert len(wired.upserts) == 2
    assert wired.auth.stamps["uid-ada"]["firm_id"] == "acme-legal"
