---
date: 2026-06-07
bead: polyglot-pdf-0y7
title: "Loop-breaker for the confirm_field / next_field_hint spin on an unconfirmable field"
tags: [testing, conventions]
---

## Trigger

`polyglot-pdf-0y7` (P1 bug): the demo console showed a tight loop on
`p1_line1_aliennumber` -- Confirming field -> computeNextField -> section
completion check (`allFieldsConfirmed: false`, next field = the SAME field) ->
next-field/confirm re-request -> Confirming field -> ... forever, while Gemini
stopped responding. The bead depended on `polyglot-pdf-0zr` (value-never-lands),
now closed, and asked for a defensive loop-breaker regardless.

## What shipped

**Mechanism of the loop.** `SchemaFormStateManager.confirmField`
(`schemaFormState.ts`) no-ops -- `return state` unchanged -- when the field has no
value (you can't confirm what isn't filled). So `computeNextField({skipConfirmed:
true})` keeps returning the same unconfirmed field, the frontend keeps answering
the backend's confirm/next-field requests with it, the backend re-requests, and
nothing advances. The `0zr` fix (A-Number normalization) removed the specific
*trigger* (the value now lands), but any future unfillable/unconfirmable field
could re-create the spin.

**The loop-breaker (`webFormConnection.handleConfirmFieldRequest`).** After calling
`confirmField`, check whether the field ACTUALLY became confirmed
(`isFieldConfirmed`). If not, it was a no-op -- count consecutive failed confirms
per field id (`confirmFailField` / `confirmFailCount`). At `CONFIRM_FAIL_LIMIT`
(2) consecutive failures on the same field, break the spin: send a **level-1
`recovery_prompt`** with the next-field hint (re-asks the user for the value via
the existing recovery channel that `websocket_routes.py` already relays to Gemini
-- no backend change needed), then reset so it re-arms rather than firing every
cycle. A successful confirm, or a switch to a different field, resets the streak.

**Diagnosability.** The `confirmField` no-op was previously SILENT, which is why
the spin was hard to diagnose. Added a `console.warn` there so the no-op (and thus
the stall) is visible in the demo console.

**Why reuse `recovery_prompt` rather than a new message type.** The frontend
already has `sendRecoveryPrompt(level, hint)` and the backend already handles
`recovery_prompt` (level -> configured prompt -> Gemini). A new message type
(e.g. `confirm_field_error`) would need backend wiring too -- and notably the
existing `dependency_error` the frontend sends is NOT in the backend dispatch
list, so a new type would be a silent no-op without backend work. Reusing the
working channel keeps this a frontend-only, in-scope fix.

Decisions made autonomously (defended in the merge ping): threshold of 2 (one
retry before intervening -- a single transient no-op shouldn't nag the user);
reuse of `recovery_prompt` over a new wire message (avoids a backend contract
change, which would be a step-2 escalation); adding the no-op warning (cheap
diagnosability, the silence was the root of the hard-to-debug-ness).

## Lessons

A guard that silently `return`s unchanged (the `confirmField` no-op) can strand a
request/response protocol in an invisible infinite loop -- the consumer must detect
"my action did not take effect" and have an escape hatch, not just assume progress.
Generalizes to any state-machine step driven by an external requester; captured
here + the tool-call-flow doc.

## Doc freshness

- **Bumped** `docs/components/tool-call-flow.md` -- added a "Frontend loop-breaker"
  note to the `confirm_field` round-trip section + a journal pointer to its stamp.
- **Reviewed and left** `schema-forms.md` / `confirmation-and-audit.md` /
  `stateless-architecture.md` (flagged stale): they track `schemaFormState.ts`,
  which this PR touched only by adding a diagnostic `console.warn` to the existing
  no-op -- the documented behavior (the no-op itself) is unchanged, so no prose
  edit was warranted.

## Verification

- New `frontend/src/webFormConnection.confirmloop.test.ts` (5 cases: no prompt
  under the limit; break with a level-1 recovery prompt at the limit; re-arm
  without spamming; reset-on-successful-confirm; per-field-id tracking) -- all pass.
- Full frontend suite: 120/123 (the 3 failures are the pre-existing
  `DisclaimerModal` regex bug, bd polyglot-pdf-pwt).
- Typecheck: 0 new errors (24 pre-existing, identical count with/without).
- NOT browser-verifiable: the loop only arises in a live WS voice session
  (backend + microphone + Gemini), so it was verified by the targeted unit test
  driving `handleConfirmFieldRequest` directly. (The worktree has no
  `frontend/node_modules`; the toolchain ran via a temporary symlink to the main
  repo's install -- gitignored, not committed.)

## Beads housekeeping

`polyglot-pdf-hrn` (P1 harness epic) again flagged stale in_progress -- another
track's active epic, left as-is (noted), same call as prior closeouts. Also filed
`polyglot-pdf-bw8` this session for the non-prompt scar-#6 backend cleanup
(emoji/em-dash in log strings + comments) surfaced while ASCII-checking the Gemini
prompts -- distinct from this bead.

## Files touched

- `frontend/src/webFormConnection.ts` -- loop-breaker in `handleConfirmFieldRequest` + the `confirmFailField`/`confirmFailCount`/`CONFIRM_FAIL_LIMIT` tracking fields.
- `frontend/src/schema-forms/state/schemaFormState.ts` -- `console.warn` on the `confirmField` no-op (was silent).
- `frontend/src/webFormConnection.confirmloop.test.ts` -- NEW: 5 regression tests for the loop-breaker.
- `docs/components/tool-call-flow.md` -- "Frontend loop-breaker" note + stamp.
