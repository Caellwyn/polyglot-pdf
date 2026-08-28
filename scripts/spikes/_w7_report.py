"""One-off ad-hoc analysis for the W-7 naive-vs-deployed cost report. Reads
only committed artifacts under scripts/spikes/data/, reuses
analyze_naive_vs_deployed.load_run / replay_total / naive_replay /
project_unhappy / text_sidecar_cost_from_summary. Not a permanent module."""
from __future__ import annotations
import json
import statistics
from pathlib import Path

import sys
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from analyze_naive_vs_deployed import (
    load_run, replay_total, naive_replay, project_unhappy,
    text_sidecar_cost_from_summary,
)
from backend.config import GEMINI_PRICING_BY_FAMILY

DATA = _HERE / "data" / "wiadk-full"
PILOT = _HERE / "data" / "wiadk-pilot"

RUNS = {
    "D_happy_1": DATA / "costs_w7_2.5_dti_cont_comp_der_happy_20260827T193603Z.csv",
    "D_happy_2": DATA / "costs_w7_2.5_dti_cont_comp_der_happy_20260827T193939Z.csv",
    "D_unhappy_1": DATA / "costs_w7_2.5_dti_cont_comp_der_unhappy_20260827T194334Z.csv",
    "D_unhappy_2": DATA / "costs_w7_2.5_dti_cont_comp_der_unhappy_20260827T195050Z.csv",
    "N_happy": DATA / "costs_w7_2.5_naive_happy_20260827T193127Z.csv",
    "N_unhappy": DATA / "costs_w7_2.5_naive_unhappy_20260827T195815Z.csv",
}
PILOT_RUN = PILOT / "costs_w7_2.5_naive_happy_20260827T192900Z.csv"

traces = {k: load_run(v) for k, v in RUNS.items()}
pilot_trace = load_run(PILOT_RUN)

print("=" * 100)
print("SECTION 1: REPLAY VALIDATION")
print("=" * 100)
for k, tr in traces.items():
    res = replay_total(tr)
    delta = res["total_cost"] - tr["recorded_total_cost"]
    print(f"{k:14s} recorded={tr['recorded_total_cost']:.6f} replayed={res['total_cost']:.6f} "
          f"delta={delta:+.6f} cached_total={tr['cached_total']} "
          f"cache_summary={tr['meta'].get('cache_summary')}")

print()
print("=" * 100)
print("SECTION 2: TEXT SIDECAR")
print("=" * 100)
for k in ["D_happy_1", "D_happy_2", "D_unhappy_1", "D_unhappy_2"]:
    tr = traces[k]
    summ = tr["summary"]
    voice_recorded = summ["headline"]["voice_usd"]
    text_recorded = summ["headline"]["text_usd"]
    all_in_recorded = summ["headline"]["all_in_usd"]
    by_caller = summ["headline"]["text_usd_by_caller"]
    voice_replay = replay_total(tr)["total_cost"]
    recon_all_in = voice_replay + text_recorded
    print(f"{k:14s} voice_recorded={voice_recorded:.6f} voice_replay={voice_replay:.6f} "
          f"text_recorded={text_recorded:.6f} by_caller={by_caller} "
          f"all_in_recorded={all_in_recorded:.6f} recon(voice_replay+text)={recon_all_in:.6f} "
          f"delta={recon_all_in-all_in_recorded:+.6f}")
    # check price_text_usage path used -- check pro_pass block for model name
    pp = tr["meta"].get("pro_pass", {})
    print(f"    pro_pass model={pp.get('model')} usd(summary.pro_pass)={summ.get('pro_pass',{}).get('usd')}")
    sec = summ.get("secretary", {})
    print(f"    secretary calls={sec.get('calls')}")

print()
print("=" * 100)
print("SECTION 3: COST-LINE BREAKDOWN (modality shares)")
print("=" * 100)
def modality_totals(tr):
    rates = tr["rates"]
    tot = {"text_input": 0.0, "audio_input": 0.0, "text_output": 0.0, "audio_output": 0.0}
    for q in tr["questions"]:
        tot["text_input"] += q["text_input"] * rates["text_input"]
        tot["audio_input"] += q["audio_input"] * rates["audio_input"]
        tot["text_output"] += q["text_output"] * rates["text_output"]
        tot["audio_output"] += q["audio_output"] * rates["audio_output"]
    total = sum(tot.values())
    shares = {k: (v / total if total else 0.0) for k, v in tot.items()}
    return tot, shares, total

