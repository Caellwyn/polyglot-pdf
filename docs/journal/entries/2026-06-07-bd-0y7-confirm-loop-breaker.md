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

> **Collision note.** A parallel session shipped a *different* 0y7 loop-breaker as
> PR #111, which merged into `dev` while this PR (#113) was in review. Rather than
> abandon either, this PR was **rebased onto #111 and reworked to be a strict
> superset** of it -- it keeps both of #111's user-facing behaviors (the `onError`
> toast and the section-switch streak resets in `switchToSection` *and*
> `startSection`) and adds three improvements #111 lacked. See "Superset over PR
> #111" below.

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

**Fix (`frontend/src/webFormConnection.ts`, `handleConfirmFieldRequest`).** Gate on
the field's **value**, not on `confirmField`'s confirmed flag. Before recording any
confirmation, check whether the field has a usable value
(`state.fieldValues[field_id]?.value` is not null/undefined/empty). If it does NOT,
the confirm cannot make progress: count consecutive failed confirms of the *same*
field id (`lastUnconfirmableFieldId` + `unconfirmableConfirmCount`), and every
`UNCONFIRMABLE_CONFIRM_LIMIT` (2) attempts `send({type: 'completion_message', ...})`
telling Gemini the field has no value, to stop calling `confirm_field` on it, and to
ask the user then call `update_form_fields` -- up to a hard
`UNCONFIRMABLE_REPROMPT_CAP` (3), after which it stops re-prompting entirely. Only
when the field HAS a value does it call `confirmField`/`save` and run the
section-completion / auto-switch branch. All three counters reset on a successful
confirm and on every (re)connect (`handleOpen`).

**Why gate on value, not on `confirmField`'s flag (fresh-eyes PR #113, #1).** The
first draft checked `isFieldConfirmed` after calling `confirmField`. But
`confirmField` only no-ops when there is **no `fieldValues` entry at all** -- it
would still *succeed* (set `confirmed: true`) on an entry that exists with an
empty/null value (e.g. Gemini called `update_form_fields` with `""` first). That
both hides the loop AND lets an empty field count as done, so `computeNextField`
would skip it and the section could auto-complete with unfilled data. Keying the
guard on the value closes both holes: an empty field is never recorded as confirmed,
and the loop is detected regardless of whether a map entry exists.

