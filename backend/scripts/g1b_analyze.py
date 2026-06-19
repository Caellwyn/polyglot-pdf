"""G1b analysis -- slice the bake-off CSV into the report tables.

bd polyglot-pdf-0zp3. The probe (probe_g1b_model_size_bakeoff.py) writes one row
per (model x size x case) with detected/distance/class/latency/tokens/cost. This
script reads the latest (or a named) CSV and prints the breakdowns the bead asks
for that the probe's headline matrix does not: accuracy by CONTRADICTION DISTANCE
(close vs far/cross-section) and by CLASS, per model and size. Pure offline; no
API calls.

Usage:
    PYTHONPATH=. python backend/scripts/g1b_analyze.py [path/to/g1b_bakeoff_*.csv]
"""
from __future__ import annotations

import csv
import glob
import os
import sys
from collections import defaultdict

OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scripts", "spikes", "data",
)


def _latest_csv() -> str:
    files = sorted(glob.glob(os.path.join(OUT_DIR, "g1b_bakeoff_*.csv")))
    if not files:
        print("no g1b_bakeoff_*.csv found", flush=True)
        sys.exit(1)
    return files[-1]


def _pct(n, d):
    return f"{n/d:.3f}" if d else "  -  "


def _distance_bucket(dist: int) -> str:
    if dist == 0:
        return "single/0"
    if dist <= 5:
        return "near(1-5)"
    if dist <= 20:
        return "mid(6-20)"
    return "far(21+)"


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else _latest_csv()
    print(f"analyzing {os.path.basename(path)}\n", flush=True)
    rows = list(csv.DictReader(open(path, encoding="utf-8")))

    models = sorted({r["model"] for r in rows})
    sizes = sorted({int(r["size"]) for r in rows})

    # ---- recall by DISTANCE bucket, per model (pooled over sizes) ----
    print("=== RECALL by contradiction DISTANCE (per model, pooled over sizes) ===",
          flush=True)
    print("(does a model still catch a contradiction whose halves are far apart?)\n")
    buckets = ["single/0", "near(1-5)", "mid(6-20)", "far(21+)"]
    hdr = f"{'model':<24} " + " ".join(f"{b:>11}" for b in buckets)
    print(hdr, flush=True)
    for model in models:
        det = defaultdict(int)
        tot = defaultdict(int)
        for r in rows:
            if r["model"] == model and r["is_contradiction"] == "1":
                b = _distance_bucket(int(r["distance"]))
                tot[b] += 1
                det[b] += r["detected"] == "1"
        cells = " ".join(f"{_pct(det[b], tot[b]):>11}" for b in buckets)
        print(f"{model:<24} {cells}", flush=True)
    print("  (blank = no contradiction case fell in that distance bucket)\n", flush=True)

    # ---- recall by CLASS, per model (pooled over sizes) ----
    print("=== RECALL by contradiction CLASS (per model, pooled over sizes) ===\n",
          flush=True)
    classes = sorted({r["cls"] for r in rows if r["is_contradiction"] == "1"})
    hdr = f"{'model':<24} " + " ".join(f"{c[:11]:>13}" for c in classes)
    print(hdr, flush=True)
    for model in models:
        det = defaultdict(int)
        tot = defaultdict(int)
        for r in rows:
            if r["model"] == model and r["is_contradiction"] == "1":
                tot[r["cls"]] += 1
                det[r["cls"]] += r["detected"] == "1"
        cells = " ".join(f"{_pct(det[c], tot[c]):>13}" for c in classes)
        print(f"{model:<24} {cells}", flush=True)
    print()

    # ---- recall/precision by SIZE, per model (does accuracy degrade with length?) ----
    print("=== RECALL / PRECISION by SIZE (per model) ===\n", flush=True)
    print(f"{'model':<24} " + " ".join(f"{('sz'+str(s)):>16}" for s in sizes), flush=True)
    for model in models:
        cells = []
        for size in sizes:
            tp = fn = fp = 0
            for r in rows:
                if r["model"] == model and int(r["size"]) == size:
                    if r["is_contradiction"] == "1":
                        tp += r["detected"] == "1"
                        fn += r["detected"] == "0"
                    elif r["n_flagged"] != "0":
                        fp += 1
            rec = _pct(tp, tp + fn)
            prec = _pct(tp, tp + fp)
            cells.append(f"r{rec}/p{prec}")
        print(f"{model:<24} " + " ".join(f"{c:>16}" for c in cells), flush=True)
    print("  (r=recall p=precision; watch whether recall holds as size grows)\n",
          flush=True)


if __name__ == "__main__":
    main()
