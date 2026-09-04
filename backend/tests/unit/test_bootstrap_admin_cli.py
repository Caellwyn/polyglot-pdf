"""scripts/bootstrap_admin_user.py CLI contract (bd polyglot-pdf-7w17m).

Pins the operator-facing safety properties, in the shape
test_bootstrap_firm_cli.py established for --project handling and
test_editor_identity.py established for claim merge/revoke:
- the claims stamp MERGES over existing custom claims (set_custom_user_claims
  REPLACES the whole object -- the read-then-spread is the script's single
  highest-risk line, same as its two siblings);
- --revoke removes ONLY app_admin, leaving other claims intact, and kills
  live sessions via revoke_refresh_tokens;
- a mismatched resolved project ABORTS with exit 2 before anything is
  written (a claim stamped into the wrong project fails silently);
- the dead project polyglot-forms-919f2 is refused outright;
- --list reports every app_admin account and writes nothing;
- an unknown email exits 1 without touching firebase_admin's write surface.

The CLI is driven as main([...]), mirroring both siblings.

Each test's docstring names the mutation that must turn it red. ASCII only.
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

import scripts.bootstrap_admin_user as boot  # noqa: E402
from admin_backend.services.admin_auth import APP_ADMIN_CLAIM  # noqa: E402

PROJECT = "polyglot-demo-aa709"


class _FakeUser:
    def __init__(self, uid, claims=None, email=None):
        self.uid = uid
        self.custom_claims = claims
        self.email = email


class _AuthStub:
    """Captures the firebase_admin.auth surface the script touches."""

    def __init__(self, users):
        self.users = users  # email -> _FakeUser
        self.stamps = {}  # uid -> claims payload
        self.revoked_sessions = []

    def get_user_by_email(self, email):
        user = self.users.get(email)
        if user is None:
            raise fb_auth.UserNotFoundError(f"no user for {email}")
        return user

    def set_custom_user_claims(self, uid, claims):
        self.stamps[uid] = dict(claims)

    def revoke_refresh_tokens(self, uid):
        self.revoked_sessions.append(uid)


@pytest.fixture
def wired(monkeypatch):
    """An app already 'initialized' on the right project plus a capturing
    auth stub -- mirrors test_bootstrap_firm_cli.py's `wired` fixture."""
    auth_stub = _AuthStub(users={})

    monkeypatch.setattr(firebase_admin, "_apps", {"[DEFAULT]": object()})
    monkeypatch.setattr(
        firebase_admin, "initialize_app",
        lambda *a, **kw: pytest.fail(
            "initialize_app must not run when an app exists"),
    )
    monkeypatch.setattr(
        firebase_admin, "get_app",
        lambda: SimpleNamespace(project_id=PROJECT),
    )
    monkeypatch.setattr(fb_auth, "get_user_by_email", auth_stub.get_user_by_email)
    monkeypatch.setattr(
        fb_auth, "set_custom_user_claims", auth_stub.set_custom_user_claims
    )
    monkeypatch.setattr(
        fb_auth, "revoke_refresh_tokens", auth_stub.revoke_refresh_tokens
    )
    return auth_stub


def _argv(*extra, email="ada@example.com", project=PROJECT):
    return ["--email", email, "--project", project, *extra]


def test_granting_stamps_app_admin_true_and_exits_0(wired):
    """Mutation: stamp a falsy/non-True value for APP_ADMIN_CLAIM -- red
    (test_admin_auth.py's non-boolean-truthy test pins the READER side; this
    pins the WRITER)."""
    wired.users["ada@example.com"] = _FakeUser("uid-ada")

    rc = boot.main(_argv())

    assert rc == 0
    assert wired.stamps["uid-ada"][APP_ADMIN_CLAIM] is True


def test_existing_custom_claims_survive_the_grant(wired):
    """THE clobber pin: set_custom_user_claims replaces the whole claims
    object, so the script must read-then-spread. Mutation: replace
    {**existing, ...} with a bare {APP_ADMIN_CLAIM: True} payload in
    stamp_admin_claim -- the firm_id claim vanishes and this goes red."""
    wired.users["ada@example.com"] = _FakeUser(
        "uid-ada", claims={"firm_id": "acme", "firm_role": "manager"}
    )

    rc = boot.main(_argv())

    assert rc == 0
    assert wired.stamps["uid-ada"] == {
        "firm_id": "acme",
        "firm_role": "manager",
        APP_ADMIN_CLAIM: True,
    }


def test_revoke_removes_only_the_admin_claim_and_kills_sessions(wired):
    """Mirrors test_revoke_removes_only_the_editor_claim: dropping the claim
    alone leaves an already-signed-in admin working for up to an hour, so
    revoke_refresh_tokens must also fire. Mutation: drop the
    revoke_refresh_tokens call from revoke_admin_claim -- the sessions
    assert goes red."""
    wired.users["ada@example.com"] = _FakeUser(
        "uid-ada", claims={"firm_id": "acme", APP_ADMIN_CLAIM: True}
    )

    rc = boot.main(_argv("--revoke"))

    assert rc == 0
    assert wired.revoked_sessions == ["uid-ada"]
    left = wired.stamps["uid-ada"]
    assert APP_ADMIN_CLAIM not in left, "admin access must be gone"
    assert left["firm_id"] == "acme", "unrelated claims must SURVIVE"


