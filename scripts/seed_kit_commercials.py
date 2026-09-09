"""One-time migration: seed the `kits/{kit_id}` commercial doc for every kit
on disk (Epic 2 bead A6, epic polyglot-pdf-e374w).

WHY THIS EXISTS. The mint route (bead A3) and the admin console's kit
commercials page (Track B/C) both read `kits/{kit_id}` for `credit_cost` and
`burn_cap_usd` (docs/sprint_22_admin-console_plan.md's "Migration" section;
doc shape in docs/components/auth.md). Nothing writes that collection today
except the future `PUT /admin/kits/{kit_id}/commercial` route -- so before
that route exists, and before `CREDITS_ENFORCED` can be switched on for any
channel, every kit needs a real commercial doc. This script performs that
one-time seed from the kits already on disk.

    backend/.venv/Scripts/python.exe scripts/seed_kit_commercials.py \\
        --project polyglot-demo-aa709 --default-credit-cost 5 --dry-run

    ... --project polyglot-demo-aa709 --default-credit-cost 5

    ... --project polyglot-demo-aa709 --default-credit-cost 5 \\
        --kits-root form-kits --actor jsmith

FOR EVERY KIT IN THE STORE: this script walks `--kits-root` (default the
repo's `form-kits/` directory, matching scripts/translation_lint.py's CLI
convention) rather than going through the async `FormKitStore` interface
(backend/services/form_kits.py) -- a plain filesystem walk needs no event
loop, no `backend.config.get_settings()` FORM_KITS_MODE resolution, and no
GCS credentials, and every kit this migration needs to see (published,
draft, or otherwise) lives in that directory on the operator's checkout. A
kit directory with no readable `metadata.json` is skipped with a warning,
not aborted -- one malformed kit must not block seeding every other one.

burn_cap_usd: read from the kit's OWN `metadata.json` key
`link_cost_ceiling_usd` (backend/services/link_budget.py's
KIT_COST_CEILING_KEY) where present and a valid positive number -- today
that is w7 and i-90 at $3 each (bd polyglot-pdf-gob8l) -- else
`--default-burn-cap-usd` (falls back again to
link_budget.DEFAULT_LINK_COST_CEILING_USD, the same $10 the runtime
resolves when nothing else is set, so an un-overridden kit's ceiling matches
what a pre-A6 link would already have gotten). THE METADATA KEY IS LEFT IN
PLACE -- vestigial after this bead (the plan is explicit: "stop reading it,
do not delete it from published kits"). This script only READS it; nothing
here mutates any kit's metadata.json.

credit_cost: from a REQUIRED `--default-credit-cost N` (positive int). There
is no per-kit override for it today (no pricing signal exists to derive one
per-form) -- every kit gets the same default; the admin console's future
PUT route is where a real per-kit price gets set.

display: `{"label": <kit's metadata.json "label", or the kit_id if absent>}`
-- the console's kit commercials page needs a human name to show and
metadata.json is the only source of one today.

IDEMPOTENT, RE-RUN-SAFE, BUT NOT A NO-OP ON A CHANGED DEFAULT. A re-run
overwrites `credit_cost`, `burn_cap_usd`, and `display` on every kit with
whatever this invocation's flags resolve to -- this is a SEED script for the
pre-console window, not a "set once" migration: an operator changing the
`--default-credit-cost` before the console exists needs the re-run to take
effect, and the plan gives the console (Track B) sole ownership of
per-kit pricing after that route ships. Two consecutive runs with the SAME
flags are a true no-op in effect (same doc written twice), but the doc is
still re-written -- there is no marker field to skip. `updated_by`/
`updated_at` are stamped on every write for exactly this reason: the console
can tell "seeded by this script" from "priced by an admin" by actor alone.

--dry-run prints, per kit, the doc it would write and touches no Firestore
write (metadata.json reads are local filesystem, not Firestore).

--project is REQUIRED and pins the target deterministically -- the same
reasoning scripts/bootstrap_firm.py, scripts/grant_credits.py and
scripts/backfill_firm_kind.py document at length.

Credentials note: this runs under YOUR OWN gcloud ADC, not a Cloud Run
runtime SA. Your principal needs Firestore write access on the target
project.

Exit codes: 0 = every kit was seeded (or, with --dry-run, would be); 1 = one
or more kits failed to write (named on stderr) -- fix and re-run, re-runs
are idempotent; 2 = NOTHING was attempted: bad arguments (including the
missing required --default-credit-cost), a dead or mismatched project, or
no kits found under --kits-root.

ASCII only (repo rule).
"""
import argparse
import json
import os
import sys
from pathlib import Path

