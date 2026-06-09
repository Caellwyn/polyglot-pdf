---
date: 2026-06-09
bead: polyglot-pdf-0ux
title: "Tool-response missing id crashed the receive loop after the first fill (native-audio, AI Studio)"
tags: [hotfix, testing]
---

## Trigger

The g8w voice harness, on its first live run, filled the first field correctly and
then the backend crashed:

```
ValueError: FunctionResponse request must have an `id` field from the response of a
ToolCall.FunctionalCalls in Google AI.
  at backend/adapters/live_ai_gemini.py send_tool_response
```

The crash killed the receive loop right after the first `update_form_fields`, so
Gemini never continued -- no verify question, no advance. In the real app this
would mean voice form-filling dies after one field. It bites local dev / AI Studio
(`VERTEXAI=false`); prod (Vertex) was latent.

## What shipped

`_build_function_response(tool_name, response_payload, call_id)` -- a module-level
helper in `live_ai_gemini.py` that echoes the `call_id` back on the
`FunctionResponse` when present (and omits it only if genuinely absent). Both
inline build sites now use it:

- the **event.tool_call** path (was `FunctionResponse(name, response)` with NO id,
  on a wrong "the SDK matches by order" comment -- it always dropped the id), and
- the **model_turn.parts** path (already conditional on `call_id`).

Plus a regression test: `test_run_session_loop_dispatches_tool_calls` now asserts
`response_obj.id == "call-1"` (the event.tool_call path), and the `tks`
id-absent test keeps passing (an id-less call still gets a response, no crash). A
diagnostic probe `backend/scripts/probe_tool_call_id.py` is committed.

## Diagnosis (the key insight)

The model was NOT omitting the id. The probe (real Gemini 2.5 native-audio, AI
Studio) showed the tool call arrives via `event.tool_call` WITH a valid id:

```
[tool_call] path=event.tool_call name='update_form_fields'
            id='function-call-211044821233914278' has_id_attr=True
ANY call missing id: False
```

So the id was right there in `call_id` (captured at the top of the handler) -- our
code dropped it. The SDK enforces the id ONLY on the mldev (AI Studio) path
(`google.genai/live.py` `_LiveClientToolResponse_to_mldev`); the Vertex path does
not, which is why prod stayed green while local dev crashed.

## Verified

Re-ran the g8w harness against a backend carrying this fix (2.5 native-audio):
**0 crashes** across runs (was crashing every run), the `update_form_fields`
tool_response sends cleanly, and Gemini CONTINUES the turn (many transcript events
AFTER the tool response, where before the loop was dead). Full backend suite: 224
passed.

## Follow-up

Validating the fix surfaced a SEPARATE issue (filed `polyglot-pdf-par`): with the
crash gone, Gemini fills the field and keeps talking but does NOT call
`confirm_field` after the user says "yes" -- so confirmation never lands. That's a
distinct tool-call-reliability matter (same class as
`gemini-3p1-skips-update-form-fields`), not this crash; the harness correctly
reports it as FLAKY rather than a false PASS.

## Doc freshness

`voice-ai.md` tracks `live_ai_gemini.py`; the change is an internal correctness fix
to the tool-response build (no change to the documented tool-call flow's contract),
reviewed and its date bumped with a pointer here.

## Files touched

- `backend/adapters/live_ai_gemini.py` -- `_build_function_response` helper; both
  build sites use it; corrected the wrong "SDK matches by order" comments.
- `backend/tests/unit/test_live_ai_gemini.py` -- assert the echoed id; corrected
  the `tks` test's comment.
- `backend/scripts/probe_tool_call_id.py` -- new diagnostic probe.
