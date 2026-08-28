"""Replay/projection analysis: recompute a measured run's dollars from its own
token counts, re-bill it under a NAIVE (no-compression, full-SI, no-eviction)
billing rule, and project a happy-path run's growth pattern onto the unhappy
turn structure (bd polyglot-pdf-89mt cache-evidence follow-on).

This is a REPLAY tool, not a new pricing model: every dollar figure it produces
is arithmetic over ALREADY-MEASURED per-question token counts x the rate table
GEMINI_PRICING_BY_FAMILY (imported from backend/config.py -- never copied as
literals, so a rate-table edit there is felt here automatically). Nothing in
this module calls a live model; it only reads committed run artifacts.

Two run-artifact eras exist under scripts/spikes/data/, BOTH handled by
load_run:
  - June-2026 12-cell matrix format (costs_<model>_<arm>_<path>_<stamp>.csv +
    .meta.json only -- see cost_matrix_lib.py's _cell_frames for the reference
    reader). No .summary.json sidecar.
  - The current cherry-picked harness format (measure_form_session_costs.py):
    same 11-column CSV, PLUS <stem>.summary.json (pre-priced headline
    aggregates) and sometimes <stem>.turns.csv (a separate per-turn latency
    dump this module does not need). meta.json in this era additionally
    carries cache_summary/cached_curve/traffic_types (bd 89mt cache-evidence
    fields) when the run predates or postdates that instrumentation.

Both eras write the SAME 11-column per-question CSV (question number, audio in
tokens/cost, audio out tokens/cost, text in tokens/cost, text out tokens/cost,
total tokens, total cost) and the same meta.json keys this module reads
(tier, model, arm, path, prompt_curve, cached_curve, rates_per_token). load_run
does not need to branch on era for the fields it actually uses -- it detects
the era only to decide whether to also load summary.json (informational only;
never fed into replay_total, which recomputes independently from the CSV).

ASSUMPTIONS (named per the task, since the run artifacts don't document them
in one place):
  - The CSV's per-question token columns ARE the billed counts for that
    question already (not a cumulative curve) -- confirmed against
    cost_matrix_lib._validate, which recomputes the *cost* columns from the
    *token* columns at the stated rate and requires an exact match. This
    module's replay_total does the same recomputation and is expected to
    match the CSV's own "total cost" column exactly (that IS the pinned test).
  - meta["tier"] ("2.5" / "3.1") is the correct key into
    GEMINI_PRICING_BY_FAMILY for the WHOLE run -- true for every artifact
    inspected (a run is single-model; GEMINI_PRICING_BY_FAMILY is keyed on the
    same "2.5"/"3.1" strings the harness already writes to meta["tier"]).
  - meta["cached_curve"] (bd 89mt), when present, is one entry per raw
    usage_metadata event, not per question -- replay_total sums it and treats
    ANY nonzero total as a hard error (see below), so this assumption only
    matters for the exact wording of that error, not for correctness.
  - The Live cost path bills 100% of prompt tokens at the full input rate
    (verified in live_ai_gemini._cost_for_turn and in
    GEMINI_PRICING_BY_FAMILY, which has no cached-token row) -- so as long as
    cached_curve sums to zero (the measured evidence across every run
    inspected for bd 89mt: 5/5 runs, 496/496 events, all cached=null),
    replay_total's full-rate recomputation is correct BY CONSTRUCTION, not
    coincidentally. A future run with a nonzero cache would need a discount
    line this module does not have -- replay_total refuses to silently
    under/over-count that run rather than guess (see replay_total docstring).
  - text_sidecar_cost operates on WHATEVER token-count data is actually
    available for a text-sidecar event. The current harness's persisted
    artifacts do NOT retain per-event text_ai_usage token counts (log_sink,
    which carries them live in measure_form_session_costs.build_summary, is
    never written to meta.json or summary.json -- only the pre-priced
    aggregate summary.json['headline']['text_usd'] survives). So
    text_sidecar_cost accepts a list of per-event dicts carrying
    prompt_tokens/cached_tokens/output_tokens/model (the shape a future
    persisted-events run, or a hand-built synthetic trace, would carry) and
    prices each with price_text_usage; called with an empty list (the only
    thing derivable from today's committed artifacts) it returns 0.0, which
    is correct for those artifacts (their sidecar cost is only visible via
    the pre-priced summary.json aggregate, reported separately in __main__ as
    "already-priced (from summary.json)" rather than re-derived).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.config import GEMINI_PRICING_BY_FAMILY  # noqa: E402

_SPIKES_DIR = str(Path(__file__).resolve().parent)
if _SPIKES_DIR not in sys.path:
    sys.path.insert(0, _SPIKES_DIR)
# price_text_usage lives in the harness script, NOT in
# backend/adapters/text_ai_gemini.py (that module has no such function -- it
# only logs raw usage via _log_usage). Importing it here rather than
# reimplementing keeps the cached_input discount logic in exactly one place
# (bd 0cyu scar: a second flat-rate copy mispriced pro-model calls once
# already).
import measure_form_session_costs as _mfsc  # noqa: E402

price_text_usage = _mfsc.price_text_usage

CSV_COLUMNS = [
    "question number",
    "audio in tokens", "audio in token cost",
    "audio out tokens", "audio out token cost",
    "text in tokens", "text in token cost",
    "text out tokens", "text out token cost",
    "total tokens", "total cost",
]

MODALITY_TOKEN_COLS = {
    "text_input": "text in tokens",
    "audio_input": "audio in tokens",
    "text_output": "text out tokens",
    "audio_output": "audio out tokens",
}


# --------------------------------------------------------------------- a.
# load_run

def load_run(csv_path: Path, meta_path: Path | None = None) -> dict:
    """Load one run's per-question trace, handling both artifact eras.

    Returns a dict:
      stamp, tier, model, arm, path, rates (the run's OWN rates_per_token, as
        billed), questions: [{"q": int, "audio_input": int, "audio_output":
        int, "text_input": int, "text_output": int, "total_tokens": int,
        "total_cost": float}, ...],
      recorded_total_cost (float, sum of the CSV's own "total cost" column --
        the ground truth replay_total must reproduce),
      cached_total (int, sum of meta["cached_curve"] non-null numeric
        entries; 0 if the run predates that field),
      meta (the raw parsed meta.json dict, for callers that need more, e.g.
        turn counts for project_unhappy),
      summary (the raw parsed summary.json dict, or None if this run's era
        didn't write one -- informational only, never used by replay_total).
    """
    csv_path = Path(csv_path)
    if meta_path is None:
        meta_path = _sibling_meta_path(csv_path)
    meta_path = Path(meta_path)

    with csv_path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != CSV_COLUMNS:
            raise ValueError(
                f"unrecognized CSV column shape in {csv_path.name}: "
                f"{reader.fieldnames!r} != {CSV_COLUMNS!r}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"no question rows in {csv_path.name}")

    questions = []
    recorded_total = 0.0
    for r in rows:
        q = {
            "q": int(r["question number"]),
            "text_input": int(r["text in tokens"]),
            "audio_input": int(r["audio in tokens"]),
            "text_output": int(r["text out tokens"]),
            "audio_output": int(r["audio out tokens"]),
            "total_tokens": int(r["total tokens"]),
            "total_cost": float(r["total cost"]),
        }
        questions.append(q)
        recorded_total += q["total_cost"]

    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    tier = meta.get("tier") or _tier_from_filename(csv_path.name)
    if tier not in GEMINI_PRICING_BY_FAMILY:
        raise ValueError(
            f"{csv_path.name}: tier {tier!r} (from meta.json/filename) is not "
            f"a known pricing family {sorted(GEMINI_PRICING_BY_FAMILY)}")

    cached_curve = meta.get("cached_curve") or []
    cached_total = sum(
        c for c in cached_curve if isinstance(c, (int, float)) and c)

    summary_path = csv_path.with_suffix("").with_suffix("")  # strip nothing yet
    summary_path = csv_path.parent / (csv_path.stem + ".summary.json")
    summary = (json.loads(summary_path.read_text(encoding="utf-8"))
               if summary_path.exists() else None)

    return {
        "stamp": meta.get("started") or csv_path.stem,
        "tier": tier,
        "model": meta.get("model"),
        "arm": meta.get("arm"),
        "path": meta.get("path"),
        "rates": meta.get("rates_per_token") or GEMINI_PRICING_BY_FAMILY[tier],
        "questions": questions,
        "recorded_total_cost": round(recorded_total, 6),
        "cached_total": cached_total,
        "meta": meta,
        "summary": summary,
        "csv_path": csv_path,
        "meta_path": meta_path,
    }


def _sibling_meta_path(csv_path: Path) -> Path:
    return csv_path.parent / (csv_path.stem + ".meta.json")


def _tier_from_filename(name: str) -> str | None:
    """Fallback tier sniff for a CSV with no meta.json alongside it (every
    committed artifact has one, but a hand-built test fixture might not)."""
    for tier in GEMINI_PRICING_BY_FAMILY:
        if f"_{tier}_" in name or name.startswith(f"costs_{tier}_"):
            return tier
    return None


# --------------------------------------------------------------------- b.
# replay_total

def replay_total(trace: dict, rates: dict | None = None) -> dict:
    """Recompute the run's billed dollars from its own per-question token
    counts x rates (imported from backend.config.GEMINI_PRICING_BY_FAMILY;
    rates defaults to trace["rates"], the run's OWN billed rate table, so a
    caller doing a like-for-like replay never has to look the tier up twice).

    Live-path cached tokens: the Live cost path
    (backend/adapters/live_ai_gemini.py _cost_for_turn) bills every prompt
    token at the full input rate and GEMINI_PRICING_BY_FAMILY has no
    cached-token discount row (bd 89mt evidence: 5/5 recorded runs show the
    API never populates cached_content_token_count on this path -- reported
    is False, every cached value is null). If a run's cached_curve DOES sum to
    something nonzero, this function's full-rate replay would silently
    OVER-count that run relative to what was actually billed -- so it raises
    instead of guessing at a discount this codebase has no rate for.

    Returns {"per_question": [{"q", "cost"}, ...], "total_cost": float}.
    """
    rates = rates or trace["rates"]
    cached_total = trace.get("cached_total", 0)
    if cached_total:
        raise ValueError(
            f"replay_total: run {trace.get('stamp')!r} reports "
            f"{cached_total} nonzero cached tokens on the Live path, but "
            "GEMINI_PRICING_BY_FAMILY has no cached-token discount row and "
            "the full-rate replay below would over-count this run. Add a "
            "cached-token rate before replaying a run with real cache hits.")

    per_question = []
    total = 0.0
    for q in trace["questions"]:
        cost = (q["text_input"] * rates["text_input"]
                + q["audio_input"] * rates["audio_input"]
                + q["text_output"] * rates["text_output"]
                + q["audio_output"] * rates["audio_output"])
        per_question.append({"q": q["q"], "cost": cost})
        total += cost
    return {"per_question": per_question, "total_cost": round(total, 6)}


# --------------------------------------------------------------------- c.
# naive_replay

def naive_replay(trace: dict, naive_si_tokens: float, rates: dict | None = None) -> dict:
    """Re-bill the SAME conversation under NAIVE (no-eviction, no-compression,
    full-SI-every-turn) billing rules: prompt(t) = naive_si_tokens + the sum
    of every prior event's NEW text+audio (nothing ever evicted), with the
    SAME output tokens the run actually produced (naive billing does not
    change what the model says, only what context it re-reads).

    This is arithmetic replay over the measured per-question NEW-token deltas
    (text_input/audio_input, which the harness already reports as
    per-question deltas -- see CounterTracker.delta_and_advance -- so they
    ARE the "new" tokens contributed by that turn, not a cumulative prompt
    size), NOT a re-run of the actual session. Each question's naive prompt
    cost is (naive_si_tokens + cumulative new-input-tokens-so-far) x
    text_input rate for the NEW text this turn plus audio at the audio rate
    for the NEW audio this turn -- i.e. the naive SI/history overhead is
    charged as TEXT context (the SI itself is text), on top of that
    question's own new audio+text input, exactly mirroring how the real
    per-question rows already separate "this question's new tokens" from
    "the fixed system-instruction floor" would look if nothing were ever
    evicted.

    Returns {"per_question": [{"q", "prompt_tokens", "cost"}, ...],
    "total_cost": float}.
    """
    rates = rates or trace["rates"]
    per_question = []
    total = 0.0
    cumulative_new_input = 0.0
    for q in trace["questions"]:
        # This turn's own new input (text+audio) is billed at its own rate;
        # everything ACCUMULATED before this turn is re-sent as SI/history
        # context and billed as extra text-input tokens (the eviction-free
        # assumption: nothing that was ever said is ever dropped).
        history_tokens = naive_si_tokens + cumulative_new_input
        prompt_cost = (history_tokens * rates["text_input"]
                       + q["text_input"] * rates["text_input"]
                       + q["audio_input"] * rates["audio_input"])
        output_cost = (q["text_output"] * rates["text_output"]
                       + q["audio_output"] * rates["audio_output"])
        cost = prompt_cost + output_cost
        per_question.append({
            "q": q["q"],
            "prompt_tokens": history_tokens + q["text_input"] + q["audio_input"],
            "cost": cost,
        })
        total += cost
        cumulative_new_input += q["text_input"] + q["audio_input"]
    return {"per_question": per_question, "total_cost": round(total, 6)}


# --------------------------------------------------------------------- d.
# project_unhappy

def project_unhappy(happy_trace: dict, turns_multiplier: float = 2.0) -> dict:
    """Extend the measured per-event growth pattern of a HAPPY-path run to the
    UNHAPPY turn structure (4 turns/question -- value, reject, corrected
    value, confirm -- vs happy's 2 -- value, confirm), by REPLAY ARITHMETIC
    over the happy run's own measured per-question deltas, NOT a curve fit.

    Model: the happy run's per-question text/audio-input DELTA is treated as
    the cost of ONE (value, confirm) turn pair. An unhappy question spends
    turns_multiplier times as many turns (default 2.0 = 4 turns / 2 turns),
    so its input-token cost is scaled by that multiplier per question (the
    same new-content-per-turn rate, just more turns saying it): a rejected
    value, its rejection, the corrected value, and the confirmation all cost
    roughly what one extra (value, confirm) pair costs, which is exactly the
    happy run's own per-question increment. Output tokens (what the MODEL
    says) scale the same way -- an unhappy question gets one extra
    value-then-confirm round from the model too (acknowledging the
    correction, then confirming again).

    This reuses ONLY the happy trace's own measured per-question arithmetic
    (no fitted curve, no external growth-rate table) -- it is projection by
    replaying the SAME measured deltas turns_multiplier times, which is what
    "replay-arithmetic style, not a polynomial fit" means here.

    Returns {"per_question": [{"q", "text_input", "audio_input",
    "text_output", "audio_output", "total_tokens", "cost"}, ...],
    "total_cost": float}, priced at happy_trace["rates"].
    """
    rates = happy_trace["rates"]
    per_question = []
    total = 0.0
    for q in happy_trace["questions"]:
        ti = q["text_input"] * turns_multiplier
        ai = q["audio_input"] * turns_multiplier
        to = q["text_output"] * turns_multiplier
        ao = q["audio_output"] * turns_multiplier
        cost = (ti * rates["text_input"] + ai * rates["audio_input"]
                + to * rates["text_output"] + ao * rates["audio_output"])
        per_question.append({
            "q": q["q"],
            "text_input": ti, "audio_input": ai,
            "text_output": to, "audio_output": ao,
            "total_tokens": ti + ai + to + ao,
            "cost": cost,
        })
        total += cost
    return {"per_question": per_question, "total_cost": round(total, 6)}


# --------------------------------------------------------------------- e.
# text_sidecar_cost

def text_sidecar_cost(events: list[dict]) -> dict:
    """Price a list of text-sidecar (secretary/validator/pro-pass) usage
    events by REUSING measure_form_session_costs.price_text_usage, keyed off
    each event's own `model` field (bd 0cyu scar: a flat rate mispriced the
    W6 pro pass at the flash-lite rate; price_text_usage's cached_input
    discount + per-model rate row is the fix, imported rather than
    reimplemented so there is exactly one copy of that pricing logic).

    Each event dict is expected to carry prompt_tokens, cached_tokens,
    output_tokens, and model (the shape the harness's log_sink text_ai_usage
    records have LIVE, at run time -- see build_summary in
    measure_form_session_costs.py). NOTE: today's committed run artifacts do
    NOT persist these per-event records to disk (only the pre-priced
    aggregate lands in summary.json's headline.text_usd /
    text_usd_by_caller) -- so this function is exercised against a
    hand-built or future-persisted events list, and correctly returns 0.0
    total for an empty list (see module docstring assumption on this).

    Returns {"per_event": [{"caller", "model", "usd"}, ...], "total_usd": float}.
    """
    per_event = []
    total = 0.0
    for e in events:
        usd = price_text_usage(
            e.get("prompt_tokens", 0), e.get("cached_tokens", 0),
            e.get("output_tokens", 0), model=e.get("model"))
        per_event.append({
            "caller": e.get("caller", ""), "model": e.get("model"), "usd": round(usd, 6)})
        total += usd
    return {"per_event": per_event, "total_usd": round(total, 6)}


def text_sidecar_cost_from_summary(summary: dict | None) -> float:
    """The already-priced text-sidecar total for a run whose per-event token
    counts were never persisted (today's norm -- see module docstring): read
    it straight off summary.json's headline.text_usd rather than pretending
    it can be re-derived from data that isn't there. Returns 0.0 if the run
    has no summary.json (the June-era format) or wired no text sidecar."""
    if not summary:
        return 0.0
    return float((summary.get("headline") or {}).get("text_usd") or 0.0)


# --------------------------------------------------------------------- f.
# __main__

def _fmt_usd(x: float) -> str:
    return f"${x:.6f}"


def _print_table(rows: list[tuple[str, str]]) -> None:
    width = max(len(r[0]) for r in rows) if rows else 0
    for label, value in rows:
        print(f"  {label.ljust(width)} : {value}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("csv_path", type=Path, help="run CSV path (e.g. "
                   "scripts/spikes/data/costs_2.5_unbounded_happy_*.csv)")
    p.add_argument("--mode", choices=["replay", "naive", "project-unhappy"],
                   default="replay")
    p.add_argument("--naive-si-tokens", type=float, default=25639.0,
                   help="naive mode: fixed SI token floor re-sent every turn "
                        "(default: the measured full-form-legacy SI token "
                        "count, cost_matrix_lib SI_SCENARIOS_CHARS full-dump "
                        "anchor)")
    p.add_argument("--turns-multiplier", type=float, default=2.0,
                   help="project-unhappy mode: unhappy/happy turn-count ratio")
    args = p.parse_args(argv)

    trace = load_run(args.csv_path)
    print(f"run: {trace['stamp']} tier={trace['tier']} arm={trace['arm']} "
          f"path={trace['path']} questions={len(trace['questions'])}")
    print()

    if args.mode == "replay":
        result = replay_total(trace)
        rows = [
            ("recorded total (from CSV)", _fmt_usd(trace["recorded_total_cost"])),
            ("replayed total (tokens x rates)", _fmt_usd(result["total_cost"])),
            ("delta", _fmt_usd(result["total_cost"] - trace["recorded_total_cost"])),
            ("cached tokens (Live path)", str(trace["cached_total"])),
        ]
        sidecar_usd = text_sidecar_cost_from_summary(trace["summary"])
        if sidecar_usd:
            rows.append(("text sidecar (from summary.json, already priced)",
                        _fmt_usd(sidecar_usd)))
        _print_table(rows)
    elif args.mode == "naive":
        naive = naive_replay(trace, args.naive_si_tokens)
        deployed = replay_total(trace)
        rows = [
            ("deployed (measured/replayed) total", _fmt_usd(deployed["total_cost"])),
            (f"naive (SI={int(args.naive_si_tokens)} tok, no eviction) total",
             _fmt_usd(naive["total_cost"])),
            ("naive - deployed", _fmt_usd(naive["total_cost"] - deployed["total_cost"])),
            ("naive / deployed",
             f"{(naive['total_cost'] / deployed['total_cost']):.2f}x"
             if deployed["total_cost"] else "n/a"),
        ]
        _print_table(rows)
    else:
        proj = project_unhappy(trace, args.turns_multiplier)
        rows = [
            ("happy total (measured)", _fmt_usd(trace["recorded_total_cost"])),
            (f"projected unhappy total ({args.turns_multiplier}x turns)",
             _fmt_usd(proj["total_cost"])),
        ]
        _print_table(rows)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
