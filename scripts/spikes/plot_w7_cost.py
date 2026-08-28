"""Three plots for the W-7 deploy-fidelity cost measurement (bd polyglot-pdf-89mt).

    1. cost per field -- happy and unhappy together
    2. token burn by type -- happy
    3. token burn by type -- unhappy

Usage (repo root, backend venv):
    python scripts/spikes/plot_w7_cost.py scripts/spikes/data/89mt-w7-derived

EVERY run this reads must PROVE it is the configuration we intended. Two
measurements in this bead were retracted because an analysis silently read the
wrong run file -- once via a directory glob that alphabetically preferred a
non-compression run, once by comparing quantities that measure different things.
So this script:

  - takes an explicit directory and matches ONLY *_der_* files (the derived,
    deploy-fidelity runs), never a bare *happy* glob;
  - ASSERTS each run's meta["compression_effective"] shows derivation was on and
    reports the expected trigger, and REFUSES to plot otherwise;
  - prints the config it verified, so the plot and its provenance travel
    together.

ASCII only.
"""
from __future__ import annotations

import csv
import glob
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")  # headless: write files, never try to open a window
import matplotlib.pyplot as plt

EXPECTED_TRIGGER = 7526  # pre-registered; see the bead and the findings doc


def _load(data_dir: str, path_tag: str) -> tuple[dict, list[dict]]:
    """Return (meta, turn_rows) for the derived run of the given path."""
    metas = sorted(glob.glob(os.path.join(data_dir, f"*_der_{path_tag}_*.meta.json")))
    if not metas:
        raise SystemExit(
            f"No derived ({path_tag}) run in {data_dir}. Expected a file matching "
            f"*_der_{path_tag}_*.meta.json -- a run WITHOUT --derive-compression "
            "is not deploy-fidelity and must not be plotted."
        )
    meta = json.loads(open(metas[-1], encoding="utf-8").read())

    eff = meta.get("compression_effective") or {}
    if not eff.get("derived_from_si_floor"):
        raise SystemExit(
            f"{metas[-1]}: compression_effective says derivation was OFF "
            f"({eff!r}). This run does not describe the deployed config."
        )
    if eff.get("trigger_tokens") != EXPECTED_TRIGGER:
        raise SystemExit(
            f"{metas[-1]}: trigger was {eff.get('trigger_tokens')!r}, expected "
            f"{EXPECTED_TRIGGER}. The measurement config is not what the analysis "
            "assumes -- refusing to plot."
        )

    turns_path = metas[-1].replace(".meta.json", ".turns.csv")
    rows = list(csv.DictReader(open(turns_path, encoding="utf-8")))
    print(f"  {path_tag:8} verified: trigger={eff['trigger_tokens']} "
          f"window={eff['window_tokens']} floor={eff.get('si_floor_tokens')} "
          f"clamped={eff.get('clamped_to_api_minimum')} turns={len(rows)}")
    return meta, rows


def _per_field(rows: list[dict]) -> tuple[list[int], list[float], list[str]]:
    """Collapse turns to one cost per question, preserving field order."""
    order: list[str] = []
    cost: dict[str, float] = {}
    label: dict[str, str] = {}
    for r in rows:
        q = r["q"]
        if q not in cost:
            order.append(q)
            cost[q] = 0.0
            label[q] = r.get("field_id") or ""
        cost[q] += float(r["cost_usd"])
    return ([int(q) for q in order],
            [cost[q] for q in order],
            [label[q] for q in order])


def plot_cost_per_field(happy, unhappy, out_path):
    hq, hc, hlab = _per_field(happy)
    uq, uc, _ = _per_field(unhappy)
    fig, ax = plt.subplots(figsize=(12, 5.5))
    ax.plot(hq, hc, marker="o", linewidth=1.8, label="happy (2 turns/field)")
    ax.plot(uq, uc, marker="s", linewidth=1.8, label="unhappy (4 turns/field)")
    ax.set_xlabel("field (in the order asked)")
    ax.set_ylabel("cost for that field (USD)")
    ax.set_title("W-7 cost per field -- deploy-fidelity config "
                 f"(derived trigger {EXPECTED_TRIGGER} / window 6026)")
    ax.set_xticks(hq)
    ax.set_xticklabels([f"{n}\n{l[:14]}" for n, l in zip(hq, hlab)],
                       rotation=60, ha="right", fontsize=6.5)
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    print("wrote", out_path)


def plot_token_burn(rows, title, out_path):
    """Per-turn token burn split by modality, plus the context curve.

    THE TWO ARE NOT THE SAME QUANTITY and the labels must not imply they are:

      * the modality lines are BILLED TOKENS SUMMED OVER EVERY EVENT in the
        turn -- a turn averages ~2.1 billed events (a tool call re-sends the
        whole context), so text-in routinely runs 2-3x the context size;
      * the context line is ONE SAMPLE -- the context size reported by the
        LAST event of the turn -- which is what the compression window bounds.

    Plotting them on one axis without saying so reads as "the context spiked to
    17k", which it never does: it stays under 7.5k all run.
    """
    turns = [int(r["turn"]) for r in rows]
    series = [
        ("text in (summed over the turn's events)", [int(r["text_in"]) for r in rows]),
        ("audio in (summed)", [int(r["audio_in"]) for r in rows]),
        ("text out (summed)", [int(r["text_out"]) for r in rows]),
        ("audio out (summed)", [int(r["audio_out"]) for r in rows]),
    ]
    fig, ax = plt.subplots(figsize=(12, 5.5))
    for name, ys in series:
        ax.plot(turns, ys, marker=".", linewidth=1.5, label=name)
    prompt = [int(r["prompt_tokens"] or 0) for r in rows]
    ax.plot(turns, prompt, linewidth=1.6, linestyle="--", color="black",
            label="context size at end of turn (NOT a per-turn total)")
    ax.set_xlabel("turn")
    ax.set_ylabel("tokens")
    ax.set_title(title + "\nbilled = sum over ~2.1 events/turn; context is bounded by the 6,026 window",
                 fontsize=10)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    print("wrote", out_path)


def main() -> None:
    data_dir = sys.argv[1] if len(sys.argv) > 1 else "scripts/spikes/data/89mt-w7-derived"
    print(f"reading derived runs from {data_dir}")
    _, happy = _load(data_dir, "happy")
    _, unhappy = _load(data_dir, "unhappy")

    out = os.path.join(data_dir, "plots")
    os.makedirs(out, exist_ok=True)
    plot_cost_per_field(happy, unhappy, os.path.join(out, "w7_cost_per_field.png"))
    plot_token_burn(happy, "W-7 token burn by type -- HAPPY path",
                    os.path.join(out, "w7_token_burn_happy.png"))
    plot_token_burn(unhappy, "W-7 token burn by type -- UNHAPPY path",
                    os.path.join(out, "w7_token_burn_unhappy.png"))


if __name__ == "__main__":
    main()
