---
date: 2026-06-08
bead: polyglot-pdf-tks
title: "Tool-call round-trip audit: guarantee a tool_response so Gemini never blocks on the first turn"
tags: [hotfix, testing]
---

## Trigger

The maintainer suspected something was going wrong in the full conversational
round-trip for tool calls -- Gemini speaks, the user responds, Gemini triggers a
tool, the system validates and responds, Gemini reads the response back. There was
no open bead covering the end-to-end flow, so we opened `polyglot-pdf-tks` to audit
it. The specific worry that drove this PR: Gemini Live blocks in a hard way if she
does not get a response to a tool call, and the failure shows up on the very first
tool-call/response loop -- before any section switching.

## What shipped

A static trace of the whole round-trip plus two fixes to the parts that can leave a
tool call unanswered.

**Fix #1 + #2 -- the adapter `model_turn.parts` receive path always emits a
response now.** Gemini Live emits a function call one of two ways, and the adapter
handles both: the canonical `event.tool_call` path and a speculative
`server_content.model_turn.parts[].function_call` fallback. On the parts path the
`FunctionResponse` append was gated on `tool_name AND call_id`, with two failure
modes that each left a call unanswered (and so blocked Gemini forever):
1. a `function_call` arriving with no `id` -> `call_id` falsy -> no response
   appended at all;
2. a tool-callback exception -> caught, `response_payload` coerced to `{}` -> but
   the same `call_id` gate could still skip the append.
The sibling `event.tool_call` path was already resilient (gates on `tool_name`
alone, omits `id`, the SDK matches by order). The fix makes the parts path match
it: append on `tool_name` only, include `id` only when present. Now every named
call -- including one whose callback raised -- gets at least an empty `{}` ack.

**Also folded in: the `confirm_field` false-completion fix (same bead, committed
earlier in the branch).** `request_next_field_hint()` returned `None` for BOTH a
genuine "form complete" AND a 2s frontend timeout, and `_handle_confirm_field_tool`
then told Gemini "All fields confirmed" for both -- so a slow round-trip made her
wrap the form up early. Added a `HINT_REQUEST_TIMEOUT` sentinel returned only on
timeout/error; the tool response now distinguishes hint / genuine-complete /
timeout (on timeout it explicitly tells Gemini NOT to assume completion). The
sentinel never reaches the wire (collapses to `None`).

**Tests.** Two new adapter regression tests
(`test_model_turn_parts_tool_call_without_id_still_responds`,
`test_model_turn_parts_tool_call_exception_still_responds`) prove the parts path
responds when the id is missing and when the callback raises. The `confirm_field`
three-way outcome is pinned by `TestConfirmFieldNextHint` (hint / complete /
timeout) and the two corrected coordinator timeout tests. Full backend suite: 223
passed / 2 skipped (up 2 from the new tests).

**Deferred (filed, not fixed here):**
- `polyglot-pdf-y4a` (new) -- `switch_section` orphans its own `tool_response`: its
  handler awaits `switch_to_section` -> `finalize()` -> `self._bg_task.cancel()`,
  which cancels the very receive-loop task that would send the response, on the old
  session it just closed. Deferred per the maintainer: section switching is
  mid-form, not the blocking first turn. Three fix options recorded on the bead.
- The frontend hallucination-reject desync (the frontend can silently drop an
  update the backend already acked to Gemini) remains open on `polyglot-pdf-tks` --
  it needs a design call, not an obvious fix.

**Pre-existing, not introduced here:** the one failing test
(`test_activity_signals_suppressed_in_native_vad`) fails identically on the base
checkout (proven via `git stash`); it is a native-VAD activity-signal test
unrelated to this change. Spun off as a background task to fix separately.

## Lessons

The two adapter receive paths drifting apart was the root hazard: one was resilient
(append on `tool_name`, no `id`), the other was not (append on `tool_name AND
call_id`). When two code paths handle "the same event two ways," a guard that is
safe on one becomes a silent hang on the other. The SDK-canonical shape
(per `docs/genai_docs/gemini_live_api_examples.md`) is `event.tool_call` with
`FunctionResponse(name=..., id=fc.id, ...)`, and the SDK matches responses to calls
by order when `id` is omitted -- so gating a response on `id` is never correct.

## Doc freshness

- `docs/components/tool-call-flow.md` -- updated (and `Last updated` bumped to
  2026-06-08): rewrote the `confirm_field` round-trip to document the three hint
  outcomes, and added a "Response invariant (every call gets a response)" note to
  the inbound section pointing the `switch_section` orphan case at `polyglot-pdf-y4a`.
- `docs/components/voice-ai.md` -- reviewed, left as-is: its tool-calling section
  delegates the full call/response sequence to `tool-call-flow.md` (already
  updated) rather than duplicating the FunctionResponse detail, so its
  current-state prose is still accurate.
- Many other component/standard docs are flagged STALE by the freshness check, but
  that staleness pre-dates this branch (their `Last updated` dates and the
  triggering file mtimes come from OTHER recent commits, not this PR's change) and
  their prose does not describe the tool-response path this PR touched. Left
  as-is per the doc-maintenance rule (a stale doc tracking files this branch did
  not meaningfully change is noted, not bumped).

## Files touched

- `backend/adapters/live_ai_gemini.py` -- parts-path `FunctionResponse` append
  gates on `tool_name` only; `id` included only when present.
- `backend/services/request_coordinator.py` -- `HINT_REQUEST_TIMEOUT` sentinel;
  timeout/error branches return it instead of `None`.
- `backend/services/callback_handler.py` -- `_handle_confirm_field_tool` three-way
  branch on hint result; `send_form_update` collapses the sentinel to `None`.
- `backend/tests/unit/test_live_ai_gemini.py` -- two new parts-path regression tests.
- `backend/tests/test_callback_handler.py` -- `TestConfirmFieldNextHint` (3 cases).
- `backend/tests/test_request_coordinator.py` -- two timeout tests updated to the
  sentinel contract.
- `docs/components/tool-call-flow.md` -- response invariant + confirm_field outcomes.
