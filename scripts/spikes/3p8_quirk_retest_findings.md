# gemini-3.8-live targeted re-tests (bd polyglot-pdf-r3ham.4, r3ham.11)

**Date:** 2026-11-18 (UTC).

**Model:** `gemini-3.8-live` on Vertex us-central1, google-genai 2.8.0. Each item cites the 2.5 record it is compared against.

**Spend:** about $7.1 for the batch, all serial:
- $6.80 for the 9 harness runs (sum of `all_in_usd`);
- about $0.3 for the probes.

**Raw data:** `scripts/spikes/data/r3ham/quirks/`:
- harness runs: `.summary.json`, `.meta.json`, `.csv` and `.turns.csv` per run;
- probe JSONs.

The harness `--debug` transcripts (`*.debug.json`) and the run logs stay local and are NOT committed.

## Verdicts

| Item | Verdict vs 2.5 | One line |
|---|---|---|
| PTT barge-in during a pending BLOCKING call | **changed: new 3.8 failure** | No `tool_call_cancellation` arrives, the barge is lost, and the session stays dead for the NEXT turn too (3 of 3, twice). Filed as bd **polyglot-pdf-dakii** (P1). |
| Temperature 0.4 vs 1.0 | **unchanged** | Cost, fill and latency are the same at both. Keep 0.4: its reasons (clearer speech, judged by ear, and spell-back validated at 0.4) were not re-tested. |
| Language lock (es / zh / hi / ru / ar) | **unchanged** | All 5 languages were spoken in the target script on 14 of 14 questions. Fill was 13-14 of 14. |
| `speech_config.language_code` on vs off (Spanish) | **unchanged; no effect on clean audio** | Accepted on 3.8 (no 1007). Language lock, fill and cost were identical with it off. Not shown removable (see details). |
| 1011 tool-shape probe | **unchanged** | All 36 turns clean: 4 cells x 3 reps x 3 turns. |
| `confirm_field` sequencing probe | **unchanged** | `confirm_field` fired after the "yes" in 3 of 3 runs, never early. |
| Idle gap (frame-free session gap) | **unchanged** | All 5 scored sessions answered the turn after a gap (15 s, 60 s, 90 s, and 180 s twice), with no close, as on 2.5. |
| Input transcription (bd fa4x) | **unchanged** | Fires on every PTT turn: 6 of 6 in the cost probe, and on every barge-in trial. |
| Voice name (Algieba) | **unchanged** | Accepted on 3.8. A bogus name is rejected with 1007, as on 2.5. |
| Session over 15 min, resumption off vs on (bd r3ham.11) | **inconclusive** | GoAway arrived at about 9.5-10 min, as on 2.5. Both resumption arms were confounded by the q17 desync (bd r3ham.10, now 4 of 5 I-90 runs). |

**No workaround was shown removable** by this batch. Every 2.5-era guard tested still holds or is harmless on 3.8, so no removal beads were filed.

## Details

### PTT barge-in during a pending BLOCKING call (new on 3.8)

**Probe:** `scripts/spikes/probe_bargein_blocking_3p8.py`, run twice: 3 trials plus a control, then 3 more trials with `--followup`. The setup mirrors deploy for the parts under test:
- every declaration is BLOCKING, as the adapter sets on 3.8;
- AUDIO response modality;
- input and output transcription on;
- PTT activity brackets.

**Sequence, in all 6 barge trials:**
1. The utterance produces an `update_form_fields` call. The probe does not answer it.
2. 0.3 s later the user speaks again.
3. The server sends `interrupted` and `turn_complete` within about 0.1 s.
4. No `tool_call_cancellation` arrives, and no new tool call is made.
5. The barge utterance is not transcribed.
6. The late tool response for the original id gets no reply.
7. With `--followup`, a further PTT turn 10 s later is not transcribed or answered either.

**The control arm,** where the call is answered at once, replies normally.

**Reading:** a barge during a pending call wedges the whole session until a reconnect. Exposure in production:
- small for the fast tools (update/confirm are answered in milliseconds);
- real for slow ones: `ask_secretary`, the `name_spellback` TTS render, and validator-backed writes.

The adapter has no `tool_call_cancellation` handler and nothing reconnects a silent session. The candidate fixes are in bd dakii.

### Temperature 0.4 vs 1.0

W-7 happy path, n=2 at 1.0 against the n=3 Phase 3 group at 0.4 (`3p8_cost_bench_findings.md`):

| | $ / form | Fields correct | First-audio p50 |
|---|---|---|---|
| 1.0 | $0.899, $0.886 | 21, 21 of 22 | 1.20 s, 1.22 s |
| 0.4 | $0.905 mean | 21, 21, 21 | 1.16 s pooled |

The one miss is the same at both temperatures (`Ana` stored as `Anna`, bd r3ham.15). Nothing measurable depends on temperature.

The 0.4 setting rests on speech clarity judged by ear and on the spell-back validation having been run at 0.4 (`backend/config.py`, bd 0rpu). This batch does not re-test either, so there is no case for changing it.

### Language slice and `speech_config.language_code`

W-7 happy path, first 14 questions, one run per language, `--spoken-language <L>`. Vietnamese is not a supported language, so Arabic replaces it.

The language check counts the writing script of the model's output transcript per question; the debug transcripts stay local.

