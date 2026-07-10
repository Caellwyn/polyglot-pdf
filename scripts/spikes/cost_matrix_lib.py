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

Token model for what-if scenarios (calibrated from the data at load time):
  prompt_tokens(first billed event) ~= CHAR_RATE * si_chars + FIXED_OVERHEAD
  with both anchors taken from the loaded 2.5 cells' (si_chars,
  prompt_curve[0]) pairs -- full-form (25,639 chars / 8,165 tok) and
  section-1 (4,587 chars / 2,275 tok) -- giving CHAR_RATE ~0.280 tok/char and
  FIXED_OVERHEAD ~992 tok (the tool declarations + initiating message).
  LIMITATION: the calibration is 2.5-only; 3.1 bills ~2.8% fewer tokens for
  the same SI (7,934 vs 8,165 measured), so 3.1 what-if outputs are
  systematically a few percent optimistic on top of the model's best-case
  framing.
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

# Calibration anchors are DERIVED FROM THE DATA at load time (calibrate(),
# called by load_matrix()), never hardcoded: anchor A = the full-form arm's
# (system_instruction_chars, prompt_curve[0]); anchor B = the section-reset
# arm's (system_instruction_chars, greeting_tokens) -- BOTH from the same
# session (the SECTION-1 whole-session greeting; an earlier hardcoded version
# paired the greeting tokens with section-2's SI size, fresh-eyes round 1).
CHAR_RATE: float = float("nan")
FIXED_OVERHEAD: float = float("nan")

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
    """Estimated first-event prompt tokens for a given system-instruction
    size. Raises until load_matrix()/calibrate() has run -- silently
    propagating NaN through a cost table is the failure mode this guards."""
    if CHAR_RATE != CHAR_RATE:  # NaN check without importing math
        raise RuntimeError("calibration not loaded -- call load_matrix() first")
    return CHAR_RATE * si_chars + FIXED_OVERHEAD


# --------------------------------------------------------------------- loading

