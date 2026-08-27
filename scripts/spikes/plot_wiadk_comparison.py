"""Five comparison charts for the W-7 naive-vs-deployed cost measurement
(bd polyglot-pdf-4loz, wiadk data set).

Reads the 6 runs committed under scripts/spikes/data/wiadk-full/:
  - deployed (dti+continuous+derived-compression) arm: 2 happy + 2 unhappy runs
  - naive (legacy full-schema SI, no compression) arm: 1 happy + 1 unhappy run

and writes 5 PNGs into scripts/spikes/data/wiadk-full/plots/:

  1. cumulative_cost_happy.png   -- cumulative all-in cost vs question, happy
  2. cumulative_cost_unhappy.png -- same, unhappy
  3. session_cost_bars.png       -- grouped bars, arm x path, all-in session cost
  4. modality_breakdown.png      -- stacked voice-cost modality shares, arm x path
  5. context_curve.png           -- per-event prompt tokens: sawtooth vs ramp+trim

Style borrowed from scripts/spikes/plot_w7_cost.py: headless Agg backend,
explicit file matching (never a bare glob that could silently prefer the
wrong run), and a printed provenance line for every run read.

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

DATA_DIR_DEFAULT = "scripts/spikes/data/wiadk-full"

# The Live API's observed hard context-length trim point for native-audio
# sessions (see the eviction_drops in the naive-arm metas: prompt fell from
# ~31.8-31.9k to ~27.9-28.0k at that point in both naive runs). Not a
# documented API constant -- an empirically observed platform behavior.
PLATFORM_TRIM_TOKENS = 32000

# The deployed arm's derived-compression config (from the meta files'
# compression_effective block), used to annotate the context_curve chart.
DEPLOYED_TRIGGER = 9517
DEPLOYED_WINDOW = 8017
DEPLOYED_FLOOR = 5766

# The cross-form proxy variance for the deployed-arm error bars: the i90-full
# E1 happy-path triplet (T055600Z/T061257Z/T062904Z; see
# scripts/spikes/systems_stress_findings.md section 3), a DIFFERENT form
# (113-question I-90, not this 22-question W-7) run under a similar
# dti+continuous+compression config. It stands in for "how much does all-in
# session cost vary run-to-run under this architecture" since the W-7 arm
# itself only has 2 replicates per path -- not enough to compute its own
# variance. This is a proxy, not a W-7-specific measurement; the chart labels
# it as such.
I90_E1_TRIPLET_USD = [2.425401, 2.416718, 2.486589]


def _cross_form_cv() -> float:
    mean = statistics.mean(I90_E1_TRIPLET_USD)
    sd = statistics.stdev(I90_E1_TRIPLET_USD)  # sample stdev, n=3
    cv = sd / mean
    print(f"  cross-form proxy CV from i90-full E1 triplet {I90_E1_TRIPLET_USD}: "
          f"mean=${mean:.4f} sd=${sd:.4f} CV={cv:.4f} ({cv*100:.2f}%)")
    return cv


def _load(data_dir: str, pattern: str, label: str) -> dict:
    """Load ONE meta.json matching pattern; refuse on 0 or >1 matches."""
    matches = sorted(glob.glob(os.path.join(data_dir, pattern)))
    if not matches:
        raise SystemExit(f"No file matching {pattern!r} in {data_dir} for {label}.")
    path = matches[-1]
    meta = json.loads(open(path, encoding="utf-8").read())
    # The bars use the headline all-in (voice + text sidecar, greeting as its
    # own separate line -- the SAME convention as the findings doc and the
    # 89mt-comparable numbers). turns.csv's cumulative_cost_usd seeds from the
    # greeting and excludes the text sidecar, so reading turns[-1] as "the
    # session cost" mixed conventions and drifted the naive endpoints ~1-2
    # cents high (fresh-eyes finding, bd polyglot-pdf-wiadk).
    summary_path = path.replace(".meta.json", ".summary.json")
    summary = json.loads(open(summary_path, encoding="utf-8").read())
    meta["_headline_all_in_usd"] = float(summary["headline"]["all_in_usd"])
    print(f"  {label:28} <- {os.path.basename(path)} "
          f"(arm={meta.get('arm')} path={meta.get('path')} "
          f"wall_clock_s={meta.get('wall_clock_s')} "
          f"all_in=${meta['_headline_all_in_usd']:.6f})")
    return meta


def load_all(data_dir: str) -> dict:
    print(f"reading wiadk runs from {data_dir}")
    runs = {
        "deployed_happy_1": _load(data_dir, "costs_w7_2.5_dti_cont_comp_der_happy_20260827T193603Z.meta.json", "deployed happy #1"),
        "deployed_happy_2": _load(data_dir, "costs_w7_2.5_dti_cont_comp_der_happy_20260827T193939Z.meta.json", "deployed happy #2"),
        "deployed_unhappy_1": _load(data_dir, "costs_w7_2.5_dti_cont_comp_der_unhappy_20260827T194334Z.meta.json", "deployed unhappy #1"),
        "deployed_unhappy_2": _load(data_dir, "costs_w7_2.5_dti_cont_comp_der_unhappy_20260827T195050Z.meta.json", "deployed unhappy #2"),
        "naive_happy": _load(data_dir, "costs_w7_2.5_naive_happy_20260827T193127Z.meta.json", "naive happy"),
        "naive_unhappy": _load(data_dir, "costs_w7_2.5_naive_unhappy_20260827T195815Z.meta.json", "naive unhappy"),
    }
    # Provenance assertions -- refuse to plot a run that isn't the config we
    # think it is. Mirrors plot_w7_cost.py's compression_effective checks.
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


def _turn_cumulative_cost(meta: dict) -> tuple[list[int], list[float]]:
    """Question index and running VOICE cost, one point per question (last
    turn seen for that q). turns.csv's cumulative_cost_usd is seeded with the
    greeting cost; subtract that seed so the curve shows question-driven
    accumulation in the same greeting-excluded convention as the headline
    numbers (the greeting is reported as its own line in the findings doc)."""
    greeting = float(meta.get("greeting_cost_usd") or 0.0)
    q_list: list[int] = []
    cost_list: list[float] = []
    seen: dict[int, float] = {}
    for t in meta["turns"]:
        seen[int(t["q"])] = float(t["cumulative_cost_usd"]) - greeting
    for q in sorted(seen):
        q_list.append(q)
        cost_list.append(seen[q])
    return q_list, cost_list


def _eviction_questions(meta: dict) -> list[int]:
    """Map eviction_drops (indexed by EVENT number) to the question number
    active at that point, for annotation on the cumulative-cost chart."""
    drops = meta.get("eviction_drops") or []
    if not drops:
        return []
    # events_mode/turns don't carry an explicit event->question map here, so
    # approximate: event index scales roughly with turn index; use the
    # fraction of the way through the event stream to place a vertical line
    # at the corresponding fraction of questions. This is an approximation
    # for annotation purposes only, not a claimed exact mapping.
    total_events = meta.get("cache_summary", {}).get("events") or 0
    n_questions = meta.get("questions") or 22
    out = []
    for drop in drops:
        event_idx = drop[0]
        if total_events:
            frac = event_idx / total_events
        else:
            frac = 0.0
        out.append(max(1, round(frac * n_questions)))
    return out


def plot_cumulative_cost(runs: dict, path_tag: str, out_path: str) -> None:
    dep1 = runs[f"deployed_{path_tag}_1"]
    dep2 = runs[f"deployed_{path_tag}_2"]
    naive = runs[f"naive_{path_tag}"]

    q1, c1 = _turn_cumulative_cost(dep1)
    q2, c2 = _turn_cumulative_cost(dep2)
    qn, cn = _turn_cumulative_cost(naive)

    # Mean of the two deployed runs (aligned by question index; both cover
    # the same 22 questions).
    assert q1 == q2, "deployed run question indices do not align"
    mean_c = [(a + b) / 2.0 for a, b in zip(c1, c2)]

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.plot(q1, c1, linewidth=1.0, color="#4C72B0", alpha=0.4)
    ax.plot(q2, c2, linewidth=1.0, color="#4C72B0", alpha=0.4)
    ax.plot(q1, mean_c, linewidth=2.6, color="#4C72B0",
            label=f"deployed config -- mean of 2 runs (final ${mean_c[-1]:.2f})")
    ax.plot(qn, cn, linewidth=2.6, color="#C44E52", marker="o", markersize=3,
            label=f"naive config -- 1 run (final ${cn[-1]:.2f})")

    # Annotate naive force-trim events (platform-side context eviction).
    trim_qs = _eviction_questions(naive)
    for i, tq in enumerate(sorted(set(trim_qs))):
        ax.axvline(tq, color="#C44E52", linestyle=":", alpha=0.5, linewidth=1.2)
        if tq in qn:
            y = cn[qn.index(tq)]
            ax.annotate("platform force-trim" if i == 0 else "",
                        xy=(tq, y), xytext=(tq + 0.3, y * 0.55 if y else 0.1),
                        fontsize=8, color="#C44E52")

    path_label = "Happy path (customer answers cleanly)" if path_tag == "happy" else \
                 "Unhappy path (customer corrects/backtracks)"
    ax.set_title(f"W-7 form: running cost as the conversation proceeds -- {path_label}",
                 fontsize=13)
    ax.set_xlabel("question number (1-22)")
    ax.set_ylabel("total cost so far, this session (USD)")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper left", fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print("wrote", out_path)


def plot_session_cost_bars(runs: dict, out_path: str) -> None:
    cv = _cross_form_cv()

    dep_happy = [runs["deployed_happy_1"]["_headline_all_in_usd"],
                 runs["deployed_happy_2"]["_headline_all_in_usd"]]
    dep_unhappy = [runs["deployed_unhappy_1"]["_headline_all_in_usd"],
                   runs["deployed_unhappy_2"]["_headline_all_in_usd"]]
    naive_happy = runs["naive_happy"]["_headline_all_in_usd"]
    naive_unhappy = runs["naive_unhappy"]["_headline_all_in_usd"]

    dep_happy_mean = statistics.mean(dep_happy)
    dep_unhappy_mean = statistics.mean(dep_unhappy)

    labels = ["Happy path", "Unhappy path"]
    dep_vals = [dep_happy_mean, dep_unhappy_mean]
    naive_vals = [naive_happy, naive_unhappy]
    dep_err = [dep_happy_mean * cv, dep_unhappy_mean * cv]

    x = range(len(labels))
    width = 0.32
    fig, ax = plt.subplots(figsize=(9, 6))
    bars_dep = ax.bar([i - width / 2 for i in x], dep_vals, width,
                       yerr=dep_err, capsize=6, color="#4C72B0",
                       label="Deployed config (mean of 2 runs)")
    bars_naive = ax.bar([i + width / 2 for i in x], naive_vals, width,
                         color="#C44E52", label="Naive config (1 run)")

    for bars, vals in ((bars_dep, dep_vals), (bars_naive, naive_vals)):
        for bar, v in zip(bars, vals):
            ax.annotate(f"${v:.2f}", xy=(bar.get_x() + bar.get_width() / 2, v),
                        xytext=(0, 4), textcoords="offset points",
                        ha="center", fontsize=10, fontweight="bold")

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_ylabel("total session cost, all-in (USD)")
    ax.set_title("W-7 form: total cost per completed session, deployed vs naive setup",
                 fontsize=13)
    ax.grid(alpha=0.3, axis="y")
    ax.legend(fontsize=9)
    fig.text(0.5, -0.02,
              f"Error bars on the deployed bars: +/-{cv*100:.1f}% run-to-run variability,\n"
              "a proxy measured on a different, larger form (I-90, 3 repeated runs) under "
              "a similar setup -- not measured on W-7 itself.",
              ha="center", fontsize=8, style="italic")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("wrote", out_path)


MODALITIES = [
    ("text_in", "text heard as instructions (text-in)", "#4C72B0"),
    ("audio_in", "customer's spoken answers (audio-in)", "#55A868"),
    ("text_out", "text the AI produces (text-out)", "#C44E52"),
    ("audio_out", "AI's spoken replies (audio-out)", "#8172B2"),
]


def _modality_cost(meta: dict) -> dict:
    rates = meta["rates_per_token"]
    totals = {"text_in": 0, "audio_in": 0, "text_out": 0, "audio_out": 0}
    for t in meta["turns"]:
        for k in totals:
            totals[k] += int(t[k])
    cost = {
        "text_in": totals["text_in"] * rates["text_input"],
        "audio_in": totals["audio_in"] * rates["audio_input"],
        "text_out": totals["text_out"] * rates["text_output"],
        "audio_out": totals["audio_out"] * rates["audio_output"],
    }
    return cost


def plot_modality_breakdown(runs: dict, out_path: str) -> None:
    groups = [
        ("Deployed\nhappy", [runs["deployed_happy_1"], runs["deployed_happy_2"]]),
        ("Deployed\nunhappy", [runs["deployed_unhappy_1"], runs["deployed_unhappy_2"]]),
        ("Naive\nhappy", [runs["naive_happy"]]),
        ("Naive\nunhappy", [runs["naive_unhappy"]]),
    ]

    per_group_cost = []
    for _, metas in groups:
        costs = [_modality_cost(m) for m in metas]
        avg = {k: statistics.mean(c[k] for c in costs) for k in costs[0]}
        per_group_cost.append(avg)

    fig, ax = plt.subplots(figsize=(10, 6.5))
    x = range(len(groups))
    bottoms = [0.0] * len(groups)
    for key, label, color in MODALITIES:
        vals = [per_group_cost[i][key] for i in range(len(groups))]
        ax.bar(list(x), vals, bottom=bottoms, label=label, color=color, width=0.6)
        for i, (v, b) in enumerate(zip(vals, bottoms)):
            if v > 0.03 * sum(per_group_cost[i].values()):
                ax.annotate(f"${v:.2f}", xy=(i, b + v / 2), ha="center",
                            va="center", fontsize=8, color="white", fontweight="bold")
        bottoms = [b + v for b, v in zip(bottoms, vals)]

    for i, total in enumerate(bottoms):
        ax.annotate(f"${total:.2f}", xy=(i, total), xytext=(0, 4),
                    textcoords="offset points", ha="center", fontsize=10, fontweight="bold")

    ax.set_xticks(list(x))
    ax.set_xticklabels([g[0] for g in groups], fontsize=10)
    ax.set_ylabel("voice-conversation cost (USD, average of the runs in that group)")
    ax.set_title("W-7 form: where the voice-conversation cost goes, by input/output type",
                 fontsize=13)
    ax.grid(alpha=0.3, axis="y")
    ax.legend(loc="upper left", fontsize=8.5, framealpha=0.9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print("wrote", out_path)


def plot_context_curve(runs: dict, out_path: str) -> None:
    dep1 = runs["deployed_happy_1"]
    dep2 = runs["deployed_happy_2"]
    naive = runs["naive_happy"]

    dep1_curve = dep1["prompt_curve"]
    dep2_curve = dep2["prompt_curve"]
    naive_curve = naive["prompt_curve"]

    fig, ax = plt.subplots(figsize=(12, 6.5))
    ax.plot(range(1, len(dep1_curve) + 1), dep1_curve, linewidth=1.3,
            color="#4C72B0", alpha=0.55, label="deployed, run #1")
    ax.plot(range(1, len(dep2_curve) + 1), dep2_curve, linewidth=1.3,
            color="#264478", alpha=0.85, label="deployed, run #2")
    ax.plot(range(1, len(naive_curve) + 1), naive_curve, linewidth=2.0,
            color="#C44E52", marker=".", markersize=4, label="naive, single run")

    ax.axhline(PLATFORM_TRIM_TOKENS, color="black", linestyle="--", linewidth=1.3,
                label=f"observed platform force-trim ceiling (~{PLATFORM_TRIM_TOKENS:,} tokens)")
    ax.axhline(DEPLOYED_TRIGGER, color="#4C72B0", linestyle=":", linewidth=1.1,
                label=f"deployed: compression triggers at {DEPLOYED_TRIGGER:,} tokens")
    ax.axhline(DEPLOYED_WINDOW, color="#4C72B0", linestyle="-.", linewidth=1.0,
                label=f"deployed: compresses back down to {DEPLOYED_WINDOW:,} tokens")

    # Annotate the naive run's two observed platform force-trims.
    for i, (event_idx, before, after) in enumerate(naive.get("eviction_drops", [])):
        if 1 <= event_idx <= len(naive_curve):
            ax.annotate("platform force-trim" if i == 0 else "",
                        xy=(event_idx, after), xytext=(event_idx + 1, after - 3500),
                        fontsize=8, color="#C44E52",
                        arrowprops=dict(arrowstyle="->", color="#C44E52", alpha=0.7))

    ax.set_title(
        "The heart of the cost difference: how big the conversation's memory gets, "
        "event by event",
        fontsize=12.5)
    ax.set_xlabel("event number within the session (voice turns + tool-call round-trips)")
    ax.set_ylabel("prompt size at that event (tokens)")
    ax.grid(alpha=0.3)
    ax.legend(loc="center right", fontsize=8.5, framealpha=0.92)
    fig.text(0.5, -0.02,
              "Deployed setup: a controlled compression step keeps the conversation's "
              "memory in a repeating sawtooth under 10k tokens.\n"
              "Naive setup: memory grows without bound until the platform itself "
              "silently force-trims it back near 28k -- a blunt, uncontrolled cut.",
              ha="center", fontsize=8.5, style="italic")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("wrote", out_path)


def main() -> None:
    data_dir = sys.argv[1] if len(sys.argv) > 1 else DATA_DIR_DEFAULT
    runs = load_all(data_dir)

    out = os.path.join(data_dir, "plots")
    os.makedirs(out, exist_ok=True)

    plot_cumulative_cost(runs, "happy", os.path.join(out, "cumulative_cost_happy.png"))
    plot_cumulative_cost(runs, "unhappy", os.path.join(out, "cumulative_cost_unhappy.png"))
    plot_session_cost_bars(runs, os.path.join(out, "session_cost_bars.png"))
    plot_modality_breakdown(runs, os.path.join(out, "modality_breakdown.png"))
    plot_context_curve(runs, os.path.join(out, "context_curve.png"))


if __name__ == "__main__":
    main()