# Make backend.* importable when run as python scripts/seed_kit_commercials.py
# from the repo root (or anywhere -- resolve relative to this file).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# The former prod project is DEAD and unreachable (maintainer, 2026-08-14).
# Same refusal every other migration/operator script in this repo carries.
DEAD_PROJECTS = {"polyglot-forms-919f2"}

# The metadata.json key a kit uses to override the global spend ceiling
# (backend/services/link_budget.py's KIT_COST_CEILING_KEY). Kept as a
# literal, not an import, for the same module-load-ordering reason every
# sibling script in this repo documents: pinned against the service's
# constant by test_kit_cost_ceiling_key_matches_link_budget_constant.
KIT_COST_CEILING_KEY = "link_cost_ceiling_usd"

# link_budget.DEFAULT_LINK_COST_CEILING_USD, mirrored here (not imported) for
# the same reason. Pinned against the service's constant by
# test_default_burn_cap_matches_link_budget_default.
DEFAULT_BURN_CAP_USD = 10.0

FIRESTORE_COLLECTION = "kits"

ACTOR_PREFIX = "system:seed_kit_commercials_cli"


def _actor(explicit: str | None) -> str:
    """Never blank -- see scripts/grant_credits.py's `_actor()` for the
    identical reasoning and the identical stripped-operator-segment
    concern."""
    import getpass

    who = explicit.strip() if isinstance(explicit, str) else explicit
    if not who:
        try:
            who = getpass.getuser().strip()
        except Exception:  # noqa: BLE001 -- no username on some hosts
            who = None
    return "{}:{}".format(ACTOR_PREFIX, who or "unknown")


def _positive_number(raw, fallback):
    """Parse a positive, finite number from kit metadata; anything else
    (missing, wrong type, non-positive, NaN/inf, bool) falls back. Mirrors
    backend/services/link_budget.py's _positive_float defensive parsing --
    the plan requires a bad kit-metadata edit to never remove a form's
    ceiling, which means this script's fallback direction must match the
    runtime's."""
    if isinstance(raw, bool):
        return fallback
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return fallback
    if value <= 0 or value != value or value == float("inf"):
        return fallback
    return value


def _iter_kit_dirs(kits_root: Path):
    """Every immediate subdirectory of kits_root that looks like a kit (has
    a metadata.json, readable or not) -- sorted for deterministic output.
    Directories with no metadata.json at all (e.g. `_translation/`, a
    stray non-kit folder) are silently skipped, matching
    scripts/translation_lint.py's glossary-adjacent-directory handling.
    """
    if not kits_root.is_dir():
        return []
    dirs = [
        p for p in sorted(kits_root.iterdir())
        if p.is_dir() and (p / "metadata.json").exists()
    ]
    return dirs


