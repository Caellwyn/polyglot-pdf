"""Analysis library for the sprint-4 cost matrix (bd polyglot-pdf-6x1y).

ALL computation for the cost-analysis notebook lives HERE, in reviewable
functions, so an adversarial fresh-eyes pass can verify the math against the
raw data BEFORE any analysis prose is built on the outputs (maintainer gate,
2026-06-12). The notebook (`cost_matrix_analysis.ipynb`) only calls this
module and renders.

Inputs: the bd-wyhh matrix under scripts/spikes/data/ -- 12 cells of
`costs_<model>_<arm>_<path>_<stamp>.csv` (per-question, 11 columns) +
`.meta.json` sidecars (per-turn latency, per-question tools, prompt curves,
eviction drops, errors). Ground truth for every number here is those files.

Data-validity rules (encoded, not hand-waved):
  - A question is INVALID when ALL of its turns stalled (the session was dead
    for the whole question; its row is a ~0-token artifact). This covers both
    the GoAway-truncated 3.1 cells (dead from ~q13 to the end) and the 2.5
    section-reset 1006 patch (q16-17 dead, q18-20 recovered after the next
    section restart -- a from-q-onward rule would wrongly drop the recovery).
  - A question with SOME stalled turns is flagged `degraded` but kept (its
    costs are real, just under-counted).
  - Section-reset "eviction drops" are session-restart curve resets, never
    compression; they are labeled `restart` in the curves table.

Token model for what-if scenarios (calibrated, both anchors measured):
  prompt_tokens(turn 1) ~= CHAR_RATE * si_chars + FIXED_OVERHEAD
  where CHAR_RATE and FIXED_OVERHEAD are solved from two measured pairs:
  the full-form turn-1 prompt (8,165 tok @ 25,632 SI chars) and the 3.1
  section-2 restart greeting (2,311 tok @ 3,831 SI chars). FIXED_OVERHEAD
  (~1.28k tok) is the tool declarations + initiating message, consistent with
  the h04c with-tools floor (~1,137 tok before the initiating message).
"""

from __future__ import annotations

import json
import re
import statistics
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"
SCHEMA_PATH = (Path(__file__).resolve().parent.parent.parent
               / "frontend" / "public" / "adult_intake_demo_schema.json")

# Per-1M USD list prices, mirrored from backend/config.py GEMINI_PRICING_BY_FAMILY
# (verified vs Google's page 2026-06-12). Mirrored as literals so the notebook
# has no backend import side effects; the loader CHECKS them against the CSVs.
RATES = {
    "2.5": {"text_input": 0.50, "audio_input": 3.00, "text_output": 2.00, "audio_output": 12.00},
    "3.1": {"text_input": 0.75, "audio_input": 3.00, "text_output": 4.50, "audio_output": 12.00},
}

# Measured calibration anchors (see module docstring).
_ANCHOR_FULL = (25_632, 8_165)   # (SI chars, turn-1 prompt tokens), full-form arm
_ANCHOR_SECTION = (3_831, 2_311)  # 3.1 section-2 restart greeting
CHAR_RATE = (_ANCHOR_FULL[1] - _ANCHOR_SECTION[1]) / (_ANCHOR_FULL[0] - _ANCHOR_SECTION[0])
FIXED_OVERHEAD = _ANCHOR_SECTION[1] - CHAR_RATE * _ANCHOR_SECTION[0]

CSV_COLUMNS = [
    "question number",
    "audio in tokens", "audio in token cost",
    "audio out tokens", "audio out token cost",
    "text in tokens", "text in token cost",
    "text out tokens", "text out token cost",
    "total tokens", "total cost",
]

_NAME_RE = re.compile(r"costs_(?P<model>[\d.]+)_(?P<arm>[\w-]+)_(?P<path>\w+)_(?P<stamp>\w+)\.csv$")


def si_tokens_from_chars(si_chars: float) -> float:
    """Estimated turn-1 prompt tokens for a given system-instruction size."""
    return CHAR_RATE * si_chars + FIXED_OVERHEAD


# --------------------------------------------------------------------- loading

