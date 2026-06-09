---
date: 2026-06-09
bead: polyglot-pdf-8c0
title: "WS-C1: restore recovery prompts + make them audible (zy3)"
tags: [hotfix, testing]
---

## Trigger

First implementation bead of the voice round-trip hardening epic
(`polyglot-pdf-wpw`), executed per the finalized plan
(`please-check-out-the-serene-church.md`, which superseded the draft charter
after a fresh-model review re-verified every anchor claim against source).
The bug: commit 7a30ad4 dropped `RECOVERY_PROMPT_LEVEL_1/2/3` from `Settings`,
so every activity-watchdog recovery level raised `AttributeError` --
caught by `websocket_routes` and turned into a `recovery_prompt_failed`
message the frontend silently drops. Net effect: when a conversation stalled,
the user heard nothing at every escalation level (bd `polyglot-pdf-zy3`,
found by fresh-eyes on PR #111).

## What shipped

- Restored the three `RECOVERY_PROMPT_LEVEL_*` scripts on `Settings`
  (`backend/config.py`), recovered from the removal commit's parent. The
  level-3 farewell was re-authored slightly: the historical wording told the
  user to click a "Connect to Voice" button that no longer exists in the
  frontend.
- Red-first spec `backend/tests/unit/test_recovery_prompt.py` -- 7 tests, 5 of
  which failed with the zy3 `AttributeError` before the fix. The spec uses a
  REAL `Settings()` deliberately: the failure was invisible to any test that
  mocked settings. Includes an ASCII-cleanliness test for the scripts
  (scar #6) and level-routing/no-op cases.
- Dropped the emoji from the level-3 log string in
  `form_filling_service.send_recovery_prompt` (scar #6, cp1252).
- **No delivery rerouting needed** (the bead's conditional resolved to "no"):
  the epic charter worried a passive context hint with no turn boundary stays
  silent on 3.1, but that predates the 1g6 model-conditional send fix.
  Verified by code trace: `send_recovery_prompt -> send_context_hint ->
  send_text_message -> text_sender -> _send_text_turn`, which is
  turn-initiating on both families (2.5/demo: `send_client_content` with
  `turn_complete=True`; 3.1: `send_realtime_input(text=)`, which
  `probe_3p1_1007.py` verified returns audio). A live "recovery audio heard"
  check was handed off to the 8k8 harness scenario (bead comment trail on
  8c0 + 8k8) -- no local `GEMINI_API_KEY` is available for a standalone probe,
  and the live check already belongs to 8k8's test map.
- Fresh-eyes triage breakdown: recorded in the merge ping (this entry predates
  the review rounds; the PR body is not re-edited after review per closeout
  doctrine).

## Lessons

- The zy3 class (config read crashes at use-time, invisible until spoken) is
  exactly why this epic's tests construct REAL `Settings()` -- a mocked
  settings object validates the mock, not the config. Generalizes to any
  Settings-consuming path.
- A charter claim can go stale fast in an active repo: two of the draft
  charter's WS-C items (sentinel leak, passive-hint silence) were already
  fixed/moot by the time work started. Re-verify each claim against source at
  bead start, not just at epic planning (this is also recorded in the epic's
  plan-review deltas).

## Doc freshness

No tier-2 component/standards docs track `backend/config.py` prompt settings
specifically; `check_doc_freshness.py` reported all tracked docs fresh at prep.
No CLAUDE.md changes.

## Files touched

- `backend/config.py` -- restored the three recovery prompt settings.
- `backend/services/form_filling_service.py` -- emoji removed from the L3 log
  string.
- `backend/tests/unit/test_recovery_prompt.py` -- new red-first spec (7 tests).
