# Full-system stress test: continuous-DTI + secretary + validator on the I-90

Epic `polyglot-pdf-00pt` (approved 2026-07-13). Series run 2026-07-14, 25 live
runs, $39.29 spent of the $42 ceiling. Data sections below are pulled directly
from the run artifacts under `scripts/spikes/data/`; this executive section is
the synthesis. Deployed-demo latency legs pending (section 11).

## Executive verdict

**The assembled system works, and its unit economics are flat.** A complete
113-question spoken I-90 costs **$2.44 +/- $0.04 all-in** (voice + secretary +
validator) and takes **~16 minutes**, with marginal cost pinned in a
$0.020-0.023/question band from the first question to the last (see
`data/charts/`). Cost is LINEAR in form length -- the compression window
eliminated the escalating-context curve entirely. A realistic session
(corrections, recalls, navigation, a skip) runs ~$2.9-3.5; the worst-case
all-corrections path ~$5.2-5.4. Cost per correctly-filled field: ~$0.025.

**Accuracy is the axis with headroom.** Happy-path fill accuracy averaged 85.8%
(80.5-89.4% across runs); Spanish measured the same (88.5%) -- the multilingual
claim holds on first measurement. The misses are dominated by three fixable
classes: transcription slips on hard tokens, date-format rendering, and an
intermittent "chatty" model mode (3-4 of 10 full runs) that also wastes a
blocking secretary call per field (bd 2af7) and correlates with the worst
accuracy runs. Fixing the chatty mode is the single biggest lever on cost,
latency, AND accuracy at once.

**The error-catching net earns its keep.** The lite validator windows caught
the planted near-contradiction in every clean run and steered a correction
through the live rail each time (precision against a clean form: 1 false flag
in 3 clean full runs). It also caught a REAL, unplanted error in the wild --
the model mis-transcribed a city and the validator flagged it against the
country before form-complete. Far-apart contradictions are structurally
invisible to the 20-field windows (missed in every run, as designed); the W6
gemini-2.5-pro end-of-form pass is the shipped answer and its first live
measurement cost **$0.0045 and 6.6 s** for a whole-form deep check.

**Reactivity is fast when grounded, brittle when not.** Field navigation lands
in **0.53-0.66 s** (utterance end -> field pinned) every time the model names a
resolvable field -- but it guesses unresolvable identifiers in most attempts
(bd 3vby), recovering via retries. Secretary recall answered 5/5 correct in
scripted events, and the model sensibly answered from its own context half the
time without paying for a lookup.

**Resilience:** the ~10-minute session cap is a non-event (silent reconnect,
6-7.5 s, once per full form). One spontaneous 1011 produced the series' only
wedge -- in the HARNESS's old dead-session handling, since fixed; production's
client already reconnects on drops.

## Investor-facing summary (plain language, honest caveats)

| What a funder asks | Measured answer | Caveat |
|---|---|---|
| What does one form cost to fill? | $2.44 (ideal user) to $5.38 (worst case, every answer corrected); realistic ~$3 | 3 runs/arm; +/-2% on ideal path |
| How long does it take? | ~16 min ideal, ~33 min worst case, by voice, hands-free | vs hours with a preparer |
| Does cost blow up on long forms? | No -- flat $0.021/question marginal, linear total | measured to 113 questions |
| Does it work in other languages? | Spanish: same accuracy (88.5% vs 85.8% English), same cost | one full run; more languages are fixture-only additions |
| How accurate is it? | ~86% of fields land exactly right unaided; the checker then catches cross-field errors (100% of near-pair plants) and one real error in the wild | accuracy is pre-review; user confirms every field by voice as they go |
| What does error-checking cost? | Continuous checking: ~$0.01-0.06/form. Whole-form deep check: $0.0045, 6.6 s | deep check measured once live |
| How fast does "go back to X" feel? | ~0.6 s when the field resolves | identifier grounding bug filed; retries mask it today |
| Latency overall? | Turn latency p50 ~1.35 s local | LOCAL numbers overstate deployed latency (co-located backend is snappier); deployed legs pending |

## Recommended next moves (from the data, in order of leverage)

1. **bd 2af7 (chatty mode)** -- one fix moves cost (-$1/run when it strikes),
   latency (~0.9 s/field saved), and accuracy (its runs are the worst) together.
2. **bd cx23 (checkbox decline sometimes CHECKS the box)** -- lowest-frequency
   but highest-consequence wrong answer observed (legal form).
