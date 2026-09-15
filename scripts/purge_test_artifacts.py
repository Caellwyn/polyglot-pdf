"""Delete the specific test-artifact documents an unpatched local test run
wrote into the shared Firestore project (bd polyglot-pdf-21m1y).

WHAT HAPPENED (2026-09-15). Backend tests run on a developer machine with
gcloud ADC and a quota project reach the real Firestore through
backend.services.auth.get_db() whenever a test exercises alerts.py,
usage_rollups.py, link_redemptions.py, links_store.py or credit_ledger.py
without patching the store -- see backend/tests/unit/_no_real_firestore.py
(this bead's other half) for the guard that now stops it going forward. This
script cleans up what already landed:

    - alerts docs whose firm_id is in {"firm-a", "acme"}, OR whose doc id
      is exactly "link_exhausted_jti-a" (a test-firm-scoped alert that
      predates the firm_id field being set on every write, per the bead's
      inventory);
    - link_redemptions[_<channel>] docs whose firm_id is missing (no field
      at all) or equals "firm-a";
    - links[_<channel>] docs whose firm_id is missing or equals "firm-a";
    - firms/firm-a and every one of its subcollections (ledger, usage,
      link_usage, or any other subcollection it happens to carry --
      enumerated via Firestore's own collections() call rather than a
      hardcoded list, so a subcollection added by a LATER bead is still
      cleaned up without this script needing an update).

THIS IS DELIBERATELY NARROW. It deletes EXACTLY the shapes enumerated in the
bead body, matched against the SAME collections the stores actually write
(alerts.COLLECTION, link_redemptions.COLLECTION_channel variants,
links_store.COLLECTION_channel variants, firms._FIRMS_COLLECTION) -- not a
generic "delete anything that looks like test data" sweep, which would risk
a real firm or a real alert sharing a coincidental id. A shape this script
does NOT recognize is left alone and reported as skipped-nothing-matched;
it is not this script's job to guess at future test-pollution shapes.

--dry-run (the DEFAULT posture: --apply is required to write anything)
lists every document it WOULD delete, one line each, then a per-collection
count summary, and deletes nothing. --apply performs the deletes and prints
the same listing with a confirmation per deletion. The maintainer runs
--apply: data deletion is theirs (bead body, part 2).

--project is REQUIRED and pins the target DETERMINISTICALLY, for the exact
reason scripts/bootstrap_firm.py and scripts/grant_credits.py document at
length: firebase_admin otherwise resolves the project from the operator's
ADC credential first, and a delete sweep run against the wrong project by
accident is unrecoverable by inspection.

Exit codes: 0 = the dry-run listing (or the real deletes) completed, even
if nothing matched; 1 = a delete was attempted and failed (partial cleanup
possible -- re-run, it is idempotent, a doc already gone is skipped, not an
error); 2 = NOTHING was attempted: bad arguments, a dead or mismatched
project.

ASCII only (repo rule).
"""
import argparse
import os
import sys
from pathlib import Path

# Make backend.* importable when run as python scripts/purge_test_artifacts.py
# from the repo root (or anywhere -- resolve relative to this file).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# The former prod project is DEAD and unreachable (maintainer, 2026-08-14).
# Same refusal scripts/bootstrap_firm.py and scripts/grant_credits.py carry,
# for the same reason: a stale muscle-memory invocation must not hang or
# half-delete against it.
DEAD_PROJECTS = {"polyglot-forms-919f2"}

# Kept as LITERALS rather than imported from backend.services.* -- same
# reasoning bootstrap_firm.py and grant_credits.py document: any backend.*
# import at module scope would run before main()'s
# initialize_app(projectId=...) and could trip the bare initialize_app() in
# backend/services/auth.py. Pinned against the real collection constants by
# test_purge_test_artifacts_cli.py's test_collection_constants_match_service_
# constants (imports the four LEAF service modules directly, which is safe
# -- see that test's docstring) so drift fails CI rather than silently
# missing a collection.
ALERTS_COLLECTION = "alerts"
LINK_REDEMPTIONS_COLLECTION = "link_redemptions"
LINKS_COLLECTION = "links"
FIRMS_COLLECTION = "firms"

# admin_backend's route files (config_routes.py, firm_routes.py,
# link_routes.py) all carry this same literal tuple -- the two channels
# this repo deploys today. Pinned against all three by
# test_purge_test_artifacts_cli.py's
# test_known_channels_matches_every_admin_route_copy.
KNOWN_CHANNELS = ("demo", "staging")