def _cell_frames(csv_path: Path):
    m = _NAME_RE.search(csv_path.name)
    if not m:
        raise ValueError(f"unrecognized data file name: {csv_path.name}")
    key = m.groupdict()
    meta = json.loads(csv_path.with_suffix("").with_suffix("").name and
                      (csv_path.parent / (csv_path.stem + ".meta.json")).read_text(encoding="utf-8"))
    qdf = pd.read_csv(csv_path)
    if list(qdf.columns) != CSV_COLUMNS or len(qdf) != 20:
        raise ValueError(f"CSV shape contract violated: {csv_path.name}")

    turns = pd.DataFrame(meta["turns"])
    # Per-question validity: a question is dead iff ALL its turns stalled.
    dead_qs: set[int] = set()
    dead_from_q = None  # first dead question (run-summary annotation only)
    if len(turns):
        by_q = turns.groupby("q")["stalled"].agg(["all", "any"])
        dead_qs = set(int(q) for q in by_q.index[by_q["all"]])
        if dead_qs:
            dead_from_q = min(dead_qs)
    degraded_qs = set(turns.loc[turns["stalled"], "q"].tolist()) - dead_qs

    for col, val in (("model", key["model"]), ("arm", key["arm"]), ("path", key["path"])):
        qdf[col] = val
        turns[col] = val
    qdf = qdf.rename(columns={"question number": "q"})
    qdf["valid"] = ~qdf["q"].isin(dead_qs)
    qdf["degraded"] = qdf["q"].isin(degraded_qs) & qdf["valid"]
    qdf["tools"] = qdf["q"].map(lambda q: meta["per_question_tools"].get(str(q), []))
    expected_updates = 1 if key["path"] == "happy" else 2
    qdf["update_calls"] = qdf["tools"].map(lambda t: sum(1 for x in t if x == "update_form_fields"))
    qdf["confirm_calls"] = qdf["tools"].map(lambda t: sum(1 for x in t if x == "confirm_field"))
    qdf["tool_compliant"] = (qdf["update_calls"] >= expected_updates) & (qdf["confirm_calls"] >= 1)

    curve = pd.DataFrame({"prompt_tokens": meta["prompt_curve"]})
    curve["event_index"] = range(1, len(curve) + 1)
    drop_idx = {d[0] for d in meta.get("eviction_drops", [])}
    curve["drop"] = curve["event_index"].isin(drop_idx)
    curve["drop_kind"] = None
    curve.loc[curve["drop"], "drop_kind"] = (
        "restart" if key["arm"] == "section-reset" else "eviction")
    for col, val in (("model", key["model"]), ("arm", key["arm"]), ("path", key["path"])):
        curve[col] = val

    run = {
        **{k: key[k] for k in ("model", "arm", "path")},
        "stamp": key["stamp"],
        "si_chars": meta.get("system_instruction_chars"),
        "greeting_tokens": meta.get("greeting_tokens"),
        "trigger": meta.get("trigger"), "window": meta.get("window"),
        "dead_from_q": dead_from_q,
        "n_stalled_turns": int(turns["stalled"].sum()) if len(turns) else 0,
        "n_errors": len(meta.get("errors", [])),
        "confirmed_fields": len(meta.get("client_confirmed_fields", [])),
        "schema_scope": meta.get("schema_scope"),
    }
    return qdf, turns, curve, run


def load_matrix(data_dir: Path = DATA_DIR):
    """Load all 12 cells -> (questions, turns, curves, runs) tidy DataFrames."""
    qs, ts, cs, rs = [], [], [], []
    files = sorted(data_dir.glob("costs_*.csv"))
    if len(files) != 12:
        raise ValueError(f"expected 12 matrix CSVs, found {len(files)} in {data_dir}")
    for f in files:
        q, t, c, r = _cell_frames(f)
        qs.append(q); ts.append(t); cs.append(c); rs.append(r)
    questions = pd.concat(qs, ignore_index=True)
    turns = pd.concat(ts, ignore_index=True)
    curves = pd.concat(cs, ignore_index=True)
    runs = pd.DataFrame(rs)
    _validate(questions)
    return questions, turns, curves, runs


