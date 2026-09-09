---
date: 2026-09-09
bead: polyglot-pdf-cjifh
title: "feat(telemetry): E3.2 live-voice plumbing -- firm/employee/link/kit/channel/model reach the adapter's usage event"
sprint: 22
tags: [conventions, testing]
---

## Trigger

Epic 3 bead 2 of the admin-console program (`docs/sprint_22_admin-console_plan.md`,
Epic 3 "Usage event v2", live path plumbing). Bead `polyglot-pdf-wio6m` (E3.1)
shipped the usage-event v2 CONTRACT -- one `_emit_usage` shape, a closed
`usage_kind` set, and `USAGE_CONTEXT_KEYS` (`firm_id`, `employee_id`,
`link_jti`, `kit_id`, `channel`, `model`) written unconditionally on every
call -- but the live adapter's per-turn `log_gemini_api_response` call site
was left compiling unchanged, with those six keywords accepted but never
supplied. `_handle_fill_session` in `backend/routes/websocket_routes.py`
already received `kit_id`, `firm_id`, `link_jti`, `link_employee_id` as
parameters (the claims are decoded one function up, in
`fill_form_from_schema`), but only `kit_id` + `firm_id` reached
`FormFillingService.start_session`, and only `form_session_id`/`form_id`/
`current_section_id` reached `LiveAIGemini.set_session_context`. So every
live-voice usage event emitted `firm_id`/`employee_id`/`link_jti`/`kit_id`/
`channel`/`model` as `None`, even for a session that genuinely had them --
the schema had the columns, the live path just never filled them in.

## What shipped

Widened the chain in three files:

- `backend/routes/websocket_routes.py`: `_handle_fill_session`'s call into
  `service.start_session` now passes `link_jti` and a NEW `usage_employee_id`
  parameter. `usage_employee_id` is DELIBERATELY DISTINCT from the existing
  `link_employee_id` parameter: `link_employee_id` feeds
  `log_form_session_start`'s confirmation-audit "who sent the link" field,
  which is contractually `None` for a staff session (per that function's own
  docstring -- "they are their own originator"). The usage event has a
  different requirement: attribute EVERY session to a person. So a staff
  session's `usage_employee_id` carries the staff uid
  (`claims.get("uid") or claims.get("sub")`) instead of `None`, while a
  client-link session carries the same value on both parameters. Conflating
  the two would have silently changed the confirmation-audit record's
  meaning for staff sessions -- caught before landing by re-reading
  `log_form_session_start`'s docstring, not by a test failure.
- `backend/services/form_filling_service.py`: `start_session` gains
  `link_jti`/`employee_id` params, preserved across the internal
  section-switch restart the same way `kit_id`/`firm_id` already are (that
  restart re-enters `start_session` with the new section's schema but
  `firm_id=None`/`kit_id=None`, relying on "only overwrite when non-None").
  Widens the `set_session_context(...)` call with `firm_id`, `employee_id`,
  `link_jti`, `kit_id`, and `channel=link_tokens.link_channel()` -- the same
  process-wide helper the link mint/redeem paths already use, imported
  locally (matching the existing convention in `credit_ledger.py` /
  `links_store.py` / `link_redemptions.py` / `runtime_config.py`, all of
  which import `link_channel` inside the function rather than at module
  scope).
- `backend/adapters/live_ai_gemini.py`: `set_session_context` gains the five
  context params, stored on the adapter (`self._firm_id` etc.). No
  contextvar needed -- `dependencies.get_live_ai` already builds one fresh
  `LiveAIGemini` per WebSocket, so these ids already scope correctly to one
  connection (unlike the per-process `TextAIGemini` singleton bd t86oz will
  have to route around). The per-turn `log_gemini_api_response` call now
  passes all six context keywords plus `model=self._model_name`.

## Lessons

