#!/usr/bin/env python3
"""Bake-off runner: score every available extractor arm and emit a table.

Throwaway research harness for bd polyglot-pdf-7a9.4. Given a set of already-
produced draft schemas (one per arm, written by arm_gemini.py / the Claude arm /
etc.), this scores each against the ground truth via scripts/schema_score.py and
prints a per-tool x per-half x per-form table plus a machine-readable JSON.

It does NOT call any model itself -- the arms write their draft JSON first (so a
failed/expensive arm never blocks the rest), and this consumes those files. Arms
whose draft file is missing are reported as "not run" (e.g. Document AI, which
needs GCP provisioning), so the table is honest about coverage.

ASCII-only (cp1252 safe). Usage:

    python scripts/bakeoff/run_bakeoff.py --manifest scripts/bakeoff/manifest.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Optional

# Reuse the real scorer.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import schema_score  # noqa: E402


def _hdr(p: float) -> str:
    return "  -  " if p != p else f"{p:5.1f}"


def _f1(a: dict) -> float:
    return a["detection"]["f1"]


def _attr_avg(a: dict) -> float:
    """Mean of the applicable per-attribute accuracies (a-half summary)."""
    vals = [v["pct"] for v in a["attributes"].values()
            if v["applicable"] and v["pct"] == v["pct"]]
    return sum(vals) / len(vals) if vals else float("nan")


def _rel_recall(b: dict) -> float:
    """Total conditional relationships recovered / total in ground truth (b-half)."""
    rec = tot = 0
    for v in b["conditionals"].values():
        rec += v["recovered"]
        tot += v["total"]
    return schema_score._pct(rec, tot)


def _struct_recall(b: dict) -> float:
    vals = [v["pct"] for v in b["structure"].values() if v["pct"] == v["pct"]]
    return sum(vals) / len(vals) if vals else float("nan")


def run(manifest: dict) -> dict:
    results: dict[str, Any] = {"forms": {}}
    for form_id, form in manifest["forms"].items():
        truth = form["truth"]
        per_arm = {}
        for arm_name, draft_path in form["arms"].items():
            if not draft_path or not os.path.exists(draft_path):
                per_arm[arm_name] = {"status": "not run",
                                     "reason": "draft file missing"}
                continue
            try:
                sc = schema_score.score(draft_path, truth, label=f"{form_id}:{arm_name}")
            except Exception as e:  # a bad/empty draft must not sink the table
                per_arm[arm_name] = {"status": "error",
                                     "reason": f"{type(e).__name__}: {e}"}
                continue
            a, b = sc["field_extraction"], sc["relationships"]
            per_arm[arm_name] = {
                "status": "scored",
                "a_detection_f1": _f1(a),
                "a_attr_avg": _attr_avg(a),
                "b_conditional_recall": _rel_recall(b),
                "b_structure_recall": _struct_recall(b),
                "full": sc,
            }
        results["forms"][form_id] = {"truth": truth, "arms": per_arm}
    return results


def render_table(results: dict) -> str:
    L = []
    L.append("=" * 78)
    L.append("EXTRACTOR BAKE-OFF  (bd polyglot-pdf-7a9.4)")
    L.append("=" * 78)
    L.append("Scores are percentages. (a) = field extraction, (b) = relationships.")
    L.append("  a.F1   = field detection F1 (precision/recall of finding fields)")
    L.append("  a.attr = mean per-attribute accuracy over matched fields")
    L.append("  b.cond = conditional-relationship recall (show_if/controls/...)")
    L.append("  b.strc = structural recall (parts/sections/supplements/tables)")
    L.append("")
    for form_id, form in results["forms"].items():
        L.append(f"FORM: {form_id}   (truth: {form['truth']})")
        L.append(f"  {'arm':28s} {'a.F1':>6s} {'a.attr':>7s} "
                 f"{'b.cond':>7s} {'b.strc':>7s}")
        L.append("  " + "-" * 60)
        for arm, r in form["arms"].items():
            if r["status"] != "scored":
                L.append(f"  {arm:28s}   [{r['status']}: {r.get('reason','')}]")
                continue
            L.append(f"  {arm:28s} {_hdr(r['a_detection_f1']):>6s} "
                     f"{_hdr(r['a_attr_avg']):>7s} "
                     f"{_hdr(r['b_conditional_recall']):>7s} "
                     f"{_hdr(r['b_structure_recall']):>7s}")
        L.append("")
    return "\n".join(L)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Score the bake-off arms.")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args(argv)

    with open(args.manifest, encoding="utf-8") as fh:
        manifest = json.load(fh)
    results = run(manifest)
    print(render_table(results))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2)
        print(f"[wrote {args.json_out}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