def _validate(questions: pd.DataFrame) -> None:
    """Self-check: every CSV cost column recomputes from tokens x RATES.

    Tolerance 2e-6 USD per cell (the CSVs round to 6 decimals)."""
    for (model,), grp in questions.groupby(["model"]):
        r = RATES[model]
        for tok_col, cost_col, rate in (
            ("audio in tokens", "audio in token cost", r["audio_input"]),
            ("audio out tokens", "audio out token cost", r["audio_output"]),
            ("text in tokens", "text in token cost", r["text_input"]),
            ("text out tokens", "text out token cost", r["text_output"]),
        ):
            err = (grp[tok_col] * rate / 1e6 - grp[cost_col]).abs().max()
            if err > 2e-6:
                raise AssertionError(
                    f"cost column {cost_col} does not recompute for model {model} (max err {err})")
        tot_err = (grp[["audio in token cost", "audio out token cost",
                        "text in token cost", "text out token cost"]].sum(axis=1)
                   - grp["total cost"]).abs().max()
        if tot_err > 5e-6:
            raise AssertionError(f"total cost does not sum for model {model} (max err {tot_err})")


# ------------------------------------------------------------------ summaries

def arm_summary(questions: pd.DataFrame, runs: pd.DataFrame,
                valid_only: bool = True) -> pd.DataFrame:
    """Per-cell totals. valid_only=True drops post-death rows (the honest
    comparison basis); the truncated cells are then also flagged so partial
    totals are never read as full-run totals."""
    q = questions[questions["valid"]] if valid_only else questions
    g = (q.groupby(["model", "arm", "path"])
         .agg(questions_counted=("q", "count"),
              total_tokens=("total tokens", "sum"),
              total_cost=("total cost", "sum"),
              text_in_tokens=("text in tokens", "sum"),
              audio_in_tokens=("audio in tokens", "sum"),
              text_out_tokens=("text out tokens", "sum"),
              audio_out_tokens=("audio out tokens", "sum"),
              compliant_questions=("tool_compliant", "sum"))
         .reset_index())
    g["text_in_share"] = g["text_in_tokens"] / g["total_tokens"]
    g["cost_per_question"] = g["total_cost"] / g["questions_counted"]
    g = g.merge(runs[["model", "arm", "path", "dead_from_q", "n_stalled_turns",
                      "confirmed_fields", "greeting_tokens"]],
                on=["model", "arm", "path"], how="left")
    g["truncated"] = g["dead_from_q"].notna()
    return g.sort_values(["model", "path", "arm"]).reset_index(drop=True)


def latency_summary(turns: pd.DataFrame) -> pd.DataFrame:
    t = turns.dropna(subset=["latency_s"])
    return (t.groupby(["model", "arm", "path"])["latency_s"]
            .agg(n="count", median=lambda s: statistics.median(s),
                 p90=lambda s: s.quantile(0.9))
            .reset_index())


def conversation_growth_per_turn(curves: pd.DataFrame, runs: pd.DataFrame) -> pd.DataFrame:
    """Per-turn CONVERSATION growth (prompt growth above the SI base) fitted on
    the unbounded arms' curves -- the input the window model needs.

    Uses the median per-event increment over non-drop events, scaled by
    events-per-question to a per-question rate as well."""
    rows = []
    for (model, path), grp in curves[curves["arm"] == "unbounded"].groupby(["model", "path"]):
        grp = grp.sort_values("event_index")
        run = runs[(runs["model"] == model) & (runs["arm"] == "unbounded")
                   & (runs["path"] == path)].iloc[0]
        # Limit to the live portion of truncated runs.
        prompts = grp["prompt_tokens"].tolist()
        incs = [b - a for a, b in zip(prompts, prompts[1:]) if b >= a]
        per_event = statistics.median(incs) if incs else 0.0
        n_live_q = (run["dead_from_q"] - 1) if pd.notna(run["dead_from_q"]) else 20
        events_per_q = len(prompts) / max(n_live_q, 1)
        rows.append({"model": model, "path": path,
                     "growth_per_event": per_event,
                     "events_per_question": events_per_q,
                     "growth_per_question": per_event * events_per_q})
    return pd.DataFrame(rows)


# ------------------------------------------------------- what-if window model

