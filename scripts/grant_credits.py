"""Grant or adjust a firm's credit balance from the command line
(Epic 2 bead A2, epic polyglot-pdf-e374w).

WHY A CLI AT ALL, WHEN THE ADMIN CONSOLE IS COMING. The console's firm pages
(Epic 2 Track C) are several beads away, but the mint route starts debiting
credits the moment bead A3 lands. Without a way to PUT credits in, the first
funded firm cannot mint, and without a way to take them back out, a
mis-typed grant is unfixable. This script is that pair -- grant and adjust --
running through the SAME transactional helper the console will use, so
nothing here is a second implementation of the invariant that the console
would later have to be reconciled with.

    backend/.venv/Scripts/python.exe scripts/grant_credits.py grant acme-legal \\
        --credits 500 --project polyglot-demo-aa709 --dry-run

    ... grant acme-legal --credits 500 --type purchase --usd 249.00 \\
        --project polyglot-demo-aa709

    ... adjust acme-legal --credits -50 --reason "double-charged on 09-07" \\
        --project polyglot-demo-aa709

TWO SUBCOMMANDS, NOT ONE FLAG. `grant` writes a credit-ADDING entry
(promo_grant by default; purchase or subscription_grant with --type, which
then REQUIRE --usd) and refuses a negative --credits. `adjust` writes an
`adjustment`, takes either sign, and REQUIRES --reason. Splitting them this
way means the dangerous operation -- an arbitrary signed correction to a
paying firm's balance -- cannot be reached by fat-fingering a minus sign
into the everyday one; it needs a different verb AND a justification.

--dry-run PRINTS the entry it would write and touches Firestore only for the
read that shows the current balance. Every real run writes exactly ONE
ledger entry, updates the balance in the same transaction, and emits one
`ledger_export` structured log line (the income feed Epic 3's BigQuery sink
consumes) -- the helper does all three; this script only decides the
arguments.

--project is REQUIRED and pins the target DETERMINISTICALLY, for the reason
scripts/bootstrap_firm.py spells out at length: firebase_admin otherwise
resolves the project from the operator's gcloud ADC credential first, and
credits granted into the wrong project are invisible until someone goes
looking.

ACTOR. Entries carry `actor` so the ledger is attributable. This script
stamps `system:grant_credits_cli:<operator>` where <operator> is --actor if
given, else the OS username -- never blank, which the helper refuses
outright. It is deliberately distinguishable from a console grant's actor
(a real Firebase uid): "a human ran a script" and "a human clicked a button
behind the admin auth gate" are different provenance, and the ledger should
say which.

NO CHANNEL. Grants and adjustments carry channel=None, exactly like the
admin service's future grant route: an operator granting credits is not
acting on a channel, and the balance is not channel-partitioned
(backend/services/firms.py). Only the mint DEBIT (bead A3, on the public
backend) fills in a channel.

Credentials note: this runs under YOUR OWN gcloud ADC, not a Cloud Run
runtime SA. Your principal needs Firestore write access on the target
project.

Exit codes: 0 = the entry was written (or, with --dry-run, would have been);
1 = the ledger write was refused (unknown firm, insufficient balance, a
malformed entry); 2 = NOTHING was attempted: bad arguments, a dead or
mismatched project.

ASCII only (repo rule).
"""
import argparse
import getpass
import os
import sys
from pathlib import Path

# Make backend.* importable when run as python scripts/grant_credits.py from
# the repo root (or anywhere -- resolve relative to this file).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# The former prod project is DEAD and unreachable (maintainer, 2026-08-14).
# Same refusal scripts/bootstrap_firm.py carries, for the same reason: a
# stale muscle-memory invocation must not hang or half-write against it.
DEAD_PROJECTS = {"polyglot-forms-919f2"}

# The credit-ADDING types `grant` may write. Kept as literals rather than
# imported from backend.services.credit_ledger for the reason
# bootstrap_firm.py documents: any backend.* import at module scope would
# run before main()'s initialize_app(projectId=...) and could trip the bare
# initialize_app() in backend/services/auth.py. Pinned against the service's
# constants by test_grant_type_choices_match_service_constants so the drift
# fails CI rather than silently.
GRANT_TYPE_CHOICES = ["promo_grant", "purchase", "subscription_grant"]

# The subset of GRANT_TYPE_CHOICES that records money changing hands and so
# requires --usd. Mirrors credit_ledger.USD_REQUIRED_TYPES; pinned against it
# by test_usd_required_types_match_service_constants.
USD_REQUIRED_TYPES = {"purchase", "subscription_grant"}

ADJUSTMENT_TYPE = "adjustment"

ACTOR_PREFIX = "system:grant_credits_cli"


def _actor(explicit):
    """The `actor` string stamped onto the entry.

    Never blank (the helper refuses a blank actor): falls back to the OS
    username, and to "unknown" only if even that is unavailable -- an
    unattributable entry is still better than a refused correction, but it
    should look conspicuously unattributable in the console.
    """
    who = explicit
    if not who:
        try:
            who = getpass.getuser()
        except Exception:  # noqa: BLE001 -- no username on some hosts
            who = None
    return "{}:{}".format(ACTOR_PREFIX, who or "unknown")


