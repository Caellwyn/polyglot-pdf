---
date: 2026-11-18
bead: polyglot-pdf-e72on
title: "measure(cost): re-measure session cost split and compression eviction on gemini-3.8-live"
tags: [performance, harness, testing]
---

## Trigger

Epic `polyglot-pdf-r3ham` validates the production voice tier after the cutover from 2.5 native audio to `gemini-3.8-live`; 2.5 retires on Vertex on 2026-12-13. This PR ships phases 2-4 of that plan, which closes four beads:
- **r3ham.3:** spelling read-back with the TTS clip off.
- **r3ham.14:** the strict W-7 answer key, plus re-voiced spelled-name fixtures.
- **e72on:** the cost and latency benchmark.
- **r3ham.4:** targeted re-tests of the 2.5-era quirks.

All runs were on Vertex, serial, at production config (`--compression --derive-compression`, PTT, temperature 0.4). Epic spend to date is about $42 of the $50 budget.

## What shipped

- **`scripts/spikes/3p8_spelling_findings.md` (r3ham.3).** Do NOT retire the `name_spellback` clip.
  - At temperature 0.4, 2 of 15 read-backs reproduced 2.5's sticky-first-spelling defect.
  - The clip also exposes stored-value letter errors.
  - Retirement stays a maintainer decision.
- **Strict W-7 answer key and fixtures (r3ham.14).** `W7_EXPECTED`, pinned by `test_measure_harness_w7_expected.py`. The spelled-name fixtures now say "spelled A - N - A", because gTTS read "A N A" as a word.
- **`scripts/spikes/3p8_cost_bench_findings.md` (e72on).**
  - 3.8 costs about 30% more per W-7 than 2.5 at n=3 ($0.905 vs $0.697).
  - Latency is flat, and fill accuracy is equivalent.
  - Thinking and input transcription are costed as their own lines.
  - Eviction fires, and more often than on 2.5 (12-16 per W-7 vs 6).
  - No I-90 run completes, because of the q17 desync (r3ham.10).
- **`scripts/spikes/3p8_quirk_retest_findings.md` (r3ham.4).**
  - One new failure: a PTT barge-in while a BLOCKING call is pending wedges the session. Filed as bd `polyglot-pdf-dakii` (P1).
  - Temperature, language lock, `language_code`, 1011, `confirm_field`, idle gap, input transcription and voice name are unchanged.
  - Resumption is inconclusive (r3ham.11).
  - No workaround is removable.
- **Measured cost invariant.** `docs/standards/logging-and-cost.md` is rewritten for 3.8, keeping 2.5 as the prior record. The CLAUDE.md doc-map line matches it.
- **Probe fixes and additions.**
  - `diag_idle_gap_5j3im.py`: its tool stub is now awaitable.
  - New: `probe_bargein_blocking_3p8.py`, `probe_input_transcription_cost.py`, `spell_readback_truth_score.py`.
- **Not in this PR:** the pitch READMEs and the write-up (r3ham.5) go in a separate, maintainer-merged PR.

## Lessons

- **Per-event token counts do not compare across models.** 3.8 reports ONE `usage_metadata` event per turn, at about twice the size of 2.5's roughly two events. Text-in per form is about equal on both. The same one-event shape makes the harness mark long first turns `stalled` when the event lands late. Compare per-form totals, never per-event.
- **A probe written against one model can hide a stub bug that another model trips.** The idle-gap probe's sync `on_tool_call` stub was dead code on 2.5, which never called a tool. On 3.8 (call-then-speak) it crashed turn 1. When re-running an old probe on a new model, read its callbacks first.
- **An n=1 smoke result can reverse at n=3.** The smoke run had 3.8 about 4% cheaper; the benchmark has it about 30% dearer. Quote only the n=3 figure.

## Doc freshness

- **Bumped:**
  - `docs/standards/logging-and-cost.md`: invariant rewritten, new stamp. Its stamp stack, now 7, is tracked in bd `polyglot-pdf-1igex`.
  - `docs/standards/si-reduction.md`: the cost-rationale pointer.
  - `CLAUDE.md`: the doc-map cost line.
- **Edited to drop the stale "audio-in now leads" restatement:** `docs/research/secretary-agent-research-plan.md` and `docs/sprint_20_sol-intro-tts_plan.md`, which are plan records.
- **Other STALE flags** (admin-service.md and others) track files this branch did not touch, and were already stale.

## Files touched

- `scripts/spikes/3p8_spelling_findings.md`, `3p8_cost_bench_findings.md`, `3p8_quirk_retest_findings.md`: new.
- `scripts/spikes/3p8_smoke_findings.md`: correction.
- `scripts/spikes/measure_form_session_costs.py`: strict W-7 key, spelled names.
- `backend/tests/unit/test_measure_harness_w7_expected.py`: new.
- `scripts/spikes/probe_bargein_blocking_3p8.py`, `probe_input_transcription_cost.py`, `spell_readback_truth_score.py`: new.
- `scripts/spikes/diag_idle_gap_5j3im.py`: async tool stub.
- `scripts/spikes/fixtures/audio_cache/*.pcm`: re-voiced name clips.
- `scripts/spikes/data/r3ham/{spelling,bench,quirks}/`: run artifacts, no debug transcripts.
- `tests/e2e/voice-harness/RUNBOOK.md`, `driver_w7_desync.mjs`: spelling-run driver.
- `docs/standards/logging-and-cost.md`, `docs/standards/si-reduction.md`, `CLAUDE.md`, `docs/research/secretary-agent-research-plan.md`, `docs/sprint_20_sol-intro-tts_plan.md`.
- `backend/tests/unit/test_52qm4_secretary_visibility_boundary.py`: docstring only.
