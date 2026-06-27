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

    # Merge ONLY runs of the CURRENT corpus version. The corpus content changed in
    # bd wf3q (validated answer key + label resolution + isolated injections), so a
    # row from an OLDER run shares case_ids with the new corpus but was measured on
    # DIFFERENT payloads; deduping by (size, model, case_id) across versions would
    # silently blend contaminated + clean numbers (Codex review, PR #253). Rows
    # carrying a `corpus_fp` that does not match the current corpus -- and rows from
    # runs that predate the column entirely (no `corpus_fp`) -- are EXCLUDED, with
    # the dropped count reported so the exclusion is never silent.
    from backend.scripts.g1b_corpus import corpus_fingerprint
    current_fp = corpus_fingerprint()

    # key -> best row. "best" = a non-errored row beats an errored one; among
    # equal-error rows, the LAST file (most recent run) wins.
    best: dict = {}
    fieldnames: list = []
    dropped_fp = dropped_no_fp = 0
    for f in files:
        for r in csv.DictReader(open(f, encoding="utf-8")):
            row_fp = r.get("corpus_fp")
            if not row_fp:
                dropped_no_fp += 1
                continue  # pre-fingerprint run (old corpus) -- never merge
            if row_fp != current_fp:
                dropped_fp += 1
                continue  # a different corpus version -- never merge
            for k in r:  # union of columns across run files (schemas may differ)
                if k not in fieldnames:
                    fieldnames.append(k)
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
    if dropped_no_fp or dropped_fp:
        print(f"[corpus-version filter] excluded {dropped_no_fp} pre-fingerprint "
              f"row(s) + {dropped_fp} other-corpus row(s); merging only corpus_fp="
              f"{current_fp}", flush=True)
    if not best:
        print(f"no rows match the current corpus_fp={current_fp}; re-run the probe "
              f"on this corpus before merging.", flush=True)
        return

    rows = list(best.values())
    rows.sort(key=lambda r: (int(r["size"]), r["model"], r["case_id"]))

    # RE-SCORE `detected` from the captured per-group flags using the CURRENT
    # stdlib scorer (full-group, prefix-tolerant). This corrects rows from OLDER
    # run files (which were scored with the previous any-overlap / exact-match
    # logic) without re-calling the API. It needs the PER-GROUP structure
    # (`flagged_groups`, groups '|'-separated, fields ';'-separated); rows from
    # runs predating that column are left as-scored (no flagged_groups to re-derive
    # from). Imports the STDLIB-ONLY scorer + corpus -- NO google.genai, so the
    # offline merge runs without the API SDK (Codex review).
    from backend.scripts.g1b_corpus import build_corpus
    from backend.scripts.g1b_scoring import detected as _detected
    expected_by_case: dict = {}
    for size in sorted({int(r["size"]) for r in rows}):
        for c in build_corpus(size):
            expected_by_case[c.case_id] = c.expected_conflicts
    rescored = skipped_no_groups = 0
    for r in rows:
        exp = expected_by_case.get(r["case_id"])
        if exp is None or r.get("error"):
            continue
        if "flagged_groups" not in r or r.get("flagged_groups") is None:
            skipped_no_groups += 1
            continue
        flagged = [set(f for f in g.split(";") if f)
                   for g in r["flagged_groups"].split("|") if g]
        new_det = int(_detected(exp, flagged))
        if str(new_det) != r["detected"]:
            r["detected"] = str(new_det)
            rescored += 1
    if rescored:
        print(f"re-scored {rescored} cells (full-group, prefix-tolerant)", flush=True)
    if skipped_no_groups:
        print(f"left {skipped_no_groups} pre-flagged_groups rows as-scored", flush=True)

    out = os.path.join(OUT_DIR, "g1b_bakeoff_MERGED.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, restval="")
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
