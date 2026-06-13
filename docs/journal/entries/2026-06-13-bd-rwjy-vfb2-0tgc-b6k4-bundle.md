---
date: 2026-06-13
beads: [polyglot-pdf-rwjy, polyglot-pdf-vfb2, polyglot-pdf-0tgc, polyglot-pdf-b6k4]
pr: TBD
tags: [bug, backend, frontend, tests, callback, latency, audit]
---

# Bug-fix bundle: rwjy + vfb2 + 0tgc + b6k4

Four small correctness fixes bundled into one PR.

## rwjy -- confirmation audit logging silently disabled

`CallbackHandler.__init__` accepts `form_id` and `form_session_id` for the
confirmation audit guard (`if self._form_id and self._form_session_id: log_field_confirmation(...)`).
But `start_session` was constructing `CallbackHandler` before extracting `form_id`
from the schema (form_id was extracted later, only for the token-logging context).
Fix: extract `form_id` before the constructor call and pass both IDs in.

## vfb2 -- wasted next_field_hint round-trip on update path

`send_form_update()` always awaited `request_next_field_hint()` (~2s round-trip on
slow clients). Every caller on the `update_form_fields` path discards the return
value -- the hint is intentionally deferred to `confirm_field` to save tokens
(already documented in `tool-call-flow.md` line 86-87). Fix: add `request_hint:
bool = False` parameter; the round-trip only fires when callers opt in.

## 0tgc -- onStopCapture/onFormComplete dead on ConnectionCallbacks

Both callbacks were declared on `ConnectionCallbacks` and read in
`handleConfirmFieldRequest` (audio-stop before section switch, form-complete
notification), but the `callbacks` object built inside `createConnectionManager`
never populated them. Fix: wire `onStopCapture` to `audioManager.stopRecording()`
and `onFormComplete` to a console log in the closure.

## b6k4 -- mirror-impl rate-limit tests + vacuous assertNoRearmOnFreshMount

Rate-limit warn tests in `micSendGate.test.ts` used a hand-copied closure with
zero coverage of the production code. Fix: extract `createMicDropWarn()` from
`connection.ts` (exported), drive tests through it directly.
`assertNoRearmOnFreshMount` in `VoiceOverlayResizeFlip.test.tsx` had no `expect()`
calls. Fix: assert `createConnectionManager` was called (standalone path created
its own manager) so the test actually pins observable behavior.

## Doc-freshness triage

Stale-doc checker flagged docs tracking `callback_handler.py`, `form_filling_service.py`,
and `connection.ts`. Reviewed each:

- `tool-call-flow.md`: already states "update_form_fields does NOT fetch the
  next-field hint" (lines 86-87) -- vfb2 fix enforces this at code level; doc accurate.
- `confirmation-and-audit.md`: documents that confirmation logging fires after
  recorded=true; rwjy fix makes the code actually do what the doc says; doc accurate.
- `voice-ai.md`, `websocket-routing.md`, `stateless-architecture.md`,
  `voice-and-vad.md`: connection.ts changes (createMicDropWarn helper + two callback
  wires) add no new architectural behavior; doc content unchanged.
- `config-deployment.md`, `context-compression.md`, `hipaa-pii-policy.md`: flagged
  by file mtime only; none describe callback_handler or form_filling_service
  internals touched by this PR.
- `beads-remote-bootstrap.md`, `pdf-filling.md`: flagged by mtime of unrelated files
  (bd_prime.py, pdfFiller.ts) not changed by this PR.

All stale flags are mtime false-positives; no doc content updates required.
