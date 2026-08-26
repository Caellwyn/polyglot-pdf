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

SCOPE. Everything under backend/ that ships -- routes, services, adapters,
utils, models, ports, and the module root -- derived by EXCLUSION, so a new
package is covered the day it appears. (The first version scanned routes and
services only; routes import adapters and utils transitively, so a privileged
call there was invisible to the guard written to catch exactly that.) The
scripts/ bootstrap tools are NOT in scope: they run under an operator's own
gcloud credentials, where these calls are correct and necessary.

Static on purpose -- no token, no deploy, no network -- so it runs in CI on
every change.
"""
import ast
import pathlib

# DERIVED from the installed SDK, not hand-listed. My first version named
# eight calls and missed twenty -- including generate_sign_in_with_email_link,
# the magic-link flow the maintainer says future users will arrive through.
# That is the same hand-list failure this repo has now hit four times.
#
# The rule is INVERTED: everything in firebase_admin.auth touches the Identity
# Toolkit API and needs an IAM permission, EXCEPT verifying a token, which is
# pure signature math against public keys. So allow-list the safe ones and
# treat the rest as privileged -- a new SDK function is covered the day it
# ships instead of the day someone remembers to add it.
_SIGNATURE_ONLY = {
    "verify_id_token",   # public-key signature check; no API call, no IAM
}


def _privileged_calls():
    """Every firebase_admin.auth callable that needs an IAM permission."""
    import firebase_admin.auth as fb_auth

    return {
        name for name in dir(fb_auth)
        if not name.startswith("_")
        and name[0].islower()
        and callable(getattr(fb_auth, name, None))
        and name not in _SIGNATURE_ONLY
    }


# EVERYTHING Cloud Run executes, not just where the bug happened to be. The
# first version scanned routes/ + services/ only -- but routes import adapters
# and utils transitively, so a privileged call added there would have been
# invisible to the very guard written to prevent it. No live instance today;
# the SCOPE hole was real.
#
# Derived by EXCLUSION (everything under backend/, minus what does not run in
# the service) rather than by listing what to include, so a NEW top-level
# package is covered the day it appears instead of silently skipped.
_NOT_DEPLOYED = {"tests", ".venv", "__pycache__", "docs", "logs", "scripts"}


def _deployed_sources():
    """Every .py file the Cloud Run service can execute."""
    root = pathlib.Path(__file__).resolve().parents[2]
    for f in sorted(root.rglob("*.py")):
        rel = f.relative_to(root)
        if any(part in _NOT_DEPLOYED for part in rel.parts):
            continue
        yield f, root


def test_the_deployed_service_makes_no_privileged_firebase_auth_call():
    """A privileged call here fails on the FIRST request in production."""
    privileged = _privileged_calls()
    offenders = []
    for f, root in _deployed_sources():
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if name in privileged:
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
