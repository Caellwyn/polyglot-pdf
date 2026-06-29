"""Aggregate the G1c tuning runs (bd polyglot-pdf-08zv).

Pools all g1c_precision_*.csv runs by (prompt, size) -- summing tp/fn/fp/tn across
repeats so the recall/precision numbers average out per-call cheap-model noise --
and prints the precision lever's baseline-vs-tuned comparison. Also summarizes the
latency lever (g1c_latency_*.csv) if present. STDLIB-only.
"""
from __future__ import annotations

import csv
import glob
import os
import statistics
import sys
from collections import defaultdict

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Add the repo root to sys.path so `python backend/scripts/g1c_aggregate.py` works
# from the repo root WITHOUT a PYTHONPATH=. prefix (the imports below need the
# `backend` package; Codex review on PR #262).
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_DATA = os.path.join(_REPO_ROOT, "scripts", "spikes", "data")


def _precision():
    files = sorted(glob.glob(os.path.join(_DATA, "g1c_precision_2026*.csv")))
    if not files:
        print("no g1c_precision_*.csv runs found")
        return
    # Pool ONLY rows from the CURRENT corpus version. Each row carries corpus_fp;
    # rows from a different (older / contaminated / future) corpus must NOT be summed
    # into the clean-corpus recommendation, even though they share a (prompt, size)
    # key (Codex review on PR #262 -- the same fingerprint discipline as g1b_merge).
    from backend.scripts.g1b_corpus import corpus_fingerprint
    from backend.scripts.g1b_scoring import is_model_format_error
    current_fp = corpus_fingerprint()
    agg = defaultdict(lambda: {"tp": 0, "fn": 0, "fp": 0, "tn": 0, "runs": set()})
    dropped_fp = 0
    # Score rows EXACTLY as the probe does (g1b_scoring): a MODEL-FORMAT failure
    # (json_error / no_tool_call) is NOT skipped -- it is an empty verdict, i.e. a
    # MISS on a contradiction (FN) and a clean-pass on a clean case (TN). Only a
    # TRANSPORT failure (timeout / 5xx / connect) is excluded as "no measurement".
    # Skipping json_error would undercount FN and inflate recall (fresh-eyes, 08zv).
    for f in files:
        for r in csv.DictReader(open(f, encoding="utf-8")):
            if (r.get("corpus_fp") or "") != current_fp:
                dropped_fp += 1
                continue  # different corpus version -- never pool
            k = (r["prompt"], r["size"])
            c = agg[k]
            c["runs"].add(os.path.basename(f))
            err = r.get("error") or ""
            if err and not is_model_format_error(err):
                continue  # transport failure -> no measurement (excluded)
            # model-format failure falls through with detected=0 / n_flagged=0,
            # so it scores as FN (contradiction) or TN (clean) -- matching the probe.
            if r["is_contradiction"] == "1":
                c["tp" if r["detected"] == "1" else "fn"] += 1
            else:
                c["fp" if int(r["n_flagged"]) > 0 else "tn"] += 1
    if dropped_fp:
        print(f"(excluded {dropped_fp} row(s) from a different corpus_fp; "
              f"pooling only corpus_fp={current_fp})")
    if not agg:
        print(f"no rows match the current corpus_fp={current_fp}; "
              f"re-run probe_g1c_tuning.py on this corpus.")
        return
    hdr = ("prompt", "size", "runs", "recall", "prec", "tp", "fn", "fp")
    print(f"{hdr[0]:<9}{hdr[1]:>5}{hdr[2]:>5}{hdr[3]:>8}{hdr[4]:>7}"
          f"{hdr[5]:>5}{hdr[6]:>4}{hdr[7]:>4}")
    for prompt in ("baseline", "tuned"):
        for size in ("20", "40", "132"):
            c = agg.get((prompt, size))
            if not c:
                continue
            rec = c["tp"] / (c["tp"] + c["fn"]) if (c["tp"] + c["fn"]) else 0.0
            prec = c["tp"] / (c["tp"] + c["fp"]) if (c["tp"] + c["fp"]) else 0.0
            print(f"{prompt:<9}{size:>5}{len(c['runs']):>5}{rec:>8.3f}{prec:>7.3f}"
                  f"{c['tp']:>5}{c['fn']:>4}{c['fp']:>4}")


def _latency():
    files = sorted(glob.glob(os.path.join(_DATA, "g1c_latency_2026*.csv")))
    if not files:
        print("\n(no g1c_latency_*.csv runs yet)")
        return
    print(f"\n=== LATENCY LEVER: pooled over {len(files)} run(s) ===")
    # Same current-corpus_fp filter as the precision branch: never blend latency
    # rows from a different corpus version (different payloads/case mix) into the
    # pooled p50/p90 (Codex review on PR #262).
    from backend.scripts.g1b_corpus import corpus_fingerprint
    current_fp = corpus_fingerprint()
    lat = defaultdict(list)
    dropped_fp = 0
    for f in files:
        for r in csv.DictReader(open(f, encoding="utf-8")):
            if (r.get("corpus_fp") or "") != current_fp:
                dropped_fp += 1
                continue
            if not r["error"]:
                lat[r["variant"]].append(float(r["latency_s"]))
    if dropped_fp:
        print(f"(excluded {dropped_fp} row(s) from a different corpus_fp; "
              f"pooling only corpus_fp={current_fp})")
    if not any(lat.values()):
        print(f"no latency rows match the current corpus_fp={current_fp}.")
        return
    print(f"{'variant':<10}{'n':>4}{'p50':>8}{'p90':>8}{'max':>8}")
    for variant in ("baseline", "trim"):
        v = sorted(lat.get(variant, []))
        if not v:
            continue
        p50 = statistics.median(v)
        p90 = v[int(0.9 * (len(v) - 1))]
        print(f"{variant:<10}{len(v):>4}{p50:>8.2f}{p90:>8.2f}{max(v):>8.2f}")


if __name__ == "__main__":
    _precision()
    _latency()