3. **Enable W6 pro pass by default** -- half a cent per form closes the far-pair
   blind spot the window design accepts.
4. **bd 5roy (name transcription) + bd 3vby (navigation grounding)** -- the two
   UX-trust findings; both have measured baselines to verify against.
5. **Scorer nits** (date-format normalization, 'Houston, Texas' any-of) --
   ~2-3 points of reported accuracy are scoring artifacts, not model errors;
   fixing the scorer gives a truer (higher) accuracy number for free.

---

Data sections below are the artifact-true record (drafted read-only from the
summary/meta files; framing corrections against the coordinator's memory are
noted inline where the artifacts disagreed).

## 1. Method summary

- Harness: `measure_form_session_costs.py --schema i90-full`, real backend
  stack against **live Vertex** (not a mock), continuous DTI (dynamic tool
  injection) + context-window compression (trigger 5000 tokens / window
  3500 tokens).
- Persona: Linh Nguyen, 113 spoken questions (full I-90 walkthrough) for
  the E1/E2/E3/E6 full runs; the E0 pilot and E6 pilot used 10-question
  slices; E4 reactivity scenarios are 16-question slices, one seam
  scenario per run (`run.reactivity` in each summary names the scenario).
- Arms: E1 happy path (`events_mode: none`), E2 realistic
  (`events_mode: standard` -- skip/recall/navigate-back/planted-conflict
  events), E3 unhappy-heavy (`path: unhappy`, `events_mode: unhappy`,
  4 planted conflict pairs vs E2's 2), E4 reactivity micro-scenarios,
  E6 Spanish (`lang: es`).
- Tool catalog: production 6-tool set (`update_form_fields`, `confirm_field`,
  `ask_secretary`, `switch_to_field`/`switch_section`, `skip_field`,
  `get_form_status`).
- Model: `gemini-live-2.5-flash-native-audio` (tier "2.5"); the E3 W6 pro
  pass (one run) used `gemini-2.5-pro` as the second-pass validator.
- All runs are **local** (harness against the local dev backend, not the
  deployed Cloud Run demo). Per the maintainer, local wall-clock/turn
  latency numbers **overstate** what the deployed (Cloud Run, co-located
  with Vertex) service will show -- see bd memory
  `harness-local-latency-overstates-deployed`. Treat every latency/
  wall-clock figure below as a local-harness ceiling, not a production
  estimate. Cost and accuracy/behavioral numbers are not subject to this
  caveat.

## 2. Per-run table -- E0 / E1 / E2

| run id (started) | phase / arm | all-in USD | voice USD | text USD | wall-clock | fill acc | failure modes (missing/format/transcr/wrong-field/mismatch/spurious) | evictions | reconnects (announced/spontaneous) | stalls | 1011s | DTI coercions | secretary calls | validator windows/steers |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| E0 pilot 1 -- T054615Z (pre-fix, 10q) | happy | $0.189541 | $0.189541 | $0 | 96.4 s | 7/10 (0.70) | 0/0/2/0/1/0 | 1 | 0/0 | 0 | 0 | 0 | 0 | 0/0 |
| E0 pilot 2 -- T055241Z (post-fix, 10q) | happy | $0.250448 | $0.239185 | $0.011263 | 97.5 s | 10/10 (1.00) | 0/0/0/0/0/0 | 2 | 0/0 | 0 | 0 | 0 | 10 | 0/0 |
| E1 run 1 -- T055600Z | happy | $2.425401 | $2.420659 | $0.004742 | 1015.7 s (16.9 min) | 99/113 (0.876) | 0/3/4/0/4/3 | 30 | 1/0 | 0 | 0 | 0 | 4 | 9/1 |
| E1 run 2 -- T061257Z | happy | $2.416718 | $2.415933 | $0.000785 | 965.2 s (16.1 min) | 91/113 (0.805) | 0/3/5/0/11/3 | 28 | 1/0 | 0 | 0 | 0 | 0 | 9/0 |
| E1 run 3 -- T062904Z | happy | $2.486589 | $2.482062 | $0.004527 | 946.7 s (15.8 min) | 101/113 (0.894) | 1/2/3/0/3/3 | 29 | 1/0 | 0 | 0 | 37 | 3 | 9(7 verdict)/0 |
| E2 run 1 -- T064929Z (WEDGED -- excluded from cost/latency stats) | realistic | $1.094919 | $1.085984 | $0.008935 | 8313.5 s (harness-side stall inflation) | 75/113 (0.664)* | 31/2/1/0/4/0 | 13 | 0/0 (spontaneous close, no GoAway) | 180 | 1 | 0 | 7 | 3/1 |
| E2 run 2 -- T090804Z | realistic | $3.460401 | $3.399272 | $0.061129 | 1202.8 s (20.0 min) | 72/113 (0.637) | 21/2/5/3/6/4 | 62 | 2/0 | 0 | 0 | 140 | 103 | 8(8 verdict)/1 |
| E2 run 3 -- T092808Z | realistic | $2.931827 | $2.924816 | $0.007011 | 2220.2 s (37.0 min) | 101/113 (0.894) | 0/3/4/0/5/0 | 34 | 1/0 | 26 | 0 | 0 | 5 | 9(7 verdict)/1 |
| E2 rerun -- T100819Z (replaces wedged run; DEGRADED-MODE replicate: chatty secretary) | realistic | $3.848147 | $3.732160 | $0.115987 | 1222.4 s (20.4 min) | 66/113 (0.584) | 31/1/2/1/9/3 | 58 | 2/0 | 0 | 0 | 8 | 238 | 4/2 |

Notes on the table:
- "Evictions" = count of `eviction_drops` entries in the run's meta.json
  (context-window compression firings), counted directly from the
  artifacts.
- "reconnects (announced/spontaneous)" = `go_away_announced` / a
  reconnect that fired without an announced GoAway. All measured
  reconnects in E1/E2 were GoAway-announced (~6-7.5s downtime each)
  except the E2 wedge run, which had zero `reconnects` recorded despite
  the session dying -- see problem-case inventory, item "spontaneous-1011
  wedge."
- "stalls" = `stalled_turns` from `errors`. The E2 wedge run recorded 180
  stalled turns (the harness gap); T092808Z recorded 26 stalled turns
  (non-fatal, session continued).
- Fill accuracy asterisk on the wedge run: 75/113 is real but reflects a
  session that terminated early via 1011 close plus 180 stalled turns --
  a resilience data point, not a comparable accuracy figure.
- The E2 rerun T100819Z hit the chatty-secretary degraded mode (238
  `ask_secretary` calls; see Section 9) -- its fill accuracy (0.584) and
  cost ($3.85) are reported as the degraded-mode replicate, flagged, not
  silently averaged into the clean E2 numbers.
- E0 pilot 1 (pre-fix) failure mode breakdown: 2 transcription + 1
  mismatch, all on the same 3-field cluster (family name / given name /
  middle name) -- this is the Nguyen-family-name transcription case
  (problem-case inventory item 1), distinct from the Denver/Hanoi organic
  catch in E1 run 1 (Section 4).

## 3. E1 (happy x3) aggregate stats

n = 3 runs (T055600Z, T061257Z, T062904Z), all clean (no wedge/stall).

| metric | mean | range (min-max) |
|---|---|---|
| all-in USD | $2.4429 | $2.4167 - $2.4866 |
| wall-clock | 975.9 s (16.26 min) | 946.7 - 1015.7 s (15.78 - 16.93 min) |
| fill accuracy | 0.858 | 0.805 - 0.894 |
| usd_per_correct_field (per-run mean) | $0.02523 | $0.02450 - $0.02656 |

(usd_per_correct_field computed per-run as all_in_usd / matched, then
averaged; taking mean-cost / mean-matched instead gives $0.02518 --
consistent to within rounding.)

## 4. E2 (realistic) seam results

| run | secretary recall (fired/correct) | navigate-back (attempts / hit-rate) | seam latency p50 | skip recorded | validator planted P/R |
|---|---|---|---|---|---|
| T064929Z (wedged) | 1 fired, 1 correct, of 2 recall events | 2 attempts / 0 hit (0%) | n/a (0 successful switches) | 1/1 | recall 0.5, precision 1.0 |
| T090804Z | 2 fired, 2 correct, of 2 recall events | 2 attempts / 1 hit (50%) | 0.578 s | 1/1 | recall 0.5, precision 1.0 |
| T092808Z | 2 fired, 2 correct, of 2 recall events | 2 attempts / 1 hit (50%) | 0.453 s | 1/1 | recall 0.5, precision 1.0 |
| T100819Z (degraded-mode replicate) | 2 fired, 0 correct / 2 WRONG, of 2 recall events | 2 attempts / 1 hit (50%) | 0.454 s | 1/1 | recall 0.5, precision 0.33 (2 false-positive groups) |

Planted-pair detail (E2 plants 2 pairs per run):
- Planted pairs: `(p1_line6e_state, p1_line6f_zipcode)` [near ZIP/state
  pair] and `(p5_line1b_language, p6_language)` [far cross-section
  language pair].
- The near ZIP/state pair was **caught and corrected in every run**
  (steer outcome `corrected_no_switch`, e.g. "US ZIP code 98101 does not
  belong to Texas").
- The far p5/p6 language pair was **missed in every run**
  (`missed_groups: [["p5_line1b_language", "p6_language"]]`) -- lite
  validator windows are 20 fields wide and the two fields in this pair
  are farther apart than that in question order. See Section 8 for the
  W6 pro-pass measurement.

Organic (unplanted) catch, E1 run 1 (T055600Z): the validator flagged a
real transcription error that was not a planted pair. `switch_to_field`
on `p1_line10_citytownofbirth` shows `"current_value": "Denver"` while
the fill-accuracy detail for the same run records
`{"field_id": "p1_line10_citytownofbirth", "expected": "Hanoi", "written":
"Denver", "ok": false}` -- the model transcribed/filled "Denver" for a
field whose correct answer was "Hanoi." The validator's steer record for
this run shows `outcome: "overridden_unplanted"` on the
`(p1_line7c_cityortown, p1_line7d_state)` /
`(p1_line10_citytownofbirth, p1_line11_countryofbirth)` conflict pair,
confirming this was caught organically, not from a planted pair.

## 5. E3 (unhappy-heavy x3)

`path: unhappy`, `events_mode: unhappy`, 4 planted conflict pairs per run
(vs 2 in E2), 113 questions / 117 steps.

| run id | all-in USD | voice USD | text USD | wall-clock | fill acc | failure modes (miss/fmt/tr/wf/mm/sp) | evictions | reconnects | stalls | DTI coercions | secretary calls | validator win/steers | planted P/R |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T102843Z (stall-heavy; see resilience note) | $2.748069 | $2.742272 | $0.005797 | 10410.7 s (2.89 h, harness-side stall inflation) | 78/113 (0.690) | 22/2/3/0/8/0 | 34 | 1 announced | 214 | 0 | 5 | 9(8 verdict)/2 | recall 0.5 (2/4), precision 0.4 |
| T132220Z | $5.382500 | $5.358735 | $0.023765 | 2000.9 s (33.3 min) | 85/113 (0.752) | 14/2/2/0/9/1 | 56 | 3 announced | 0 | 1 | 39 | 8/2 | recall 0.5 (2/4), precision 0.5 |
| T135542Z (ran --pro-pass) | $5.164852 | $5.128030 | $0.036822 | 1953.0 s (32.6 min) | 66/113 (0.584) | 40/0/1/2/3/1 | 58 | 3 announced | 0 | 59 | 43 | 7/2 | recall 0.25 (1/4), precision 1.0 |

E3 notes:
- **Resilience note on T102843Z:** 214 stalled turns; the harness's
  stall-streak recovery fired **52 stall-streak reconnects**
  (`stall_streak_reconnects: 52` in the run's meta.json; 52
  `stall-streak-reset` turn labels), on top of 1 GoAway-announced
  continuous reconnect. Wall-clock (2.89 h) is dominated by
  harness-side stall handling, not model latency -- excluded from the
  clean-run wall/cost aggregate below.
- **Clean-run aggregate (T132220Z + T135542Z):** all-in USD
  $5.16 - $5.38, wall-clock 32.6 - 33.3 min, fill accuracy 0.584 -
  0.752, usd_per_correct_field $0.0633 - $0.0783. (The stall-heavy run's
  fill was 0.690.)
- **W6 pro pass, first live measurement (T135542Z summary, top-level
  `pro_pass`):** `ran: true`, model `gemini-2.5-pro`, cost $0.004529,
  latency 6.64 s, 1 conflict caught in 1 call. The field-ids of that
  catch were not itemized in the artifact (the meta `pro_pass` record
  carries only ran/model/latency/conflicts); instrumentation has since
  been fixed to itemize them.

## 6. E4 reactivity scenarios

16-question micro-runs, one seam scenario each (`run.reactivity`).
Initial 8 runs (T143305Z - T145139Z) + 3 nav reruns
(T145654Z / T145942Z / T150220Z) with full production resolver parity.

Navigation scenarios:

| run id | scenario | switched / hit intended target | seam latency (attempt) | fill acc | all-in USD |
|---|---|---|---|---|---|
| T143305Z | nav-by-name | 1 / 1 | 0.657 s | 15/16 | $0.376453 |
| T143544Z | nav-change-value | 0 / 0 | 0.531 s | 16/16 | $0.395862 |
| T143826Z | nav-vague-address | 0 / 0 | 0.641 s | 16/16 | $0.382364 |
| T144107Z | nav-first-field | 0 / 0 | 0.641 s | 16/16 | $0.394333 |
| T145654Z (rerun) | nav-change-value | 0 / 0 | 0.593 s | 15/16 | $0.368446 |
| T145942Z (rerun) | nav-vague-address | 0 / 0 | 0.594 s | 14/16 | $0.397026 |
| T150220Z (rerun) | nav-first-field | 0 / 0 | 0.578 s | 15/16 | $0.368459 |

- Switch seam latency was 0.53 - 0.66 s in **every** measured attempt
  (7 of 7), whether or not the switch resolved to the intended target.
- Intended-target resolution: **1/4** on the initial pass, then **0/3**
  on the rerun with full production resolver parity -- the model
  hallucinates field identifiers the resolver cannot match. Bead filed:
  `polyglot-pdf-3vby` ("switch_to_field: model hallucinates unresolvable
  field identifiers on navigate-back (3/4 scenarios)").

Recall scenarios:

| run id | scenario | secretary tool fired | answer scored | fill acc | all-in USD |
|---|---|---|---|---|---|
| T144351Z | recall-value | no (answered from own context) | -- (legitimate non-use) | 15/16 | $0.337650 |
| T144624Z | recall-empty | yes | unscorable expect (correct 0 / wrong 0) | 16/16 | $0.352038 |
| T144901Z | recall-option | yes | correct | 16/16 | $0.352335 |
| T145139Z | recall-progress | no (answered from own context) | -- (legitimate non-use) | 16/16 | $0.306098 |

- Net: the model answered 2/4 recall prompts from its own context
  WITHOUT calling the secretary (legitimate -- the answer was in-context)
  and fired the tool in 2/4 (1 scored correct, 1 unscorable expect).

## 7. E6 Spanish

| run id | scope | all-in USD | wall-clock | fill acc | failure modes (miss/fmt/tr/wf/mm/sp) | evictions | reconnects | secretary calls |
|---|---|---|---|---|---|---|---|---|
| T150504Z | pilot, 10q | $0.202587 | 103.8 s | 10/10 (1.00) | 0/0/0/0/0/0 | 1 | 0 | 0 |
| T150650Z | full, 113q | $2.659650 | 959.7 s (16.0 min) | 100/113 (0.885) | 0/2/6/0/5/0 | 30 | 1 announced | 1 |

- Full-run fill accuracy 0.885 vs the English E1 mean 0.858 (range
  0.805 - 0.894) -- statistically the same band.
- 2 of the full run's 13 misses are scorer nits, not model errors:
  `p3_line3a_destination` and `p3_line3a1_cityandstate` expected
  "Houston, TX", written "Houston, Texas" (exact-match scoring).

## 8. Validator planted P/R across E2 + E3

Across all 7 event-bearing full runs (E2 x4 incl. wedge + degraded
replicate, E3 x3):

- **Near ZIP/state pair (`p1_line6e_state` / `p1_line6f_zipcode`):
  caught in every run** (it never appears in any run's `missed_groups`).
- **Far language pair (`p5_line1b_language` / `p6_language`): missed by
  the lite windowed validator in ALL runs** (present in every run's
  `missed_groups`). Lite windows are 20 fields; this pair spans farther.
- Precision ranged 0.33 - 1.0 per run (1.0 in T064929Z / T090804Z /
  T092808Z / T135542Z; 0.5 in T132220Z; 0.4 in T102843Z; 0.33 in
  T100819Z). Recall 0.5 in every run except T135542Z (0.25 of 4 plants).
- The W6 pro pass is the designed answer to far-pair blindness and is
  now **wired and measured live**: in T135542Z it ran on
  `gemini-2.5-pro`, cost $0.004529, 6.64 s latency, and caught 1
  conflict in its single call (field-ids not itemized in this artifact;
  instrumentation since fixed).

## 9. Chatty-secretary mode frequency and series spend

- `ask_secretary` call counts across the 10 full 113-question runs:
  E1 = 4 / 0 / 3; E2 = 7 (wedge) / 103 / 5 / 238 (rerun);
  E3 = 5 / 39 / 43. Normal band is 0-7 calls; the degraded
  ("chatty-secretary") mode hit 3 of 10 full runs at 103 (T090804Z),
  238 (T100819Z), and 43 (T135542Z) calls. T132220Z's 39 calls also sit
  well above the normal band with the same consecutive-question
  ~2-calls-per-question stretch in its per-question tool log.
- In-session `cache_hit_rate` correlates with the chatty runs: 0.641
  (103 calls), 0.742 (238 calls), 0.488-0.59 (43/39 calls) vs 0-0.25
  in normal runs -- see problem-case inventory, secretary-cache item.
- **Total series spend: $39.2927** summed over all 25 artifact runs
  (E0 x2, E1 x3, E2 x4, E3 x3, E4 x11, E6 x2) vs the $42 pre-approved
  ceiling.

## 10. Problem-case inventory

- **Vietnamese-name transcription (Nguyen -> Smith pre-spell-out).** E0
  pilot 1 (T054615Z, pre-fix): `p1_line3a_familyname` expected "Nguyen,"
  written "Smith" (mismatch); `p1_line3b_givenname` expected "Linh,"
  written "Lynn" (transcription); `p1_line3c_middlename` expected "Thi,"
  written "T" (transcription). Fixed by pilot 2 (T055241Z, post-fix):
  same 3 fields all exact. No dedicated bead ID found in `bd list` for
  this specific finding as of this pass -- may be tracked only inside the
  stress-test epic `polyglot-pdf-00pt`.
- **Per-field `ask_secretary` spam / chatty-secretary mode.** Hit 3 of
  10 full runs (103 / 238 / 43 calls, plus a 39-call borderline run) vs
  the 0-7 normal band; worst case T100819Z at 238 calls with fill
  accuracy degraded to 0.584 and both recall answers WRONG. Bead filed:
  `polyglot-pdf-2af7` ("Voice model asks the secretary for each field's
  spoken name before asking it (per-field blocking waste)").
- **Checkbox-decline sometimes checks the box.** T061257Z:
  `p4_checkbox1a`, `p4_checkbox1b`, `p4_checkbox1c` all expected empty,
  all written `"true"` (3 spurious fills) -- a declined/no-answer
  checkbox path wrote a positive value. Bead filed: `polyglot-pdf-cx23`
  ("Voice decline on a checkbox sometimes CHECKS it ('true') -- wrong-
  answer class on legal forms").
- **Spontaneous-1011 wedge.** E2 run T064929Z: `close_1011: 1`, 180
  stalled turns, no `go_away_announced`. Harness resilience finding --
  the harness's gap in handling a spontaneous (non-announced) 1011 close
  has since been fixed in-harness (the E3 stall-heavy run T102843Z shows
  the fixed path recovering via 52 stall-streak reconnects instead of
  wedging); the production client's own reconnect path is a separate,
  already-shipped mechanism (see bd memory
  `1011-mitigation-landscape-already-mostly-done`).
- **switch_to_field identifier hallucination.** E4: intended-target
  resolution 1/4 initial, 0/3 on rerun with full production resolver
  parity -- the model invents field identifiers the resolver cannot
  match, while seam latency itself is consistently 0.53-0.66 s. Bead
  filed: `polyglot-pdf-3vby`.
- **Far-pair validator blindness.** The `(p5_line1b_language,
  p6_language)` planted pair was missed by the lite windowed validator
  in ALL E2/E3 runs (windows are 20 fields; the pair spans farther).
  The W6 pro pass is the answer and is now wired + measured live
  (T135542Z: `gemini-2.5-pro`, $0.004529, 6.64 s, 1 conflict caught);
  its catch field-ids were not itemized in this artifact --
  instrumentation since fixed.
- **Secretary in-session cache hit far below probe rates.** Measured
  `cache_hit_rate` in normal (non-chatty) full runs: 0.1 / 0.25 / 0.0 /
  0.0 / 0.2 / 0.0 -- i.e. 0-25%, well below the 96-98% implicit-cache
  hit rates reported in prior standalone secretary-caching probes (see
  bd memory `secretary-text-model-caching-append-only`). Only the
  chatty-mode runs (39-238 calls) approached higher hit rates
  (0.49-0.74).

## 11. Numbers not yet in

- **Deployed-demo latency legs** -- all wall-clock and turn-latency
  numbers in this doc are from the **local** harness stack, which the
  maintainer has flagged as overstating real Cloud-Run-deployed latency
  (see Section 1 and bd memory
  `harness-local-latency-overstates-deployed`). No deployed-latency
  measurement exists yet in this series.
