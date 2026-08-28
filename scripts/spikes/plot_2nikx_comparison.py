"""Four comparison charts for the i90-v2 naive-vs-deployed cost measurement
(bd polyglot-pdf-2nikx, 2nikx data set), plus the cross-form W-7-vs-i90-v2
"moat widens" bar chart.

Reads the runs committed under scripts/spikes/data/2nikx-full/ (deployed:
4 happy + 3 unhappy runs, of which 2 happy + 2 unhappy are the valid measured
runs used for the headline numbers -- the rest are method-development
diagnostics excluded per the findings doc) and scripts/spikes/data/wiadk-full/
(the W-7 study, for the cross-form bar chart), and writes 4 PNGs into
scripts/spikes/data/2nikx-full/plots/:

  1. cumulative_cost_happy.png   -- cumulative all-in cost vs question, happy,
                                    deployed-mean vs naive (2 platform
                                    force-trims annotated)
  2. cumulative_cost_unhappy.png -- same, unhappy; naive line ENDS at q39
                                    (model wedged, run aborted -- the line
                                    stopping short is the point)
  3. session_cost_bars.png       -- grouped bars, 4 arms x 2 forms (W-7 +
                                    i90-v2 side by side); naive-unhappy i90-v2
                                    bar is hatched and labeled DID NOT COMPLETE
  4. cost_per_confirmed_field.png -- per-confirmed-field cost bars, both forms

This is a SIBLING of plot_wiadk_comparison.py, not an extension of it: the
two scripts share no code (the wiadk script only writes into its own
wiadk-full/plots/ and its per-form constants -- PLATFORM_TRIM_TOKENS,
DEPLOYED_TRIGGER/WINDOW/FLOOR, the I90_E1_TRIPLET_USD proxy -- are specific to
that 22-question form and that run set). The i90-v2 run set has its own
compression config, its own eviction geometry, a 57-question axis, and an
aborted unhappy run with no natural "final point" to draw a line through --
different enough shapes that copy-and-adjust would have obscured more than it
shared. What IS reused is the _load-with-provenance-assertion pattern and the
overall plotting style (headless Agg, explicit file matching, printed
provenance for every run read).

ASCII only.
"""
from __future__ import annotations

import glob
import json
import os
import statistics
import sys

import matplotlib
matplotlib.use("Agg")  # headless: write files, never try to open a window
import matplotlib.pyplot as plt

DATA_DIR_DEFAULT = "scripts/spikes/data/2nikx-full"
W7_DATA_DIR_DEFAULT = "scripts/spikes/data/wiadk-full"

# The i90-v2 deployed arm's derived-compression config (from the meta files'
# compression_effective block), used for provenance assertions.
DEPLOYED_TRIGGER = 10890
DEPLOYED_WINDOW = 9390

N_QUESTIONS = 57


def _load(data_dir: str, pattern: str, label: str) -> dict:
    """Load ONE meta.json matching pattern; refuse on 0 or >1 matches."""
    matches = sorted(glob.glob(os.path.join(data_dir, pattern)))
    if len(matches) != 1:
        raise SystemExit(
            f"Expected exactly 1 file matching {pattern!r} in {data_dir} for "
            f"{label}, found {len(matches)}: {matches}"
        )
    path = matches[0]
    meta = json.loads(open(path, encoding="utf-8").read())
    # Headline all-in cost (voice + text sidecar, greeting as its own
    # separate line) -- the same convention as the findings doc, read from
    # summary.json's headline block rather than turns.csv's
    # cumulative_cost_usd (which seeds from the greeting and excludes the
    # text sidecar -- see plot_wiadk_comparison.py's _load docstring for the
    # drift this caused, bd polyglot-pdf-wiadk).
    summary_path = path.replace(".meta.json", ".summary.json")
    summary = json.loads(open(summary_path, encoding="utf-8").read())
    meta["_headline"] = summary["headline"]
    meta["_headline_all_in_usd"] = float(summary["headline"]["all_in_usd"])
    print(f"  {label:28} <- {os.path.basename(path)} "
          f"(arm={meta.get('arm')} path={meta.get('path')} "
          f"wall_clock_s={meta.get('wall_clock_s')} "
          f"steps={summary['headline'].get('steps')} "
          f"matched={summary['headline']['fill_accuracy']['matched']}/"
          f"{summary['headline']['fill_accuracy']['total']} "
          f"all_in=${meta['_headline_all_in_usd']:.6f})")
    return meta


