---
date: 2026-07-09
bead: polyglot-pdf-7yra
title: "Voice skip_field tool -- skip a required field by voice, distinct from N/A"
tags: [voice-ai, schema-forms, ws-protocol, testing]
---

## Trigger

The user base is non-English-proficient and potentially vision-impaired, so
VOICE is the primary path. c7st+4dxt (PR #363) shipped the `skipped` flag +
enforcement + a click "Skip for now" button, but a click is not enough for this
audience -- they need to skip by voice. And today the voice path CANNOT skip a
required field: the assistant's only "skip/NA" mechanism is `update_form_fields`
with value "", and the frontend REJECTS "" on a REQUIRED field
(webFormConnection handleConfirmFieldRequest `hasUsableValue` gate), so a
required-field skip deadlocks in a confirm loop.

## Maintainer design (2026-07-09)

- A NEW `skip_field(field_id)` tool, DISTINCT from "not applicable". SKIP = "the
  question applies but I can't answer now" (defer to a translator / look it up);
  N/A = "the question doesn't apply to me" (a real answer).
- SKIP and N/A are TWO DISTINCT outcomes: SKIP -> the `skipped` flag (from 4dxt),
  renders "needs follow-up", PDF blank; N/A -> the existing `update_form_fields ""`
  path (a real, complete answer), PDF blank.
- The assistant CONFIRMS VERBALLY before acting on either ("Would you like to skip
  this question?" -> skip_field; "You said this is not applicable, right?" ->
  update_form_fields "").

## Implementation (skip_field mirrors confirm_field's synchronous round-trip)

- **backend/config.py:** new `skip_field` tool declaration (auto-registers via
  the adapter's `_function_declarations`); SI wording in ALL THREE templates (the
  legacy `SYSTEM_INSTRUCTION` full-schema default, the DTI thin-principal, and the
  JIT template) now distinguishes SKIP vs NOT-APPLICABLE and requires a verbal
  confirm before `skip_field` -- the tool is registered in every mode, so every
  template needs the guidance.
- **backend/services/request_coordinator.py:** `request_skip_field(field_id)`
  (copies `request_confirm_field`) sends `{type:"skip_field", request_id,
  field_id}` and awaits the FE ack; `handle_skip_field_response` resolves it.
- **backend/services/form_filling_service.py:** `handle_skip_field_response`
  delegates to the coordinator.
- **backend/routes/websocket_routes.py:** a `skip_field_response` inbound arm.
- **backend/services/callback_handler.py:** `on_tool_call` routes `skip_field` to
  `_handle_skip_field_tool`, which does the DTI current-field coercion, calls
  `request_skip_field`, and on `recorded` runs the SAME section-boundary /
  next-field-hint advance as confirm (a skipped field satisfies the section).
- **frontend/src/webFormConnection.ts:** a `skip_field` dispatch case ->
  `handleSkipFieldRequest`, which -- with NO usable-value gate -- calls
  `SchemaFormStateManager.markFieldSkipped(state, field_id, 'ai_voice')` and runs
  the identical advance/ack path as confirm (`sendSkipFieldResponse`).

## Contract updates

- `docs/standards/ws-protocol.md`: documented `skip_field` (backend->frontend) +
  `skip_field_response` (frontend->backend).
- `test_tool_contract_static.py`: `EXPECTED_TOOL_NAMES` + `SAMPLE_ARGS` + the
  dispatcher-wiring assertion now cover `skip_field` (7 tools).

## Verification

- New `backend/tests/unit/test_skip_field_tool.py` (5 cases): recorded skip
  advances; not-recorded -> failure (no advance); timeout -> failure; section
  boundary short-circuits the hint; the declared `field_id` arg is read.
- New `frontend/src/webFormConnection.skipfield.test.ts` (3 cases): an empty
  REQUIRED field is recorded skipped (the case confirm refuses) with `skipped`
  flag + null value + recorded:true ack; unknown field -> recorded:false; no ack
  without a request_id.
- Full frontend suite green (51 files / 841 tests); full backend suite green; tsc
  clean; tool + ws-protocol contract tests green.

## Not in scope

The N/A path is unchanged (already works via `update_form_fields ""`). This bead
adds the missing SKIP path only.
