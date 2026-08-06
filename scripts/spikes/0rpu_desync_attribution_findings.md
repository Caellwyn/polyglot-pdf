# Audio/transcript desync attribution -- STT-scored harness runs (bd polyglot-pdf-0rpu)

**Date:** 2026-08-05 (overnight). **Model:** `gemini-live-2.5-flash-native-audio`
(Vertex, project polyglot-demo-aa709), SDK google-genai >= 2.8, LIVE_TEMPERATURE=0.4,
native VAD. **Harness:** `tests/e2e/voice-harness/driver_w7_desync.mjs` (headless
Playwright, scripted gTTS fixtures, W-7 kit, 15 fields: checkboxes -> 6 spelled
names -> 6 non-name fields). **Scorer:** `scripts/spikes/stt_readback_diff.py`
(Vertex 2.5-flash, thinking budget 0, temperature 0) + offline utterance
containment (`utterance_diff.py`, session scratchpad). Raw artifacts (WAVs, dev
JSONLs, token logs, driver reports): session scratchpad `evidence/night/{smoke,runB,runA,runB2}`
-- PII-bearing, deliberately NOT committed; copy out before scratchpad cleanup if
needed long-term.

## Question

The model's AUDIO says the wrong thing (wrong name, wrong field's question,
phantom values) while tool calls and the output-text transcript stay correct.
Prior evidence correlated onset with a context-compression eviction. Is eviction
the trigger?

## Answer (measured)

**NO -- eviction is neither necessary nor, in these controlled runs, even a clear
amplifier.** The audio/text divergence is a BASELINE stochastic defect of the
native-audio model: the no-compression control diverged at a per-generation rate
at least as high as the compression runs pooled (3-4/21 vs 4/39). The historical
"every read-back after the eviction was wrong" correlation (the maintainer's
trials) stands as a real observation, but tonight's data shows the defect fires
freely without any eviction. B1's striking post-eviction cluster did NOT
replicate in B2.

## Runs

| Run | Compression | Turns | Cost | Evictions | Divergence events |
|-----|-------------|-------|------|-----------|-------------------|
| B (baseline) | ON (derived 9377/7877) | 63 | $0.9291 | 4 (-2893/-1367/-1221/-2123) | 3 (gens 5/7/9), all in the first (largest) eviction's wake; 0 pre-eviction |
| A (control) | OFF | 66 | $1.4887 | 0 | 3 utterance-diverged (gens 3/14/18) + 1 text-only silent spell-back (gen 8), scattered |
| B2 (replication) | ON (derived 9377/7877) | 63 | $0.9301 | 4 (-2927/-1166/-1329/-2034) | 1 (gen 16), 40s after eviction #4; post-eviction-#1 window CLEAN |

**The attractor.** Five of the seven audio-side divergences across all three runs
are the SAME utterance family -- "Okay, and what is your first/last name?" -- an
early-form name question the audio head regresses to from mid-form context
(B1 g5 first / g7 last / g9 first; B2 g16 first at country-of-birth; A g18 last at
country-of-birth). It appears in NO text track, ever. The audio head has a stable
fallback attractor; where the text head tracks true form state, the audio head
intermittently snaps back to asking for names.

Driver verdict PASS 15/15 fields (fill+confirm+advance) in every run -- the
MECHANICAL channel (tool calls, field state) never failed, in any run. Only
speech diverged. (Same asymmetry as all four historical incident sessions.)

## Run B detail -- the eviction-clustered pattern

