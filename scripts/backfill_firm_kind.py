"""One-time migration: give every pre-A1 firm doc a kind + balance
(Epic 2 bead A6, epic polyglot-pdf-e374w).

WHY THIS EXISTS. Bead A1 added `kind` and `balance_credits` to
`firms/{firm_id}`, and `backend/services/firms.py:firm_kind()` treats a doc
with NO `kind` key as `"live"` (fail-closed: a mis-defaulted mock firm only
blocks staging testing, a mis-defaulted live firm mints for free). That
default is a SAFE STOPGAP, not a place to leave firm docs indefinitely -- an
admin console that lists firms wants a real, stored `kind` on every row, and
`CREDITS_ENFORCED` (bead A3) needs every firm to carry an actual
`balance_credits` before it is switched on, or a firm with no ledger history
enforces against a phantom 0 that was never written. This script performs
that one-time backfill.

    backend/.venv/Scripts/python.exe scripts/backfill_firm_kind.py \\
        --project polyglot-demo-aa709 --mock acme-dev,staging-test --dry-run

    ... --project polyglot-demo-aa709 --mock acme-dev,staging-test

    ... --project polyglot-demo-aa709 --mock acme-dev \\
        --seed-credits 500 --seed-reason "launch seed"

RULE: EVERY FIRM GETS `kind=live` UNLESS NAMED IN `--mock`. This is the
plan's explicit allowlist model, not a guess from firm metadata: an operator
names every firm that is a test/staging fixture; every firm NOT named is
treated as a real paying customer. That is the conservative direction (see
backend/services/firms.py's kind-defaulting docstring) -- a live firm
wrongly marked mock merely fails to bill; a mock firm wrongly marked live
mints for free once enforcement is on.

WHAT GETS WRITTEN, PER FIRM:
  - `kind`: set ONLY when the firm doc has no `kind` key yet. A firm that
    already carries a `kind` (from bootstrap_firm.py's now-required --kind,
    or a previous run of this script) is NEVER overwritten -- this script
    fills the GAP the pre-A1 window left, it does not re-litigate an
    operator's deliberate choice.
  - `balance_credits` / `balance_updated_at`: set ONLY when the firm doc has
    no `balance_credits` key yet (same reasoning: upsert_firm() already
    0-initializes this on every NEW firm since bead A1, so this only ever
    fires for docs older than that).
  - `plan` (bd polyglot-pdf-0euzk): set ONLY when the firm doc has no `plan`
    key yet, to backend/services/plans.py's DEFAULT_PLAN ({tier: "starter",
    monthly_credits: 35, rollover: True} -- the maintainer's 2026-09-14
    starting numbers, rollover flipped True by bd polyglot-pdf-hnlj3,
    2026-09-15: "credits roll over -- no real reason not to"). Independent
    of the kind/balance backfill above: a
    firm created AFTER admin_backend/routes/firm_routes.py's create route
    started writing a default plan already has one and is skipped for this
    step alone, while an OLDER firm predating that route gets caught up
    here regardless of whether its kind/balance needed backfilling too.
  - an optional ONE-TIME `promo_grant` ledger entry via
    `--seed-credits N`, written through the SAME transactional helper
    (backend/services/credit_ledger.py:append_entry) the console and
    scripts/grant_credits.py use -- never a second balance writer. Applied
    to EVERY firm this run touches (mock and live alike): the plan's exit
    criterion is "a funded firm exists to debit", and staging needs credits
    on its mock firms to test the mint path before enforcement flips on
    anywhere.

IDEMPOTENT BY CONSTRUCTION, NOT BY A MARKER FIELD. A re-run:
  - skips `kind` and `balance_credits`/`balance_updated_at` writes on any
    firm that already has them (the gap that made this script necessary is,
    by definition, gone once it has run once);
  - --seed-credits is NOT re-applied on a second run for a firm that
    already received THIS script's seed grant: the ledger entry emitted by
    this script carries `reason="backfill_firm_kind seed <run marker>"`
    is impractical to de-duplicate on (grant amounts can legitimately
    repeat), so instead this script's seed step is scoped to firms it just
    gave a KIND to on THIS invocation (i.e. firms that had no `kind` key
    before this run). A firm that already had a stored `kind` -- meaning an
    earlier run of this script, or a manually-bootstrapped firm -- is
    skipped for the seed step too, even the FIRST time this script runs
    against it. This makes a second run of the exact same command a true
    no-op: nothing to backfill, nothing (new) to seed.

--dry-run prints, per firm, what WOULD change (kind, balance init, seed
grant) and writes nothing.

--project is REQUIRED and pins the target deterministically -- the same
reasoning scripts/bootstrap_firm.py and scripts/grant_credits.py document at
length: firebase_admin otherwise resolves the project from the operator's
gcloud ADC credential first, and a migration run into the wrong project is
invisible until someone goes looking.

Credentials note: this runs under YOUR OWN gcloud ADC, not a Cloud Run
runtime SA. Your principal needs Firestore read+write on the target project.

Exit codes: 0 = the sweep completed (every firm backfilled or already
current; with --dry-run, nothing was written); 1 = one or more firms failed
to write (named on stderr) -- fix and re-run, re-runs are idempotent;
2 = NOTHING was attempted: bad arguments, a dead or mismatched project.

ASCII only (repo rule).
"""
import argparse
import os
import sys
from pathlib import Path