for k, tr in traces.items():
    tot, shares, total = modality_totals(tr)
    print(f"{k:14s} total_voice_replay={total:.6f}")
    for m in ["audio_input", "text_input", "text_output", "audio_output"]:
        print(f"    {m:14s} usd={tot[m]:.6f} share={shares[m]*100:.2f}%")

print()
print("D-arm happy mean shares (2 runs):")
d_happy_shares = [modality_totals(traces[k])[1] for k in ["D_happy_1", "D_happy_2"]]
for m in ["audio_input", "text_input", "text_output", "audio_output"]:
    vals = [s[m] * 100 for s in d_happy_shares]
    print(f"  {m}: {statistics.mean(vals):.2f}% (runs: {vals})")

print("D-arm unhappy mean shares (2 runs):")
d_unhappy_shares = [modality_totals(traces[k])[1] for k in ["D_unhappy_1", "D_unhappy_2"]]
for m in ["audio_input", "text_input", "text_output", "audio_output"]:
    vals = [s[m] * 100 for s in d_unhappy_shares]
    print(f"  {m}: {statistics.mean(vals):.2f}% (runs: {vals})")

print()
print("N-arm happy/unhappy shares:")
for k in ["N_happy", "N_unhappy"]:
    tot, shares, total = modality_totals(traces[k])
    print(f"  {k}: audio_in={shares['audio_input']*100:.2f}% text_in={shares['text_input']*100:.2f}% "
          f"text_out={shares['text_output']*100:.2f}% audio_out={shares['audio_output']*100:.2f}%")

print()
print("=" * 100)
print("SECTION 4: ESTIMATOR GRADING")
print("=" * 100)
# (a) Estimator A: naive_replay of D-unhappy mean trace, naive_si=28660
NAIVE_SI = 28660.0
measured_naive_unhappy = traces["N_unhappy"]["recorded_total_cost"]
for k in ["D_unhappy_1", "D_unhappy_2"]:
    tr = traces[k]
    naive_res = naive_replay(tr, NAIVE_SI)
    print(f"Estimator A on {k}: naive_replay total={naive_res['total_cost']:.6f} "
          f"delta vs measured N_unhappy ${measured_naive_unhappy:.6f} = "
          f"{naive_res['total_cost']-measured_naive_unhappy:+.6f} "
          f"({(naive_res['total_cost']/measured_naive_unhappy-1)*100:+.1f}%)")

a_mean = statistics.mean([
    naive_replay(traces["D_unhappy_1"], NAIVE_SI)["total_cost"],
    naive_replay(traces["D_unhappy_2"], NAIVE_SI)["total_cost"],
])
print(f"Estimator A MEAN of two D-unhappy runs: {a_mean:.6f} vs measured {measured_naive_unhappy:.6f} "
      f"delta={a_mean-measured_naive_unhappy:+.6f} ({(a_mean/measured_naive_unhappy-1)*100:+.1f}%)")

# trim-aware variant: cap modeled per-event prompt at 32k tokens
def naive_replay_trim_aware(trace, naive_si_tokens, cap=32000, rates=None):
    rates = rates or trace["rates"]
    per_question = []
    total = 0.0
    cumulative_new_input = 0.0
    for q in trace["questions"]:
        history_tokens = naive_si_tokens + cumulative_new_input
        this_turn_prompt = history_tokens + q["text_input"] + q["audio_input"]
        if this_turn_prompt > cap:
            # force-trim: the platform blind-trims oldest history back down;
            # model the trimmed prompt as capped at `cap` (same shape as the
            # real eviction_drops evidence: prompt falls back near the SI floor
            # + a residual window, but the simplest capture of "not unbounded"
            # is to cap history_tokens so this turn's own new tokens still bill
            # in full, and future history compounds from the trimmed point).
            overflow = this_turn_prompt - cap
            history_tokens = max(0.0, history_tokens - overflow)
            cumulative_new_input = max(0.0, cumulative_new_input - overflow)
        prompt_cost = (history_tokens * rates["text_input"]
                       + q["text_input"] * rates["text_input"]
                       + q["audio_input"] * rates["audio_input"])
        output_cost = (q["text_output"] * rates["text_output"]
                       + q["audio_output"] * rates["audio_output"])
        cost = prompt_cost + output_cost
        per_question.append({"q": q["q"], "prompt_tokens": history_tokens + q["text_input"] + q["audio_input"], "cost": cost})
        total += cost
        cumulative_new_input += q["text_input"] + q["audio_input"]
    return {"per_question": per_question, "total_cost": round(total, 6)}

