---
date: 2026-06-07
bead: polyglot-pdf-0y7
title: "Loop-breaker for the confirm_field / next_field_hint spin on an unconfirmable field"
tags: [conventions]
---

## Trigger

`polyglot-pdf-0y7` (P1 bug): the demo console showed a tight loop on
`p1_line1_aliennumber` -- Confirming field -> computeNextField -> section
completion check (`allFieldsConfirmed: false`, `nextFieldInCurrentSection` = the
SAME field) -> `next_field_hint_response` -> backend re-requests -> Confirming
field ... forever, while Gemini went silent. Blocked-on bead `polyglot-pdf-0zr`
(value-never-lands) is now closed, but 0y7 explicitly asked for a **loop-breaker**
so a field that genuinely cannot be confirmed does not spin even if a future bug
re-creates the no-value condition.

## What shipped

**Mechanism.** `SchemaFormStateManager.confirmField()` is a no-op when the target
field has no value (`if (!fieldValue) return state;` -- "field doesn't exist" in
the `fieldValues` map). So when the backend asks to `confirm_field` an empty
field, the field stays unconfirmed; `computeNextField({skipConfirmed:true})`
returns that SAME field (PRIORITY 1 is "first filled-but-unconfirmed", PRIORITY 2
the first empty field -- either way the unfillable field wins); and
`handleConfirmFieldRequest` saw `nextField != null`, skipped the
section-completion branch, and **returned silently**. The backend then re-requested
the next-field hint, got the same field, told Gemini to confirm it again, and the
cycle repeated with no progress and no user-visible error.

**Fix (`frontend/src/webFormConnection.ts`, `handleConfirmFieldRequest`).** After
calling `confirmField`, check whether the confirm actually took
(`SchemaFormStateManager.isFieldConfirmed`). If it did NOT, count consecutive
failed confirms of the *same* field id (`lastUnconfirmableFieldId` +
`unconfirmableConfirmCount`). Past a small threshold
(`UNCONFIRMABLE_CONFIRM_LIMIT = 2`), break the spin: reset the counter and
`send({type: 'completion_message', message: ...})` telling Gemini the field has no
value, to stop calling `confirm_field` on it, and to ask the user for the value
then call `update_form_fields` before confirming. The counter resets on a genuine
successful confirm too, so a real later attempt is not penalized. On the
unconfirmable path the handler returns early -- correctly skipping the
section-completion / auto-switch branch, since an unconfirmed field means the
section is by definition not complete.

**Why a re-prompt rather than a hard error.** The loop's root is Gemini
confirming before a value lands; the corrective is to redirect Gemini to *collect*
the value (the productive next step) rather than surface a dead-end error to the
user. `completion_message` is the existing wire type that maps to
`service.send_prompt()` (`websocket_routes.py:374`), which calls
`send_client_content()` to actually make Gemini speak/act -- exactly what a
re-prompt needs.

**Scope decision (defended below).** The fix is **frontend-only** and reuses the
already-documented `completion_message` message type -- no new client->backend
contract, no wire-format change, no backend edit. That keeps it inside the bead
and out of step-2 escalation territory.

## Lessons

A handler that "does nothing" on a degenerate input (here: an early `return` after
a no-op confirm) is invisible until it is driven in a loop by a remote peer -- then
"does nothing" becomes "spins forever." When a request can legitimately fail to
make progress, detect the *no-progress* condition explicitly and emit a corrective
signal, rather than silently returning and trusting the peer not to retry.

## Fresh-eyes triage (PR TBD)

(Filled in at closeout after the fresh-eyes pass.)

## Doc freshness

- **Reviewed and left** every doc the freshness checker flagged. The flags are
  overwhelmingly pre-existing mtimes from other PRs (backend `config.py`,
  `live_ai_gemini.py`, `callback_handler.py`, `schemaFormState.ts`, etc.). The only
  flag attributable to *this* change is `webFormConnection.ts`, which appears in
  the **Tracks:** lines of `websocket-routing.md` and `stateless-architecture.md`.
  Neither doc is invalidated: `websocket-routing.md:65` already documents the
  `completion_message` wire type this fix reuses, and the stateless invariant is
  untouched (no server-side field state added). No doc bump needed.

## Verification

- `vitest run` (jsdom): the new `webFormConnection.confirmloop.test.ts` (3 tests)
  passes; full suite is **118 pass + the new 3**, with the **3 pre-existing
  DisclaimerModal** failures unchanged (Chinese-text `getByText`, bd
  polyglot-pdf-pwt) -- confirmed pre-existing by stashing this change and re-running
  that file (still 3 fail).
- New test drives a `confirm_field` message through the real `ws.onmessage`
  dispatch against a one-field schema with no value, and asserts: no prompt on the
  first failed confirm, exactly one corrective `completion_message` once the limit
  is hit, and at most a couple of prompts across many failed confirms (never
  one-per-request -- the anti-spin guarantee).
- NOT browser-verifiable: the loop only arises inside a live WebSocket voice
  session (backend + Gemini), which the static preview cannot exercise.
- Note: the worktree has no `frontend/node_modules`; the toolchain was run by
  temporarily junctioning the main repo's install (not committed).

## Beads housekeeping

The housekeeping audit again flagged `polyglot-pdf-hrn` (P1 harness epic) as stale
in_progress; unrelated to this bead and owned by another active track -- left as-is
(noted, not transitioned), same call as the prior closeouts.

## Files touched

- `frontend/src/webFormConnection.ts` -- loop-breaker in `handleConfirmFieldRequest`: count consecutive failed confirms of the same unconfirmable field and re-prompt Gemini past the limit.
- `frontend/src/webFormConnection.confirmloop.test.ts` -- new regression test for the loop-breaker.