def test_revoking_a_non_admin_is_a_no_op_reported_distinctly(wired, capsys):
    """--revoke on an account that never held app_admin must not write
    anything, and must say so distinctly from 'unknown_email'. Mutation:
    fold not_an_admin into the unknown_email branch -- the message assert
    goes red."""
    wired.users["bo@example.com"] = _FakeUser("uid-bo", claims={})

    rc = boot.main(_argv("--revoke", email="bo@example.com"))

    assert rc == 0
    assert wired.stamps == {}
    assert wired.revoked_sessions == []
    assert "did not have admin access" in capsys.readouterr().out


def test_unknown_email_on_grant_exits_1_and_writes_nothing(wired, capsys):
    """Mutation: swallow UserNotFoundError and stamp a synthesized uid
    anyway -- the exit-code and stamps asserts go red."""
    rc = boot.main(_argv(email="ghost@example.com"))

    out = capsys.readouterr()
    assert rc == 1
    assert wired.stamps == {}
    assert "ghost@example.com" in out.out


def test_unknown_email_on_revoke_exits_1(wired, capsys):
    rc = boot.main(_argv("--revoke", email="ghost@example.com"))

    assert rc == 1
    assert "ghost@example.com" in capsys.readouterr().out


def test_list_reports_every_admin_and_writes_nothing(wired, monkeypatch, capsys):
    """--list must never touch set_custom_user_claims. Mutation: drop the
    APP_ADMIN_CLAIM filter in list_admin_users -- a non-admin account leaks
    into the report and this goes red."""
    class _Page:
        def __init__(self, users, nxt=None):
            self.users = users
            self._next = nxt

        def get_next_page(self):
            return self._next

    users = [
        _FakeUser("uid-ada", claims={APP_ADMIN_CLAIM: True}, email="ada@example.com"),
        _FakeUser("uid-bo", claims={"firm_id": "acme"}, email="bo@example.com"),
    ]
    monkeypatch.setattr(fb_auth, "list_users", lambda: _Page(users))
    monkeypatch.setattr(
        fb_auth, "set_custom_user_claims",
        lambda *a, **kw: pytest.fail("--list must write nothing"),
    )

    rc = boot.main(["--list", "--project", PROJECT])

    out = capsys.readouterr().out
    assert rc == 0
    assert "ada@example.com" in out
    assert "bo@example.com" not in out


def test_mismatched_resolved_project_aborts_with_exit_2(wired, monkeypatch, capsys):
    """Mutation: delete the resolved == args.project assertion -- the
    explode-mock stamp fires and this goes red."""
    monkeypatch.setattr(
        firebase_admin, "get_app",
        lambda: SimpleNamespace(project_id="somebody-elses-project"),
    )
    monkeypatch.setattr(
        fb_auth, "set_custom_user_claims",
        lambda *a, **kw: pytest.fail("must not write into a mismatched project"),
    )
    wired.users["ada@example.com"] = _FakeUser("uid-ada")

    rc = boot.main(_argv())

    assert rc == 2
    assert wired.stamps == {}
    assert "refusing" in capsys.readouterr().err


def test_dead_project_is_refused_before_any_init(monkeypatch, capsys):
    """polyglot-forms-919f2 is dead (maintainer 2026-08-14): exit 2 before
    firebase_admin is even initialized. Mutation: drop the DEAD_PROJECTS
    check -- the explode-mock init fires."""
    monkeypatch.setattr(firebase_admin, "_apps", {})
    monkeypatch.setattr(
        firebase_admin, "initialize_app",
        lambda *a, **kw: pytest.fail(
            "must not initialize against the dead project"),
    )

    rc = boot.main(_argv(project="polyglot-forms-919f2"))

    assert rc == 2
    assert "DEAD" in capsys.readouterr().err


def test_missing_email_and_missing_list_is_refused_by_argparse(wired):
    """Neither an email nor --list: argparse's ap.error() exits 2."""
    with pytest.raises(SystemExit) as exc:
        boot.main(["--project", PROJECT])
    assert exc.value.code == 2


def test_positional_email_is_accepted(wired):
    """Running `bootstrap_admin_user.py someone@example.com --project ...`
    must work -- rejecting it is a bad first experience for the one tool
    that grants access (same UX bootstrap_editor_user.py provides).
    Mutation: drop the email_positional fallback -- ap.error fires and this
    goes red."""
    wired.users["ada@example.com"] = _FakeUser("uid-ada")

    rc = boot.main(["ada@example.com", "--project", PROJECT])

    assert rc == 0
    assert wired.stamps["uid-ada"][APP_ADMIN_CLAIM] is True


def test_rerun_is_idempotent(wired):
    """Running the same grant twice succeeds twice with the same end state
    (the read-then-spread merge is naturally idempotent)."""
    wired.users["ada@example.com"] = _FakeUser("uid-ada")
    argv = _argv()

    assert boot.main(argv) == 0
    assert boot.main(argv) == 0
    assert wired.stamps["uid-ada"][APP_ADMIN_CLAIM] is True