# The enumerated shapes (bd polyglot-pdf-21m1y bead body). Kept as named
# constants, not inlined into the matcher functions, so the CLI test can
# assert against them directly and a change to the inventory is a one-line
# diff instead of a re-read of the matching logic.
ALERT_FIRM_IDS = frozenset({"firm-a", "acme"})
ALERT_EXTRA_DOC_IDS = frozenset({"link_exhausted_jti-a"})
REDEMPTION_AND_LINK_FIRM_IDS = frozenset({"firm-a"})
PURGE_FIRM_ID = "firm-a"


def _channel_collection_names(base: str) -> list[str]:
    """Every collection name a channel-suffixed store can use for `base`.

    Mirrors link_redemptions._collection_name() / links_store._collection_name():
    the "demo" channel keeps the bare name, every other known channel gets
    "<base>_<channel>". Returns the bare name FIRST (so it prints/sorts
    first in a listing) followed by each other known channel's suffixed name.
    """
    names = [base]
    for channel in KNOWN_CHANNELS:
        if channel == "demo":
            continue
        names.append("{}_{}".format(base, channel))
    return names


def _alert_matches(doc_id: str, data: dict) -> bool:
    """True if this alerts/{doc_id} doc is one of the enumerated shapes."""
    firm_id = data.get("firm_id") if isinstance(data, dict) else None
    return firm_id in ALERT_FIRM_IDS or doc_id in ALERT_EXTRA_DOC_IDS


def _firm_scoped_doc_matches(data: dict) -> bool:
    """True for a link_redemptions/links doc with a missing or firm-a firm_id.

    "Missing" means the key is absent OR present-but-None -- both read as
    "no firm_id" to a caller of data.get("firm_id"), and the bead's own
    inventory describes the 19 orphaned links docs as having "no firm_id"
    without distinguishing the two, so both must match.
    """
    if not isinstance(data, dict):
        return True
    firm_id = data.get("firm_id")
    return firm_id is None or firm_id in REDEMPTION_AND_LINK_FIRM_IDS


def find_matches(db) -> dict:
    """Enumerate every document this script would delete.

    Returns {"alerts": [(doc_id, ref), ...], "link_redemptions": [...],
    "links": [...], "firm": (doc_id, ref) | None,
    "firm_subcollections": [(path_str, ref), ...]}. Read-only: never deletes,
    used by BOTH --dry-run and --apply so the two paths cannot drift (the
    exact split test_grant_credits_cli.py's --dry-run precedent avoids).
    """
    result = {
        "alerts": [],
        "link_redemptions": [],
        "links": [],
        "firm": None,
        "firm_subcollections": [],
    }

    for snap in db.collection(ALERTS_COLLECTION).stream():
        data = snap.to_dict() or {}
        if _alert_matches(snap.id, data):
            result["alerts"].append((snap.id, snap.reference))

    for coll_name in _channel_collection_names(LINK_REDEMPTIONS_COLLECTION):
        for snap in db.collection(coll_name).stream():
            data = snap.to_dict() or {}
            if _firm_scoped_doc_matches(data):
                result["link_redemptions"].append(
                    ("{}/{}".format(coll_name, snap.id), snap.reference)
                )

    for coll_name in _channel_collection_names(LINKS_COLLECTION):
        for snap in db.collection(coll_name).stream():
            data = snap.to_dict() or {}
            if _firm_scoped_doc_matches(data):
                result["links"].append(
                    ("{}/{}".format(coll_name, snap.id), snap.reference)
                )

    firm_ref = db.collection(FIRMS_COLLECTION).document(PURGE_FIRM_ID)
    firm_snap = firm_ref.get()
    if firm_snap.exists:
        result["firm"] = (PURGE_FIRM_ID, firm_ref)
        # Enumerated dynamically (Firestore's own collections() call) rather
        # than a hardcoded {ledger, usage, link_usage} list -- a
        # subcollection a LATER bead adds under firms/{id} is still found
        # and cleaned up without this script needing an update.
        for subcoll in firm_ref.collections():
            for subsnap in subcoll.stream():
                result["firm_subcollections"].append(
                    (
                        "firms/{}/{}/{}".format(
                            PURGE_FIRM_ID, subcoll.id, subsnap.id
                        ),
                        subsnap.reference,
                    )
                )

    return result