# Make backend.* importable when run as python scripts/backfill_firm_kind.py
# from the repo root (or anywhere -- resolve relative to this file).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# The former prod project is DEAD and unreachable (maintainer, 2026-08-14).
# Same refusal scripts/bootstrap_firm.py and scripts/grant_credits.py carry,
# for the same reason: a stale muscle-memory invocation must not hang or
# half-write against it.
DEAD_PROJECTS = {"polyglot-forms-919f2"}

# Kept as literals (NOT imported from backend.services.firms) deliberately:
# any backend.* import at module scope would run before main()'s
# initialize_app(projectId=...) and could trip the bare initialize_app() in
# backend/services/auth.py -- the exact ordering trap bootstrap_firm.py's
# main() documents. Pinned against the service's constants by
# test_kind_choices_match_service_constants so drift fails CI instead of
# silently.
KIND_MOCK = "mock"
KIND_LIVE = "live"

# The ledger entry type this script's --seed-credits writes. Promotional --
# not a purchase or subscription -- because a migration seed is not money
# changing hands (mirrors scripts/grant_credits.py's default `grant` type
# and credit_ledger.USD_REQUIRED_TYPES' exclusion of promo_grant).
SEED_ENTRY_TYPE = "promo_grant"

ACTOR_PREFIX = "system:backfill_firm_kind"


def _actor() -> str:
    """Never blank -- see scripts/grant_credits.py's `_actor()` for the
    identical reasoning. This script has no --actor flag (it is a sweep,
    not a per-firm operator action), so it always stamps the OS username,
    falling back to "unknown"."""
    import getpass

    try:
        who = getpass.getuser().strip()
    except Exception:  # noqa: BLE001 -- no username on some hosts
        who = None
    return "{}:{}".format(ACTOR_PREFIX, who or "unknown")


def _parse_mock_allowlist(raw: str | None) -> set[str]:
    """--mock is a comma-separated list of firm_ids; blank entries and
    surrounding whitespace are dropped (mirrors bootstrap_firm.py's
    --allowed-kits parsing style). No --mock at all means the allowlist is
    empty -- every firm this run touches becomes `live`."""
    if not raw:
        return set()
    return {piece.strip() for piece in raw.split(",") if piece.strip()}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill kind + balance_credits on every pre-A1 firm "
        "doc; every firm gets kind=live unless named in --mock."
    )
    parser.add_argument(
        "--project", required=True,
        help="target Firebase project (deterministic: pre-initializes "
        "firebase_admin with this projectId AND asserts the resolved app "
        "project matches)",
    )
    parser.add_argument(
        "--mock", default=None,
        help="comma-separated firm_ids to mark kind=mock; every OTHER firm "
        "this run touches becomes kind=live",
    )
    parser.add_argument(
        "--seed-credits", type=int, default=None,
        help="if given, grant this many credits (must be positive) as a "
        "promo_grant to every firm THIS RUN gives a kind to (skips firms "
        "that already had a stored kind)",
    )
    parser.add_argument(
        "--seed-reason", default=None,
        help="optional note stored on the seed grant's ledger entry",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="print what would change per firm; write nothing",
    )
    return parser


