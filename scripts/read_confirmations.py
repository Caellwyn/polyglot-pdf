"""Operational retrieval for the confirmation audit trail (bd polyglot-pdf-z2is).

The confirmation trail exists for liability protection: per-field records of
"the user confirmed this field, by this method, at this time" -- metadata only,
never values (docs/standards/confirmation-and-audit.md). This script is the
operational entry point for actually RETRIEVING a form-session's trail, e.g.
for a support question or a legal request. Without it, read_confirmation_log
had no caller outside tests and the durable trail was reachable only via the
Firestore console.

Usage (from the repo root, with the backend venv):

    # Deployed trail (Firestore; needs ADC for the project):
    CONFIRMATION_FIRESTORE_ENABLED=true GOOGLE_CLOUD_PROJECT=<project> \
        backend/.venv/Scripts/python.exe scripts/read_confirmations.py fss_abc123

    # Local dev trail (JSONL under CONFIRMATION_LOG_DIR):
    backend/.venv/Scripts/python.exe scripts/read_confirmations.py fss_abc123

Prints one JSON object per line (chronological), or a count summary with
--summary. Exit 0 with events found; exit 1 if the session has no events.
"""
import argparse
import json
import os
import sys
from pathlib import Path

# Make `backend.*` importable when run as `python scripts/read_confirmations.py`
# from the repo root (or anywhere -- resolve relative to this file).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Retrieve a form-session's confirmation audit trail."
    )
    parser.add_argument("form_session_id", help="e.g. fss_abc123_xyz789")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="print a per-event-type count instead of the full JSONL",
    )
    parser.add_argument(
        "--firestore",
        action="store_true",
        help="force the Firestore sink on for this read "
        "(same as CONFIRMATION_FIRESTORE_ENABLED=true)",
    )
    args = parser.parse_args()

    if args.firestore:
        os.environ["CONFIRMATION_FIRESTORE_ENABLED"] = "true"

    from backend.utils.confirmation_logger import (
        ConfirmationReadError,
        read_confirmation_log,
    )

    # strict=True: a FAILED Firestore query (perms/ADC/project) must never be
    # reported as "no events found" -- for a legal-retrieval tool those are
    # opposite answers (bd z2is fresh-eyes finding).
    try:
        events = read_confirmation_log(args.form_session_id, strict=True)
    except ConfirmationReadError as e:
        print(
            f"RETRIEVAL FAILED for {args.form_session_id}: could not query the "
            f"Firestore sink ({e}). This is NOT evidence the record is absent -- "
            "check ADC credentials, GOOGLE_CLOUD_PROJECT, and that the caller "
            "has roles/datastore.user.",
            file=sys.stderr,
        )
        return 2

    if not events:
        print(
            f"No confirmation events found for {args.form_session_id} "
            "(check CONFIRMATION_FIRESTORE_ENABLED / ADC project for deployed "
            "trails, or CONFIRMATION_LOG_DIR for local ones).",
            file=sys.stderr,
        )
        return 1

    if args.summary:
        counts: dict = {}
        for e in events:
            counts[e.get("event", "?")] = counts.get(e.get("event", "?"), 0) + 1
        print(json.dumps({
            "form_session_id": args.form_session_id,
            "total_events": len(events),
            "by_type": counts,
            "first": events[0].get("timestamp"),
            "last": events[-1].get("timestamp"),
        }, indent=2, default=str))
    else:
        for e in events:
            print(json.dumps(e, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
