#!/usr/bin/env python3
"""Grant (or revoke) schema-editor access for a person (bd polyglot-pdf-hn0jq).

  python scripts/bootstrap_editor_user.py --email maria@example.com --role editor
  python scripts/bootstrap_editor_user.py --email maria@example.com --revoke
  python scripts/bootstrap_editor_user.py --list

This is the ALLOWLIST: an account has editor access only if someone ran this for
it. Revoking one person touches only that person -- no shared secret to rotate,
which is the whole point of the change (epic criterion 2).

MIRRORS scripts/bootstrap_firm.py as a TEMPLATE rather than extending it.
Maintainer constraint, 2026-08-20: do not create new dependencies a future
separation epic would have to unravel. The editor stamps its OWN claim
(schema_editor_role); the firm script stamps firm_id/firm_role; neither reads
the other's.
"""
from __future__ import annotations

import argparse
import os
import sys


def _project_python() -> str:
    """Where the project's interpreter actually lives.

    NOT relative to this script: a git WORKTREE has no .venv of its own -- it
    lives in the main checkout -- so resolving from __file__ printed a path
    that does not exist, which is worse than no suggestion at all. Ask git for
    the common dir, and fall back to the script's own tree outside a repo.
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
    operator nothing about what actually went wrong. Say the real thing, and
    print the command that works.

    This runs at MODULE LOAD, before the backend import below, because that
    import is what fails. A check inside main() is too late: the traceback has
    already happened. (Measured -- the first version was in main() and never
    ran.)
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
            + "\" you@example.com\n\n")
        raise SystemExit(2)


_require_project_python()

# The claim name is owned by the editor's auth service -- importing it keeps the
# writer and the reader from drifting apart.
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
from backend.services.editor_auth import (  # noqa: E402
    EDITOR_ROLE_CLAIM,
    ROLE_AUTHOR,
    ROLE_EDITOR,
)

# Suppress the child console window every subprocess opens on Windows
# (bd polyglot-pdf-5k32 / bd polyglot-pdf-rdftu). Duplicated rather than
# imported from swarm_config because importing that module mutates PATH and
# loads a config file -- side effects this script must not take on.
def windowless_creationflags() -> int:
    """subprocess creationflags that suppress child console windows on Windows."""
    if sys.platform == "win32":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


_VALID_ROLES = (ROLE_EDITOR, ROLE_AUTHOR)


def _init_firebase() -> None:
    import firebase_admin

    if not firebase_admin._apps:
        firebase_admin.initialize_app()


def stamp_editor_role(email: str, role: str) -> tuple[str, str]:
    """Stamp schema_editor_role on the Firebase account for `email`.

    Returns (status, detail): ("stamped", uid) | ("unknown_email", email)
    | ("error", message). Never raises -- one bad address must not abort a batch.
    """
    from firebase_admin import auth as fb_auth

    try:
        user = fb_auth.get_user_by_email(email)
    except fb_auth.UserNotFoundError:
        return ("unknown_email", email)
    except Exception as e:  # pragma: no cover - network/SDK shapes vary
        return ("error", f"{email}: {e}")

    try:
        # set_custom_user_claims REPLACES the entire claims object -- it does NOT
        # merge. Read the existing claims and spread them first, or any unrelated
        # claim this account carries (firm_id, firm_role) is silently destroyed.
        # The same hazard is called out in bootstrap_firm.py and pinned there by
        # a test; it is pinned here too.
        existing = user.custom_claims or {}
        fb_auth.set_custom_user_claims(
            user.uid, {**existing, EDITOR_ROLE_CLAIM: role}
        )
    except Exception as e:  # pragma: no cover
        return ("error", f"{email}: {e}")
    return ("stamped", user.uid)


def revoke_editor_role(email: str) -> tuple[str, str]:
    """Remove schema_editor_role, leaving every other claim intact.

    Deleting the KEY rather than blanking it: a falsy role and an absent role
    both fail the reader's `role not in _VALID_ROLES` check, but an absent key
    is the honest representation of "no editor access", and it keeps the claims
    object from accumulating tombstones.
    """
    from firebase_admin import auth as fb_auth

    try:
        user = fb_auth.get_user_by_email(email)
    except fb_auth.UserNotFoundError:
        return ("unknown_email", email)
    except Exception as e:  # pragma: no cover
        return ("error", f"{email}: {e}")

    existing = dict(user.custom_claims or {})
    if EDITOR_ROLE_CLAIM not in existing:
        return ("not_an_editor", email)
    existing.pop(EDITOR_ROLE_CLAIM)
    try:
        fb_auth.set_custom_user_claims(user.uid, existing)
        # Dropping the claim is not enough: claims only reach a NEWLY MINTED
        # token, so an already-signed-in user keeps full access until theirs
        # expires. Revoking the refresh tokens is what makes "revoked" mean
        # revoked NOW, which is what the shared secret did on rotation.
        fb_auth.revoke_refresh_tokens(user.uid)
    except Exception as e:  # pragma: no cover
        return ("error", f"{email}: {e}")
    return ("revoked", user.uid)


def list_editor_users() -> list[tuple[str, str]]:
    """Every account carrying an editor role, as (email, role).

    The allowlist has no separate store -- the claims ARE the allowlist -- so
    this is the only way to answer "who has access?".
    """
    from firebase_admin import auth as fb_auth

    out: list[tuple[str, str]] = []
    page = fb_auth.list_users()
    while page:
        for user in page.users:
            role = (user.custom_claims or {}).get(EDITOR_ROLE_CLAIM)
            if role:
                out.append((user.email or user.uid, role))
        page = page.get_next_page()
    return sorted(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    # Accept the email POSITIONALLY as well as via --email. Running
    # `bootstrap_editor_user.py someone@example.com` is the obvious
    # invocation, and rejecting it with "unrecognized arguments" is a bad
    # first experience for the one tool that grants access.
    ap.add_argument("email_positional", nargs="?", metavar="EMAIL",
                    help="the person's Firebase account email")
    ap.add_argument("--email", help="the person's Firebase account email")
    ap.add_argument("--role", choices=_VALID_ROLES, default=ROLE_EDITOR,
                    help="editor (default) or author")
    ap.add_argument("--revoke", action="store_true",
                    help="remove editor access from --email")
    ap.add_argument("--list", action="store_true",
                    help="show every account with editor access")
    args = ap.parse_args(argv)
    if not args.email and args.email_positional:
        args.email = args.email_positional

    if not args.list and not args.email:
        ap.error("give an email (positionally or with --email), or --list")

    _require_project_python()
    _init_firebase()

    if args.list:
        rows = list_editor_users()
        if not rows:
            print("No accounts have schema editor access.")
            return 0
        print(f"{len(rows)} account(s) with schema editor access:")
        for email, role in rows:
            print(f"  {email:40} {role}")
        return 0

    if args.revoke:
        status, detail = revoke_editor_role(args.email)
        print({
            "revoked": f"Revoked editor access for {args.email} (uid {detail}).",
            "not_an_editor": f"{args.email} did not have editor access.",
            "unknown_email": f"No Firebase account for {args.email}.",
        }.get(status, f"ERROR: {detail}"))
        return 0 if status in ("revoked", "not_an_editor") else 1

    status, detail = stamp_editor_role(args.email, args.role)
    print({
        "stamped": f"Granted {args.role} access to {args.email} (uid {detail}).",
        # NOT "they must sign in once" -- there is no product path that lets a
        # new person do that. The hosted editor now has a real Firebase SIGN-IN
        # (SignInGate.tsx, bd polyglot-pdf-yswp3), but deliberately no SIGN-UP:
        # editor access is granted, never self-served, so a brand-new person
        # still cannot create an account by trying to use the editor. Telling
        # an operator to wait for something that cannot happen is worse than
        # telling them nothing.
        "unknown_email": (
            f"No Firebase account for {args.email}. Create it first -- the "
            "Firebase console (Authentication -> Users -> Add user), the "
            "Admin SDK, or gcloud -- then run this again. The editor has a "
            "sign-in screen but no sign-up, so the account cannot create "
            "itself."),
    }.get(status, f"ERROR: {detail}"))
    return 0 if status == "stamped" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