Timeline (gens = per-generation output-audio WAVs, STT-transcribed and compared
with the model's own text track for the same seq window):

- gens 0-4 (pre-eviction): audio == text, 5/5 aligned, containment 0.78-1.00.
- Eviction #1 (-2893, the largest) lands at 09:07:07 during the 1a-first ->
  1a-middle boundary -- the exact spot the maintainer's failing session evicted.
- gens 5/7/9 (post-eviction #1): audio asks a DIFFERENT, EARLIER-STYLE question
  than the text track. E.g. gen 5 audio: "Okay, and what is your first name?"
  vs text: "How do you spell your last name?" -- wrong field by voice, AND the
  spell-first phrasing dropped (both maintainer-reported error modes). The audio
  phrasings appear NOWHERE in the whole session's text track (kill-shot against
  any pairing/off-by-one artifact; pre-eviction gens align under the identical
  pairing).
- gens 10-19: re-aligned, INCLUDING straight through evictions #2-#4 and a
  date-format validation retry. Small evictions did not desync in this run.

## Run A detail -- desync without ANY eviction

Token curve monotonic (zero drops, floor 4396 -> peak ~13k; no compression).

- gen 3: audio speaks **"Okay, so the first name is J-A-M-E-S."** -- the name
  JAMES was never uttered by any fixture (1a-first is J-O-H-N; the us-person
  field's value is Loretta Johnson). The text track for this generation is
  EMPTY (NO_TRANSCRIPT): the audio head spoke with no text-head counterpart.
  WAV preserved for ear-verification.
- gen 14: **the identical phantom utterance replays five minutes later** during
  mailing_city -- while the text head correctly asks the address question. The
  acoustic self-loop, with no eviction anywhere in the session.
- gen 8: the text track contains a spelled read-back ("J-O-S-E,") the audio
  NEVER SPOKE (audio went straight to the next question) -- divergence in the
  opposite direction (text-only content).
- (gen 1 was a scorer false positive -- audio "I-T-I-N" vs text "ITIN"; fixed
  with an acronym allowlist, commit on this branch.)

## Interpretation

1. The output text transcript is NOT a post-hoc transcription of the audio: the
   two tracks each contain content the other lacks (gen 3: audio-only; gen 8:
   text-only). They are separately-conditioned generation paths. (Matches the
   both-direction divergence in public reports; no Google architecture statement
   exists either way -- see the research digest on bd 0rpu.)
2. The audio path stochastically loses/regresses its conversational state --
   snapping to the name-question attractor, fabricating a name never uttered
   (phantom J-A-M-E-S, gen 3, with an EMPTY text window), replaying that phantom
   verbatim 5 minutes later at an unrelated field (gen 14), and skipping spoken
   read-backs the text track claims (gen 8) -- while text + tool paths track true
   state throughout.
3. Eviction's role after replication: B1's post-big-eviction cluster (3 events)
   did not recur in B2 (post-#1 window clean; 1 event after #4), and the
   no-eviction control diverged at a similar-or-higher per-gen rate. At n=3 the
   defensible statement is: baseline defect, possibly weather-sensitive to large
   evictions, NOT eviction-caused. The maintainer's human sessions (real mic
   audio, slower pacing, longer accumulated audio context) may sit in a regime
   where evictions matter more -- the harness's synthetic pacing is a known
   difference; do not over-generalize tonight's null to human sessions.

## Cost fact (Stage 4 input)

Compression saved ~38% of session cost on this 15-field form ($0.93 vs $1.49).
Disabling it outright has a real price that grows with form length; and per Run
A it does NOT eliminate the desync anyway.

## Consequences for the fix ladder

- Eviction-elimination policies (defer / boundary-restart / disable) REDUCE the
  clustered failures but cannot be the whole fix (A proves baseline events).
- Fixes must therefore target read-back INTEGRITY independent of compression:
  echo diet (Stage 3), client audio hygiene (Stage 2), and -- promoted by
  tonight's evidence -- evaluating the half-cascade tier (separate TTS; no
  native audio head to desync) and/or on-screen verification for names.
- Upstream report material is strong: phantom-name WAV + empty transcript +
  replay-at-wrong-field WAV + full timelines. (python-genai #2117 and
  adk-python #4231 are the closest public parallels; nothing public matches
  this exact signature with a confirmed fix.)

## Scorer notes (for reuse)

- Vertex 2.5-flash THINKS BY DEFAULT: thinking_budget=0 is mandatory or costs
  explode (Gate 2). STT of a full run costs ~$0.003.
- Letters-only comparison misses utterance-level divergence when the model
  skips spell-backs entirely (Run B spelled zero read-backs); the utterance
  containment pass catches it. Two false-positive classes fixed: 2-letter
  dotted abbreviations (U.S.), known acronyms (I-T-I-N vs ITIN).
- Divergence verdicts need BOTH tracks non-trivial; NO_TRANSCRIPT (audio with
  an empty text window) turned out to be evidence, not noise (gen 3).

## Corrections to prior records

- "Session 1 (Jose/Smith) had zero compression events, peak 8547" (bd 0rpu
  notes): WRONG -- that session (LiveAI-213ac218, main-repo token log) had FOUR
  evictions; 8547 was the final-turn prompt count. Eviction emits no event; the
  only signal is a prompt-token drop that does not return to the connect floor.
- Historical correlation stands (every incident session had evictions) but Run A
  shows correlation != sole causation.

## POST-HOC DISCOVERY (2026-08-05 morning): divergence is INTERRUPTION-LOCKED

Prompted by the maintainer's question ("was this introduced by the spell-out
instruction?"), a free re-analysis of the flush-edge metadata on every WAV dump:

| Flush edge | Generations | Diverged | Rate |
|---|---|---|---|
| turn_complete (model finished speaking) | 46 | 0 | 0% |
| interrupted (generation cut mid-stream) | 14 | 7 | 50% |

ALL SEVEN divergences across all three runs -- including the phantom J-A-M-E-S
pair and every attractor emission -- occurred on generations whose audio stream
was INTERRUPTED. Zero divergences on cleanly-completed generations, in any run,
with or without compression.

REINTERPRETATION:
- The trigger is interruption of an in-flight generation (barge-in / next input
  arriving while the model speaks). After an interruption the audio head resumes
  from truncated acoustic state -- regressing to common phrasings ("Okay, and
  what is your first name?" -- which also occurs as LEGITIMATE output, so it is
  in-distribution resumption, not novel confabulation... except J-A-M-E-S, which
  matches no name in any of tonight's sessions and remains the strongest
  upstream-report artifact), while the text head restarts cleanly from text
  context.
- The historical eviction correlation was a PROXY: evictions and interruptions
  both concentrate late-session, in the rapid-fire name block. The maintainer's
  checkbox->names confound instinct was pointing at the real variable all along
  -- the names sequence changes the interaction RHYTHM (short turns, fast
  answers, frequent barge-ins), and rhythm drives interruptions.
- The spell-out instruction's CONTENT is exonerated (divergent utterances
  IGNORE it: generic phrasing, no spell-first); its WORKFLOW plausibly
  multiplied exposure by creating exactly that rapid short-turn rhythm.
