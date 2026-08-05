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