def load_all(data_dir: str) -> dict:
    print(f"reading 2nikx runs from {data_dir}")
    runs = {
        # The two VALID deployed happy runs (all_in ~$2.04/$2.07, 48/57
        # matched). The other two happy files in this dir (T013010Z at
        # matched=1, T020339Z at matched=14) are method-development
        # diagnostics -- excluded here, not loaded at all.
        "deployed_happy_1": _load(data_dir, "costs_i90-v2_2.5_dti_cont_comp_der_happy_20260828T021631Z.meta.json", "deployed happy #1"),
        "deployed_happy_2": _load(data_dir, "costs_i90-v2_2.5_dti_cont_comp_der_happy_20260828T022519Z.meta.json", "deployed happy #2"),
        # The two VALID deployed unhappy runs (all_in ~$4.27/$4.05, 48/57
        # matched). The third unhappy file (T024500Z, steps=33, matched=12)
        # is a guard-aborted desync diagnostic -- excluded, not loaded.
        "deployed_unhappy_1": _load(data_dir, "costs_i90-v2_2.5_dti_cont_comp_der_unhappy_20260828T030509Z.meta.json", "deployed unhappy #1"),
        "deployed_unhappy_2": _load(data_dir, "costs_i90-v2_2.5_dti_cont_comp_der_unhappy_20260828T032527Z.meta.json", "deployed unhappy #2"),
        "naive_happy": _load(data_dir, "costs_i90-v2_2.5_naive_happy_20260828T034310Z.meta.json", "naive happy"),
        "naive_unhappy": _load(data_dir, "costs_i90-v2_2.5_naive_unhappy_20260828T035215Z.meta.json", "naive unhappy"),
    }
    # Provenance assertions -- refuse to plot a run that isn't the config we
    # think it is (mirrors plot_wiadk_comparison.py's checks).
    for key in ("deployed_happy_1", "deployed_happy_2", "deployed_unhappy_1", "deployed_unhappy_2"):
        eff = runs[key].get("compression_effective") or {}
        if not eff.get("derived_from_si_floor"):
            raise SystemExit(f"{key}: compression_effective shows derivation OFF ({eff!r}).")
        if eff.get("trigger_tokens") != DEPLOYED_TRIGGER or eff.get("window_tokens") != DEPLOYED_WINDOW:
            raise SystemExit(
                f"{key}: trigger/window {eff.get('trigger_tokens')}/{eff.get('window_tokens')} "
                f"!= expected {DEPLOYED_TRIGGER}/{DEPLOYED_WINDOW}."
            )
    for key in ("naive_happy", "naive_unhappy"):
        if runs[key].get("compression"):
            raise SystemExit(f"{key}: compression is ON -- this is not the naive arm.")
    return runs


def load_w7(data_dir: str) -> dict:
    """Load the W-7 study's 6 runs, for the cross-form bar chart only. Same
    provenance assertions as plot_wiadk_comparison.py."""
    print(f"reading wiadk (W-7) runs from {data_dir}")
    runs = {
        "deployed_happy_1": _load(data_dir, "costs_w7_2.5_dti_cont_comp_der_happy_20260827T193603Z.meta.json", "W-7 deployed happy #1"),
        "deployed_happy_2": _load(data_dir, "costs_w7_2.5_dti_cont_comp_der_happy_20260827T193939Z.meta.json", "W-7 deployed happy #2"),
        "deployed_unhappy_1": _load(data_dir, "costs_w7_2.5_dti_cont_comp_der_unhappy_20260827T194334Z.meta.json", "W-7 deployed unhappy #1"),
        "deployed_unhappy_2": _load(data_dir, "costs_w7_2.5_dti_cont_comp_der_unhappy_20260827T195050Z.meta.json", "W-7 deployed unhappy #2"),
        "naive_happy": _load(data_dir, "costs_w7_2.5_naive_happy_20260827T193127Z.meta.json", "W-7 naive happy"),
        "naive_unhappy": _load(data_dir, "costs_w7_2.5_naive_unhappy_20260827T195815Z.meta.json", "W-7 naive unhappy"),
    }
    for key in ("deployed_happy_1", "deployed_happy_2", "deployed_unhappy_1", "deployed_unhappy_2"):
        eff = runs[key].get("compression_effective") or {}
        if not eff.get("derived_from_si_floor"):
            raise SystemExit(f"W-7 {key}: compression_effective shows derivation OFF ({eff!r}).")
    for key in ("naive_happy", "naive_unhappy"):
        if runs[key].get("compression"):
            raise SystemExit(f"W-7 {key}: compression is ON -- this is not the naive arm.")
    return runs


