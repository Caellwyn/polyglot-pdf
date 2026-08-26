"""What the DEPLOYED service may ask Firebase for.

WHY THIS FILE EXISTS. Three bugs in one day reached the live app through a
green suite, green CI, nine review rounds and a cross-surface pass. The last
one -- check_revoked on the auth handshake -- broke EVERY connection with
INSUFFICIENT_PERMISSION, and no test could have caught it: every test stubs
the Firebase SDK, so the stub cheerfully answers a call the real service
account is forbidden to make.

THE STRUCTURAL GAP: a mock proves the code CALLS something. It cannot prove
the caller is ALLOWED to. Those are different questions, and only the second
was failing.

WHAT THIS CHECKS INSTEAD: the deployed service runs as polyglot-backend-sa,
whose roles are deliberately narrow (aiplatform.user, datastore.user,
logging.logWriter, secretmanager.secretAccessor, storage.objectViewer). None
grants firebaseauth.users.get, so any Firebase Auth call beyond verifying a
token's SIGNATURE fails in production, always, on the first request.

SCOPE. backend/routes and backend/services are what Cloud Run executes. The
scripts/ bootstrap tools are NOT in scope: they run under an operator's own
gcloud credentials, where these calls are correct and necessary.

Static on purpose -- no token, no deploy, no network -- so it runs in CI on
every change.
"""
import ast
import pathlib

# Calls needing a Firebase Auth permission the runtime SA does not hold.
# verify_id_token(token) alone is FINE: signature verification needs no IAM.
_PRIVILEGED = {
    "get_user",
    "get_user_by_email",
    "list_users",
    "set_custom_user_claims",
    "revoke_refresh_tokens",
    "delete_user",
    "create_user",
    "update_user",
}

_DEPLOYED_DIRS = ("routes", "services")


def _deployed_sources():
    root = pathlib.Path(__file__).resolve().parents[2]
    for d in _DEPLOYED_DIRS:
        for f in sorted((root / d).rglob("*.py")):
            yield f, root


def test_the_deployed_service_makes_no_privileged_firebase_auth_call():
    """A privileged call here fails on the FIRST request in production."""
    offenders = []
    for f, root in _deployed_sources():
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if name in _PRIVILEGED:
                offenders.append("{}:{} calls {}()".format(
                    f.relative_to(root).as_posix(), node.lineno, name))

    assert not offenders, (
        "The deployed service makes Firebase Auth calls its service account "
        "cannot perform. Each fails with INSUFFICIENT_PERMISSION on the first "
        "request in production, and no mocked test will see it:"
        + chr(10) + "  " + (chr(10) + "  ").join(offenders)
        + chr(10) + chr(10)
        + "Either grant polyglot-backend-sa the IAM role (a deliberate "
          "widening the maintainer approves) or do not make the call.")


def test_verify_id_token_is_not_called_with_check_revoked():
    """The specific flag that took the app down, pinned by name.

    check_revoked turns a signature check into a USER-RECORD FETCH. It reads
    as a small hardening flag, which is why it survived review twice: the AST
    test above catches privileged METHOD calls, and this catches the KEYWORD
    that quietly becomes one.
    """
    offenders = []
    for f, root in _deployed_sources():
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if kw.arg == "check_revoked" and not (
                        isinstance(kw.value, ast.Constant)
                        and kw.value.value is False):
                    offenders.append("{}:{}".format(
                        f.relative_to(root).as_posix(), node.lineno))

    assert not offenders, (
        "check_revoked is set on a token verification in the deployed "
        "service. It needs firebaseauth.users.get, which polyglot-backend-sa "
        "does not have, so EVERY request will 403:"
        + chr(10) + "  " + (chr(10) + "  ").join(offenders))