for k in ["D_unhappy_1", "D_unhappy_2"]:
    tr = traces[k]
    trim_res = naive_replay_trim_aware(tr, NAIVE_SI)
    print(f"Estimator A (trim-aware, cap=32k) on {k}: total={trim_res['total_cost']:.6f} "
          f"delta vs measured={trim_res['total_cost']-measured_naive_unhappy:+.6f} "
          f"({(trim_res['total_cost']/measured_naive_unhappy-1)*100:+.1f}%)")
a_trim_mean = statistics.mean([
    naive_replay_trim_aware(traces["D_unhappy_1"], NAIVE_SI)["total_cost"],
    naive_replay_trim_aware(traces["D_unhappy_2"], NAIVE_SI)["total_cost"],
])
print(f"Estimator A trim-aware MEAN: {a_trim_mean:.6f} vs measured {measured_naive_unhappy:.6f} "
      f"delta={a_trim_mean-measured_naive_unhappy:+.6f} ({(a_trim_mean/measured_naive_unhappy-1)*100:+.1f}%)")

# (b) Estimator B: project_unhappy on N_happy trace, turns_multiplier from actual turn counts
n_happy_turns = len(traces["N_happy"]["meta"]["turns"])
n_unhappy_turns = len(traces["N_unhappy"]["meta"]["turns"])
turns_mult = n_unhappy_turns / n_happy_turns
print(f"\nN_happy turns={n_happy_turns} N_unhappy turns={n_unhappy_turns} turns_multiplier={turns_mult:.4f}")
proj = project_unhappy(traces["N_happy"], turns_multiplier=turns_mult)
print(f"Estimator B: project_unhappy(N_happy, mult={turns_mult:.4f}) total={proj['total_cost']:.6f} "
      f"vs measured {measured_naive_unhappy:.6f} delta={proj['total_cost']-measured_naive_unhappy:+.6f} "
      f"({(proj['total_cost']/measured_naive_unhappy-1)*100:+.1f}%)")

# (c) pilot pre-registration grading
pilot_pred = 2.27
n_happy_actual = traces["N_happy"]["recorded_total_cost"]
print(f"\nPre-registered pilot prediction=${pilot_pred:.2f} vs measured N_happy actual=${n_happy_actual:.6f} "
      f"delta={n_happy_actual-pilot_pred:+.6f} ({(n_happy_actual/pilot_pred-1)*100:+.1f}%)")

print()
print("=" * 100)
print("SECTION 5: FOOTNOTES")
print("=" * 100)
# (a) schema-only naive variant: subtract booklet's token share from text-in of every billed event
si_chars = 109722
booklet_chars = 81242
booklet_share = booklet_chars / si_chars
si_tokens_total = 27923.0  # given SI text-in token count for the full SI+booklet
booklet_tokens = booklet_share * si_tokens_total
schema_only_tokens = si_tokens_total - booklet_tokens
print(f"booklet_share={booklet_share:.6f} booklet_tokens={booklet_tokens:.2f} "
      f"schema_only_SI_tokens={schema_only_tokens:.2f}")

def schema_only_replay(trace, booklet_tokens_removed, rates=None):
    """Billing-arithmetic-only re-sum: subtract booklet_tokens_removed x
    text_input rate from EVERY billed event's text-in cost (behavior held
    fixed -- same turns, same audio, same output; only the fixed per-event
    SI-text floor shrinks by the booklet's share)."""
    rates = rates or trace["rates"]
    total = 0.0
    n_events = len(trace["questions"])
    reduction_per_event = booklet_tokens_removed * rates["text_input"]
    for q in trace["questions"]:
        cost = (q["text_input"] * rates["text_input"]
                + q["audio_input"] * rates["audio_input"]
                + q["text_output"] * rates["text_output"]
                + q["audio_output"] * rates["audio_output"])
        cost -= reduction_per_event
        total += cost
    return round(total, 6), n_events

for k in ["N_happy", "N_unhappy"]:
    tr = traces[k]
    schema_total, n_events = schema_only_replay(tr, booklet_tokens)
    recorded = tr["recorded_total_cost"]
    print(f"{k}: n_events(rows)={n_events} schema-only replay total={schema_total:.6f} "
          f"(recorded full={recorded:.6f}, savings={recorded-schema_total:.6f}, "
          f"{(1-schema_total/recorded)*100:.1f}% reduction)")