def _turn_cumulative_cost(meta: dict) -> tuple[list[int], list[float]]:
    """Question index and running VOICE cost, one point per question (last
    turn seen for that q). turns.csv's cumulative_cost_usd is seeded with the
    greeting cost; subtract that seed so the curve shows question-driven
    accumulation in the same greeting-excluded convention as the headline
    numbers."""
    greeting = float(meta.get("greeting_cost_usd") or 0.0)
    seen: dict[int, float] = {}
    for t in meta["turns"]:
        seen[int(t["q"])] = float(t["cumulative_cost_usd"]) - greeting
    q_list = sorted(seen)
    cost_list = [seen[q] for q in q_list]
    return q_list, cost_list


def _eviction_questions(meta: dict) -> list[int]:
    """Map eviction_drops (indexed by EVENT number) to the question number
    active at that point, for annotation on the cumulative-cost chart. An
    approximation (event index scaled by fraction-of-total-events onto the
    question axis), same method as plot_wiadk_comparison.py."""
    drops = meta.get("eviction_drops") or []
    if not drops:
        return []
    total_events = meta.get("cache_summary", {}).get("events") or 0
    n_questions = meta.get("questions") or N_QUESTIONS
    out = []
    for drop in drops:
        event_idx = drop[0]
        frac = (event_idx / total_events) if total_events else 0.0
        out.append(max(1, round(frac * n_questions)))
    return out


def plot_cumulative_cost_happy(runs: dict, out_path: str) -> None:
    dep1 = runs["deployed_happy_1"]
    dep2 = runs["deployed_happy_2"]
    naive = runs["naive_happy"]

    q1, c1 = _turn_cumulative_cost(dep1)
    q2, c2 = _turn_cumulative_cost(dep2)
    qn, cn = _turn_cumulative_cost(naive)

    assert q1 == q2, "deployed run question indices do not align"
    mean_c = [(a + b) / 2.0 for a, b in zip(c1, c2)]

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.plot(q1, c1, linewidth=1.0, color="#4C72B0", alpha=0.4)
    ax.plot(q2, c2, linewidth=1.0, color="#4C72B0", alpha=0.4)
    ax.plot(q1, mean_c, linewidth=2.6, color="#4C72B0",
            label=f"deployed config -- mean of 2 runs (final ${mean_c[-1]:.2f})")
    ax.plot(qn, cn, linewidth=2.6, color="#C44E52", marker="o", markersize=3,
            label=f"naive config -- 1 run (final ${cn[-1]:.2f})")

    trim_qs = _eviction_questions(naive)
    for i, tq in enumerate(sorted(set(trim_qs))):
        ax.axvline(tq, color="#C44E52", linestyle=":", alpha=0.5, linewidth=1.2)
        if tq in qn:
            y = cn[qn.index(tq)]
            ax.annotate("platform force-trim" if i == 0 else "",
                        xy=(tq, y), xytext=(tq + 0.4, y * 0.6 if y else 0.2),
                        fontsize=8, color="#C44E52")

    ax.set_title(
        "I-90 (v2) form, 57 questions: running cost as the conversation "
        "proceeds -- Happy path (customer answers cleanly)",
        fontsize=12.5)
    ax.set_xlabel("question number (1-57)")
    ax.set_ylabel("total cost so far, this session (USD)")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper left", fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print("wrote", out_path)


