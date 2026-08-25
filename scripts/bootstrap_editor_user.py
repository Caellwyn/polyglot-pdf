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
import sys

# The claim name is owned by the editor's auth service -- importing it keeps the
# writer and the reader from drifting apart.
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
from backend.services.editor_auth import (  # noqa: E402
    EDITOR_ROLE_CLAIM,
    ROLE_AUTHOR,
    ROLE_EDITOR,
)

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
    ap.add_argument("--email", help="the person's Firebase account email")
    ap.add_argument("--role", choices=_VALID_ROLES, default=ROLE_EDITOR,
                    help="editor (default) or author")
    ap.add_argument("--revoke", action="store_true",
                    help="remove editor access from --email")
    ap.add_argument("--list", action="store_true",
                    help="show every account with editor access")
    args = ap.parse_args(argv)

    if not args.list and not args.email:
        ap.error("give --email, or --list")

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
        "unknown_email": (f"No Firebase account for {args.email}. They must sign "
                          "in once before a role can be granted."),
    }.get(status, f"ERROR: {detail}"))
    return 0 if status == "stamped" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
