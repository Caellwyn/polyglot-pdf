"""Create/update a firm record and stamp firm identity claims (bd polyglot-pdf-lo88).

The firm tier's admin bootstrap: creates (or idempotently updates) the
firms/{firm_id} Firestore document and stamps the firm_id + firm_role custom
claims on the firm's staff Firebase accounts, keyed by their email addresses.
firm_role is "manager" (firm-level management) or "employee" (send-a-link
staff) per the four-level access model
(docs/sprint_19_firm-tier-kit-lifecycle_plan.md, 2026-08-14 addendum).

Usage (from the repo root, with the backend venv):

    backend/.venv/Scripts/python.exe scripts/bootstrap_firm.py acme-legal \
        --name "Acme Legal Aid" --contact intake@acme-legal.example \
        --allowed-kits w7,i-90 \
        --kind live \
        --manager-email ada@acme-legal.example \
        --employee-email bo@acme-legal.example \
        --project polyglot-demo-aa709

    # Preview: performs the READ-ONLY email lookups (so unknown addresses
    # surface before the real run) but writes NOTHING:
    ... --dry-run

--kind is REQUIRED (Epic 2 bead A1): "mock" firms can mint credits on
staging without moving real money; "live" firms are the paying customers,
gated to minting only on the explicit demo channel
(backend/routes/link_routes.py's mint gate). There is no default -- an
operator who has not decided which this firm is must not silently get
"live" (which mints for free until credit enforcement is switched on) or
"mock" (which would make a real firm invisible to production billing). A
firm doc with no `kind` key at all -- pre-migration docs only -- is treated
as "live" by the fail-closed service-layer reader
(backend/services/firms.py:firm_kind()); local minting needs the dev
account's own firm created with --kind mock.

--project is REQUIRED and pins the target DETERMINISTICALLY: firebase_admin
otherwise resolves the project from the operator's gcloud ADC credential
first (same trap scripts/read_confirmations.py documents). The script
additionally ASSERTS the resolved app project equals --project and aborts
otherwise -- a claim stamped into the wrong project fails silently and is
unrecoverable by inspection.

Credentials note: this runs under YOUR OWN gcloud ADC, not the Cloud Run
runtime SA (whose roles/datastore.user covers the backend's own access; see
scripts/setup-gcp-project.sh). Your principal needs Firestore write access
AND Firebase Auth admin on the target project.

TOKEN REFRESH: a stamped claim appears in the staff member's decoded ID
token only on their NEXT token refresh (up to ~1h). To see it immediately,
have them sign out/in, or force getIdToken(true) client-side.

Exit codes: 0 = firm doc written and ALL staff emails stamped (or, with
--dry-run, all lookups succeeded); 1 = one or more staff emails failed
(unknown address or error) -- fix and re-run, re-runs are idempotent;
2 = NOTHING was stamped: invalid firm_id, dead/mismatched project, or the
firm doc write failed.

ASCII only (repo rule).
"""
import argparse
import os
import re
import sys
from pathlib import Path

# Make backend.* importable when run as python scripts/bootstrap_firm.py
# from the repo root (or anywhere -- resolve relative to this file).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# The former prod project is DEAD and unreachable (maintainer, 2026-08-14).
# Refuse it outright so a stale muscle-memory invocation cannot hang or
# half-write against it. Repo-wide reference purge: bd polyglot-pdf-je6iy.
DEAD_PROJECTS = {"polyglot-forms-919f2"}

# _KIT_ID_RE's length bound (backend/routes/form_kit_routes.py) with
# OPTION_SLUG_PATTERN's character class (backend/models/
# conditional_vocabulary.py). Lowercase-only on purpose: Firestore doc IDs
# are case-sensitive, so Acme/acme would be two different firms -- an
# operator error this rule makes impossible.
FIRM_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,127}$")

ROLE_MANAGER = "manager"
ROLE_EMPLOYEE = "employee"

