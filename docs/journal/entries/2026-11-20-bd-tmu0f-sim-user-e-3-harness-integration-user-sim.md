---
date: 2026-11-20
bead: polyglot-pdf-tmu0f
title: "sim-user E.3: harness integration -- --user sim, playback-aware turn gate, TTS mouth, PCM capture, strict scoring"
tags: [harness, testing]
---

## Trigger

The maintainer wanted a full simulated form run before deploying the 3.8
transcript fix and the build fix to the demo, and asked for it to use the
Haiku tester. The actor core (E.1, `polyglot-pdf-ctzze`) and the STT
divergence scorer (E.2, `polyglot-pdf-wqnxr`) had merged, but nothing yet
let the actor drive a session. This bead is E.3 of epic `polyglot-pdf-ya4vi`
(plan `docs/sprint_25_sim-user_plan.md`, approved 2026-11-18). The maintainer
chose a local run, since the harness talks to Gemini directly and cannot
attach to the deployed staging service.

## What shipped

- **`--user sim` mode in `scripts/spikes/measure_form_session_costs.py`.**
  The scripted path stays the default and is untouched; every sim hook is
  inert when `gen_recorder` is None.
  - `--ears {transcript,stt}`, `--actor {haiku,stub}`, `--persona`,
    `--tts {gtts,chirp3}`, `--max-user-turns`.
  - Exit codes: 3 if the actor fell back 5 times in a row; 4 if the STT
    divergence log is invalid; 5 if the run ended incomplete.
- **`GenerationRecorder`** captures each model generation: its PCM, its
  transcript, any tool calls, and how it closed. The boundaries are the
  adapter's existing `_dev_flush_audio_dump` edges.
- **The turn gate.** The user speaks only when all of these hold:
  - the generation closed (turn_complete, interrupted, or a 5 s
    silence-close for a withheld completion);
  - no tool call is pending, and a post-tool grace period has passed;
  - simulated playback has ended, counting queued audio and the
    name_spellback clip;
  - a quiet window has passed.
- **`gate_violations` counts real overlap:** model audio arriving, or a
  generation opening, while the user's own speech is being injected.
- **Heard vs. waited-for.** The loop keeps what has been heard (`cursor`)
  separate from the reply it waits for (`watermark`). A late generation is
  still heard, and never mistaken for the reply.
- **The name_spellback clip is heard.** In sim mode the fake client feeds
  the backend's own `build_spellback_text` output to the actor.
- **Scoring:** `filled_confirmed`, `correct_vs_factsheet` (the strict scorer
  plus `W7_EXPECTED`) and `off_sheet_values`, reported side by side and
  never mixed.
- **Cost lines:** Gemini Live, sidecar, actor, TTS and STT.
- **Records:** `scripts/spikes/data/sim_user/<base>.sim-user.json`, with
  `persona_id` on every record and no PCM.
- **Guards:**
  - a fact-sheet key missing from the loaded kit aborts the run;
  - the kit's sha256 is recorded;
  - a missing Haiku key exits cleanly;
  - the STT quota project is resolved from the harness's Vertex project,
    with a pre-flight STT probe before any Gemini session opens.
- **Actor fixes (`sim_user/actor.py`):**
  - empty model text becomes "(silence)" in history, which fixes a Claude
    API 400;
  - spoken-digit runs are matched to digits;
  - the confirm rule accepts the same value said differently;
  - a correction of a spellable fact spells it.
- **STT fixes (`sim_user_stt.py`):**
  - an optional explicit quota project;
  - clips over 55 s are split for sync recognition, with a short tail folded
    into the previous piece;
  - a split clip's confidence is the minimum over its pieces, the same as a
    single request, so one corrupted piece still triggers the
    low-confidence check.
- **Chirp3 TTS** uses the same resolved quota project and gets a pre-flight
  call before any Gemini session opens.
- **Five live bring-up runs** are committed with an index
  (`scripts/spikes/data/sim_user/RUNS.md`). The last one, on the near-final
  harness, completed W-7 on `gemini-3.8-live`:
  - 22/22 filled and confirmed, 22/22 correct;
  - 47 turns, 0 gate violations, 0 STT errors;
  - 44 of 45 scored generations matched their transcript;
  - $1.48 all-in.
  Total spend across the five runs was about $5.

## Lessons

- **A harness can mistake a long, legitimate model turn for a stall.** A
  gate timeout has to start from the expected end of playback. W-7's
  option recital runs about 88 s.
- **3.8 withholds turn_complete in practice.** The live runs saw it. A
  simulated user needs a silence-close, as a human just presses
  push-to-talk.
- **A fake client that skips a side channel deafens the sim user.** The
  spellback clip is played by the client, not the model, so it has to be
  fed to the actor explicitly.
- **A measurement re-checked microseconds after its own precondition is a
  tautology.** The first `gate_violations` was zero by construction; a
  reviewer caught it.
- **A free failure path hides a broken run.** Systematic STT errors and
  actor fallbacks must fail the run loudly. An incomplete run must not
  exit 0.
- **gTTS cannot say Ana distinctly from Anna** (bd r3ham.14 again). Any
  name-correction measurement depends on the user spelling.

## Doc freshness

- No `components/` or `standards/` doc tracks the spike harness. The plan
  doc is unchanged.
- `closeout_prep` flags stacked `*Last updated:*` stamps in six docs this
  branch does not touch. They are already tracked by beads
  `polyglot-pdf-8yxx6`, `polyglot-pdf-1igex` and `polyglot-pdf-4iyi6`.
- CLAUDE.md is unchanged.

## Files touched

- `scripts/spikes/measure_form_session_costs.py`: sim mode, recorder, gate,
  driver, TTS mouth, scoring, records, guards.
- `scripts/spikes/sim_user/actor.py`: history substitution, digit matching,
  prompt rules, spelled corrections.
- `scripts/spikes/sim_user_stt.py`: explicit project, long-clip splitting.
- `.gitignore`: the Chirp3 TTS cache.
- `backend/tests/unit/test_sim_user_harness.py` (new),
  `test_sim_user_actor.py`, `test_sim_user_stt.py`.
- `scripts/spikes/data/costs_w7_3.8_dti_cont_sim_*`,
  `scripts/spikes/data/sim_user/*`: five synthetic runs and `RUNS.md`.
- `scripts/spikes/fixtures/audio_cache/*.pcm`: new gTTS cache entries
  (committed by the existing convention).