| Language | Questions spoken in target script | Fields correct | $ (14 q) |
|---|---|---|---|
| Spanish | 14 of 14 (0 English function words) | 13 of 14 | $0.559 |
| Chinese | 14 of 14 (CJK dominant; Latin share = echoed names/addresses) | 13 of 14 | $0.575 |
| Hindi | 14 of 14 (Devanagari) | 13 of 14 | $0.545 |
| Russian | 14 of 14 (Cyrillic) | 14 of 14 | $0.578 |
| Arabic | 14 of 14 (Arabic) | 14 of 14 | $0.681 |
| Spanish, `SPEECH_LANGUAGE_CODE_ENABLED=false` | 14 of 14 | 13 of 14 | $0.553 |

- Every miss is the same `Ana` -> `Anna` normalization (bd r3ham.15).
- `language_code` exists for MUMBLED session-language words, where an un-biased listener slips to a neighbouring language (the es->pt case, bd m1lg / y25o).
- Clean gTTS fixtures cannot trigger that case, so "no effect" here does NOT make it removable. It is accepted on 3.8 and costs nothing.

### 1011 tool-shape probe

`scripts/spikes/diag_native_audio_1011_tools.py`, cells P1, P2, P3 and C1 (full production tool shape), 3 reps x 3 turns, all on 3.8.
- Every turn was clean, with `wire_ok` on every cell.
- On 2.5 the same probe also survived once the config was deploy-shaped (bd h04c).
- The probe sends its declarations without `behavior=BLOCKING`, so the BLOCKING shape is covered by the harness runs instead. None of the 18 3.8 harness runs across Phases 3 and 4 had a 1011 close. The only server closes were two code-1000 closes at GoAway.

### `confirm_field` sequencing probe

`backend/scripts/probe_confirm_field.py`, `PROBE_MODEL=gemini-3.8-live`, 3 runs, on Vertex. The script's "(AI Studio)" header is a stale label; the client is built with `vertexai=True`.
- `update_form_fields` fired 3 of 3 times.
- The verify question was spoken 3 of 3 times.
- `confirm_field` fired after the "yes" 3 of 3 times, and never early.

This matches 2.5. Like the 1011 probe it does not set BLOCKING. The harness runs, which do, call `confirm_field` on every confirmed W-7 field.

### Idle gap

`scripts/spikes/diag_idle_gap_5j3im.py` (deploy-shaped: real SI, real tools, VAD off). Each arm runs one live session: a 1.2 s tone turn, a gap with ZERO frames sent, then a second turn.

| Gap | Turn after the gap answered | Close |
|---|---|---|
| 15 s | 1 of 1 | none |
| 60 s | 1 of 1 | none |
| 90 s | 1 of 1 | none |
| 180 s | 2 of 2 | none |

- **2.5 record:** 6 of 6 survived at 30 s, 90 s and 180 s (`idle_gap_5j3im_findings.md`). This is unchanged.
- **Probe bug, fixed in this branch.** The first attempt crashed because 3.8 answers the tone with a `get_form_status` call on turn 1, and the probe's tool stub was a sync function returning None, which the adapter cannot await. The stub is now async and returns a payload. 2.5 never called a tool in this probe.
- **Three more arms were unscored** (`INCONCLUSIVE_TURN1`). In those, 3.8 gave no reply to the 1.2 s tone on turn 1, before any gap. That is about the stimulus (a tone, not speech), not the gap.

Data: `idle_gap_3p8.json`, `idle_gap_3p8_b.json`, `idle_gap_3p8_c.json`.

### Input transcription (bd fa4x), voice name

- **Input transcription:** `input_transcription` events fire on every PTT turn on 3.8. That was 6 of 6 turns in `probe_input_transcription_cost.py` (see `3p8_cost_bench_findings.md`) and every trial of the barge-in probe. On 2.5 it fired at START=HIGH. Unchanged.
- **Voice name:** `backend/scripts/probe_voice_name.py` shows the configured `Algieba` opens a session on 3.8, and a nonsense name is rejected with 1007 "No matching speaker voice". Unchanged.

### Long session, resumption off vs on (bd r3ham.11)

- **Resumption off** (production default): the three Phase 3 I-90 runs. Every session over about 10 min got a GoAway (`time_left=30s`), and the reconnect was clean in all 3 cases that came before a desync (`3p8_cost_bench_findings.md`).
- **Resumption on** (`SESSION_RESUMPTION_ENABLED=true`), I-90 v2, n=1:
  - Handles were captured all session. GoAway arrived during q20, and the resumed reconnect happened before q21.
  - But the session had already desynced at q17 (`phys_street`, "same, 2140 Elmwood Drive"). `confirm_field` returned `confirmed=False`, and the model ran one field behind through q20.
  - After the reconnect it went tool-silent for q21-q26, and the derailment guard aborted the run.
- **Harness fidelity gap:** after a reconnect the harness sends the initiating message with `is_resume=False`, so the resumed-session template path is not exercised.

**Verdict: inconclusive.** Both arms need a session that gets past q17 cleanly, so bd r3ham.10 blocks this measurement. The q17 desync is now 4 of 5 I-90 v2 runs on 3.8.

### Turns where the model seemed not to reply: a harness artifact, not a regression

The harness marks a turn `stalled` when no new `usage_metadata` arrives before it moves on.
- On 3.8, 1-3 turns per run are marked that way, against 0 on 2.5. It is almost always the first W-7 confirm and the I-90 q4 confirm.
- Those are the longest model turns: the first W-7 confirm runs about 39 s of audio.
- The turn-audio audit shows the model DID speak on them. 3.8 sends ONE usage event per turn, at its end, so on a long turn that event lands after the harness has moved on and is counted with the next turn.

Fill and cost totals are unaffected. No bead was filed.

## Caveats

- **Small n.** Every item is n=1-3, enough to catch a regression, not to bound a rate.
- **Synthetic speech.** Answers are clean gTTS speech, and the scripted user always says yes.
- **Local runs.** Latency figures are local.
