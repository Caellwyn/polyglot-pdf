---
date: 2026-06-03
bead: polyglot-pdf-u01
title: "VAD invalid-sensitivity no longer drops realtime_input_config; stale dev-logging comment + retired Gemini alias fixed"
tags: [voice, vad, config, logging, conventions]
---

## Trigger

Three small backend config/adapter beads, all fresh-eyes findings from earlier
PRs, bundled into one PR because each is individually too small for its own cycle:

- `bd polyglot-pdf-u01` (bug, from PR #36 fresh-eyes): an invalid
  `VAD_*_SENSITIVITY` value silently dropped the whole `realtime_input_config`.
- `bd polyglot-pdf-jpe` (chore, from PR #38 fresh-eyes): a logging-policy comment
  named the dead `VFF_DEV_LOGGING` env var.
- `bd polyglot-pdf-0kv` (task, from PR #37 fresh-eyes): the Gemini-connection
  diagnostic script hardcoded a retired native-audio model alias.

## What shipped

**u01 — the real fix.** In `LiveAIGemini._build_vad_settings`
(`backend/adapters/live_ai_gemini.py`), a typo'd sensitivity (e.g.
`VAD_START_SENSITIVITY=MEDIUM`) made the enum bracket lookup
`types.StartSensitivity['START_SENSITIVITY_MEDIUM']` raise `KeyError`. The caller
in `_run_session_loop` wraps the build in a broad `except Exception` that logs
`failed_to_set_realtime_input_config` and continues **without** setting
`config['realtime_input_config']` at all — so one typo dropped the ENTIRE VAD
config, reverting the session to Gemini's default VAD while the adapter still
sent manual `activity_start/end` (a conflicting, undefined turn-taking state).
Fix: whitelist `LOW`/`HIGH`/`UNSPECIFIED` inside the builder and skip unknown
values with an `invalid_vad_sensitivity_skipped` warning, so the valid axis +
padding still apply and the typo degrades gracefully instead of nuking the config.
Added `test_vad_invalid_sensitivity_is_skipped_not_fatal` (start typo'd, end
valid -> end + padding survive).

**jpe — comment correction, no behavior change.** `callback_handler.py:194`
claimed `_dev_log` is gated by `VFF_DEV_LOGGING=true`. That env var is dead config
(no code reads it; already documented as such in
`docs/components/config-deployment.md`). The real gate is the `backend/.env.DEV`
marker file via `DEV_LOGGING_ENABLED` in `backend/utils/dev_file_logger.py`.
Comment now names the marker and explicitly flags `VFF_DEV_LOGGING` as dead. This
is HIPAA-adjacent clarity (the comment describes when field values may be logged).

**0kv — diagnostic script fix.** `scripts/test_gemini_connection.py` hardcoded
`gemini-live-2.5-flash-preview-native-audio-09-2025`, a retired alias the Live
API rejects (1008 not found), so the script always failed at connect. Now reads
`GEMINI_LIVE_MODEL` (default `gemini-2.5-flash-native-audio-preview-12-2025`,
matching the contract test `test_live_ai_gemini_integration.py`). Because
native-audio models reject `TEXT` modality (1007), also switched the request to
`AUDIO` and the receive loop to traverse `server_content.model_turn.parts ->
inline_data.data` (the pattern the vendored `docs/genai_docs/` reference uses)
instead of reading `response.text`.

## Doc-freshness review (no doc edits)

closeout_prep flagged several tier-2/standards docs as stale (timestamp-only:
their tracked source files were touched after the doc's `Last updated:`). Reviewed
each against this branch's actual changes; **none of them is wrong**, so no
timestamps were bumped (per the freshness protocol's "or note the review in the
closeout journal entry" path):

- `voice-and-vad.md` — describes when the VAD knobs are sent; says nothing about
  invalid-value handling. The fix hardens that path without changing the stated
  contract.
- `config-deployment.md` — already documents `VFF_DEV_LOGGING` as dead config;
  the jpe comment fix *aligns* code with the doc.
- `ai-models.md`, `hipaa-pii-policy.md`, `logging-and-cost.md`,
  `confirmation-and-audit.md`, `risk-rating.md` — none assert anything my
  comment/validation/diagnostic changes contradict.

## Stale-bead note

closeout_prep flagged `polyglot-pdf-hrn` (P1 epic, in_progress 2d) as stale. It is
unrelated to this PR and owned as a separate in-flight epic; left untouched
rather than transitioning someone else's active epic.