**Getting the test's mocks right at the SDK boundary took several wrong
turns worth recording.** The bead's exit criterion asked for tests that
"drive the real handshake path with the adapter mocked at the SDK boundary."
Three separate mock-shape bugs each produced an indefinite hang rather than
a clean failure, which made them expensive to diagnose (stack-trace-on-timeout
scripting, print-tracing through `form_filling_service.py`, and finally
comparing against `test_live_ai_gemini.py`'s already-proven fixture shape):

1. `LiveAIGemini()`'s `vertexai=False` + no-api-key branch falls through to
   a BARE, REAL `genai.Client()` if `genai` is left unpatched -- it tries
   Application Default Credentials discovery and hangs. Always patch
   `backend.adapters.live_ai_gemini.genai` before constructing the adapter
   in a test, even one that never expects the connection to succeed.
2. `_run_session_loop`'s connect handling branches on
   `hasattr(connect_obj, "__aenter__")` where `connect_obj` is the RETURN
   VALUE OF CALLING `connect(...)` -- when `connect` is an `AsyncMock`, that
   return value is a coroutine object (no `__aenter__`), so the code takes
   the "awaitable returning a session" branch: `session = await connect_obj`.
   Wrapping the intended session inside an async-context-manager DOUBLE
   inside the mock's `return_value` makes `session` resolve to the WRAPPER
   object instead of something with `.receive()` -- every connection attempt
   then raises `AttributeError`, gets caught, and retries at
   `max_attempts = 3`, each attempt doing real (if fast) work, in a shape
   that is easy to mistake for "hanging forever" rather than "silently
   failing three times." The fix: `connect`'s `AsyncMock.return_value` must
   be the session object DIRECTLY, matching `test_live_ai_gemini.py`'s
   `mock_google_ai_client` fixture exactly.
3. `_handle_fill_session`'s post-handshake control loop reads
   `websocket.receive()` (Starlette's raw-message dict form), NOT
   `websocket.receive_text()` -- those are two DIFFERENT calls on two
   DIFFERENT code paths (`fill_form_from_schema`'s own handshake read uses
   `receive_text()`; `_handle_fill_session`'s loop uses `receive()`). A
   WebSocket test double that only configures `receive_text()` leaves
   `receive()` an unconfigured `MagicMock(spec=WebSocket)` auto-mock, which
   never produces a real `{"type": "websocket.disconnect"}` message -- the
   loop spins on an unrecognized message shape forever.

None of these three bugs were in production code; all three were mock-shape
mistakes in the TEST, each of which manifested as a silent hang rather than
a clean assertion failure or exception -- worth flagging in
`docs/standards/testing.md` if a similar mocked-SDK-boundary test comes up
again in this codebase.

**A parameter name that already exists for one purpose is a trap for a
second purpose with different semantics.** `link_employee_id` already meant
something specific (confirmation-audit originator, contractually `None` for
staff) before this bead; reusing it for the usage event's "attribute every
session to a person" requirement would have quietly widened its meaning for
an unrelated caller. Naming the second thing `usage_employee_id` instead
kept both contracts legible and testable independently.

## Doc freshness

Reviewed and updated three tier-2 docs whose `**Tracks:**` lines cover the
changed files and whose CONTENT was actually made stale by this change:
`docs/components/voice-ai.md` (the `set_session_context` bullet's documented
signature), `docs/standards/logging-and-cost.md` (the call-site-coverage
paragraph no longer lists the live site as pending), and
`docs/technical_guide.md` (Surface contract 20's two bullets that named this
bead as a future dependency). Also updated `backend/tests/test_usage_event_coverage.py`'s
module docstring and `ALLOWED_SITES` comment (code, not docs, but same
"cjifh is done" staleness).

Seven OTHER tier-2 docs (`context-compression.md`, `tool-call-flow.md`,
`websocket-routing.md`, `risk-rating.md`, `stateless-architecture.md`,
`validation-delegation.md`, `ws-protocol.md`) flag STALE in
`check_doc_freshness.py --all` because they track one of the three files
this bead edited (`websocket_routes.py`, `form_filling_service.py`,
`live_ai_gemini.py`), but their actual PROSE is unaffected: none of them
describe the usage-event context ids, the confirmation-audit
`link_employee_id` field, or anything else this diff touches (checked by
grep against each doc's content, not just its Tracks line). Left un-acked
deliberately -- `check_doc_freshness.py --ack` itself warned that acking
seven docs from one narrow bead "is audit work -- see the docs-audit bead
rather than clearing them at closeout," which is the right call: a
dedicated docs-audit pass should confirm these seven (and whatever else has
accumulated the same way) rather than a plumbing bead clearing them as a
side effect. Noted for the maintainer in the merge report instead.

## Files touched

- `backend/routes/websocket_routes.py` -- `_handle_fill_session` threads
  `link_jti` + a new `usage_employee_id` into `service.start_session`.
- `backend/services/form_filling_service.py` -- `start_session` gains
  `link_jti`/`employee_id` params (preserved across section-switch restart);
  widens the `set_session_context(...)` call with all five context ids plus
  `channel=link_tokens.link_channel()`.
- `backend/adapters/live_ai_gemini.py` -- `set_session_context` gains five
  context params, stored on the adapter; the per-turn
  `log_gemini_api_response` call now passes all six context keywords.
- `backend/tests/unit/test_usage_event_live_plumbing.py` (new) -- two
  layers: the real handshake path (link session + staff session) asserting
  the adapter ends up with the right ids, and a direct per-turn-emit test
  driving `_run_session_loop` with a fake `usage_metadata` event.
- `backend/tests/test_usage_event_coverage.py` -- comment/docstring updates
  only (cjifh is done, t86oz remains open).
- `docs/components/voice-ai.md`, `docs/standards/logging-and-cost.md`,
  `docs/technical_guide.md` -- current-state prose updates + stamp bumps.