# Measured SI sizes (chars) for the schema-feeding scenarios. full/section are
# the production templates over the real demo schema (computed offline via
# build_form_context); 'jit' is the same with USE_JIT_SCHEMA=True; 'drip' is
# the instruction template with NO field schema at all (fields drip in through
# conversation/tool responses and are therefore EVICTABLE -- maintainer
# scenario, 2026-06-12).
SI_SCENARIOS_CHARS = {
    "full-dump (today's no-sections port)": 25_632,
    "jit-manifest (built, unmeasured live)": 10_204,
    "drip-in (instruction only, schema via tools)": 3_289,
}
# 15 real sections; per-section legacy SI sizes (chars) for the section-reset
# extrapolation, measured offline over the real schema.
SECTION_SI_CHARS = [4_570, 3_831, 5_699, 4_089, 3_542, 3_615, 3_659, 6_313,
                    3_733, 3_681, 5_237, 3_289, 3_361, 9_496, 4_301]


def window_cost_curve(si_chars: float, growth_per_q: float, n_questions: int,
                      model: str, windows: list[int],
                      trigger_headroom: float = 1.30,
                      out_share: float = 0.06) -> pd.DataFrame:
    """Modeled cumulative TEXT-INPUT cost over n_questions for a sliding-window
    session, per candidate window size, for one SI scenario.

    Model (stated so review can attack it):
      base = si_tokens_from_chars(si_chars)            # unevictable floor
      conversation after q questions: c(q) = growth_per_q * q, capped by the
      window's evictable budget. The API's target_tokens lands ABOVE the base
      (h04c/wyhh: landing ~ base + retained conversation), so a window W keeps
      conv between W_lo and W_hi where W_hi = trigger = W * trigger_headroom
      and W_lo = W (both measured-from-base, i.e. the evictable budget is
      max(W - base, 0)). Steady-state per-turn prompt ~= base + midpoint.
      Per-question prompt billing ~= 2 turns (happy) -- the caller passes
      growth_per_q for the path it wants; this function works per-question.
      Output tokens are excluded (out_share kept for sensitivity, default off
      in the cost: this is the TEXT-IN curve the SI lever moves).

    Returns tidy DataFrame: window, q, prompt_tokens_avg, cum_text_in_cost.
    """
    rate = RATES[model]["text_input"] / 1e6
    base = si_tokens_from_chars(si_chars)
    rows = []
    for w in windows:
        evictable_budget = max(w - base, 0.0)
        hi = evictable_budget * trigger_headroom
        cum_cost = 0.0
        for q in range(1, n_questions + 1):
            conv = growth_per_q * q
            if evictable_budget <= 0:
                conv_eff = conv  # window below base: nothing evictable, grows unbounded
            elif conv <= hi:
                conv_eff = conv
            else:
                conv_eff = (evictable_budget + hi) / 2  # steady-state sawtooth midpoint
            prompt = base + conv_eff
            # Each question re-bills the prompt on each of its turns; the
            # caller's growth_per_q already encodes the path's turns/question,
            # so we bill prompt once per TURN via turns-per-question implied
            # by growth: approximate 2 turns (happy) / 4 (unhappy) is folded
            # into growth_per_q's calibration -- here we bill per question
            # using the measured events_per_question from the data instead.
            cum_cost += prompt * rate * _TURN_BILLS_PER_Q
            rows.append({"window": w, "q": q,
                         "prompt_tokens_avg": prompt,
                         "cum_text_in_cost": cum_cost})
    return pd.DataFrame(rows)


# Billed usage events per question, measured from the matrix (median events
# per question across unbounded cells is ~2.05 happy / ~4.1 unhappy; the
# notebook sets this per path from conversation_growth_per_turn()).
_TURN_BILLS_PER_Q = 2.0


def set_turn_bills_per_question(value: float) -> None:
    global _TURN_BILLS_PER_Q
    _TURN_BILLS_PER_Q = float(value)


def section_reset_model_cost(growth_per_q: float, questions_per_section: list[int],
                             model: str, si_chars_per_section: list[float] | None = None
                             ) -> float:
    """Modeled cumulative text-in cost for the section-reset flow over a whole
    form: each section starts a fresh session (its own SI base), conversation
    grows within the section only."""
    rate = RATES[model]["text_input"] / 1e6
    sis = si_chars_per_section or SECTION_SI_CHARS
    total = 0.0
    for n_q, si_chars in zip(questions_per_section, sis):
        base = si_tokens_from_chars(si_chars)
        for q in range(1, n_q + 1):
            total += (base + growth_per_q * q) * rate * _TURN_BILLS_PER_Q
    return total