# (b) naive on 3.1 rates
rates_31 = GEMINI_PRICING_BY_FAMILY["3.1"]
print(f"\n3.1 rates: {rates_31}")
for k in ["N_happy", "N_unhappy"]:
    tr = traces[k]
    res31 = replay_total(tr, rates=rates_31)
    print(f"{k} on 3.1 rates: total={res31['total_cost']:.6f} "
          f"(2.5 recorded={tr['recorded_total_cost']:.6f}, "
          f"ratio={res31['total_cost']/tr['recorded_total_cost']:.4f}x)")

# (c) Cloud TTS spell-back line
CHIRP3_HD_RATE_PER_1M_CHARS = 30.0  # list price, training-data vintage, verify before external use
print(f"\nCloud TTS Chirp 3 HD rate assumed: ${CHIRP3_HD_RATE_PER_1M_CHARS}/1M chars "
      "(list price, training-data vintage, verify before external use -- not sourced from repo)")
for k in ["D_happy_1", "D_happy_2", "D_unhappy_1", "D_unhappy_2"]:
    tr = traces[k]
    chars = tr["meta"].get("spellback_total_chars", 0)
    cost = chars / 1_000_000 * CHIRP3_HD_RATE_PER_1M_CHARS
    print(f"{k}: spellback_total_chars={chars} spellback_count={tr['meta'].get('spellback_count')} "
          f"-> TTS cost=${cost:.8f}")

print()
print("=" * 100)
print("SECTION 6: VARIANCE BAND (i90-full E1 happy triplet)")
print("=" * 100)
E1_STAMPS = ["20260714T055600Z", "20260714T061257Z", "20260714T062904Z"]
e1_dir = _HERE / "data"
e1_costs = []
for stamp in E1_STAMPS:
    p = e1_dir / f"costs_i90-full_2.5_dti_cont_comp_happy_{stamp}.csv"
    tr = load_run(p)
    e1_costs.append(tr["recorded_total_cost"])
    print(f"  {stamp}: recorded_total={tr['recorded_total_cost']:.6f}")
e1_mean = statistics.mean(e1_costs)
e1_stdev = statistics.stdev(e1_costs)  # sample stdev, n=3
e1_cv = e1_stdev / e1_mean * 100
print(f"E1 triplet: mean={e1_mean:.6f} stdev={e1_stdev:.6f} CV={e1_cv:.2f}%")

d_happy_mean = statistics.mean([traces["D_happy_1"]["recorded_total_cost"], traces["D_happy_2"]["recorded_total_cost"]])
d_unhappy_mean = statistics.mean([traces["D_unhappy_1"]["recorded_total_cost"], traces["D_unhappy_2"]["recorded_total_cost"]])
print(f"\nApplying E1 CV={e1_cv:.2f}% as cross-form proxy band to n=2 deployed means:")
print(f"  D_happy mean=${d_happy_mean:.6f} -> band [${d_happy_mean*(1-e1_cv/100):.6f}, ${d_happy_mean*(1+e1_cv/100):.6f}]")
print(f"  D_unhappy mean=${d_unhappy_mean:.6f} -> band [${d_unhappy_mean*(1-e1_cv/100):.6f}, ${d_unhappy_mean*(1+e1_cv/100):.6f}]")

print()
print("=" * 100)
print("SECTION 7: PER-FIELD")
print("=" * 100)
for k, tr in traces.items():
    confirmed = len(tr["meta"].get("client_confirmed_fields", []))
    all_in = tr["summary"]["headline"]["all_in_usd"] if tr["summary"] else tr["recorded_total_cost"]
    usd_per_field_summary = tr["summary"]["headline"].get("usd_per_correct_field") if tr["summary"] else None
    computed = all_in / confirmed if confirmed else None
    print(f"{k:14s} confirmed_fields={confirmed} all_in=${all_in:.6f} "
          f"usd_per_correct_field(summary)={usd_per_field_summary} computed={computed}")

print()
print("Headline means verification:")
print(f"  Deployed happy mean all_in = ({traces['D_happy_1']['summary']['headline']['all_in_usd']} + "
      f"{traces['D_happy_2']['summary']['headline']['all_in_usd']}) / 2 = "
      f"{(traces['D_happy_1']['summary']['headline']['all_in_usd']+traces['D_happy_2']['summary']['headline']['all_in_usd'])/2:.6f}")
print(f"  Deployed unhappy mean all_in = ({traces['D_unhappy_1']['summary']['headline']['all_in_usd']} + "
      f"{traces['D_unhappy_2']['summary']['headline']['all_in_usd']}) / 2 = "
      f"{(traces['D_unhappy_1']['summary']['headline']['all_in_usd']+traces['D_unhappy_2']['summary']['headline']['all_in_usd'])/2:.6f}")