def main(argv=None) -> int:
    # main(argv), like bootstrap_firm.main and grant_credits.main: tests
    # drive the CLI directly with no module-reload/argv-monkeypatch fixture.
    args = _build_parser().parse_args(argv)

    if args.project in DEAD_PROJECTS:
        print(
            "project {} is DEAD and unreachable (maintainer 2026-08-14, bd "
            "polyglot-pdf-je6iy); refusing.".format(args.project),
            file=sys.stderr,
        )
        return 2
    if args.seed_credits is not None and args.seed_credits <= 0:
        print("--seed-credits must be a positive int", file=sys.stderr)
        return 2

    mock_allowlist = _parse_mock_allowlist(args.mock)

    # Initialize firebase_admin with the target project BEFORE any backend.*
    # import: backend/services/auth.py calls a bare initialize_app() at
    # module import time, and whichever init runs first wins (the ordering
    # trap bootstrap_firm.py's main() documents at length).
    import firebase_admin

    if not firebase_admin._apps:
        firebase_admin.initialize_app(options={"projectId": args.project})

    resolved = firebase_admin.get_app().project_id
    if resolved != args.project:
        print(
            "resolved firebase_admin project is {!r}, not {!r} -- refusing "
            "to write into the wrong project. (Was firebase_admin "
            "initialized before this script ran?)".format(
                resolved, args.project),
            file=sys.stderr,
        )
        return 2
    # Set only AFTER the assertion passes: the abort path must not leave the
    # process env pointed at a project this run refused to write into.
    os.environ["GOOGLE_CLOUD_PROJECT"] = args.project

    from firebase_admin import firestore

    from backend.services import credit_ledger, plans
    from backend.services.auth import get_db

    db = get_db()
    actor = _actor()

    failures: list[str] = []
    touched = 0
    seeded = 0

    for snap in db.collection("firms").stream():
        firm_id = snap.id
        firm = snap.to_dict() or {}
        had_kind = "kind" in firm
        had_balance = "balance_credits" in firm
        had_plan = "plan" in firm

        target_kind = KIND_MOCK if firm_id in mock_allowlist else KIND_LIVE

        payload: dict = {}
        if not had_kind:
            payload["kind"] = target_kind
        if not had_balance:
            # Mirrors upsert_firm()'s first-create payload
            # (backend/services/firms.py): balance_credits and
            # balance_updated_at are written together, never one without
            # the other, so a backfilled firm's doc shape matches a
            # normally-created firm's exactly.
            payload["balance_credits"] = 0
            payload["balance_updated_at"] = firestore.SERVER_TIMESTAMP
        if not had_plan:
            # dict(...) copies plans.DEFAULT_PLAN rather than writing the
            # same mutable module-level object into every touched firm doc.
            payload["plan"] = dict(plans.DEFAULT_PLAN)

        # Seed grant is scoped to firms this run is FIRST assigning a kind
        # to -- see the module docstring's idempotency section. A firm that
        # already had a stored kind is never seeded by this script, even on
        # its very first run against that firm (an operator who bootstrapped
        # or previously backfilled it made that call already; a second,
        # separate credit decision belongs to grant_credits.py, not a
        # silent re-seed here).
        will_seed = (
            args.seed_credits is not None and not had_kind
        )

        if not payload and not will_seed:
            continue  # already fully current; true no-op re-run

        touched += 1

        if args.dry_run:
            if payload:
                print(
                    "DRY RUN: firms/{} would get {}".format(firm_id, payload)
                )
            if will_seed:
                print(
                    "DRY RUN: firms/{} would be granted {} credits "
                    "(promo_grant)".format(firm_id, args.seed_credits)
                )
            continue

        try:
            if payload:
                snap.reference.set(payload, merge=True)
                print("wrote firms/{}: {}".format(firm_id, payload))
            if will_seed:
                result = credit_ledger.append_entry(
                    db,
                    firm_id,
                    entry_type=SEED_ENTRY_TYPE,
                    amount=args.seed_credits,
                    actor=actor,
                    reason=args.seed_reason,
                    # channel is explicitly None: a migration seed is not a
                    # channel action, exactly like an operator grant
                    # (scripts/grant_credits.py's module docstring).
                    channel=None,
                )
                seeded += 1
                print(
                    "seeded firms/{}/ledger/{}: +{} credits -> balance {} "
                    "credits".format(
                        firm_id, result["doc_id"], args.seed_credits,
                        result["balance_credits"],
                    )
                )
        except Exception as e:  # noqa: BLE001 -- one bad firm must not abort the sweep
            failures.append(firm_id)
            print(
                "FAILED firms/{}: {}".format(firm_id, e), file=sys.stderr
            )

    if args.dry_run:
        print("DRY RUN: {} firm(s) would be touched; nothing was written.".format(
            touched))
        return 0

    print(
        "backfill complete: {} firm(s) touched, {} seeded, {} failure(s)".format(
            touched, seeded, len(failures)
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
