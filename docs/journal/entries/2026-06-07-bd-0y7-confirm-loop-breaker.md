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
(2) consecutive failures on the same field, break the spin and reset (re-arm
rather than fire every cycle). A successful confirm, or a switch to a different
field, resets the streak; `switchToSection` also clears it so a stale count can't
carry into a new section with a same-named field.

**How the break is surfaced (revised after fresh-eyes -- see triage).** The break
calls `onError` with a clear message ("no value was entered, please provide it")
-- this works TODAY and is what actually informs the user. It ALSO attempts a
level-1 `recovery_prompt` (the nicer spoken Gemini re-prompt), but that backend
channel is currently broken (`RECOVERY_PROMPT_LEVEL_*` are missing from `Settings`
-> `AttributeError`, filed as `polyglot-pdf-zy3`), so it is belt-and-suspenders
that activates once zy3 lands. The original draft relied on `recovery_prompt`
ALONE, which fresh-eyes correctly flagged would have only rate-limited the spin
without ever telling anyone.

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

## Fresh-eyes triage (PR #111)

Round 1, sonnet reviewer, 4 findings, all addressed:
- **#1 (critical, ADOPTED):** `recovery_prompt` is broken backend-side
  (`RECOVERY_PROMPT_LEVEL_*` missing from `Settings`), so the original
  recovery-prompt-only break would silently fail. Fixed: surface via `onError`
  (works now) + keep the recovery_prompt as belt-and-suspenders; filed the backend
  regression as `polyglot-pdf-zy3`.
- **#4 (medium, ADOPTED):** counters not reset on section switch -> a same field_id
  in the next section could trip the breaker a cycle early. Fixed: reset in
  `switchToSection` + a test.
- **#2 (medium, ADOPTED):** test gap for A-B-A interleaving. Added the third
  `confirm('f1')` assertion.
- **#3 (low, ADOPTED):** comment said "no value" but the guard is "no entry".
  Tightened the wording.

Copilot round 1: prose-only overview, no inline findings (effectively CLEAN).

## Verification

- New `frontend/src/webFormConnection.confirmloop.test.ts` (7 cases: no break
  under the limit; break at the limit; re-arm without spamming;
  reset-on-successful-confirm; per-field-id A-B-A tracking; `onError` surfaced on
  break; streak reset on section switch) -- all pass.
- Full frontend suite: 122/125 (the 3 failures are the pre-existing
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