- Stage 2's swallowed `interrupted` signal is now adjacent to the crime scene:
  the same event the client discards is the one that predicts corrupted
  server-side audio. (The WAVs are server-generated, so the client holes do not
  CAUSE the divergence -- but the client's stale-playback behavior compounds
  what the user hears at precisely the risky moments.)

NEXT DISCRIMINATING EXPERIMENTS (cheap):
- Pacing arm: harness waits for turn_complete before injecting each answer ->
  prediction: zero divergence. (~$1)
- Barge-in arm: deliberate mid-speech injections -> prediction: divergence rate
  spikes. (~$1)
- Surgical fix candidate: interruption-TRIGGERED text re-anchor (inject current
  field + stored value as text only after an interruption event) -- precise,
  cheap, harness-measurable.

## ROUND 2 (2026-08-05, second $5): PTT + pacing arms -- MECHANISM CONFIRMED

| Arm | Mode | Mid-gen interrupts | REAL divergences (hand-adjudicated) |
|---|---|---|---|
| P-B | PTT + compression, default pacing | 2 (of 26 interrupt events -- PTT interrupts land mostly post-generation) | 0 |
| POLITE | native VAD, inject only after playback drains | 3 (collisions with silence-triggered re-prompts) | 2: "J-O-H-U-A, Jose" (corrupt JOSHUA blend at the Jose field) + "Lorena" (Loretta corrupted, truncated) |
| RUDE | native VAD, deliberate mid-speech barge-ins | 11 | 2: **"J-O-H-N, Joshua?"** (the maintainer's verbatim original report) + "J-O-H-N Johnson?" |

Cross-run total: every real divergence in ~150 scored generations across 6 runs
sits on a mid-generation interruption; ZERO on cleanly-completed generations.
Letters/utterance false-positive classes catalogued: seq-window offset under
slow pacing, acronyms, format strings (YYYY-MM-DD), near-silent WAVs.

MECHANISM (established): interrupting an in-flight generation corrupts the
audio head's acoustic continuation state. The corruption (a) manifests most
visibly in precision spell-backs -- the previous name's letter sequence blends
onto the current name word -- and (b) PERSISTS across generations (Run A's
phantom replayed verbatim 5 minutes later), so the exposure can be minutes
after the triggering interrupt.

THE MAINTAINER'S SESSIONS, RECONCILED: their smoking-gun session logged one
interrupt at 06:27:19 (options recital); wrong read-backs began at 06:28:17 --
when the FIRST SPELL-BACKS started. Interrupt -> persistent corruption ->
exposed at spelling time. The eviction at 06:28:02 was coincidental (four
harness runs with evictions and no mid-gen interrupts stayed clean).

BONUS FINDING (UX): under fast pacing the model SKIPS spell-backs entirely
(zero spelled read-backs in runs B1/B2); under drained pacing it spells
reliably. Pace pressure suppresses the instructed verification behavior.

FIX LADDER (final form):
1. Stage 2 client interrupted-forwarding + playback flush (barge-in becomes
   honest; removes the stale-tail the user hears).
2. Server-side INTERRUPT-TRIGGERED text re-anchor: on each interrupted event,
   inject a one-line text grounding (current field + stored value) before the
   next generation. Directly targets the corrupted-continuation state; the
   RUDE arm is its ready-made regression test.
3. Product/pacing: the verification read-back should be allowed to finish;
   barge-in during spell-back is the highest-risk moment (and the re-anchor
   catches it when users do it anyway).
4. Upstream report -- now with an ON-DEMAND repro recipe (RUDE arm), verbatim
   signature utterances, WAVs, and the persistence evidence.
5. Compression: unchanged (exonerated as trigger; keep the 38% saving).
6. Slim SI: unblocked; proceed on its own merits.

## ROUND 3 (2026-08-05/06): interrupt-triggered RE-ANCHOR -- REJECTED (runaway loop)

Fix-ladder item 2 (bd polyglot-pdf-oagw): after each `interrupted` event, inject
one short generic value-free text turn pointing the model back at its latest
guidance block. Flag-gated `INTERRUPT_REANCHOR_ENABLED`, default OFF.

| Arm | Injections | Interrupts | Fields | Real divergences | Cost |
|---|---|---|---|---|---|
| Control (OFF), RUDE, post-#550 | 0 | 27 | PASS 15/15 | 5 / 32 gens | $1.05 |
| Treatment (ON), RUDE | 1160 | 1160 | **PARTIAL 0/15** | unscoreable | **$9.93 / 105s** |

VERDICT: **the re-anchor is unshippable in this shape.** It creates a
self-reinforcing loop: the injected text turn makes Gemini START SPEAKING ->
the user (here, the RUDE harness) barges into that new speech -> `interrupted`
fires -> another injection. Measured cadence ~80 ms per cycle, 1160 cycles in
105 s, and the session never advanced past field 1. The maintainer's Gemini
research warned that text anchors next to verbal confirmation could aggravate
rather than help; the observed failure is worse and more mechanical than that --
it is positive feedback, not just a bad anchor.

WHY THE DESIGN INVITED IT: the injection had a correctness gate (the flag) but
NO RATE BOUND and no coupling to conversational progress. Any "respond to an
interruption by making the model talk" action is inherently re-entrant, because
talking is what gets interrupted.

WHAT WOULD HAVE TO CHANGE before this idea is testable again (all unproven):
- inject at most once per FIELD, not per interruption (progress-coupled), and/or
- a cooldown (e.g. ignore interrupts within N seconds of an injection), and/or
- a NON-SPEAKING re-ground: a channel that updates model context WITHOUT
  eliciting a spoken turn -- if the Live API offers one. `send_text_message`
  wraps every turn in activity signals precisely to elicit a response, so it is
  the wrong vehicle by construction.

COST DISCIPLINE LESSON (recorded for the experimentation skill): a probe that
makes the model SPEAK in response to a model EVENT needs a hard cycle cap
before its first live run. The pre-spend estimate for this arm was ~$1 (one
15-field session); it billed $9.93 in 105 seconds because the estimate assumed
a bounded turn count that the feature itself removed. Estimate the FAILURE mode's
cost, not just the happy path's.

STATUS: bd oagw code stays on its branch, flag OFF, NOT merged. Control-arm data
(5 real divergences / 32 gens under barge-in pressure, post-#550) stands as the
current baseline for the remaining ladder items (muted echo, SI state-move,
half-cascade).

## CORRECTION (2026-08-06): two earlier claims RETRACTED, core finding SURVIVES

Re-examined every "diverged" WAV by DURATION + sentence completeness, prompted by
the maintainer asking how an INTERRUPTED (i.e. abandoned) generation can emit
corrupted audio at all. Two classes emerged:

RETRACTED -- STT hallucination on sub-second scraps:
  runA gen 3, gen 14  -- WAV duration **0.11 s** (~2.6 KB), STT returned
  "Okay, so the first name is J-A-M-E-S." A tenth of a second cannot hold that
  sentence. The "phantom name that appears in no fixture" and the "verbatim
  replay five minutes later" findings were BOTH artifacts: the STT model
  hallucinated the same plausible sentence twice from two similar scraps.
  runA gen 18 (0.15 s) is the same class.
  => The scorer MUST skip sub-second dumps (the existing <0.4s guard was added
  for a different symptom and is evidently not applied to the utterance-diff
  path). Any finding resting on a <1s WAV is void.

SURVIVES -- real, complete, wrong sentences:
  runRUDE gens 6/8/10 (2.79-2.87 s) and control gens 9/11/15 (2.83-3.23 s) are
  FULLY FORMED utterances, e.g. "J-O-H-N, Joshua?" and "J-O-H-N, John Joshua,
  is that correct?" -- spelling one name while saying another. Truncation cannot
  produce these. The audio/text divergence on spelled read-backs is REAL.

ALSO NOTE: control gen 7 diverged on a **turn_complete** edge (not interrupted),
and its own text track was correct -- so interruption is not strictly necessary,
and the transcript-window pairing needs independent validation before any
rate statistic (the 24%-vs-3% and 44%-vs-1% figures) is quoted again. Those
rates are WITHDRAWN pending a pairing audit.

WHAT IS STILL SOLID: (a) the desync is real and specific to spelled name
read-backs; (b) it produces complete, plausible, WRONG utterances -- the
dangerous failure mode on a legal form; (c) tool calls and the text track stay
correct throughout.