def _cell_frames(csv_path: Path):
    m = _NAME_RE.search(csv_path.name)
    if not m:
        raise ValueError(f"unrecognized data file name: {csv_path.name}")
    key = m.groupdict()
    meta = json.loads(
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
    # APPROXIMATE metric: tool calls are attributed to the question whose
    # turns were active when they fired, so a confirm landing in the NEXT
    # question's window under-counts this question (systematically worse for
    # section-reset, where boundaries cut windows). Use the run-level
    # confirmed_fields (client end-state) as the primary compliance measure;
    # this flag is a secondary, per-question signal only.
    qdf["tool_compliant"] = (qdf["update_calls"] >= expected_updates) & (qdf["confirm_calls"] >= 1)

    curve = pd.DataFrame({"prompt_tokens": meta["prompt_curve"]})
    curve["event_index"] = range(1, len(curve) + 1)
    drop_map = {d[0]: (d[1], d[2]) for d in meta.get("eviction_drops", [])}
    curve["drop"] = curve["event_index"].isin(drop_map)
    # MECHANISM-based drop classification (fresh-eyes review of the section-4
    # chart, 2026-06-12). The detector flags any prompt drop > 50 tokens, but
    # the matrix contains THREE distinct mechanisms that an arm-based label
    # conflated (and mislabeled, esp. for 3.1). Classify each by WHERE it
    # lands, measured against this run's own SI floor:
    #   - session_restart: the curve falls back near a SECTION SI base (a
    #     near-total reset). Only the section-reset arm restarts; the landing
    #     is within ~1.5x the smallest prompt seen (the section-1 greeting).
    #   - audio_context_dip: 3.1 only -- a regular partial dip (3.1 retains and
    #     re-bills conversation AUDIO, so its prompt sawtooths even with NO
    #     compression and NO restart; lands HIGH, far above any SI base).
    #   - compression_eviction: sliding-window arm, a drop that is NOT a
    #     restart (lands above the section floor; the real compression signal).
    #   - billing_noise: tiny drops (< ~400 tok) with no mechanism -- turn-to-
    #     turn metering jitter, not a real context reduction.
    floor = float(curve["prompt_tokens"].min())  # ~the smallest greeting/base seen
    # A section restart resets to SOME section's SI greeting -- which varies by
    # section (the demo's sections run ~3.3k-9.5k SI chars), so a restart can
    # land well above the smallest floor. The reliable restart signature in a
    # section-reset arm is a substantial drop landing below the run's OWN
    # turn-1 prompt (the full-form SI was never sent in this arm, but the
    # turn-1 prompt is this run's largest unavoidable base; a drop below it
    # means the schema was reset to a smaller section). Uses measured curve
    # values only -- no dependency on the calibration, which has not run yet
    # at load time.
    turn1_prompt = float(curve["prompt_tokens"].iloc[0])
    restart_ceiling = turn1_prompt + 1500  # tolerate a section larger than section-1

    def _classify(ev_idx: int) -> str:
        prev, now = drop_map[ev_idx]
        size = prev - now
        if size < 400:
            return "billing_noise"
        # A real section restart is a LARGE reset (the whole accumulated
        # section context is flushed, >= ~1k tokens) that lands near a section
        # base. Requiring BOTH avoids tagging a small within-section dip that
        # merely lands low as a restart (fresh-eyes: 2.5 ev39, -572 landing at
        # 3698, is a within-section dip, NOT the section-2 restart at ev37).
        if (key["arm"] == "section-reset" and size >= 1000
                and now <= restart_ceiling):
            return "session_restart"
        if key["model"] == "3.1":
            # 3.1's intrinsic audio-context sawtooth: a partial dip that does
            # NOT reset the schema (lands above the full-form base, or is in a
            # non-restart arm). Applies in every 3.1 arm.
            return "audio_context_dip"
        if key["arm"] == "sliding-window":
            return "compression_eviction"
        return "billing_noise"

    curve["drop_kind"] = None
    curve.loc[curve["drop"], "drop_kind"] = [
        _classify(i) for i in curve.loc[curve["drop"], "event_index"]]
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
        "n_eviction_drops": len(meta.get("eviction_drops", [])),
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
    calibrate(curves, runs)
    return questions, turns, curves, runs


def calibrate(curves: pd.DataFrame, runs: pd.DataFrame) -> tuple[float, float]:
    """Solve CHAR_RATE / FIXED_OVERHEAD from two measured (si_chars, prompt
    tokens) anchors read off the loaded data. Both anchors use the SAME model
    (2.5) and the SAME metric (the session's first billed PROMPT count,
    prompt_curve[0]) -- an earlier version mixed a prompt count with a
    greeting prompt+response TOTAL and a mispaired SI size (fresh-eyes
    round 1)."""
    global CHAR_RATE, FIXED_OVERHEAD

    def _first_prompt(arm: str, path: str):
        run = runs[(runs["arm"] == arm) & (runs["model"] == "2.5")
                   & (runs["path"] == path)].iloc[0]
        curve = curves[(curves["arm"] == arm) & (curves["model"] == "2.5")
                       & (curves["path"] == path)].sort_values("event_index")
        return float(run["si_chars"]), float(curve["prompt_tokens"].iloc[0])

    a_chars, a_tok = _first_prompt("unbounded", "happy")      # full-form SI
    b_chars, b_tok = _first_prompt("section-reset", "happy")  # section-1 SI
    CHAR_RATE = (a_tok - b_tok) / (a_chars - b_chars)
    FIXED_OVERHEAD = b_tok - CHAR_RATE * b_chars
    return CHAR_RATE, FIXED_OVERHEAD


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
        # len(prompts) - 1: the first event is the session greeting, not a
        # question turn (fresh-eyes r1: counting it biased events/question
        # by ~+2.5%).
        events_per_q = (len(prompts) - 1) / max(n_live_q, 1)
        rows.append({"model": model, "path": path,
                     "growth_per_event": per_event,
                     "events_per_question": events_per_q,
                     "growth_per_question": per_event * events_per_q})
    return pd.DataFrame(rows)


# ------------------------------------------------------- what-if window model

# SI sizes (chars) for the schema-feeding scenarios, measured offline by
# running backend.services.ai_context.build_form_context over the real demo
# schema (recompute + drift-check with recompute_si_scenarios(); the notebook
# asserts the literals are current). 'full' is the production legacy template
# with all 174 fields; 'jit' is the same call with USE_JIT_SCHEMA=True (the
# manifest path -- built, never measured live); 'drip' is the template built
# with fields=[] (NO field schema at all -- fields drip in through
# conversation/tool responses and are therefore EVICTABLE; maintainer
# scenario, 2026-06-12).
SI_SCENARIOS_CHARS = {
    "full-dump (today's no-sections port)": 25_632,
    "jit-manifest (built, unmeasured live)": 10_204,
    "drip-in (fields=[]; schema via tools)": 3_069,
}
# 15 real sections; per-section legacy SI sizes (chars), same offline build
# (values are recompute_si_scenarios()['sections'] verbatim; the notebook
# drift-checks them -- the template evolves, cost impact of small drift
# ~0.1%).
SECTION_SI_CHARS = [4_571, 3_832, 5_700, 4_090, 3_543, 3_616, 3_660, 6_314,
                    3_734, 3_682, 5_238, 3_290, 3_362, 9_497, 4_302]


def recompute_si_scenarios() -> dict:
    """Recompute every SI size live from the backend templates + real schema
    (imports the backend; offline -- no network). The notebook calls this and
    surfaces any drift from the literals above.

    NOTE (bd polyglot-pdf-el92): the 'jit' scenario is no longer live-computable
    -- the JIT SI mode was removed (bd polyglot-pdf-en2j), so there is no distinct
    JIT SI to measure (a USE_JIT_SCHEMA override is a silent no-op now). We return
    the FROZEN historical literal for 'jit' so the notebook's drift-check does not
    silently report a false 0 from a legacy-vs-legacy comparison, and so the
    historical full/jit/drip analysis narrative still renders. 'full', 'drip', and
    'sections' are still recomputed live (they use the surviving legacy full-SI)."""
    import sys
    root = str(Path(__file__).resolve().parent.parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)
    from backend.services import ai_context

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    full = {"form_metadata": schema["form_metadata"], "fields": schema["fields"]}
    secs: dict[str, list] = {}
    for f in schema["fields"]:
        secs.setdefault(f.get("section_id") or "section-1", []).append(f)

    def _si_len(sch):
        # Legacy full-SI (USE_DTI off, the default) -- the only SI mode these
        # length probes can build now that JIT is gone.
        return len(ai_context.build_form_context(
            sch, {}, section_number=1, total_sections=15, section_label="X"))

    return {
        "full": _si_len(full),
        # Frozen historical value -- JIT SI removed, no longer live-computable.
        "jit": list(SI_SCENARIOS_CHARS.values())[1],
        "drip": _si_len({"form_metadata": schema["form_metadata"], "fields": []}),
        "sections": [_si_len({"form_metadata": schema["form_metadata"],
                              "fields": fl}) for fl in secs.values()],
    }


# Billed usage events per question, measured from the matrix via
# conversation_growth_per_turn() (the notebook sets this per path before
# modeling; ~2.0 happy / ~3.9 unhappy).
_EVENTS_PER_Q = 2.0


def set_events_per_question(value: float) -> None:
    global _EVENTS_PER_Q
    _EVENTS_PER_Q = float(value)


def window_cost_curve(si_chars: float, growth_per_q: float, n_questions: int,
                      model: str, configs: list[tuple[int, int]],
                      eviction_lag_q: float = 1.5,
                      events_per_q: float | None = None) -> pd.DataFrame:
    """BEST-CASE modeled cumulative TEXT-INPUT cost over n_questions for a
    sliding-window session, per (trigger_tokens, window_tokens) config, for
    one SI scenario. "Best-case" means the server evicts as configured: the
    measured matrix shows firing is not guaranteed (the 2.5 sliding happy
    cell crossed its 12k trigger around q8 and never evicted), so reality
    lands BETWEEN this model and the unbounded curve. window_model_check()
    quantifies that gap against the measured cells.

    Model (stated so review can attack it; trigger/window are TOTAL tokens,
    exactly as the API counts them -- fresh-eyes round 1 caught an earlier
    version that wrongly applied the headroom to the evictable budget):
      base = si_tokens_from_chars(si_chars)         # unevictable floor
      hi  = trigger - base   # conversation level where eviction is REQUESTED
      lo  = max(window - base, 0)  # retained conversation after eviction
                                   # (measured landings sit at/above this)
      hi <= 0 -> compression can never fire (trigger below the SI floor):
                 the curve is just unbounded growth (infeasible config).
      Conversation c(q) = growth_per_q * q until the first eviction COMPLETES
      at q_evict = hi/growth_per_q + eviction_lag_q. NOTE the lag unit is
      QUESTIONS: the measured async lag is 1-3 TURNS (eycd/h04c), so the 1.5
      default is calibrated to the ~2-events/question happy path; pass
      ~0.5-0.8 for a ~4-events/question unhappy path if precision matters
      (sensitivity over lag in [0.5, 3] does not change any conclusion
      direction in this dataset -- fresh-eyes round 2).
      After q_evict: steady-state sawtooth midpoint (lo + hi) / 2.
    Billing: each question re-bills the prompt on each billed event
    (events_per_q param, falling back to the module default set by
    set_events_per_question; measured ~2.0 happy / ~3.9 unhappy).

    Returns tidy rows: trigger, window, q, prompt_tokens_avg,
    cum_text_in_cost, feasible.
    """
    rate = RATES[model]["text_input"] / 1e6
    base = si_tokens_from_chars(si_chars)
    epq = _EVENTS_PER_Q if events_per_q is None else float(events_per_q)
    rows = []
    for trigger, window in configs:
        hi = trigger - base
        lo = max(window - base, 0.0)
        feasible = hi > 0
        q_evict = (hi / growth_per_q + eviction_lag_q) if feasible and growth_per_q > 0 else float("inf")
        steady = (lo + hi) / 2 if feasible else 0.0
        cum = 0.0
        for q in range(1, n_questions + 1):
            conv = growth_per_q * q
            conv_eff = conv if (not feasible or q <= q_evict) else min(conv, steady)
            prompt = base + conv_eff
            cum += prompt * rate * epq
            rows.append({"trigger": trigger, "window": window, "q": q,
                         "prompt_tokens_avg": prompt, "cum_text_in_cost": cum,
                         "feasible": feasible})
    return pd.DataFrame(rows)


def window_model_check(questions: pd.DataFrame, runs: pd.DataFrame,
                       growth: pd.DataFrame) -> pd.DataFrame:
    """Model-vs-measured for the four measured sliding-window cells: the
    honesty check the notebook must display before any what-if chart.

    Like-for-like basis (fresh-eyes round 2): the comparison runs over the
    questions VALID IN BOTH the sliding cell and the unbounded cell of the
    same model/path -- both truncated 3.1-unhappy cells died at different
    questions (q13 vs q12), and comparing unequal spans flipped the sign.
    Pure function: does NOT touch the module's events-per-question default."""
    rows = []
    for (model, path), grp in growth.groupby(["model", "path"]):
        g = grp.iloc[0]
        run = runs[(runs["model"] == model) & (runs["arm"] == "sliding-window")
                   & (runs["path"] == path)].iloc[0]

        def _valid_qs(arm):
            sel = ((questions["model"] == model) & (questions["path"] == path)
                   & (questions["arm"] == arm) & questions["valid"])
            return set(questions[sel]["q"])

        common_qs = _valid_qs("sliding-window") & _valid_qs("unbounded")
        n_q = len(common_qs)
        pred = window_cost_curve(run["si_chars"], g["growth_per_question"], n_q,
                                 model, [(int(run["trigger"]), int(run["window"]))],
                                 events_per_q=g["events_per_question"])
        base_sel = ((questions["model"] == model) & (questions["path"] == path)
                    & questions["q"].isin(common_qs))
        measured = questions[base_sel & (questions["arm"] == "sliding-window")]["text in token cost"].sum()
        unbounded = questions[base_sel & (questions["arm"] == "unbounded")]["text in token cost"].sum()
        rows.append({"model": model, "path": path, "n_questions": n_q,
                     "modeled_text_in": pred["cum_text_in_cost"].iloc[-1],
                     "measured_text_in": measured,
                     "unbounded_text_in": unbounded,
                     "measured_evictions": int(run["n_eviction_drops"])})
    return pd.DataFrame(rows)


def section_reset_model_cost(growth_per_q: float, questions_per_section: list[int],
                             model: str, si_chars_per_section: list[float] | None = None,
                             events_per_q: float | None = None) -> float:
    """Modeled cumulative text-in cost for the section-reset flow over a whole
    form: each section starts a fresh session (its own SI base), conversation
    grows within the section only. questions_per_section and the SI list must
    be the same length (asserted -- zip would truncate silently).
    events_per_q falls back to the module default set by
    set_events_per_question -- pass it explicitly in mixed-path notebooks
    (same purity pattern as window_cost_curve; fresh-eyes round 3)."""
    rate = RATES[model]["text_input"] / 1e6
    epq = _EVENTS_PER_Q if events_per_q is None else float(events_per_q)
    sis = si_chars_per_section or SECTION_SI_CHARS
    if len(questions_per_section) != len(sis):
        raise ValueError("questions_per_section and SI list lengths differ "
                         f"({len(questions_per_section)} vs {len(sis)})")
    total = 0.0
    for n_q, si_chars in zip(questions_per_section, sis):
        base = si_tokens_from_chars(si_chars)
        for q in range(1, n_q + 1):
            total += (base + growth_per_q * q) * rate * epq
    return total
