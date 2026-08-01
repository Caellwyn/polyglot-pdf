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

FORM SCOPING IS MANDATORY (fresh-eyes gap, 2026-08-01): the runs file holds
rows for MORE THAN ONE form, and pooling them is meaningless -- i-90 is
saturated (19/19 every run) while w7 is the contested case, so mixing them
drags both arms toward each other and silently changes the verdict. The
default is therefore the w7 comparison, and any run over multi-form data
without an explicit --form is refused rather than quietly averaged.

Usage:
    python scripts/spikes/analyze_dependency_inventory.py            # w7 (default)
    python scripts/spikes/analyze_dependency_inventory.py --form i-90
    python scripts/spikes/analyze_dependency_inventory.py --form ALL # explicit opt-in
        [--runs scripts/spikes/data/dependency_inventory_runs.jsonl]
        [--metric present|trigger_correct|spurious|inventory]

ASCII only (cp1252 safe).
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import random
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
                  max_exact: int = 200_000,
                  seed: int = 20260801) -> tuple[float, bool]:
    """Two-sided p for the difference in means, by relabeling.

    Exact enumeration when the number of splits fits in `max_exact`; otherwise
    a SEEDED RANDOM sample of relabelings. The random path matters: taking the
    lexicographically-first N combinations (the obvious shortcut) is a BIASED
    subsample -- early combinations over-represent low-index elements, i.e.
    arm `a`, since pool = a + b -- so it would silently skew p at the exact
    moment the sample grows large enough to need it (fresh-eyes gap,
    2026-08-01; first triggers around n>=11 per arm). Seeded so a rerun of the
    same data reproduces the same p.
    """
    observed = abs(statistics.fmean(b) - statistics.fmean(a))
    pool = a + b
    n = len(a)
    total_splits = math.comb(len(pool), n)
    exact = total_splits <= max_exact
    if exact:
        splits: list[tuple[int, ...]] = list(
            itertools.combinations(range(len(pool)), n))
    else:
        rng = random.Random(seed)
        idx_all = list(range(len(pool)))
        splits = [tuple(rng.sample(idx_all, n)) for _ in range(max_exact)]
    hits = 0
    for idx in splits:
        chosen = set(idx)
        left = [pool[i] for i in idx]
        right = [pool[i] for i in range(len(pool)) if i not in chosen]
        if abs(statistics.fmean(right) - statistics.fmean(left)) >= observed - 1e-12:
            hits += 1
    return hits / len(splits), exact


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", default=_DEFAULT_RUNS)
    ap.add_argument("--form", default="w7",
                    help="form to compare (default w7); 'ALL' explicitly opts "
                         "into pooling every form, which is normally wrong")
    ap.add_argument("--metric", default="present",
                    choices=("present", "trigger_correct", "spurious",
                             "inventory"))
    args = ap.parse_args(argv)

    rows = [json.loads(line) for line in open(args.runs, encoding="utf-8")
            if line.strip()]
    rows = [r for r in rows if "summary" in r]
    forms = sorted({str(r.get("form")) for r in rows})
    if args.form != "ALL":
        if args.form not in forms:
            ap.error(f"no rows for form {args.form!r} (present: "
                     f"{', '.join(forms)})")
        rows = [r for r in rows if str(r.get("form")) == args.form]
    elif len(forms) > 1:
        print(f"WARNING: pooling {len(forms)} forms ({', '.join(forms)}) -- "
              "their denominators and difficulty differ, so the pooled result "
              "is NOT the per-form verdict.\n")

    by_arm: dict[str, list[float]] = {}
    for r in rows:
        v = _metric(r["summary"], args.metric)
        if v is not None:
            by_arm.setdefault(r["arm"], []).append(v)

    totals = sorted({r["summary"]["combined_present"].split("/")[1]
                     for r in rows})
    total = totals[0] if len(totals) == 1 else "/".join(totals) + " (MIXED)"
    scope = args.form if args.form != "ALL" else f"ALL forms ({', '.join(forms)})"
    print(f"form: {scope}   metric: {args.metric}"
          + (f"  (out of {total})"
             if args.metric in ("present", "trigger_correct") else ""))
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
