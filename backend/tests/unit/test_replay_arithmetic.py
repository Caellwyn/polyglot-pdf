"""Pinned tests for scripts/spikes/analyze_naive_vs_deployed.py (bd
polyglot-pdf-89mt cache-evidence follow-on).

Two guarantees this file pins:
  1. replay_total, run against a COMMITTED June-2026-matrix artifact
     (scripts/spikes/data/costs_2.5_unbounded_happy_*.csv), reproduces that
     file's own recorded billed total to within float tolerance -- an
     EXACT-MATCH test against real, previously-measured data, not a
     synthetic fixture.
  2. naive_replay, run against a tiny hand-built 3-event trace, matches a
     value computed by hand in the test's own comment -- so the arithmetic
     itself (not just "it runs") is pinned.

ASCII only. No live Gemini calls -- this module only reads committed CSV/JSON
artifacts and does arithmetic.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")  # analyze_naive_vs_deployed -> measure_form_session_costs needs it

_REPO = Path(__file__).resolve().parent.parent.parent.parent
for p in (str(_REPO), str(_REPO / "scripts" / "spikes")):
    if p not in sys.path:
        sys.path.insert(0, p)

import analyze_naive_vs_deployed as andd  # noqa: E402

DATA_DIR = _REPO / "scripts" / "spikes" / "data"


# ------------------------------------------------------- a. exact-match replay

# Every June-2026-matrix arm this pinning covers: (glob-safe stamp, tier). The
# happy-path unbounded/2.5 cell is required to exist (it is the file this
# test's docstring names); the others run too when present, so the pin covers
# more than one arm/tier/path combination rather than a single lucky file.
_JUNE_UNBOUNDED_HAPPY_25 = sorted(
    DATA_DIR.glob("costs_2.5_unbounded_happy_*.csv"))


def test_june_matrix_artifacts_present():
    """Guard the guard: if this list is empty, every test below silently
    collects zero cases and the pin is vacuous (bd testing.md "test the
    tests"). Fail loudly instead."""
    assert _JUNE_UNBOUNDED_HAPPY_25, (
        "no scripts/spikes/data/costs_2.5_unbounded_happy_*.csv found -- "
        "the exact-match replay test below would silently test nothing")


@pytest.mark.parametrize("csv_path", _JUNE_UNBOUNDED_HAPPY_25,
                         ids=lambda p: p.stem)
def test_replay_total_reproduces_recorded_cost_exactly(csv_path):
    """EXACT-MATCH: replay_total's recomputed total must equal the CSV's own
    recorded "total cost" column sum, to within the CSV's own rounding
    tolerance (each row is rounded to 6 decimals before being written, same
    tolerance cost_matrix_lib._validate uses for the identical check)."""
    trace = andd.load_run(csv_path)
    result = andd.replay_total(trace)

    assert result["total_cost"] == pytest.approx(
        trace["recorded_total_cost"], abs=2e-5)
    # Also pin the per-question granularity: each row's replayed cost must
    # match that row's own recorded "total cost" (not just the run-level
    # sum, which could hide a canceling error between rows).
    recorded_by_q = {q["q"]: q["total_cost"] for q in trace["questions"]}
    for row in result["per_question"]:
        assert row["cost"] == pytest.approx(recorded_by_q[row["q"]], abs=2e-6)


def test_replay_total_raises_on_nonzero_cached_tokens():
    """The Live path bills every prompt token at full rate and
    GEMINI_PRICING_BY_FAMILY has no cached-token discount row -- a run
    reporting nonzero cached tokens must not be silently replayed as if the
    full-rate assumption still holds."""
    trace = andd.load_run(_JUNE_UNBOUNDED_HAPPY_25[0])
    trace = dict(trace, cached_total=42)
    with pytest.raises(ValueError, match="cached"):
        andd.replay_total(trace)


# --------------------------------------------------------- b. naive_replay unit

def _tiny_trace(rates):
    """A synthetic 3-event trace: text_input/audio_input grow question over
    question (mirrors the real per-question NEW-token deltas the harness
    reports), output tokens held constant for simplicity."""
    return {
        "stamp": "synthetic-3q",
        "tier": "2.5",
        "rates": rates,
        "questions": [
            {"q": 1, "text_input": 100, "audio_input": 20,
             "text_output": 10, "audio_output": 5, "total_tokens": 135,
             "total_cost": 0.0},
            {"q": 2, "text_input": 150, "audio_input": 30,
             "text_output": 10, "audio_output": 5, "total_tokens": 195,
             "total_cost": 0.0},
            {"q": 3, "text_input": 200, "audio_input": 40,
             "text_output": 10, "audio_output": 5, "total_tokens": 255,
             "total_cost": 0.0},
        ],
        "cached_total": 0,
    }


def test_naive_replay_hand_computed_3_event_trace():
    """Hand-computed expected dollars for a synthetic 3-event trace, at
    round, easy-to-check rates: text_input=$1/Mtok, audio_input=$2/Mtok,
    text_output=$3/Mtok, audio_output=$4/Mtok (i.e. 1e-6 / 2e-6 / 3e-6 / 4e-6
    USD per token), naive_si_tokens=1000.

    naive_replay charges, per question q:
      history_tokens(q) = naive_si_tokens + sum(new text_in + audio_in of
                           all STRICTLY EARLIER questions)
      prompt_cost(q) = history_tokens(q) * text_rate
                        + text_input(q) * text_rate
                        + audio_input(q) * audio_in_rate
      output_cost(q) = text_output(q) * text_out_rate
                        + audio_output(q) * audio_out_rate
      cost(q) = prompt_cost(q) + output_cost(q)

    Q1: history = 1000 + 0 = 1000
        prompt  = 1000*1e-6 + 100*1e-6 + 20*2e-6
                = 0.001000 + 0.000100 + 0.000040 = 0.001140
        output  = 10*3e-6 + 5*4e-6 = 0.000030 + 0.000020 = 0.000050
        cost1   = 0.001140 + 0.000050 = 0.001190

    Q2: prior new input = 100 + 20 = 120
        history = 1000 + 120 = 1120
        prompt  = 1120*1e-6 + 150*1e-6 + 30*2e-6
                = 0.001120 + 0.000150 + 0.000060 = 0.001330
        output  = 10*3e-6 + 5*4e-6 = 0.000050
        cost2   = 0.001330 + 0.000050 = 0.001380

    Q3: prior new input (Q1+Q2) = 120 + (150+30) = 300
        history = 1000 + 300 = 1300
        prompt  = 1300*1e-6 + 200*1e-6 + 40*2e-6
                = 0.001300 + 0.000200 + 0.000080 = 0.001580
        output  = 10*3e-6 + 5*4e-6 = 0.000050
        cost3   = 0.001580 + 0.000050 = 0.001630

    total = 0.001190 + 0.001380 + 0.001630 = 0.004200
    """
    rates = {"text_input": 1e-6, "audio_input": 2e-6,
             "text_output": 3e-6, "audio_output": 4e-6}
    trace = _tiny_trace(rates)

    result = andd.naive_replay(trace, naive_si_tokens=1000, rates=rates)

    expected_per_q = [0.001190, 0.001380, 0.001630]
    for row, expected in zip(result["per_question"], expected_per_q):
        assert row["cost"] == pytest.approx(expected, abs=1e-9)
    assert result["total_cost"] == pytest.approx(0.004200, abs=1e-6)


def test_naive_replay_exceeds_deployed_replay_for_growing_conversation():
    """Sanity property (not the exact-match pin, but cheap and worth having):
    naive (no-eviction, full-SI-every-turn) billing must cost AT LEAST as
    much as the deployed replay for any conversation whose tracked input
    actually grows, since naive strictly re-bills a superset of what the
    deployed run billed for input tokens."""
    rates = {"text_input": 1e-6, "audio_input": 2e-6,
             "text_output": 3e-6, "audio_output": 4e-6}
    trace = _tiny_trace(rates)
    deployed = andd.replay_total(trace, rates=rates)
    naive = andd.naive_replay(trace, naive_si_tokens=1000, rates=rates)
    assert naive["total_cost"] > deployed["total_cost"]


# ------------------------------------------------------ c. text_sidecar_cost

def test_text_sidecar_cost_reuses_price_text_usage_per_model():
    """text_sidecar_cost must price each event via price_text_usage keyed on
    that event's own model (bd 0cyu scar: a flat rate mispriced pro-model
    calls at the flash-lite rate) -- not a single flat rate for every event."""
    events = [
        {"caller": "secretary", "model": "gemini-2.5-flash-lite",
         "prompt_tokens": 10_000, "cached_tokens": 8_000, "output_tokens": 200},
        {"caller": "pro", "model": "gemini-2.5-pro",
         "prompt_tokens": 10_000, "cached_tokens": 8_000, "output_tokens": 200},
    ]
    result = andd.text_sidecar_cost(events)
    lite_usd = next(r["usd"] for r in result["per_event"] if r["caller"] == "secretary")
    pro_usd = next(r["usd"] for r in result["per_event"] if r["caller"] == "pro")
    # pro is priced meaningfully higher than lite for the identical token
    # counts (12.5x higher list input rate) -- a flat-rate bug would make
    # these equal.
    assert pro_usd > lite_usd * 5
    assert result["total_usd"] == pytest.approx(lite_usd + pro_usd, abs=1e-9)


def test_text_sidecar_cost_empty_events_is_zero():
    result = andd.text_sidecar_cost([])
    assert result == {"per_event": [], "total_usd": 0.0}


# ----------------------------------------------------------- d. load_run era

def test_load_run_handles_june_format_without_summary_json():
    """The June-2026 matrix format has no .summary.json sidecar -- load_run
    must not require one."""
    trace = andd.load_run(_JUNE_UNBOUNDED_HAPPY_25[0])
    assert trace["summary"] is None
    assert trace["tier"] == "2.5"
    assert len(trace["questions"]) == 20