**Why a hard re-prompt cap (fresh-eyes PR #113, #2).** Resetting only the
per-window counter after each re-prompt rate-limits the spin (one prompt per LIMIT
requests) but does not stop it -- if Gemini ignores the instruction, the client
re-prompts forever at half speed. The `REPROMPT_CAP` makes it a true circuit
breaker: after 3 corrective prompts for the same field, the client goes silent on
that field rather than spinning indefinitely.

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

## Superset over PR #111

PR #111 (merged into `dev` first) and this PR fix the same bead with different
implementations. This PR was rebased onto #111 and reworked so it is unambiguously
better -- it KEEPS everything #111 does and ADDS three fixes for gaps #111 has:

| Behavior | PR #111 (merged) | This PR (#113, after rework) |
|---|---|---|
| Unconfirmable detection | `isFieldConfirmed` after `confirmField` -- only catches a **missing** `fieldValues` entry | gates on the **value** -- also catches an entry that exists with an empty/null value (which `confirmField` would otherwise *confirm*, letting an empty field count as done and the section auto-complete with unfilled data) |
| Spin bound | re-arms forever (rate-limit only) | hard `REPROMPT_CAP` (3) -- a genuinely unfillable field stops entirely |
| Break signal to Gemini | `recovery_prompt` -- **broken backend-side** (`RECOVERY_PROMPT_LEVEL_*` missing, bd `polyglot-pdf-zy3`), so today only the `onError` toast fires | `completion_message` -> `send_prompt`, which is wired and works today |
| `onError` UI toast | yes | yes (kept) |
| Section-switch reset | `switchToSection` + `startSection` | `switchToSection` + `startSection` + `handleOpen` (reconnect) |

Net: this PR's break signal works now, it cannot be fooled by an empty-valued entry,
and it cannot spin forever -- while preserving #111's toast and section-switch resets.

## Lessons

A handler that "does nothing" on a degenerate input (here: an early `return` after
a no-op confirm) is invisible until it is driven in a loop by a remote peer -- then
"does nothing" becomes "spins forever." When a request can legitimately fail to
make progress, detect the *no-progress* condition explicitly and emit a corrective
signal, rather than silently returning and trusting the peer not to retry.

## Fresh-eyes triage (PR #113)

Round 1, sonnet reviewer, 5 findings:
- **#1 (blocker, ADOPTED):** the guard keyed on `confirmField`'s confirmed flag,
  which "succeeds" on an empty-valued entry -- so an empty field could be confirmed
  and skipped, and the loop missed. **Reworked to gate on the field VALUE**; an empty
  field is now never recorded as confirmed and is always treated as unconfirmable.
- **#2 (blocker, ADOPTED):** counter-reset-after-firing rate-limited the loop but
  did not stop it (re-prompt forever at half speed). **Added `UNCONFIRMABLE_REPROMPT_CAP`
  (3)** -- after 3 re-prompts for the same field, stop entirely.
- **#3 (nit, ADOPTED):** the third test's name/bound were misleading. **Replaced** with
  a hard-cap test asserting exactly 3 prompts across 100 failed confirms.
- **#4 (medium, ADOPTED):** loop-breaker counters survived reconnect -> first-confirm
  false-trip. **Reset all three counters in `handleOpen`.**
- **#5 (low, RESOLVED by the #1 rework):** redundant `save()` on the no-op path
  caused needless re-renders. The failed-confirm path now returns *before*
  `confirmField`/`save`, so no save fires on a failed confirm.

Copilot round 1: COMMENTS -- one inline finding, the same misleading-test-name issue
as fresh-eyes #3, already resolved by the #3 rework (the loose `<= 3` test is gone).

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

- `vitest run` (jsdom): the new `webFormConnection.confirmloop.test.ts` (5 tests)
  passes; full suite is **120 pass**, with the **3 pre-existing DisclaimerModal**
  failures unchanged (Chinese-text `getByText`, bd polyglot-pdf-pwt) -- confirmed
  pre-existing by stashing this change and re-running that file (still 3 fail).
- New tests drive `confirm_field` / `field_update` messages through the real
  `ws.onmessage` dispatch against a one-field schema, asserting: no prompt on the
  first failed confirm; one corrective `completion_message` once the limit is hit;
  the **empty-value-entry** case (the one the old `isFieldConfirmed` guard missed)
  is still detected; the **hard cap** holds (exactly 3 prompts across 100 failed
  confirms, then silence); and a **successful confirm** (value present) neither
  re-prompts nor leaves stale tracking.
- NOT browser-verifiable: the loop only arises inside a live WebSocket voice
  session (backend + Gemini), which the static preview cannot exercise.
- Note: the worktree has no `frontend/node_modules`; the toolchain was run by
  temporarily junctioning the main repo's install (not committed).

## Beads housekeeping

The housekeeping audit again flagged `polyglot-pdf-hrn` (P1 harness epic) as stale
in_progress; unrelated to this bead and owned by another active track -- left as-is
(noted, not transitioned), same call as the prior closeouts.

## Files touched

- `frontend/src/webFormConnection.ts` -- value-gated loop-breaker in `handleConfirmFieldRequest` (re-prompt via `completion_message` + `onError`, hard re-prompt cap); counter resets in `handleOpen` (reconnect), `startSection`, and `switchToSection`.
- `frontend/src/webFormConnection.confirmloop.test.ts` -- new regression test (5 cases: first-fail tolerance, threshold prompt, empty-value-entry detection, hard cap, successful-confirm clears tracking).
