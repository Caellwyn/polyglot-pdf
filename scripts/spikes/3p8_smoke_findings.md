# gemini-3.8-live single-run smoke test (bd polyglot-pdf-r3ham.2)

**Date:** 2026-11-17.

**Model:** `gemini-3.8-live` on Vertex us-central1. The model id was checked in every run's raw `.meta.json`.

**Instrument:** `scripts/spikes/measure_form_session_costs.py`, with:
- the turn-audio audit (bd r3ham.1, PR #909);
- the adapter transcript fix (bd r3ham.6, PR #911), applied locally for these runs.

**Config (production fidelity):**
- `--arm dti --continuous --compression --derive-compression --text-ai --pro-pass`.
- `LIVE_TEMPERATURE=0.4` and `SPELLBACK_TOOL_ENABLED=true`, the same as `deploy/channels/*.env`.
- Push-to-talk activity brackets.
- `--audit-transcripts --debug`. The debug artifacts contain transcripts, so they stay local and are not committed.

**Model spend for this phase:** about $5.8 across six runs:
- 3-question pilots;
- four W-7 runs;
- one I-90 v2 run;
- one 2.5 comparison run.

## Headline

| Run | Model | Fields correct | All-in $ | First-audio p50 / p90 | Notes |
|---|---|---|---|---|---|
| W-7, production config, **spelled names** | 3.8 | 21/22 | **$0.76** | 1.19 s / 1.50 s | 14 evictions. Cost split: text-in 59%, audio-in 33%. |
| W-7, same script and config | **2.5** | 22/22 | **$0.79** | 0.81 s / 1.30 s | 7 evictions. Cost split: audio-in 52%, text-in 42%. |
| W-7, names NOT spelled in script | 3.8 | **2/22** | $0.40 | -- | The model asks for the spelling and never moves on (see "Spelling ask" below). |
| W-7, spelled, compression OFF | 3.8 | 22/22 | $2.21 | 1.17 s / 1.34 s | Unbounded reference, not a deployed number. Prompt grew from 11.6k to 53k tokens. |
| I-90 v2, full 57 q, production config | 3.8 | **12/57** | $1.30 (aborted early) | 1.11 s / 1.30 s | GoAway at about 9.5 min. Script desynced at q17 and the session degraded after the reconnect. |

For reference, the 2.5 I-90 v2 production-config runs on 2026-08-28 (bd 2nikx) scored 48/57, at about $2.04-2.07 on the happy path.

**Caveat: the W-7 "fields correct" column is LENIENT.** The harness has no expected-value table for W-7, so any non-empty write counts as correct. A by-hand check of the written values (from `fill_accuracy.detail` in each `.meta.json`) against the script gives:
- **Both models wrote "Anna" for "My first name is Ana, A N A."** 3.8 wrote `Anna`; 2.5 wrote `ANNA`. That is a wrong name on a spelled answer, on both models, and the lenient scorer counted it as correct.
- **2.5 wrote passport number `104722285` for "1 0 4 7 2 2 8 5"**: it inserted a digit. 3.8 wrote `10472285`, which is correct.
- **Strict score on the like-for-like W-7: 3.8 20/22, 2.5 20/22.** 3.8 missed the name and the declined visa field; 2.5 missed the name and the passport number.
- Phase 3 (bd e72on) needs a strict W-7 expected-value table before its fill-accuracy numbers mean anything. The "Anna" result also bears directly on the Phase 2 spelling re-test (bd r3ham.3).

**Cost on the like-for-like W-7 run is flat.** 3.8 came in about 4% cheaper per form than 2.5 on the identical script:
- 3.8's text rates are higher: $0.75 in and $4.50 out, against $0.50 and $2.00.
- That is offset by fewer audio-in tokens (83k vs 135k) and more evictions.
- The cost ordering flipped as `logging-and-cost.md` predicted: on 3.8, text-in is the largest line.

**Latency regressed** by about 0.4 s at the median, measured from PTT release to the first audio byte. This fits 3.8's always-on reasoning: 70-80 thought tokens per turn, billed as text-out. All latencies here are from the LOCAL harness, not a deployed session.

## Checklist

| Item | Verdict | Evidence |
|---|---|---|
| Silent-audio turns (transcript, no audio) | **NOT OBSERVED (genuine)** | The 3 W-7 flags are `name_spellback` turns, where 3.8 transcribes its intended silence as `<no speech>{pause}`. That is a detector false positive, filed as r3ham.8. The 2 I-90 flags came in the post-reconnect degraded stretch. |
| Silent turn-end after a tool result | **OBSERVED 1/45** (W-7) | After `get_form_status` + `confirm_field`, the model said nothing and never asked the next field (`us_visa_type_number_expiration`, the run's only miss). This matches the developer forum reports. The audit's `silent_after_tool` is only meaningful for call-then-speak models: 2.5 speaks and then calls, so its 25 flags are an ordering artifact. |
| Runaway audio | **Not a defect on W-7; unexplained on I-90** | On W-7, the recurring ~39 s turn is the model reading all of `reason`'s options aloud, as the SI instructs (531 transcript chars). On I-90, after the reconnect, there were two 51 s turns with only 26 transcript chars. |
| Mid-sentence cut-offs / restarts | **OBSERVED, pervasive** | Examples: "What is the ZIP code The stored ZIP"; "Please spell your first name exactlyPlease spell...". Consistent with bd j9jpk: on 3.8, `turn_complete=True` text injections interrupt the model mid-sentence. A real user would hear constant false starts. **This is the highest-priority UX defect found.** |
| Spelling ask (names) | **CHANGED vs 2.5** | 3.8 strictly follows the SI's "ask for the SPELLING up front". If a user gives a name without spelling it, 3.8 re-asks indefinitely and ignores every later answer (2/22). On the same SI, 2.5 accepted the unspelled name (22/22 in August). |
| Spell-back TTS clip path | **WORKS** | `name_spellback` was called 3 times on W-7, and the model stayed silent while the clip played. |
| field_id accuracy | **Mostly OK; one cascade** | I-90 q17: "same, 2140 Elmwood Drive" was written as `phys_street=''`. The model then ran one field behind. A later `update_form_fields(phys_city)` was rejected as `unknown_fields`, and the scripted user desynced for the rest of the run. |
| Confirm before "yes" | NOT OBSERVED | -- |
| Duplicate / missed tool calls | **3.8: none duplicated. 2.5: repeats on 5/22 questions** | From `per_question_tools`. 2.5 called `update_form_fields` or `confirm_field` twice on q6, q7, q14, q16 and q18, and all were harmless re-writes or re-confirms. On 3.8, the only missed call is the declined-field row below. |
| Date format (MM/DD/YYYY) | **PASS** | All four W-7 dates were written as MM/DD/YYYY on both models, for example `03/14/1990`. |
| Declined field ("I do not have a U.S. visa") | **CHANGED vs 2.5** | 3.8 wrote `us_visa_type_number_expiration=''`, which is the run's miss. 2.5 wrote `N/A`. |
| Language drift | NOT TESTED | English only in this phase; the Spanish slice moved to r3ham.4. |
| Reconnect state restore | **DEGRADED** (I-90, n=1) | The fields already written were kept after the GoAway reconnect, but the resumed session behaved badly (see the GoAway row). Filed as r3ham.11. |
| Full option recital | **WORKS** (39 s) | All 8 `reason` options were read verbatim. The length is a UX problem, not a model defect. |
| GoAway / session cap | **OBSERVED at about 9.5 min** | `gemini_go_away_received time_left=30s` at event 1602. The harness reconnected before q24. The session then degraded and closed with `APIError close_code=1000`. `SESSION_RESUMPTION_ENABLED` is off, which is the production default. |
| 1011 / 1006 / 1008 drops | NOT OBSERVED | -- |
| Thinking tokens | PRESENT | About 70-80 per turn, folded into text-out. |
| Output transcription reaching the client | **Broken before r3ham.6, fixed by PR #911** | 3.8 bundles `output_transcription` with audio. Before the fix, 0 chars reached the client. |
| Lite models (secretary / validator) | OK | Called during these runs without failure. Quality is measured separately in PR #912 (u0kcc), which found no regression. |

## Not covered here (later phases of epic r3ham)

- **Spanish and other languages.** The 14-question language slice was not run (r3ham.4).
- **Spelling read-back with the TTS clip OFF** (r3ham.3). Needs PRs #910 and #911.
- **Temperature 0.4 vs 1.0, barge-in cancellation of BLOCKING calls, and resumption ON** (r3ham.4).
- **Repeat runs for variance.** Every number above is n=1; the e72on cost benchmark needs n=3.
- **Deployed latency.** PR #908 found 3.8 has barely run deployed so far.

## Harness change shipped with this doc

The name answers in `W7_QUESTIONS` and `I90V2_QUESTIONS` now include the spelling, for example "My first name is Ana, A N A." All 16 say/wrong lines changed. 3.8 will not fill a name without a spelling, and a cooperative user spells when asked.

As a result, W-7 and I-90 v2 numbers on name turns are not comparable to runs from before 2026-11-17. That is why the 2.5 comparison above was re-run on the new script.
