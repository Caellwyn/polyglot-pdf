"""Grant/revoke VOICE-app access for a developer account.

TWO SEPARATE ALLOWLISTS (maintainer, 2026-08-22): "voice app accounts should be
tied to firms, or a devs. editor accounts are separate ... Those should be 2
separate auth lists." This tool owns the DEV half of the voice list; firm staff
are enrolled by bootstrap_firm.py, and editor access by bootstrap_editor_user.py.

WHY THIS EXISTS: bd polyglot-pdf-hn0jq made a firm_id (or this dev claim)
REQUIRED to reach /ws/fill, /api/fill-pdf and the TTS routes. Without a way to
set it, a maintainer with no firm is locked out of the app they are building --
which is exactly what shipped in an earlier round of this bead, as a function
nothing could call.

  python scripts/bootstrap_voice_dev.py --email you@example.com
  python scripts/bootstrap_voice_dev.py --email you@example.com --revoke
  python scripts/bootstrap_voice_dev.py --list
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.auth import VOICE_DEV_CLAIM  # noqa: E402


def _init_firebase():
    import firebase_admin

    if not firebase_admin._apps:
        firebase_admin.initialize_app()


def stamp_dev_claim(email: str) -> tuple[str, str]:
    """Mark an account as a dev so it reaches the voice app without a firm."""
    from firebase_admin import auth as fb_auth

    try:
        user = fb_auth.get_user_by_email(email)
    except fb_auth.UserNotFoundError:
        return ("unknown_email", email)
    except Exception as e:  # pragma: no cover -- network/credentials
        return ("error", f"{email}: {e}")
    try:
        # set_custom_user_claims REPLACES the entire claims object -- it does
        # NOT merge. Spread the existing claims first or any unrelated claim
        # this account carries (firm_id, schema_editor_role) is destroyed.
        existing = user.custom_claims or {}
        fb_auth.set_custom_user_claims(user.uid, {**existing, VOICE_DEV_CLAIM: True})
    except Exception as e:  # pragma: no cover
        return ("error", f"{email}: {e}")
    return ("stamped", user.uid)


def revoke_dev_claim(email: str) -> tuple[str, str]:
    """Drop the dev claim, leaving every other claim intact."""
    from firebase_admin import auth as fb_auth

    try:
        user = fb_auth.get_user_by_email(email)
    except fb_auth.UserNotFoundError:
        return ("unknown_email", email)
    except Exception as e:  # pragma: no cover
        return ("error", f"{email}: {e}")

    existing = dict(user.custom_claims or {})
    if VOICE_DEV_CLAIM not in existing:
        return ("not_a_dev", email)
    existing.pop(VOICE_DEV_CLAIM)
    try:
        fb_auth.set_custom_user_claims(user.uid, existing)
        # Claims only reach a NEWLY MINTED token, so without this the account
        # keeps access until its current token expires (up to an hour).
        fb_auth.revoke_refresh_tokens(user.uid)
    except Exception as e:  # pragma: no cover
        return ("error", f"{email}: {e}")
    return ("revoked", user.uid)


def list_dev_users() -> list:
    """Every account carrying the dev claim."""
    from firebase_admin import auth as fb_auth

    out = []
    page = fb_auth.list_users()
    while page:
        for u in page.users:
            if (u.custom_claims or {}).get(VOICE_DEV_CLAIM):
                out.append(u.email or u.uid)
        page = page.get_next_page()
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--email", help="the developer's Firebase account email")
    ap.add_argument("--revoke", action="store_true",
                    help="remove dev voice access from --email")
    ap.add_argument("--list", action="store_true",
                    help="show every account with dev voice access")
    args = ap.parse_args(argv)

    if not args.list and not args.email:
        ap.error("give --email, or --list")

    _init_firebase()

    if args.list:
        rows = list_dev_users()
        if not rows:
            print("No accounts have dev voice access.")
            return 0
        print(f"{len(rows)} account(s) with dev voice access:")
        for email in rows:
            print(f"  {email}")
        return 0

    if args.revoke:
        status, detail = revoke_dev_claim(args.email)
        print({
            "revoked": f"Revoked dev voice access for {args.email} (uid {detail}).",
            "not_a_dev": f"{args.email} did not have dev voice access.",
            "unknown_email": f"No Firebase account for {args.email}.",
        }.get(status, f"ERROR: {detail}"))
        return 0 if status in ("revoked", "not_a_dev") else 1

    status, detail = stamp_dev_claim(args.email)
    print({
        "stamped": f"Granted dev voice access to {args.email} (uid {detail}).",
        "unknown_email": (f"No Firebase account for {args.email}. They must sign "
                          "in once before the claim can be set."),
    }.get(status, f"ERROR: {detail}"))
    return 0 if status == "stamped" else 1


if __name__ == "__main__":
    raise SystemExit(main())
