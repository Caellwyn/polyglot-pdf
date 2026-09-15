#!/usr/bin/env python3
"""Grant (or revoke) admin-console access for a person (bd polyglot-pdf-7w17m).

  python scripts/bootstrap_admin_user.py --email maria@example.com --project polyglot-demo-aa709
  python scripts/bootstrap_admin_user.py --email maria@example.com --revoke --project polyglot-demo-aa709
  python scripts/bootstrap_admin_user.py --list --project polyglot-demo-aa709

This is the ONLY way to create the FIRST admin -- it is the documented
operator-credential path, not a hole to close later (plan: "app_admin claim
bootstrap"). MIRRORS scripts/bootstrap_editor_user.py's shape (--email,
--revoke, --list, stamps an existing account, merges claims rather than
replacing them) and borrows scripts/bootstrap_firm.py's --project
machinery (deterministic project pin + dead-project refusal): the editor
script never took a --project flag because it was written before the
dead-project incident (bd polyglot-pdf-je6iy) made that omission a live
hazard on OTHER bootstrap scripts, and the admin claim is exactly the kind
of stamp that fails silently into the wrong project if the operator's ADC
happens to resolve elsewhere.

Deliberately NOT extending bootstrap_firm.py or bootstrap_editor_user.py:
same posture those two document about each other -- a shared base class
between three claim-stamping scripts would be a dependency a future
separation epic has to unravel, for a few dozen lines of duplication.

--project is REQUIRED and pins the target DETERMINISTICALLY: firebase_admin
otherwise resolves the project from the operator's gcloud ADC credential
first (scripts/read_confirmations.py's original warning). The script
additionally ASSERTS the resolved app project equals --project and aborts
otherwise -- a claim stamped into the wrong project fails silently and is
unrecoverable by inspection.

Credentials note: this runs under YOUR OWN gcloud ADC, not the deployed
admin-backend-sa (whose roles/firebaseauth.admin covers the SERVICE's own
access; see scripts/setup-admin-service.sh). Your principal needs Firebase
Auth admin on the target project.

TOKEN REFRESH: a stamped claim appears in the account's decoded ID token
only on their NEXT token refresh (up to ~1h). To see it immediately, have
them sign out/in, or force getIdToken(true) client-side.

Exit codes: 0 = the requested action succeeded (grant/revoke: the one
account; --list: always 0). 1 = the one account was not found, or (revoke)
did not hold admin access -- named in the output, not a batch so there is
nothing else to fail alongside it. 2 = refused before any write: dead or
mismatched project.

ASCII only (repo rule).
"""
from __future__ import annotations

import argparse
import os
import sys


def _project_python() -> str:
    """Where the project's interpreter actually lives.

    NOT relative to this script: a git WORKTREE has no .venv of its own -- it
    lives in the main checkout -- so resolving from __file__ printed a path
    that does not exist, which is worse than no suggestion at all. Ask git
    for the common dir, and fall back to the script's own tree outside a
    repo. Copied verbatim from bootstrap_editor_user.py's helper (same
    problem, same fix, not worth a shared import for one function).
    """
    import subprocess

    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    try:
        common = subprocess.run(
            ["git", "-C", here, "rev-parse", "--path-format=absolute",
             "--git-common-dir"],
            creationflags=windowless_creationflags(),
            capture_output=True, text=True, timeout=10)
        if common.returncode == 0 and common.stdout.strip():
            root = os.path.dirname(common.stdout.strip())
    except Exception:  # pragma: no cover -- git absent or slow; fall back
        pass

    for rel in (("backend", ".venv", "Scripts", "python.exe"),
                ("backend", ".venv", "bin", "python")):
        cand = os.path.join(root, *rel)
        if os.path.exists(cand):
            return cand
    return os.path.join(root, "backend", ".venv", "Scripts", "python.exe")