# Kept as literals (NOT imported from backend.services.firms) deliberately:
# any backend.* import at module scope would run before main()'s
# initialize_app(projectId=...) and could trip the bare initialize_app() in
# backend/services/auth.py -- the exact ordering trap main() documents.
# test_status_choices_match_service_constants pins these against the
# service's FIRM_STATUS_* constants so drift fails CI instead of silently.
STATUS_CHOICES = ["active", "suspended"]

# Same reasoning as STATUS_CHOICES: literals, not an import, pinned against
# backend.services.firms.FIRM_KIND_* by test_kind_choices_match_service_constants.
# No default -- --kind is a REQUIRED argparse argument (Epic 2 bead A1); see
# the module docstring for why an implicit default is wrong here.
KIND_CHOICES = ["mock", "live"]


def stamp_firm_claims(email: str, firm_id: str, firm_role: str) -> tuple[str, str]:
    """Stamp firm_id + firm_role on the Firebase account for `email`.

    Returns (status, detail): ("stamped", uid) | ("unknown_email", email)
    | ("error", message). Never raises -- one bad address must not abort
    the rest of the batch.
    """
    from firebase_admin import auth as fb_auth

    try:
        user = fb_auth.get_user_by_email(email)
    except fb_auth.UserNotFoundError:
        return ("unknown_email", email)
    except Exception as e:
        return ("error", f"{email}: {e}")
    try:
        # set_custom_user_claims REPLACES the entire claims object -- it does
        # NOT merge. Read the existing claims and spread them first, or any
        # unrelated claim this account carries is silently destroyed. This is
        # the single highest-risk line in this script; pinned by
        # test_existing_custom_claims_survive_the_stamp.
        existing = user.custom_claims or {}
        fb_auth.set_custom_user_claims(
            user.uid,
            {**existing, "firm_id": firm_id, "firm_role": firm_role},
        )
    except Exception as e:
        return ("error", f"{email}: {e}")
    return ("stamped", user.uid)