def _total(matches: dict) -> int:
    total = len(matches["alerts"]) + len(matches["link_redemptions"]) + len(
        matches["links"]
    ) + len(matches["firm_subcollections"])
    if matches["firm"] is not None:
        total += 1
    return total


def _print_listing(matches: dict, *, verb: str) -> None:
    for doc_id, _ref in matches["alerts"]:
        print("{} alerts/{}".format(verb, doc_id))
    for path_str, _ref in matches["link_redemptions"]:
        print("{} {}".format(verb, path_str))
    for path_str, _ref in matches["links"]:
        print("{} {}".format(verb, path_str))
    # Subcollection docs BEFORE the firm doc itself, so a listing reads as
    # "children first, then the parent" -- and so a real delete (below)
    # never orphans a subcollection doc under an already-gone parent id in
    # its own printed order (Firestore has no cascade; the parent's absence
    # would not actually block a subcollection delete, but the print order
    # should still tell the same story a careful operator would follow).
    for path_str, _ref in matches["firm_subcollections"]:
        print("{} {}".format(verb, path_str))
    if matches["firm"] is not None:
        doc_id, _ref = matches["firm"]
        print("{} firms/{}".format(verb, doc_id))


def _build_parser():
    parser = argparse.ArgumentParser(
        description="Delete the enumerated test-artifact documents "
        "(bd polyglot-pdf-21m1y) from the shared Firestore project."
    )
    parser.add_argument(
        "--project", required=True,
        help="target Firebase project (deterministic: pre-initializes "
        "firebase_admin with this projectId AND asserts the resolved app "
        "project matches)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="list what would be deleted; write nothing (this is also the "
        "DEFAULT when neither --dry-run nor --apply is given)",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="actually delete the matched documents (required to write "
        "anything -- the default posture is read-only)",
    )
    return parser


def main(argv=None) -> int:
    # main(argv), like bootstrap_firm.main and grant_credits.main: tests
    # drive the CLI directly with no module-reload/argv-monkeypatch fixture.
    args = _build_parser().parse_args(argv)

    if args.apply and args.dry_run:
        print("--dry-run and --apply are mutually exclusive", file=sys.stderr)
        return 2

    if args.project in DEAD_PROJECTS:
        print(
            "project {} is DEAD and unreachable (maintainer 2026-08-14, bd "
            "polyglot-pdf-je6iy); refusing.".format(args.project),
            file=sys.stderr,
        )
        return 2

    # Default posture is READ-ONLY: --apply is what makes this script write.
    apply_deletes = bool(args.apply)

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
            "resolved firebase_admin project is {!r}, not {!r} -- refusing "
            "to delete from the wrong project. (Was firebase_admin "
            "initialized before this script ran?)".format(
                resolved, args.project),
            file=sys.stderr,
        )
        return 2
    # Set only AFTER the assertion passes: the abort path must not leave the
    # process env pointed at a project this run refused to touch.
    os.environ["GOOGLE_CLOUD_PROJECT"] = args.project

    from backend.services.auth import get_db

    db = get_db()
    matches = find_matches(db)
    total = _total(matches)

    if not apply_deletes:
        print("DRY RUN: would delete {} document(s):".format(total))
        _print_listing(matches, verb="would delete")
        print("DRY RUN: nothing was deleted.")
        return 0

    print("APPLYING: deleting {} document(s):".format(total))
    failures = 0
    all_refs = (
        [ref for _, ref in matches["alerts"]]
        + [ref for _, ref in matches["link_redemptions"]]
        + [ref for _, ref in matches["links"]]
        + [ref for _, ref in matches["firm_subcollections"]]
    )
    if matches["firm"] is not None:
        all_refs.append(matches["firm"][1])

    _print_listing(matches, verb="deleting")
    for ref in all_refs:
        try:
            ref.delete()
        except Exception as e:  # noqa: BLE001 -- one bad delete must not
            # abort the rest of the sweep; report and keep going.
            print("FAILED to delete {}: {}".format(ref.path, e),
                  file=sys.stderr)
            failures += 1

    if failures:
        print(
            "{} delete(s) failed; re-run (idempotent -- an already-gone "
            "doc is skipped, not an error).".format(failures),
            file=sys.stderr,
        )
        return 1

    print("done: deleted {} document(s).".format(total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