def _build_parser():
    parser = argparse.ArgumentParser(
        description="Grant or adjust a firm's credit balance through the "
        "one transactional ledger helper."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def _common(p):
        p.add_argument("firm_id", help="firm slug, e.g. acme-legal")
        p.add_argument(
            "--credits", required=True, type=int,
            help="signed credit delta (grant: positive only; adjust: either "
            "sign, but never zero)",
        )
        p.add_argument(
            "--project", required=True,
            help="target Firebase project (deterministic: pre-initializes "
            "firebase_admin with this projectId AND asserts the resolved app "
            "project matches)",
        )
        p.add_argument(
            "--actor", default=None,
            help="who is running this (defaults to the OS username); stamped "
            "as {}:<actor> on the entry".format(ACTOR_PREFIX),
        )
        p.add_argument(
            "--dry-run", action="store_true",
            help="print the entry that would be written; read the balance "
            "but write nothing",
        )

    grant = sub.add_parser(
        "grant", help="add credits (promo_grant, purchase, subscription_grant)"
    )
    _common(grant)
    grant.add_argument(
        "--type", default=GRANT_TYPE_CHOICES[0], choices=GRANT_TYPE_CHOICES,
        help="entry type; purchase and subscription_grant REQUIRE --usd",
    )
    grant.add_argument(
        "--usd", type=float, default=None,
        help="the dollar amount paid (REQUIRED for purchase and "
        "subscription_grant, REFUSED for promo_grant -- a dollar figure on a "
        "promotional grant would be double-counted as income)",
    )
    grant.add_argument(
        "--reason", default=None, help="optional note stored on the entry"
    )

    adjust = sub.add_parser(
        "adjust", help="signed correction (requires --reason)"
    )
    _common(adjust)
    adjust.add_argument(
        "--reason", required=True,
        help="why this correction is being made -- REQUIRED (an adjustment "
        "is the one entry with no upstream event explaining it)",
    )
    return parser


def main(argv=None) -> int:
    # main(argv), like bootstrap_firm.main: tests drive the CLI directly with
    # no module-reload/argv-monkeypatch fixture.
    args = _build_parser().parse_args(argv)

    if args.project in DEAD_PROJECTS:
        print(
            "project {} is DEAD and unreachable (maintainer 2026-08-14, bd "
            "polyglot-pdf-je6iy); refusing.".format(args.project),
            file=sys.stderr,
        )
        return 2
    if args.credits == 0:
        # Caught here as well as in the helper so the operator sees it
        # without a Firestore round trip -- and so --dry-run refuses it too.
        print("--credits must be non-zero", file=sys.stderr)
        return 2

    if args.command == "grant":
        entry_type = args.type
        usd = args.usd
        if entry_type in USD_REQUIRED_TYPES and usd is None:
            print(
                "--usd is required for --type {} (it is the income figure "
                "the revenue view sums)".format(entry_type),
                file=sys.stderr,
            )
            return 2
        if entry_type not in USD_REQUIRED_TYPES and usd is not None:
            print(
                "--usd must not be passed for --type {} -- a dollar figure "
                "there would be double-counted as income".format(entry_type),
                file=sys.stderr,
            )
            return 2
        if args.credits < 0:
            print(
                "grant takes a POSITIVE --credits; use the adjust subcommand "
                "(which requires --reason) to remove credits",
                file=sys.stderr,
            )
            return 2
        reason = args.reason
    else:
        entry_type = ADJUSTMENT_TYPE
        usd = None
        reason = args.reason

    # Initialize firebase_admin with the target project BEFORE any backend.*
    # import: backend/services/auth.py calls a bare initialize_app() at
    # module import time, and whichever init runs first wins (the ordering
    # trap scripts/bootstrap_firm.py documents at length).
    import firebase_admin

    if not firebase_admin._apps:
        firebase_admin.initialize_app(options={"projectId": args.project})

    resolved = firebase_admin.get_app().project_id
    if resolved != args.project:
        print(
            "resolved firebase_admin project is {!r}, not {!r} -- refusing to "
            "write into the wrong project. (Was firebase_admin initialized "
            "before this script ran?)".format(resolved, args.project),
            file=sys.stderr,
        )
        return 2
    # Set only AFTER the assertion passes: the abort path must not leave the
    # process env pointed at a project this run refused to write into.
    os.environ["GOOGLE_CLOUD_PROJECT"] = args.project

    from backend.services import credit_ledger
    from backend.services.auth import get_db

    db = get_db()
    actor = _actor(args.actor)

    if args.dry_run:
        try:
            balance = credit_ledger.read_balance(db, args.firm_id)
        except Exception as e:  # noqa: BLE001 -- a read failure is not fatal here
            print("could not read the current balance: {}".format(e),
                  file=sys.stderr)
            balance = None
        if balance is None:
            print(
                "DRY RUN: firms/{} has NO document (or could not be read) -- "
                "a real run would be REFUSED".format(args.firm_id)
            )
        else:
            print("DRY RUN: firms/{} balance is {} credits".format(
                args.firm_id, balance))
            print("DRY RUN: would become {} credits".format(
                balance + args.credits))
        print(
            "DRY RUN: would append type={} amount={} usd_amount={} actor={} "
            "reason={!r} channel=None".format(
                entry_type, args.credits, usd, actor, reason)
        )
        print("DRY RUN: nothing was written.")
        return 0

    try:
        result = credit_ledger.append_entry(
            db,
            args.firm_id,
            entry_type=entry_type,
            amount=args.credits,
            actor=actor,
            usd_amount=usd,
            reason=reason,
            # channel stays None: an operator grant is not a channel action
            # (see the module docstring).
        )
    except Exception as e:  # noqa: BLE001 -- every refusal is exit 1 with the reason
        print("ledger write REFUSED: {}".format(e), file=sys.stderr)
        return 1

    print(
        "wrote firms/{}/ledger/{} type={} amount={} -> balance {} credits".format(
            args.firm_id, result["doc_id"], entry_type, args.credits,
            result["balance_credits"],
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