def _require_project_python() -> None:
    """A missing dependency here almost always means the WRONG interpreter.

    Run this with system Python and the failure is a ModuleNotFoundError deep
    in an import chain naming a LOGGING or web library -- which tells an
    operator nothing about what actually went wrong.
    """
    try:
        import fastapi  # noqa: F401
        import firebase_admin  # noqa: F401
        import structlog  # noqa: F401
    except ModuleNotFoundError as exc:
        sys.stderr.write(
            "\nThis needs the project's Python, not the system one "
            "(missing: " + str(exc.name) + ").\n\nRun:\n  \""
            + _project_python() + "\" \"" + os.path.abspath(__file__)
            + "\" --email you@example.com --project <project-id>\n\n")
        raise SystemExit(2)


_require_project_python()

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
# The claim name is owned by the admin service's auth module -- importing it
# keeps the writer and the reader from drifting apart.
from admin_backend.services.admin_auth import APP_ADMIN_CLAIM  # noqa: E402

# Suppress the child console window every subprocess opens on Windows
# (bd polyglot-pdf-5k32 / bd polyglot-pdf-rdftu). Duplicated rather than
# imported from swarm_config because importing that module mutates PATH and
# loads a config file -- side effects this script must not take on.
def windowless_creationflags() -> int:
    """subprocess creationflags that suppress child console windows on Windows."""
    if sys.platform == "win32":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


# The former prod project is DEAD and unreachable (maintainer, 2026-08-14).
# Refuse it outright so a stale muscle-memory invocation cannot hang or
# half-write against it. Same set scripts/bootstrap_firm.py refuses
# (bd polyglot-pdf-je6iy); duplicated rather than imported for the same
# liftability reason the module docstring gives for not sharing a base class.
DEAD_PROJECTS = {"polyglot-forms-919f2"}


def stamp_admin_claim(email: str) -> tuple[str, str]:
    """Stamp app_admin=True on the Firebase account for `email`.

    Returns (status, detail): ("stamped", uid) | ("unknown_email", email)
    | ("error", message). Never raises.
    """
    from firebase_admin import auth as fb_auth

    try:
        user = fb_auth.get_user_by_email(email)
    except fb_auth.UserNotFoundError:
        return ("unknown_email", email)
    except Exception as e:  # pragma: no cover - network/SDK shapes vary
        return ("error", f"{email}: {e}")

    try:
        # set_custom_user_claims REPLACES the entire claims object -- it does
        # NOT merge. Read the existing claims and spread them first, or any
        # unrelated claim this account carries (firm_id, schema_editor_role)
        # is silently destroyed. Same hazard bootstrap_firm.py and
        # bootstrap_editor_user.py each call out and pin.
        existing = user.custom_claims or {}
        fb_auth.set_custom_user_claims(
            user.uid, {**existing, APP_ADMIN_CLAIM: True}
        )
    except Exception as e:  # pragma: no cover
        return ("error", f"{email}: {e}")
    return ("stamped", user.uid)


def revoke_admin_claim(email: str) -> tuple[str, str]:
    """Remove app_admin, leaving every other claim intact.

    Deleting the KEY rather than setting it False: an absent key and a False
    value both fail the reader's `is not True` check, but an absent key is
    the honest representation of "no admin access", matching
    revoke_editor_role's reasoning.
    """
    from firebase_admin import auth as fb_auth

    try:
        user = fb_auth.get_user_by_email(email)
    except fb_auth.UserNotFoundError:
        return ("unknown_email", email)
    except Exception as e:  # pragma: no cover
        return ("error", f"{email}: {e}")

    existing = dict(user.custom_claims or {})
    if APP_ADMIN_CLAIM not in existing:
        return ("not_an_admin", email)
    existing.pop(APP_ADMIN_CLAIM)
    try:
        fb_auth.set_custom_user_claims(user.uid, existing)
        # Dropping the claim alone leaves an already-signed-in user working
        # for up to an hour -- claims only reach a NEWLY MINTED token.
        # Revoking the refresh tokens makes "revoked" mean revoked NOW.
        fb_auth.revoke_refresh_tokens(user.uid)
    except Exception as e:  # pragma: no cover
        return ("error", f"{email}: {e}")
    return ("revoked", user.uid)


