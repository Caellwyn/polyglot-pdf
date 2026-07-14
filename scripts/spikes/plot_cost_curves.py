"""
E1 cost-curve charts: marginal cost per question and cumulative cost, for the
three I-90 "happy path" continuous-session stress runs (bd polyglot-pdf-0cyu).

Reads the per-question cost CSVs + .meta.json (for reconnect markers) named
by the STAMPS constant below, and renders two SVGs under
scripts/spikes/data/charts/. Re-run after adding new runs by editing STAMPS.

Requires matplotlib (checked at import time; this repo's backend venv has it).
Stdlib + matplotlib only.
"""

import csv
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# ---------------------------------------------------------------------------
# Config -- edit this list to add/replace runs.
# ---------------------------------------------------------------------------

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CHARTS_DIR = os.path.join(DATA_DIR, "charts")

STAMPS = [
    "20260714T055600Z",
    "20260714T061257Z",
    "20260714T062904Z",
]

FILENAME_TMPL = "costs_i90-full_2.5_dti_cont_comp_happy_{stamp}.csv"
META_TMPL = "costs_i90-full_2.5_dti_cont_comp_happy_{stamp}.meta.json"

ROLLING_WINDOW = 11  # odd window, centered, for the bold rolling-mean line
FLAT_BAND_USD = 0.021  # annotated flat-band value (measured, see report)
FLAT_BAND_USD_REF = 0.0215  # linear-reference slope for the cumulative-cost chart

# dataviz skill palette (light theme, categorical slots 1/2/3: blue/aqua/yellow)
COLOR_RUN = ["#2a78d6", "#1baf7a", "#eda100"]
COLOR_MEAN = "#0b0b0b"       # primary ink -- bold rolling mean / reference line
COLOR_GRID = "#e1e0d9"       # hairline gridline
COLOR_AXIS = "#c3c2b7"       # baseline / axis
COLOR_MUTED = "#898781"      # axis/tick labels
COLOR_TEXT = "#0b0b0b"       # primary ink
COLOR_SECONDARY = "#52514e"  # secondary ink
SURFACE = "#fcfcfb"          # light chart surface

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Segoe UI", "Arial", "DejaVu Sans"],
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "axes.edgecolor": COLOR_AXIS,
    "axes.labelcolor": COLOR_SECONDARY,
    "text.color": COLOR_TEXT,
    "xtick.color": COLOR_MUTED,
    "ytick.color": COLOR_MUTED,
})


def load_run(stamp):
    """Return (question_numbers, total_costs) lists for one run's CSV."""
    path = os.path.join(DATA_DIR, FILENAME_TMPL.format(stamp=stamp))
    qs, costs = [], []
    with open(path, newline="", encoding="ascii") as f:
        reader = csv.DictReader(f)
        for row in reader:
            qs.append(int(row["question number"]))
            costs.append(float(row["total cost"]))
    return qs, costs


def load_reconnect_before_q(stamp):
    """Return list of before_q ints from continuous_reconnects in the meta.json."""
    path = os.path.join(DATA_DIR, META_TMPL.format(stamp=stamp))
    with open(path, encoding="ascii") as f:
        meta = json.load(f)
    return [r["before_q"] for r in meta.get("continuous_reconnects", [])]


def rolling_mean(values, window):
    """Centered simple rolling mean, shrinking window at the edges."""
    n = len(values)
    half = window // 2
    out = []
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        chunk = values[lo:hi]
        out.append(sum(chunk) / len(chunk))
    return out


