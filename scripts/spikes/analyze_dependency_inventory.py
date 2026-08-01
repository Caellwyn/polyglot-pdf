#!/usr/bin/env python3
"""Variance-aware readout of the dependency-inventory bake (bd polyglot-pdf-btbi).

Round 1 (n=1 per arm) looked like a near-doubling of relationship recall; the
n=2 confirmation did NOT reproduce it -- the CONTROL arm alone ranged 12-18 of
32 across runs, a spread as large as the apparent effect. This script exists so
the verdict is drawn from the distribution instead of a lucky pair: it reports
per-arm mean/median/range and a permutation test (exact when feasible), which
needs no scipy and makes no normality assumption on 3-6 noisy samples.

Read the p-value as "how often would shuffling the arm labels produce a gap at
least this big by chance" -- with single-digit sample counts a non-significant
result means UNDECIDED, not "no effect".

Usage:
    python scripts/spikes/analyze_dependency_inventory.py
        [--runs scripts/spikes/data/dependency_inventory_runs.jsonl]
        [--metric present|trigger_correct|spurious|inventory]

ASCII only (cp1252 safe).
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import statistics
from typing import Any, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
_DEFAULT_RUNS = os.path.join(_HERE, "data", "dependency_inventory_runs.jsonl")


def _metric(summary: dict[str, Any], metric: str) -> Optional[float]:
    if metric == "present":
        return float(summary["combined_present"].split("/")[0])
    if metric == "trigger_correct":
        return float(summary["combined_trigger_correct"].split("/")[0])
    if metric == "spurious":
        return float(summary["spurious_total"])
    if metric == "inventory":
        v = summary.get("inventory_entries")
        return float(v) if v is not None else None
    raise ValueError(metric)


def permutation_p(a: list[float], b: list[float],
                  max_exact: int = 200_000) -> tuple[float, bool]:
    """Two-sided p for the difference in means, by relabeling. Exact when the
    number of splits is small enough, else a deterministic subsample."""
    observed = abs(statistics.fmean(b) - statistics.fmean(a))
    pool = a + b
    n = len(a)
    splits = list(itertools.combinations(range(len(pool)), n))
    exact = len(splits) <= max_exact
    if not exact:
        splits = splits[:max_exact]
    hits = 0
    for idx in splits:
        left = [pool[i] for i in idx]
        right = [pool[i] for i in range(len(pool)) if i not in set(idx)]
        if abs(statistics.fmean(right) - statistics.fmean(left)) >= observed - 1e-12:
            hits += 1
    return hits / len(splits), exact


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", default=_DEFAULT_RUNS)
    ap.add_argument("--metric", default="present",
                    choices=("present", "trigger_correct", "spurious",
                             "inventory"))
    args = ap.parse_args(argv)

    rows = [json.loads(line) for line in open(args.runs, encoding="utf-8")
            if line.strip()]
    rows = [r for r in rows if "summary" in r]
    by_arm: dict[str, list[float]] = {}
    for r in rows:
        v = _metric(r["summary"], args.metric)
        if v is not None:
            by_arm.setdefault(r["arm"], []).append(v)

    total = rows[0]["summary"]["combined_present"].split("/")[1] if rows else "?"
    print(f"metric: {args.metric}" + (f"  (out of {total})"
                                      if args.metric in ("present",
                                                         "trigger_correct")
                                      else ""))
    for arm in sorted(by_arm):
        v = sorted(by_arm[arm])
        print(f"  {arm}: n={len(v)}  mean={statistics.fmean(v):.1f}  "
              f"median={statistics.median(v):.1f}  range={v[0]:.0f}-{v[-1]:.0f}  "
              f"values={[int(x) for x in by_arm[arm]]}")

    if len(by_arm) == 2 and all(len(v) >= 2 for v in by_arm.values()):
        a_name, b_name = sorted(by_arm)
        a, b = by_arm[a_name], by_arm[b_name]
        diff = statistics.fmean(b) - statistics.fmean(a)
        p, exact = permutation_p(a, b)
        print(f"\n  {b_name} - {a_name} = {diff:+.1f}  "
              f"(permutation p = {p:.3f}{'' if exact else ', subsampled'})")
        if p <= 0.05:
            print("  -> the gap is unlikely to be label-shuffling noise.")
        else:
            print("  -> UNDECIDED at this sample size: the arms overlap too "
                  "much to call. Collect more runs before claiming an effect.")
    else:
        print("\n  (need >=2 runs of each arm for the comparison)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