def list_admin_users() -> list[str]:
    """Every account carrying app_admin=True, as a sorted list of emails
    (falling back to the uid for an account with no email on file).

    The allowlist has no separate store -- the claims ARE the allowlist --
    so this is the only way to answer "who has admin access?".
    """
    from firebase_admin import auth as fb_auth

    out: list[str] = []
    page = fb_auth.list_users()
    while page:
        for user in page.users:
            if (user.custom_claims or {}).get(APP_ADMIN_CLAIM) is True:
                out.append(user.email or user.uid)
        page = page.get_next_page()
    return sorted(out)


def main(argv=None) -> int:
    # main(argv), not a bare main()+sys.argv: lets tests drive the CLI as
    # main([...]) with no module-reload/argv-monkeypatch fixture (same
    # deliberate choice bootstrap_firm.py documents).
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("email_positional", nargs="?", metavar="EMAIL",
                    help="the person's Firebase account email")
    ap.add_argument("--email", help="the person's Firebase account email")
    ap.add_argument("--revoke", action="store_true",
                    help="remove admin access from --email")
    ap.add_argument("--list", action="store_true",
                    help="show every account with admin access")
    ap.add_argument(
        "--project",
        required=True,
        help="target Firebase project (deterministic: pre-initializes "
        "firebase_admin with this projectId AND asserts the resolved app "
        "project matches)",
    )
    args = ap.parse_args(argv)
    if not args.email and args.email_positional:
        args.email = args.email_positional

    if not args.list and not args.email:
        ap.error("give an email (positionally or with --email), or --list")

    if args.project in DEAD_PROJECTS:
        print(
            f"project {args.project} is DEAD and unreachable (maintainer "
            "2026-08-14, bd polyglot-pdf-je6iy); refusing.",
            file=sys.stderr,
        )
        return 2

    _require_project_python()

    # Initialize firebase_admin with the target project BEFORE any other
    # backend/admin_backend import that might call a bare initialize_app():
    # whichever init runs first wins, so an implicit resolution (gcloud ADC)
    # could silently target the wrong project. Same ordering trap
    # bootstrap_firm.py documents and guards identically.
    import firebase_admin

    if not firebase_admin._apps:
        firebase_admin.initialize_app(options={"projectId": args.project})

    resolved = firebase_admin.get_app().project_id
    if resolved != args.project:
        print(
            f"resolved firebase_admin project is {resolved!r}, not "
            f"{args.project!r} -- refusing to write into the wrong "
            "project. (Was firebase_admin initialized before this script "
            "ran?)",
            file=sys.stderr,
        )
        return 2
    # Set only AFTER the assertion passes: the abort path must not leave the
    # process env pointed at a project this run refused to write into.
    os.environ["GOOGLE_CLOUD_PROJECT"] = args.project

    if args.list:
        rows = list_admin_users()
        if not rows:
            print("No accounts have admin console access.")
            return 0
        print(f"{len(rows)} account(s) with admin console access:")
        for email in rows:
            print(f"  {email}")
        return 0

    if args.revoke:
        status, detail = revoke_admin_claim(args.email)
        print({
            "revoked": f"Revoked admin access for {args.email} (uid {detail}).",
            "not_an_admin": f"{args.email} did not have admin access.",
            "unknown_email": f"No Firebase account for {args.email}.",
        }.get(status, f"ERROR: {detail}"))
        return 0 if status in ("revoked", "not_an_admin") else 1

    status, detail = stamp_admin_claim(args.email)
    print({
        "stamped": f"Granted admin console access to {args.email} (uid {detail}).",
        # Names the SAME remedies the editor script's grant-path message
        # names (bd polyglot-pdf-onsd6 fixed that message after it promised
        # a sign-in flow that could not create an account) -- the admin
        # console has no self-serve sign-up either, so the same falsehood
        # would be just as wrong here.
        "unknown_email": (
            f"No Firebase account for {args.email}. Create it first -- the "
            "Firebase console (Authentication -> Users -> Add user), the "
            "Admin SDK, or gcloud -- then run this again."),
    }.get(status, f"ERROR: {detail}"))
    return 0 if status == "stamped" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