def plot_marginal_cost():
    fig, ax = plt.subplots(figsize=(9.0, 5.2), dpi=150)

    all_costs_by_q = {}  # q -> list of costs across runs, for a pooled rolling mean
    reconnect_points = []  # (q, cost) markers for vertical ticks

    for i, stamp in enumerate(STAMPS):
        qs, costs = load_run(stamp)
        color = COLOR_RUN[i % len(COLOR_RUN)]
        ax.plot(
            qs, costs,
            color=color, linewidth=1.1, alpha=0.55,
            label=f"Run {i + 1} ({stamp})",
            zorder=2,
        )
        for q, c in zip(qs, costs):
            all_costs_by_q.setdefault(q, []).append(c)

        for before_q in load_reconnect_before_q(stamp):
            # locate the cost value at/near before_q for tick placement
            idx = min(range(len(qs)), key=lambda j: abs(qs[j] - before_q))
            reconnect_points.append((qs[idx], costs[idx], color))

    # Pooled rolling mean across all runs' per-question costs (mean per q, then
    # smoothed) -- this is the bold "flat marginal cost" line.
    q_sorted = sorted(all_costs_by_q)
    mean_per_q = [sum(all_costs_by_q[q]) / len(all_costs_by_q[q]) for q in q_sorted]
    smoothed = rolling_mean(mean_per_q, ROLLING_WINDOW)

    ax.plot(
        q_sorted, smoothed,
        color=COLOR_MEAN, linewidth=2.6, alpha=0.95,
        label=f"Rolling mean (window={ROLLING_WINDOW})",
        zorder=4,
        solid_capstyle="round",
    )

    # Flat-band annotation
    ax.axhline(FLAT_BAND_USD, color=COLOR_AXIS, linewidth=1.0, linestyle=(0, (4, 3)), zorder=1)
    ax.annotate(
        f"~${FLAT_BAND_USD:.3f}/question (flat band)",
        xy=(q_sorted[-1], FLAT_BAND_USD),
        xytext=(q_sorted[-1] - 2, FLAT_BAND_USD + 0.006),
        ha="right", va="bottom",
        fontsize=9.5, color=COLOR_SECONDARY,
    )

    # Reconnect tick marks -- subtle vertical ticks near the axis, not full-height
    y0, y1 = ax.get_ylim()
    tick_h = (y1 - y0) * 0.055
    for q, c, color in reconnect_points:
        ax.plot(
            [q, q], [y0, y0 + tick_h],
            color=color, linewidth=1.6, alpha=0.85, zorder=3,
            solid_capstyle="round",
        )
    if reconnect_points:
        # one shared label near the first tick group, kept out of the data
        ax.annotate(
            "| reconnect (per run)",
            xy=(reconnect_points[0][0], y0 + tick_h),
            xytext=(reconnect_points[0][0] + 2, y0 + tick_h * 2.4),
            fontsize=8.5, color=COLOR_MUTED,
        )

    ax.set_title(
        "Marginal cost per question is FLAT across the full I-90 (3 runs)",
        fontsize=13, color=COLOR_TEXT, fontweight="bold", pad=14,
    )
    ax.set_xlabel("Question number", fontsize=10.5)
    ax.set_ylabel("USD per question", fontsize=10.5)
    ax.set_xlim(1, 113)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("$%.3f"))
    ax.grid(True, axis="y", color=COLOR_GRID, linewidth=0.7, zorder=0)
    ax.grid(False, axis="x")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(COLOR_AXIS)
    ax.spines["bottom"].set_color(COLOR_AXIS)

    ax.legend(
        loc="upper left", frameon=False, fontsize=9, labelcolor=COLOR_SECONDARY,
    )

    fig.tight_layout()
    out_path = os.path.join(CHARTS_DIR, "e1_marginal_cost_per_question.svg")
    fig.savefig(out_path, format="svg")
    plt.close(fig)
    return out_path, smoothed


def plot_cumulative_cost():
    fig, ax = plt.subplots(figsize=(9.0, 5.2), dpi=150)

    max_q = 0
    for i, stamp in enumerate(STAMPS):
        qs, costs = load_run(stamp)
        cum = []
        running = 0.0
        for c in costs:
            running += c
            cum.append(running)
        color = COLOR_RUN[i % len(COLOR_RUN)]
        ax.plot(
            qs, cum,
            color=color, linewidth=1.8, alpha=0.85,
            label=f"Run {i + 1} ({stamp})",
            zorder=3,
        )
        max_q = max(max_q, max(qs))

    # Dashed linear reference line: 0.0215 * q
    ref_q = list(range(1, max_q + 1))
    ref_y = [FLAT_BAND_USD_REF * q for q in ref_q]
    ax.plot(
        ref_q, ref_y,
        color=COLOR_MEAN, linewidth=1.6, linestyle=(0, (6, 4)), alpha=0.9,
        label=f"Linear reference ({FLAT_BAND_USD_REF:.4f} x q)",
        zorder=2,
    )

    ax.set_title(
        "Cumulative cost is linear in form length",
        fontsize=13, color=COLOR_TEXT, fontweight="bold", pad=14,
    )
    ax.set_xlabel("Question number", fontsize=10.5)
    ax.set_ylabel("Cumulative USD", fontsize=10.5)
    ax.set_xlim(1, max_q)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("$%.2f"))
    ax.grid(True, axis="y", color=COLOR_GRID, linewidth=0.7, zorder=0)
    ax.grid(False, axis="x")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(COLOR_AXIS)
    ax.spines["bottom"].set_color(COLOR_AXIS)

    ax.legend(
        loc="upper left", frameon=False, fontsize=9, labelcolor=COLOR_SECONDARY,
    )

    fig.tight_layout()
    out_path = os.path.join(CHARTS_DIR, "e1_cumulative_cost.svg")
    fig.savefig(out_path, format="svg")
    plt.close(fig)
    return out_path


def main():
    os.makedirs(CHARTS_DIR, exist_ok=True)
    p1, smoothed = plot_marginal_cost()
    p2 = plot_cumulative_cost()
    print("wrote:", p1)
    print("wrote:", p2)
    print("rolling-mean flat-band range: min=%.5f max=%.5f mean=%.5f" % (
        min(smoothed), max(smoothed), sum(smoothed) / len(smoothed)
    ))


if __name__ == "__main__":
    main()