def _load_metadata(kit_dir: Path) -> dict | None:
    """The kit's metadata.json as a dict, or None on any read/parse failure.

    A malformed metadata.json must not abort the whole sweep -- mirrors
    backend/services/form_kits.py's LocalFormKitStore.load_metadata, which
    degrades to None for exactly this reason (a broken doc must not take
    down a catalogue listing that reads metadata per kit).
    """
    path = kit_dir / "metadata.json"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Seed kits/{kit_id} commercial docs for every kit under "
        "--kits-root."
    )
    parser.add_argument(
        "--project", required=True,
        help="target Firebase project (deterministic: pre-initializes "
        "firebase_admin with this projectId AND asserts the resolved app "
        "project matches)",
    )
    parser.add_argument(
        "--default-credit-cost", required=True, type=int,
        help="credit_cost for every kit (REQUIRED -- no pricing signal "
        "exists to derive one per-kit; must be a positive int)",
    )
    parser.add_argument(
        "--default-burn-cap-usd", type=float, default=DEFAULT_BURN_CAP_USD,
        help="burn_cap_usd fallback for a kit with no (or an invalid) "
        "link_cost_ceiling_usd in its metadata.json (default: {}, matching "
        "the runtime default)".format(DEFAULT_BURN_CAP_USD),
    )
    parser.add_argument(
        "--kits-root", type=Path, default=_REPO_ROOT / "form-kits",
        help="form-kits directory (default: the repo's form-kits/)",
    )
    parser.add_argument(
        "--actor", default=None,
        help="who is running this (defaults to the OS username); stamped "
        "as {}:<actor> on updated_by".format(ACTOR_PREFIX),
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="print the doc that would be written per kit; write nothing",
    )
    return parser


def main(argv=None) -> int:
    # main(argv), like the sibling migration/operator scripts: tests drive
    # the CLI directly with no module-reload/argv-monkeypatch fixture.
    args = _build_parser().parse_args(argv)

    if args.project in DEAD_PROJECTS:
        print(
            "project {} is DEAD and unreachable (maintainer 2026-08-14, bd "
            "polyglot-pdf-je6iy); refusing.".format(args.project),
            file=sys.stderr,
        )
        return 2
    if args.default_credit_cost <= 0:
        print("--default-credit-cost must be a positive int", file=sys.stderr)
        return 2
    if args.default_burn_cap_usd <= 0:
        print("--default-burn-cap-usd must be a positive number", file=sys.stderr)
        return 2

    kit_dirs = _iter_kit_dirs(args.kits_root)
    if not kit_dirs:
        print(
            "no kits found under {} (nothing to seed)".format(args.kits_root),
            file=sys.stderr,
        )
        return 2

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

    from backend.services.auth import get_db

    db = get_db()
    actor = _actor(args.actor)

    failures: list[str] = []
    seeded = 0

    for kit_dir in kit_dirs:
        kit_id = kit_dir.name
        metadata = _load_metadata(kit_dir)
        if metadata is None:
            print(
                "SKIPPED {}: metadata.json missing or unparseable".format(
                    kit_id),
                file=sys.stderr,
            )
            continue

        burn_cap_usd = _positive_number(
            metadata.get(KIT_COST_CEILING_KEY), args.default_burn_cap_usd
        )
        label = metadata.get("label")
        if not isinstance(label, str) or not label.strip():
            label = kit_id

        doc = {
            "credit_cost": args.default_credit_cost,
            "burn_cap_usd": burn_cap_usd,
            "display": {"label": label},
            "updated_by": actor,
        }

        if args.dry_run:
            print("DRY RUN: kits/{} would be set to {}".format(kit_id, doc))
            continue

        try:
            db.collection(FIRESTORE_COLLECTION).document(kit_id).set(
                {**doc, "updated_at": firestore.SERVER_TIMESTAMP}
            )
            seeded += 1
            print("wrote kits/{}: {}".format(kit_id, doc))
        except Exception as e:  # noqa: BLE001 -- one bad kit must not abort the sweep
            failures.append(kit_id)
            print("FAILED kits/{}: {}".format(kit_id, e), file=sys.stderr)

    if args.dry_run:
        print(
            "DRY RUN: {} kit(s) would be seeded; nothing was written.".format(
                len(kit_dirs))
        )
        return 0

    print(
        "seed complete: {} kit(s) seeded, {} failure(s)".format(
            seeded, len(failures)
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
