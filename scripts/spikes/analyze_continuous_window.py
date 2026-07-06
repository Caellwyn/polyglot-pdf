"""Continuous DTI + compression-window analysis (bd polyglot-pdf-ctu8).

Ingests the `dti_cont_comp` runs that `cost_matrix_lib.load_matrix` cannot:
those runs are 30-34 questions (its contract hard-requires exactly 20) and the
window/trigger that distinguishes one sweep cell from another lives in the
run's meta.json, not the filename (its `_NAME_RE` keys only model/arm/path, so
every window cell collides). This module reads the continuous runs keyed by
(window, trigger), fits per-question conversation growth from the LIVE
compression curve, reports coherence (fill accuracy, confirms, secretary
lookups, evictions), and projects cost-per-form to full length by reusing the
`cost_matrix_lib` projection math (`window_cost_curve`).

Reused from cost_matrix_lib (the trusted, adversarially-reviewed projection):
  - window_cost_curve(): the eviction-sawtooth cost model.
  - RATES: per-model per-modality $/Mtok.
NOT reused: load_matrix/_cell_frames/calibrate/conversation_growth_per_turn --
those bake in the 20-question section-matrix shape. The SI base here is read
straight from each run's meta (prompt_curve[0]) instead of the library's
global char-rate calibration.

Usage:
  python scripts/spikes/analyze_continuous_window.py            # all dti_cont_comp runs
  python scripts/spikes/analyze_continuous_window.py --project 174   # + full-form projection
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

import cost_matrix_lib as cml

DATA_DIR = Path(__file__).resolve().parent / "data"


def _read_csv_textin(csv_path: Path) -> list[float]:
    """Per-question measured text-in tokens (the CSV already sums a question's
    billed events, so this IS the per-question cost series -- do not
    reconstruct it from the per-event prompt_curve, which under-counts by
    ~1.4-1.6x, verified against these runs)."""
    import csv as _csv
    with csv_path.open(encoding="utf-8") as fh:
        return [float(r["text in tokens"]) for r in _csv.DictReader(fh)]


def _load_run(meta_path: Path) -> dict:
    """Read one continuous run's meta + per-question CSV into a flat record."""
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    fa = meta.get("fill_accuracy") or {}
    prompts = meta.get("prompt_curve") or []
    drops = meta.get("eviction_drops") or []
    lookups = meta.get("field_value_lookups") or []
    n_q = int(meta.get("questions") or 0) or 1

    # Per-question MEASURED text-in tokens from the CSV -- the ground-truth
    # cost series. Fit growth + post-eviction steady state directly from it
    # (NOT from the per-event prompt_curve, whose reconstruction overprojects).
    csv_path = meta_path.parent / (meta_path.stem[:-len(".meta")] + ".csv") \
        if meta_path.stem.endswith(".meta") else \
        meta_path.with_suffix("").with_suffix(".csv")
    textin_q = _read_csv_textin(csv_path) if csv_path.exists() else []
    # Growth = median positive step in per-question text-in over the run; the
    # post-eviction STEADY level = median of the back half (after the window
    # has bitten and the sawtooth has stabilized).
    q_incs = [b - a for a, b in zip(textin_q, textin_q[1:])]
    growth_q = statistics.median([x for x in q_incs if x > 0]) if any(x > 0 for x in q_incs) else 0.0
    half = textin_q[len(textin_q) // 2:] if textin_q else []
    steady_textin_q = statistics.median(half) if half else None
    mean_textin_q = statistics.mean(textin_q) if textin_q else None

    return {
        "stamp": meta_path.stem,
        "model": str(meta.get("model", "")),
        "tier": meta.get("tier") or meta.get("model", ""),
        "path": meta.get("path", ""),
        "continuous": bool(meta.get("continuous")),
        "compression": bool(meta.get("compression")),
        "trigger": meta.get("trigger"),
        "window": meta.get("window"),
        "questions": n_q,
        "si_chars": meta.get("system_instruction_chars"),
        "si_base_tokens": prompts[0] if prompts else None,
        "prompt_peak": max(prompts) if prompts else None,
        "n_events": len(prompts),
        "n_evictions": len(drops),
        # per-QUESTION measured text-in (the trusted cost basis)
        "textin_q": textin_q,
        "growth_per_question": growth_q,
        "steady_textin_q": steady_textin_q,
        "mean_textin_q": mean_textin_q,
        "fill_matched": fa.get("matched"),
        "fill_total": fa.get("total"),
        "fill_accuracy": fa.get("accuracy"),
        "n_confirmed": len(meta.get("client_confirmed_fields") or []),
        "n_lookups": len(lookups),
        "n_errors": len(meta.get("errors") or []),
    }


def load_continuous_runs(data_dir: Path = DATA_DIR, only_compression: bool = True) -> list[dict]:
    runs = []
    for meta_path in sorted(data_dir.glob("*dti_cont_comp*.meta.json")):
        rec = _load_run(meta_path)
        if only_compression and not (rec["continuous"] and rec["compression"]):
            continue
        runs.append(rec)
    return runs


def summarize_by_window(runs: list[dict]) -> dict[tuple, dict]:
    """Group runs by (trigger, window) and average the key signals per cell.

    This is the grouping cost_matrix_lib can't do (it collides all window
    cells). A cell with no eviction is flagged -- its growth fit is untrusted
    (the window never bit, so it's an unbounded-growth measurement, not a
    windowed one)."""
    cells: dict[tuple, list[dict]] = {}
    for r in runs:
        cells.setdefault((r["trigger"], r["window"]), []).append(r)
    out = {}
    for key, group in sorted(cells.items(), key=lambda kv: (kv[0][1] or 0)):
        evicting = [g for g in group if g["n_evictions"] > 0]

        def _avg(field, src):
            vals = [g[field] for g in src if g[field] is not None]
            return sum(vals) / len(vals) if vals else None

        out[key] = {
            "trigger": key[0],
            "window": key[1],
            "n_runs": len(group),
            "n_runs_evicting": len(evicting),
            # growth + steady are only meaningful on runs where the window bit
            "growth_per_question": _avg("growth_per_question", evicting or group),
            "steady_textin_q": _avg("steady_textin_q", evicting or group),
            "mean_textin_q": _avg("mean_textin_q", evicting or group),
            "si_chars": _avg("si_chars", group),
            "si_base_tokens": _avg("si_base_tokens", group),
            "fill_accuracy": _avg("fill_accuracy", group),
            "n_evictions_mean": _avg("n_evictions", group),
            "n_errors_mean": _avg("n_errors", group),
            "growth_trusted": len(evicting) > 0,
            "runs": group,
        }
    return out


def project_form_cost(cell: dict, n_questions: int, model: str = "2.5") -> dict:
    """Project cumulative text-in $ to n_questions from a cell's MEASURED
    per-question text-in series: a saturating ramp -- cost grows at the
    measured growth/q until it reaches the measured post-eviction steady
    level, then stays flat (the window caps it). Fit directly to measured
    data, so the model-vs-measured ratio at the run's own length is ~1.0 by
    construction (the honesty check)."""
    rate = cml.RATES[model]["text_input"] / 1e6
    growth = cell["growth_per_question"] or 0.0
    steady = cell["steady_textin_q"]
    runs = [r for r in cell["runs"] if r.get("textin_q")]
    if not runs or steady is None:
        return {"cost": None}
    q1 = statistics.mean([r["textin_q"][0] for r in runs])
    cum = 0.0
    for q in range(1, n_questions + 1):
        per_q = min(q1 + growth * (q - 1), steady)
        cum += per_q * rate
    # honesty check: same model summed to the measured length vs measured total
    n_meas = statistics.median([len(r["textin_q"]) for r in runs])
    meas_total = statistics.mean([sum(r["textin_q"]) for r in runs]) * rate
    modeled_at_meas = sum(min(q1 + growth * (q - 1), steady) for q in range(1, int(n_meas) + 1)) * rate
    return {
        "cost": cum,
        "ratio_at_measured_len": (modeled_at_meas / meas_total) if meas_total else None,
        "measured_total": meas_total,
        "measured_len": n_meas,
    }


def _fmt(v, spec="{:.4f}"):
    return spec.format(v) if isinstance(v, (int, float)) else str(v)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", default=str(DATA_DIR))
    ap.add_argument("--project", type=int, default=None,
                    help="project cost-per-form to N questions per window cell")
    ap.add_argument("--model", default="2.5", help="pricing key for projection")
    args = ap.parse_args()

    runs = load_continuous_runs(Path(args.data_dir))
    if not runs:
        print("No dti_cont_comp runs found in", args.data_dir)
        return 1

    print(f"=== {len(runs)} continuous DTI+compression run(s) ===\n")
    hdr = ("window", "trig", "runs", "evict?", "growth/q", "fill", "evict#", "err")
    print("  ".join(f"{h:>8}" for h in hdr))
    cells = summarize_by_window(runs)
    for key, c in cells.items():
        row = (
            _fmt(c["window"], "{:d}") if c["window"] else "-",
            _fmt(c["trigger"], "{:d}") if c["trigger"] else "-",
            f"{c['n_runs']}",
            f"{c['n_runs_evicting']}/{c['n_runs']}",
            _fmt(c["growth_per_question"], "{:.1f}"),
            _fmt(c["fill_accuracy"], "{:.2f}"),
            _fmt(c["n_evictions_mean"], "{:.1f}"),
            _fmt(c["n_errors_mean"], "{:.1f}"),
        )
        print("  ".join(f"{v:>8}" for v in row))
        if not c["growth_trusted"]:
            print(f"           ^ WARNING window {c['window']} never evicted in any run "
                  "-- growth fit is unbounded-growth, not windowed; do not trust.")

    if args.project:
        print(f"\n=== projected cumulative TEXT-IN cost to {args.project} questions ===")
        print("(ratio = modeled-vs-measured at the run's own length; ~1.0 = trustworthy fit)\n")
        for key, c in cells.items():
            if not c["growth_trusted"]:
                print(f"  window {c['window']}: SKIPPED (no run evicted -- growth untrusted)")
                continue
            p = project_form_cost(c, args.project, args.model)
            if p["cost"] is None:
                print(f"  window {c['window']}: SKIPPED (no measured per-question series)")
                continue
            ratio = p["ratio_at_measured_len"]
            flag = "" if (ratio and 0.9 <= ratio <= 1.1) else "  <-- CHECK: fit off >10%"
            print(f"  window {c['window']} (trigger {c['trigger']}): "
                  f"${p['cost']:.2f} / {args.project}-q form  "
                  f"[growth~{c['growth_per_question']:.0f} tok/q, "
                  f"steady~{c['steady_textin_q']:.0f} tok/q, "
                  f"ratio={ratio:.2f}]{flag}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
