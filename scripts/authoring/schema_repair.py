#!/usr/bin/env python3
"""CLI shim for the schema repair pass (bd h76m.13, P5.2).

The repair CORE lives in backend/services/schema_repair.py (same placement
rationale as schema_lint: the editor's "Repair all" route, P5.3, imports it
in-process, and CLI output must equal editor output by construction). This
shim exposes the same `repair(schema, dump=None)` for the pipeline callers
that import by file path (eval_extraction._try_repair) and adds a CLI:

    python scripts/authoring/schema_repair.py --in DRAFT.json --out FIXED.json \
        [--dump ACROFORM.json]

ASCII only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO)

from backend.services.schema_repair import (  # noqa: E402,F401 (re-export)
    RepairError, alias_hit_count, repair,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Deterministic post-LLM schema repair (bd h76m.13).")
    ap.add_argument("--in", dest="in_path", required=True, help="draft schema JSON")
    ap.add_argument("--out", dest="out_path", required=True, help="repaired output path")
    ap.add_argument("--dump", default=None,
                    help="acroform dump JSON: enables the hallucinated-widget "
                         "check (repair FAILS on invented widgets)")
    args = ap.parse_args(argv)

    with open(args.in_path, encoding="utf-8") as fh:
        schema = json.load(fh)
    dump = None
    if args.dump:
        with open(args.dump, encoding="utf-8") as fh:
            dump = json.load(fh)

    try:
        repaired, repairs = repair(schema, dump)
    except RepairError as exc:
        print(f"REPAIR-FAILED: {exc}", file=sys.stderr)
        return 1

    with open(args.out_path, "w", encoding="utf-8") as fh:
        json.dump(repaired, fh, indent=2)

    errors = sum(1 for r in repairs if r.get("error"))
    print(f"[wrote {args.out_path}] {len(repairs)} repair(s), "
          f"{errors} recorded error(s), alias hits: {alias_hit_count(repairs)}")
    for r in repairs:
        marker = "ERROR " if r.get("error") else ""
        print(f"  {marker}{r['action']} {r['path']}: {r['detail'][:100]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
