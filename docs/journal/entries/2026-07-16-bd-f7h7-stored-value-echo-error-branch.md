---
date: 2026-07-16
bead: polyglot-pdf-f7h7
title: "fix(voice): stored-value echo is success-branch-only (no echo on collapsed multi-field error path)"
tags: [hotfix, testing]
---

## Trigger

Follow-up bug filed 2026-07-16 while tracing the stored-value echo shipped in
bd polyglot-pdf-h7wx (the voice-misfire batch). The echo (`stored_values` in
the `update_form_fields` tool response) was added to BOTH branches of
`_build_update_fields_response` in `backend/services/callback_handler.py` -- the
success branch AND the error branch. h7wx's intent was to end a confabulation
class where the model read a confirmation value back from its own (compression-
evicted) memory instead of from what the client actually stored. Putting the
echo on the error branch reintroduced that exact divergence on one path.

## The bug

The error branch is reached whenever `validation_errors or unknown_fields` is
truthy. In `_handle_update_form_fields_tool`, that same condition drives the
form-update send: `send_form_update` carries real values to the client ONLY when
`not validation_errors and not unknown_fields and applied_fields`; otherwise the
`else` sends `send_form_update({}, [])` and the client stores NOTHING.

A COLLAPSED multi-field call (the model sends two field_ids in one call; DTI
mandates one) is the concrete failure: the caller keeps the first field, tracks
the rest as `rejected_fields`, and appends a `single_field_only` entry to
`validation_errors` for each rejected one. So `validation_errors` is non-empty
(-> error branch, -> `send_form_update({}, [])`, client stores nothing) YET
`applied_fields = [first_field]` and `applied_values` holds its canonical value.
The error branch then echoed that value as `stored_values`, telling the model to
read back -- and letting the user confirm -- a value the client never stored.
Client and model state diverge; the DTI SI routes the confirmation read-back
through the echo, so the confabulation-confirm class h7wx killed came back on the
error path.

Rare in practice: the public tool-argument parser (`_parse_update_arguments`)
accepts only the single-field format, so the collapsed path is only reachable if
that parser is ever loosened again. The fix hardens the invariant at the response
builder regardless.

## Fix

Option (a) from the bead -- the minimal, safest one, matching h7wx's success-path
intent: the error branch no longer sets `stored_values` at all. Reaching the
error branch means the client stored nothing, so there is never a value to echo
there. The echo remains on the success branch, where `send_form_update` actually
delivered the value. Updated the `applied_values` docstring and the voice-ai
component doc's stored-value-echo section to state the success-branch-only rule.

## Test

Added `test_collapsed_multi_field_error_carries_no_stored_values` to
`backend/tests/unit/test_stored_value_echo.py`. Because the public parser caps
arguments at one field, the test exercises the invariant at its site --
`_build_update_fields_response` with `applied_values` populated AND
`validation_errors` present (the exact shape the caller hands it in the collapsed
case) -- and asserts `stored_values` is absent. Verified the test is non-vacuous
by temporarily re-inserting the echo on the error branch: the new test failed,
then passed again once reverted. Existing success/failure echo tests and the full
backend suite (1143 passed, 1 skipped) stay green.

## Doc freshness

Bumped the two component docs that track `callback_handler.py` AND describe the
stored-value echo: `docs/components/voice-ai.md` (echo section now states the
success-branch-only rule) and `docs/components/tool-call-flow.md` (the
round-trip step-3 prose now spells out the error-branch/collapsed carve-out; its
"on success" wording already matched the fix). The other docs the freshness
checker flagged STALE -- `ai-models`, `confirmation-and-audit`,
`hipaa-pii-policy`, `logging-and-cost`, `risk-rating`,
`section-reset-deprecation`, `terminology`, `voice-and-vad`, `technical_guide`
-- were stale before this branch, from other recent commits' mtimes on
`config.py` / `live_ai_gemini.py` / etc. Two of them also track
`callback_handler.py` (`confirmation-and-audit`, `hipaa-pii-policy`) but neither
mentions the stored-value echo, and this change is PII-neutral (it REMOVES a
model-facing field and adds nothing to any log), so they were correctly left.

## Files touched

- `backend/services/callback_handler.py` -- drop the `stored_values` echo from
  the error branch of `_build_update_fields_response`; docstring updated.
- `backend/tests/unit/test_stored_value_echo.py` -- new
  `test_collapsed_multi_field_error_carries_no_stored_values`.
- `docs/components/voice-ai.md`, `docs/components/tool-call-flow.md` -- echo is
  success-branch-only.
