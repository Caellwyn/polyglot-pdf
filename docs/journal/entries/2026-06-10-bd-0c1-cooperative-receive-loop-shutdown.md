---
date: 2026-06-10
bead: polyglot-pdf-0c1
title: "WS-B core: cooperative receive-loop shutdown (closes y4a)"
tags: [hotfix, testing, harness]
---

## Trigger

The KEYSTONE of the voice round-trip hardening epic (`polyglot-pdf-wpw`, WS-B),
per the finalized plan. The `switch_section` tool callback runs ON the Gemini
receive task (`_bg_task`); the old handler awaited `finalize()` inline, which
cancels that very task BEFORE the `switch_section` FunctionResponse reaches the
wire -- orphaning the response on the session that issued it (bug y4a). It
"usually worked" only because the new session's greeting drove the model
forward; it hung whenever that turn-start didn't fire cleanly. This is the fix
that unblocks the AI-initiated section switch for the demo.

## What shipped

**"Respond, cooperatively drain, swap off-task."**

- **Adapter** (`backend/adapters/live_ai_gemini.py`): new
  `begin_graceful_shutdown()` -- synchronous, lock-free, safe to call from a
  callback on `_bg_task`. It sets `_close_after_flush`, suppresses auto-retry,
  clears `_session_ready`, and returns the per-session `_closed_event`. The
  receive loop FLUSHES its pending tool responses (`send_tool_response`) and then
  breaks on the flag -- the single flush point for both tool-call delivery paths.
  `set_callbacks` resets `_close_after_flush` and binds a fresh `_closed_event`
  per session; a task done-callback sets that event on EVERY exit path (return,
  exception, cancel) -- the anti-hang guarantee, chosen over a `try/finally`
  because it also covers cancellation and needs no re-indent of the ~1200-line
  loop. `finalize()` moves its shutdown-flag mutations INSIDE `_task_lock` (the
  shutdown race) and gained a self-call guard that downgrades a from-bg-task call
  to a graceful shutdown -- so the self-cancel can never be reintroduced.

- **Service** (`backend/services/form_filling_service.py`):
  `handle_switch_section` now returns the success payload immediately (that
  return value IS the FunctionResponse delivered on the OLD session) and runs the
  real swap on a detached `_switch_task` that awaits `_closed_event` before
  restarting -- so the old loop is fully wound down first (no two live loops
  sharing callbacks). It guards a concurrent switch (`success:false`) and the
  detached task surfaces a failed swap to the frontend as `section_switch_failed`
  instead of dying silently. `switch_to_section`'s body moved under a new
  `_switch_lock`, serializing AI-initiated vs manual switches (absorbed from
  WS-D).

- **Port** (`backend/ports/live_ai_port.py`): `begin_graceful_shutdown` added to
  `ILiveAI`.

- **Tests (red-first, recording call ORDER -- the old `.called`-only asserts
  could not catch this):** response-before-teardown; swap-awaits-closure-before-
  restart (plan hazard 5); concurrent-switch rejected; detached-failure notifies
  the FE; adapter `begin_graceful_shutdown` flag/event semantics; the `finalize`
  self-call guard; `set_callbacks` resets the flag + binds a fresh event. 244
  backend tests pass; uov.10 (one-adapter-per-WS) not regressed.

**Out of scope (deliberate):** the full "decouple callbacks from the event pump"
stays a v3jd investigate-only spike -- the serial pump is load-bearing for this
fix's flush-point correctness, and a decouple bug is a hang in front of VCs.

Fresh-eyes triage: recorded in the merge ping (this entry predates the review).

## Lessons

- **A self-cancel from inside a callback is undefined behavior, not just a
  dropped response.** `finalize()`'s `except CancelledError: pass` swallowed the
  re-delivered cancel, so the old coroutine could keep unwinding while the new
  session already started -- which is exactly why y4a "usually worked." The fix
  replaces cancel-from-within with a cooperative flag the loop polls; the
  self-call guard makes the bug unreintroducible.
- **A task done-callback beats a `try/finally` for an "always signal closure"
  guarantee.** It fires on cancellation too, and needs no re-indent of a giant
  loop body -- lower risk on the most delicate file in the repo.

## Doc freshness

Updated the two docs whose CURRENT-STATE prose this change actually altered:
- `docs/components/tool-call-flow.md` -- it previously described `switch_section`
  as the one tool that "can still orphan its response... tracked in y4a"; rewritten
  to describe the deliver-on-old-session-then-cooperatively-break flow.
- `docs/components/voice-ai.md` -- added `begin_graceful_shutdown`, the
  `set_callbacks` flag/event reset, and the `finalize` self-call guard to the
  adapter-method list.

The freshness checker also flagged `context-compression.md`, `ai-models.md`,
`hipaa-pii-policy.md`, `logging-and-cost.md`, `risk-rating.md`,
`stateless-architecture.md`, and `voice-and-vad.md` because they `Track:` the two
changed source files by glob -- but this change is concurrency/teardown only and
does not touch what any of those docs describe (PII, models, VAD, compression,
logging, statelessness, risk rubric). Reviewed and left as-is.

## Files touched

- `backend/adapters/live_ai_gemini.py` -- begin_graceful_shutdown, cooperative
  flush/break, per-session closed_event + done-callback, finalize self-call guard
  + flags-under-lock.
- `backend/services/form_filling_service.py` -- detached-swap handle_switch_section,
  _complete_section_switch, _switch_lock around switch_to_section.
- `backend/ports/live_ai_port.py` -- begin_graceful_shutdown on ILiveAI.
- `backend/tests/unit/test_section_switching.py`,
  `backend/tests/unit/test_live_ai_gemini.py` -- the red-first ordering + guard tests.
- `docs/components/tool-call-flow.md`, `docs/components/voice-ai.md` -- doc bumps.