def main(argv=None) -> int:
    # main(argv) rather than read_confirmations.py's bare main()+sys.argv:
    # a deliberate improvement so tests drive the CLI as main([...]) with no
    # module-reload/argv-monkeypatch fixture.
    parser = argparse.ArgumentParser(
        description="Create/update a firm record and stamp firm_id + "
        "firm_role custom claims on its staff accounts."
    )
    parser.add_argument("firm_id", help="firm slug, e.g. acme-legal")
    parser.add_argument("--name", required=True, help="firm display name")
    parser.add_argument(
        "--contact",
        required=True,
        help="firm contact email (free text; need not be a Firebase account)",
    )
    parser.add_argument(
        "--allowed-kits",
        default="",
        help="comma-separated kit_ids this firm may see beyond public kits",
    )
    parser.add_argument(
        "--manager-email",
        action="append",
        default=[],
        help="staff account email to stamp firm_role=manager (repeatable)",
    )
    parser.add_argument(
        "--employee-email",
        action="append",
        default=[],
        help="staff account email to stamp firm_role=employee (repeatable)",
    )
    parser.add_argument(
        "--status", default=STATUS_CHOICES[0], choices=STATUS_CHOICES
    )
    parser.add_argument(
        "--kind",
        required=True,
        choices=KIND_CHOICES,
        help="mock (staging test firm, no real money) or live (paying "
        "customer, mints only on the explicit demo channel) -- REQUIRED, "
        "no default (see the module docstring for why)",
    )
    parser.add_argument(
        "--project",
        required=True,
        help="target Firebase project (deterministic: pre-initializes "
        "firebase_admin with this projectId AND asserts the resolved app "
        "project matches)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="do the read-only email lookups but write nothing",
    )
    args = parser.parse_args(argv)

    # fullmatch, not match: a $-anchored .match still accepts a trailing
    # newline ("acme\n"), the exact bug class _KIT_ID_RE was fixed for
    # (backend/routes/form_kit_routes.py, bd polyglot-pdf-sbfk).
    if not FIRM_ID_RE.fullmatch(args.firm_id):
        print(
            f"firm_id {args.firm_id!r} is not a valid slug "
            "(lowercase ^[a-z0-9][a-z0-9_-]{0,127}$)",
            file=sys.stderr,
        )
        return 2
    if args.project in DEAD_PROJECTS:
        print(
            f"project {args.project} is DEAD and unreachable (maintainer "
            "2026-08-14, bd polyglot-pdf-je6iy); refusing.",
            file=sys.stderr,
        )
        return 2
    # casefold both sides: Firebase resolves emails case-insensitively, so
    # Ada@x / ada@x are the SAME account and would clobber roles silently.
    duplicated = {e.casefold() for e in args.manager_email} & {
        e.casefold() for e in args.employee_email
    }
    if duplicated:
        print(
            "email(s) listed under BOTH --manager-email and --employee-email: "
            + ", ".join(sorted(duplicated))
            + " -- refusing (ambiguous role; the last stamp would silently win).",
            file=sys.stderr,
        )
        return 2

    # Initialize firebase_admin with the target project BEFORE any backend.*
    # import: backend/services/auth.py calls a bare initialize_app() at
    # module import time, and whichever init runs first wins. The explicit
    # projectId option plus the assertion below are what make --project
    # deterministic (firebase_admin resolves the project from the CREDENTIAL
    # first -- see scripts/read_confirmations.py's identical warning).
    import firebase_admin

    if not firebase_admin._apps:
        firebase_admin.initialize_app(options={"projectId": args.project})

    resolved = firebase_admin.get_app().project_id
    if resolved != args.project:
        print(
            f"resolved firebase_admin project is {resolved!r}, not "
            f"{args.project!r} -- refusing to write into the wrong project. "
            "(Was firebase_admin initialized before this script ran?)",
            file=sys.stderr,
        )
        return 2
    # Set only AFTER the assertion passes: the abort path must not leave the
    # process env pointed at a project this run refused to write into.
    os.environ["GOOGLE_CLOUD_PROJECT"] = args.project

    kits = [k.strip() for k in args.allowed_kits.split(",") if k.strip()]
    staff = [(e, ROLE_MANAGER) for e in args.manager_email] + [
        (e, ROLE_EMPLOYEE) for e in args.employee_email
    ]

    if args.dry_run:
        print(
            f"DRY RUN: would upsert firms/{args.firm_id} "
            f"(name={args.name!r}, status={args.status}, kind={args.kind}, "
            f"allowed_kits={kits})"
        )
    else:
        from backend.services.firms import upsert_firm

        try:
            result = upsert_firm(
                args.firm_id, args.name, args.contact, kits, args.kind,
                status=args.status,
            )
        except Exception as e:
            print(f"firm write FAILED: {e}", file=sys.stderr)
            return 2
        verb = "created" if result["created"] else "updated"
        print(f"{verb} firms/{args.firm_id} (allowed_kits: {len(kits)})")

    failures = 0
    for email, role in staff:
        if args.dry_run:
            # Read-only lookup so unknown addresses surface BEFORE the real
            # run -- the exit-1 partial-failure path should never be
            # discovered live for the first time.
            from firebase_admin import auth as fb_auth

            try:
                fb_auth.get_user_by_email(email)
                print(f"[would-stamp {role}] {email}")
            except fb_auth.UserNotFoundError:
                print(f"[unknown_email] {email}")
                failures += 1
            except Exception as e:
                print(f"[error] {email}: {e}")
                failures += 1
            continue
        status_str, detail = stamp_firm_claims(email, args.firm_id, role)
        if status_str == "stamped":
            print(f"[stamped {role}] {email} -> uid {detail}")
        elif status_str == "unknown_email":
            print(f"[unknown_email] {email}")
            failures += 1
        else:
            print(f"[error] {detail}")
            failures += 1

    if staff and not args.dry_run:
        print(
            "NOTE: stamped claims appear in decoded ID tokens only on the "
            "next token refresh (up to ~1h; force via sign-out/in or "
            "getIdToken(true))."
        )
    if failures:
        print(
            f"{failures} staff email(s) failed; fix and re-run (idempotent).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