def plot_cumulative_cost_unhappy(runs: dict, out_path: str) -> None:
    dep1 = runs["deployed_unhappy_1"]
    dep2 = runs["deployed_unhappy_2"]
    naive = runs["naive_unhappy"]

    q1, c1 = _turn_cumulative_cost(dep1)
    q2, c2 = _turn_cumulative_cost(dep2)
    qn, cn = _turn_cumulative_cost(naive)  # qn ends at 39, NOT 57 -- the point

    assert q1 == q2, "deployed run question indices do not align"
    mean_c = [(a + b) / 2.0 for a, b in zip(c1, c2)]

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.plot(q1, c1, linewidth=1.0, color="#4C72B0", alpha=0.4)
    ax.plot(q2, c2, linewidth=1.0, color="#4C72B0", alpha=0.4)
    ax.plot(q1, mean_c, linewidth=2.6, color="#4C72B0",
            label=f"deployed config -- mean of 2 runs, all 57 questions "
                  f"(final ${mean_c[-1]:.2f})")
    # Naive line ends at q39 -- it does NOT reach q57. Draw it stopping short,
    # then mark the stop point explicitly; do not extend or interpolate.
    ax.plot(qn, cn, linewidth=2.6, color="#C44E52", marker="o", markersize=3,
            label=f"naive config -- 1 run, ABORTED at q39/57 (spent ${cn[-1]:.2f})")
    ax.scatter([qn[-1]], [cn[-1]], color="#C44E52", s=90, zorder=5,
               edgecolor="black", linewidth=1.0)

    trim_qs = _eviction_questions(naive)
    for i, tq in enumerate(sorted(set(trim_qs))):
        ax.axvline(tq, color="#C44E52", linestyle=":", alpha=0.5, linewidth=1.2)
        if tq in qn:
            y = cn[qn.index(tq)]
            ax.annotate("platform force-trim" if i == 0 else "",
                        xy=(tq, y), xytext=(tq + 0.4, y * 0.5 if y else 0.2),
                        fontsize=8, color="#C44E52")

    # The headline annotation: the line stopping short IS the chart's point.
    ax.annotate(
        "model wedged -- run aborted here\n(33/57 fields confirmed, 58%)",
        xy=(qn[-1], cn[-1]), xytext=(qn[-1] - 22, cn[-1] - 1.05),
        fontsize=9.5, fontweight="bold", color="#8B0000",
        arrowprops=dict(arrowstyle="->", color="#8B0000", linewidth=1.4))
    # Shade the region past q39 the naive run never reached.
    ax.axvspan(qn[-1], 57, color="#C44E52", alpha=0.06)
    ax.text(57, ax.get_ylim()[1] * 0.03, "never reached\n(18 questions)",
            ha="right", va="bottom", fontsize=8, color="#8B0000", style="italic")

    ax.set_title(
        "I-90 (v2) form, 57 questions: running cost as the conversation "
        "proceeds -- Unhappy path (customer corrects/backtracks)",
        fontsize=12.5)
    ax.set_xlabel("question number (1-57)")
    ax.set_ylabel("total cost so far, this session (USD)")
    ax.set_xlim(0, 58)
    ax.set_ylim(0, 7.3)
    ax.grid(alpha=0.3)
    ax.legend(loc="upper left", fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print("wrote", out_path)


def plot_session_cost_bars(runs_2nikx: dict, runs_w7: dict, out_path: str) -> None:
    """Grouped bars, 4 arms x 2 forms -- the 'moat widens' visual. The naive
    i90-v2 unhappy bar is hatched and labeled DID NOT COMPLETE since that run
    never reached the end of the form (aborted at q39/57)."""

    def means(runs):
        dep_happy = statistics.mean([runs["deployed_happy_1"]["_headline_all_in_usd"],
                                      runs["deployed_happy_2"]["_headline_all_in_usd"]])
        dep_unhappy = statistics.mean([runs["deployed_unhappy_1"]["_headline_all_in_usd"],
                                        runs["deployed_unhappy_2"]["_headline_all_in_usd"]])
        naive_happy = runs["naive_happy"]["_headline_all_in_usd"]
        naive_unhappy = runs["naive_unhappy"]["_headline_all_in_usd"]
        return dep_happy, dep_unhappy, naive_happy, naive_unhappy

    w7_dep_h, w7_dep_u, w7_naive_h, w7_naive_u = means(runs_w7)
    i90_dep_h, i90_dep_u, i90_naive_h, i90_naive_u = means(runs_2nikx)

    forms = ["W-7\n(22 questions)", "I-90 v2\n(57 questions)"]
    arms = [
        ("Deployed, happy", "#4C72B0", [w7_dep_h, i90_dep_h], [False, False]),
        ("Deployed, unhappy", "#264478", [w7_dep_u, i90_dep_u], [False, False]),
        ("Naive, happy", "#DD8452", [w7_naive_h, i90_naive_h], [False, False]),
        ("Naive, unhappy", "#C44E52", [w7_naive_u, i90_naive_u], [False, True]),
    ]

    n_forms = len(forms)
    n_arms = len(arms)
    width = 0.19
    x = list(range(n_forms))

    fig, ax = plt.subplots(figsize=(11.5, 6.5))
    ax.set_xlim(-0.75, n_forms - 1 + 0.75)
    for i, (label, color, vals, hatched) in enumerate(arms):
        offset = (i - (n_arms - 1) / 2.0) * width
        xs = [xi + offset for xi in x]
        hatch_pattern = ["//" if h else None for h in hatched]
        bars = ax.bar(xs, vals, width, color=color, label=label, edgecolor="black",
                       linewidth=0.6)
        for bar, h, v in zip(bars, hatched, vals):
            if h:
                bar.set_hatch("//")
                bar.set_edgecolor("#8B0000")
                bar.set_linewidth(1.4)
        for xi, v, h in zip(xs, vals, hatched):
            label_txt = f"${v:.2f}"
            ax.annotate(label_txt, xy=(xi, v), xytext=(0, 4),
                        textcoords="offset points", ha="center", fontsize=9,
                        fontweight="bold")
            if h:
                ax.annotate("DID NOT\nCOMPLETE\n(q39/57)",
                            xy=(xi, v), xytext=(0, -32),
                            textcoords="offset points", ha="center", fontsize=7.5,
                            color="white", fontweight="bold", linespacing=1.3)

    ax.set_xticks(x)
    ax.set_xticklabels(forms, fontsize=11)
    ax.set_ylabel("total session cost, all-in (USD)")
    ax.set_ylim(0, 7.0)
    ax.set_title(
        "The moat widens with form size: total session cost, deployed vs "
        "naive setup, W-7 vs I-90 (v2)",
        fontsize=12.5)
    ax.grid(alpha=0.3, axis="y")
    ax.legend(fontsize=9, loc="upper left")
    fig.text(0.5, -0.02,
              "Bars are the mean of 2 runs for the deployed arms (happy and "
              "unhappy) and a single run for each naive arm.\n"
              "The naive I-90 (v2) unhappy run is hatched: it spent $5.91 "
              "over 35 minutes without reaching the end of the form -- the "
              "model went tool-silent and an automated guard aborted the run.",
              ha="center", fontsize=8, style="italic")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("wrote", out_path)


def plot_cost_per_confirmed_field(runs_2nikx: dict, runs_w7: dict, out_path: str) -> None:
    """Per-confirmed-field cost bars, both forms. Uses the headline's
    precomputed usd_per_correct_field (cost / matched-fields), which for the
    aborted naive-unhappy i90-v2 run divides the $5.91 spent by only the 24
    fields it managed to confirm before wedging -- worth calling out
    explicitly since it is not comparable to a completed run's per-field
    cost in the usual sense."""

    def per_field(meta):
        h = meta["_headline"]
        return float(h["usd_per_correct_field"]), h["fill_accuracy"]["matched"], h["fill_accuracy"]["total"]

    groups = [
        ("W-7\ndeployed\nhappy", runs_w7["deployed_happy_1"], runs_w7["deployed_happy_2"]),
        ("W-7\ndeployed\nunhappy", runs_w7["deployed_unhappy_1"], runs_w7["deployed_unhappy_2"]),
        ("W-7\nnaive\nhappy", runs_w7["naive_happy"], None),
        ("W-7\nnaive\nunhappy", runs_w7["naive_unhappy"], None),
        ("I-90v2\ndeployed\nhappy", runs_2nikx["deployed_happy_1"], runs_2nikx["deployed_happy_2"]),
        ("I-90v2\ndeployed\nunhappy", runs_2nikx["deployed_unhappy_1"], runs_2nikx["deployed_unhappy_2"]),
        ("I-90v2\nnaive\nhappy", runs_2nikx["naive_happy"], None),
        ("I-90v2\nnaive\nunhappy", runs_2nikx["naive_unhappy"], None),
    ]

    vals = []
    detail = []
    hatched = []
    for label, m1, m2 in groups:
        if m2 is not None:
            v1, matched1, total1 = per_field(m1)
            v2, matched2, total2 = per_field(m2)
            vals.append(statistics.mean([v1, v2]))
            detail.append(f"{matched1}+{matched2}/{total1+total2} fields (2 runs)")
            hatched.append(False)
        else:
            v1, matched1, total1 = per_field(m1)
            vals.append(v1)
            detail.append(f"{matched1}/{total1} fields")
            hatched.append(label.startswith("I-90v2\nnaive\nunhappy"))

    colors = ["#4C72B0", "#264478", "#DD8452", "#C44E52"] * 2
    x = list(range(len(groups)))

    fig, ax = plt.subplots(figsize=(13, 6.5))
    bars = ax.bar(x, vals, color=colors, edgecolor="black", linewidth=0.6, width=0.65)
    for bar, h in zip(bars, hatched):
        if h:
            bar.set_hatch("//")
            bar.set_edgecolor("#8B0000")
            bar.set_linewidth(1.4)

    ax.set_ylim(0, max(vals) * 1.22)
    for xi, v, d, h in zip(x, vals, detail, hatched):
        ax.annotate(f"${v:.3f}\n{d}" + (" (aborted run)" if h else ""),
                    xy=(xi, v), xytext=(0, 6),
                    textcoords="offset points", ha="center", va="bottom",
                    fontsize=9.5 if not h else 8.5, fontweight="bold",
                    color="black" if not h else "#8B0000", linespacing=1.6)

    # Visual divider between the two forms.
    ax.axvline(3.5, color="black", linestyle="-", linewidth=1.0, alpha=0.5)

    ax.set_xticks(x)
    ax.set_xticklabels([g[0] for g in groups], fontsize=9)
    ax.set_ylabel("cost per confirmed field (USD)")
    ax.set_title(
        "Cost per correctly confirmed field: deployed vs naive, both forms",
        fontsize=12.5)
    ax.grid(alpha=0.3, axis="y")
    fig.text(0.5, -0.06,
              "Deployed bars are the mean of 2 runs; naive bars are a single "
              "run. The hatched I-90 (v2) naive-unhappy bar divides its "
              "$5.91 spend by only the 24 fields\nit confirmed before the "
              "run was aborted at question 39 of 57 -- not comparable to a "
              "completed run's per-field cost.",
              ha="center", fontsize=8, style="italic")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("wrote", out_path)


def main() -> None:
    data_dir = sys.argv[1] if len(sys.argv) > 1 else DATA_DIR_DEFAULT
    w7_data_dir = sys.argv[2] if len(sys.argv) > 2 else W7_DATA_DIR_DEFAULT

    runs = load_all(data_dir)
    runs_w7 = load_w7(w7_data_dir)

    out = os.path.join(data_dir, "plots")
    os.makedirs(out, exist_ok=True)

    plot_cumulative_cost_happy(runs, os.path.join(out, "cumulative_cost_happy.png"))
    plot_cumulative_cost_unhappy(runs, os.path.join(out, "cumulative_cost_unhappy.png"))
    plot_session_cost_bars(runs, runs_w7, os.path.join(out, "session_cost_bars.png"))
    plot_cost_per_confirmed_field(runs, runs_w7, os.path.join(out, "cost_per_confirmed_field.png"))


if __name__ == "__main__":
    main()
