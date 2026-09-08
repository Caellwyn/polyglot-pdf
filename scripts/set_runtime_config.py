#!/usr/bin/env python3
"""Read/set a runtime config key in app_config/{channel} (bd polyglot-pdf-bg313).

Operator CLI for backend.services.runtime_config's Firestore-backed settings,
so criterion 3 (flipping LINK_MINTING_ENABLED on staging changes /api/links/mint
with no redeploy) is verifiable BEFORE the admin console's own config route
ships (bd polyglot-pdf-li9x0). The console route is the one with an audit
trail; this script has none -- it exists to unblock verification, not to
replace the console as the operational path once it exists.

Usage (from the repo root, with the backend venv):

    backend/.venv/Scripts/python.exe scripts/set_runtime_config.py \\
        staging get
    backend/.venv/Scripts/python.exe scripts/set_runtime_config.py \\
        staging set LINK_MINTING_ENABLED true --project polyglot-demo-aa709

`get` prints the current app_config/{channel} doc (or "{} (no doc)" if none
exists) and needs no --project (Firestore reads happily under any resolvable
ADC project; the doc path is namespaced by the channel argument, not by the
project). `set` WRITES, so --project is REQUIRED and pins the target
deterministically -- same reasoning and same guard as scripts/bootstrap_firm.py
(firebase_admin otherwise resolves the project from the operator's ADC
credential first, which is not necessarily the intended one).

Only RUNTIME_CONFIG_KEYS may be set; an unknown key is refused before any
write, matching runtime_config.py's own "unknown key ignored" contract for
READS (a write-time refusal is stricter, and correctly so -- a script typo
setting a key nothing reads should fail loudly, not silently no-op forever).

Exit codes: 0 = success; 2 = bad arguments, unknown key, or a value that
fails validation; 3 = the Firestore read/write itself failed.

ASCII only.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# The former prod project is DEAD (maintainer, 2026-08-14); refuse it exactly
# like scripts/bootstrap_firm.py does, so a stale invocation cannot half-write
# against it.
DEAD_PROJECTS = {"polyglot-forms-919f2"}


def _parse_value(key: str, raw: str):
    """Turn a CLI string into the typed value runtime_config expects.

    Uses the SAME coercion runtime_config.coerce_value applies on read, so a
    value this script accepts is guaranteed to round-trip through a real
    read rather than silently becoming the env default because the stored
    shape does not match what the reader recognizes.
    """
    from backend.services import runtime_config

    return runtime_config.coerce_value(key, raw)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Read or set a key in app_config/{channel} (backend "
        "runtime config)."
    )
    parser.add_argument("channel", help="channel doc id, e.g. staging, demo")
    sub = parser.add_subparsers(dest="action", required=True)

    sub.add_parser("get", help="print the channel's current config doc")

    set_p = sub.add_parser("set", help="set one key in the channel's config doc")
    set_p.add_argument("key", help="one of RUNTIME_CONFIG_KEYS")
    set_p.add_argument("value", help="the new value (bool keys: true/false)")
    set_p.add_argument(
        "--project",
        required=True,
        help="target Firebase project (deterministic: pre-initializes "
        "firebase_admin with this projectId AND asserts the resolved app "
        "project matches -- see scripts/bootstrap_firm.py for the same "
        "guard and why it matters)",
    )

    args = parser.parse_args(argv)

    from backend.services import runtime_config

    if args.action == "get":
        # A read needs no --project pin: get_db() resolves ADC's own default
        # project, which is fine for a read-only inspection. Import lazily so
        # `get` never requires firebase_admin to already be initialized with
        # a specific project.
        from backend.services.auth import get_db

        try:
            snap = get_db().collection(runtime_config.COLLECTION).document(
                args.channel
            ).get()
        except Exception as e:
            print(f"read FAILED: {e}", file=sys.stderr)
            return 3
        doc = snap.to_dict() if snap.exists else None
        if doc is None:
            print(f"app_config/{args.channel}: {{}} (no doc)")
        else:
            for k in sorted(doc):
                flag = "" if k in runtime_config.RUNTIME_CONFIG_KEYS else "  (unknown key -- ignored on read)"
                print(f"app_config/{args.channel}.{k} = {doc[k]!r}{flag}")
        return 0

    # action == "set"
    if args.key not in runtime_config.RUNTIME_CONFIG_KEYS:
        print(
            f"{args.key!r} is not a runtime config key. Valid keys: "
            + ", ".join(sorted(runtime_config.RUNTIME_CONFIG_KEYS)),
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

    value = _parse_value(args.key, args.value)
    if value is None:
        print(
            f"{args.value!r} is not a valid value for {args.key} -- refusing "
            "to write something runtime_config's own reader would treat as "
            "malformed (which would silently fall back to the last-known-"
            "good or env default instead of applying).",
            file=sys.stderr,
        )
        return 2

    # Deterministic project pin -- see scripts/bootstrap_firm.py's identical
    # ordering and reasoning (assert BEFORE setting GOOGLE_CLOUD_PROJECT, so
    # a refused run never leaves the process env pointed at the wrong project).
    import firebase_admin

    if not firebase_admin._apps:
        firebase_admin.initialize_app(options={"projectId": args.project})
    resolved = firebase_admin.get_app().project_id
    if resolved != args.project:
        print(
            f"resolved firebase_admin project is {resolved!r}, not "
            f"{args.project!r} -- refusing to write into the wrong project.",
            file=sys.stderr,
        )
        return 2
    import os as _os

    _os.environ["GOOGLE_CLOUD_PROJECT"] = args.project

    from backend.services.auth import get_db

    try:
        get_db().collection(runtime_config.COLLECTION).document(
            args.channel
        ).set({args.key: value}, merge=True)
    except Exception as e:
        print(f"write FAILED: {e}", file=sys.stderr)
        return 3

    print(f"set app_config/{args.channel}.{args.key} = {value!r}")
    print(
        "NOTE: a process already running picks this up within its TTL cache "
        f"window ({runtime_config.TTL_SECONDS:.0f}s), no redeploy needed."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
