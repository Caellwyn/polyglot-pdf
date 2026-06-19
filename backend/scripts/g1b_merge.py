"""G1b merge -- combine the bake-off run files into one deduped dataset.

bd polyglot-pdf-0zp3. The full sweep had to be run in PIECES (the slow/flaky
gemini-3-flash-preview model and host/session interruptions made a single
all-sizes-all-models run impractical -- see the findings doc "Run mechanics").
Each piece wrote its own g1b_bakeoff_<stamp>.csv. This merges them into one
canonical CSV, deduping by (size, model, case_id) and PREFERRING a non-errored
row over an errored one for the same cell (so a case that timed out in one run
but succeeded in another is represented by the success).

Records, per cell kept, whether it came from a clean or errored row, and reports
the residual error rate per (model,size) -- gemini-3-flash-preview's elevated rate
is itself a result (the priciest candidate is also the least reliable under load).

Usage:
    PYTHONPATH=. python backend/scripts/g1b_merge.py
    # writes scripts/spikes/data/g1b_bakeoff_MERGED.csv
"""
from __future__ import annotations

import csv
import glob
import os
from collections import Counter, defaultdict

OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scripts", "spikes", "data",
)


def main() -> None:
    files = sorted(glob.glob(os.path.join(OUT_DIR, "g1b_bakeoff_2026*.csv")))
    files = [f for f in files if "MERGED" not in f]
    if not files:
        print("no bake-off CSVs found", flush=True)
        return

    # key -> best row. "best" = a non-errored row beats an errored one; among
    # equal-error rows, the LAST file (most recent run) wins.
    best: dict = {}
    fieldnames = None
    for f in files:
        for r in csv.DictReader(open(f, encoding="utf-8")):
            fieldnames = list(r.keys())
            key = (r["size"], r["model"], r["case_id"])
            cur = best.get(key)
            r_err = bool(r["error"])
            if cur is None:
                best[key] = r
            else:
                cur_err = bool(cur["error"])
                # prefer non-errored; if both same error-state, keep newer (this f).
                if cur_err and not r_err:
                    best[key] = r
                elif cur_err == r_err:
                    best[key] = r  # later file wins ties

    rows = list(best.values())
    rows.sort(key=lambda r: (int(r["size"]), r["model"], r["case_id"]))

    # RE-SCORE `detected` from the captured flagged_ids using the CURRENT scorer
    # (prefix-tolerant `_detected`). The voice model truncates field ids in its
    # tool call ('p1_line6e' for 'p1_line6e_state'), which the original
    # exact-match scoring wrongly counted as misses; re-scoring corrects those
    # cells WITHOUT re-calling the API (the model's flags were captured; only the
    # scoring of them was wrong). For text models this is a no-op (full ids ->
    # prefix-of reduces to equality). Builds the expected-conflict sets per
    # case_id from the corpus (keyed by the base case id without the size prefix
    # normalization -- the corpus case_id already includes the size, e.g.
    # 's132_zipstate_near_0').
    from backend.scripts.g1b_corpus import build_corpus
    from backend.scripts.probe_g1b_model_size_bakeoff import _detected
    expected_by_case: dict = {}
    for size in sorted({int(r["size"]) for r in rows}):
        for c in build_corpus(size):
            expected_by_case[c.case_id] = c.expected_conflicts
    rescored = 0
    for r in rows:
        exp = expected_by_case.get(r["case_id"])
        if exp is None:
            continue
        # flagged_ids is a flat ';'-joined union of all flagged fields -> one set;
        # _detected's "any expected field matches any flagged field" works on it.
        flagged = [set(x for x in r["flagged_ids"].split(";") if x)] if r["flagged_ids"] else []
        new_det = int(bool(exp) and _detected(exp, flagged))
        if str(new_det) != r["detected"]:
            r["detected"] = str(new_det)
            rescored += 1
    if rescored:
        print(f"re-scored {rescored} cells (prefix-tolerant detection)", flush=True)

    out = os.path.join(OUT_DIR, "g1b_bakeoff_MERGED.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # report coverage + residual errors
    by_size = Counter(int(r["size"]) for r in rows)
    print(f"merged {len(files)} files -> {len(rows)} unique cells", flush=True)
    print("cells by size:", dict(by_size), flush=True)
    err = defaultdict(int)
    tot = defaultdict(int)
    for r in rows:
        tot[(r["model"], r["size"])] += 1
        if r["error"]:
            err[(r["model"], r["size"])] += 1
    print("\nresidual errors per (model,size) after dedup:")
    any_err = False
    for k in sorted(tot):
        if err[k]:
            any_err = True
            print(f"  {k[0]:<24} size {k[1]:>3}: {err[k]}/{tot[k]} still errored", flush=True)
    if not any_err:
        print("  none -- every cell has a clean row", flush=True)
    print(f"\nwrote {out}", flush=True)


if __name__ == "__main__":
    main()
