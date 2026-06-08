---
date: 2026-06-07
bead: polyglot-pdf-f5w
title: "Clean up two collision artifacts from the dueling 0y7 fixes (#111 / #113)"
tags: [conventions]
---

## Trigger

Bead `polyglot-pdf-0y7` (P1, infinite confirm/next-field loop) was fixed twice in
parallel: PR #111 merged a `recovery_prompt`/`isFieldConfirmed`-based loop-breaker
into `dev`, then PR #113 (rebased onto #111) replaced it with a value-gated breaker
that is a strict superset. After #113 merged, an audit of the *combined* result
(prompted by "look for collisions or bugs in this mess") surfaced two collision
artifacts left in the merged tree. This bead cleans them up.

## What shipped

Two small, behavior-preserving fixes:

1. **Stale comment in `SchemaFormStateManager.confirmField`**
   (`frontend/src/schema-forms/state/schemaFormState.ts`). The `if (!fieldValue)`
   no-op branch carried a comment from PR #111 saying "The WebFormConnection
   loop-breaker counts these (it re-checks `isFieldConfirmed`)." PR #113 replaced
   that detection with an **upstream value gate** in `handleConfirmFieldRequest`, so
   `confirmField` is no longer the detection point -- a no-value confirm is caught
   before `confirmField` is ever called. The comment actively misdescribed the
   mechanism; reworded to state the no-entry branch is now a defensive backstop.

2. **Missing loop-breaker reset in `handlePrepareSectionSwitchRequest`**
   (`frontend/src/webFormConnection.ts`). This is the backend-initiated section
   switch; it changes section on the **same** WebSocket without reconnecting, so
   `handleOpen`'s reset does not fire. It was the only section-transition path
   without the loop-breaker reset (`handleOpen` / `startSection` / `switchToSection`
   all have it). Added the three-line reset for consistency.

## Honest scope note (defended decision)

The audit flagged #2 as a "blocker," but it is **defense-in-depth, not a bug fix**.
The streak counter is keyed on `field_id`: it only increments when the incoming
`field_id` matches `lastUnconfirmableFieldId`, else it resets to 1. Field ids are
globally unique per schema, so a stale streak from the old section cannot match a
new section's field and therefore cannot false-trip. **Verified empirically:** a
test that armed the streak, fired a backend section switch, then confirmed a field
in the new section passed *with and without* the reset -- because the id-mismatch
already resets the streak. So I removed that vacuous test (it proved nothing) and
reworded the fix's comment to say it is consistency / defense-in-depth that removes
the reliance on the id-uniqueness invariant, rather than claiming a fixed defect.
Decided to ship the cleanup anyway: the comment fix has real value (a misleading
comment in a P1-bug code path is scar tissue), and the reset is cheap insurance.

## Pre-existing findings filed separately

The same audit surfaced three issues that **predate both PRs** (not collision
damage), filed as `polyglot-pdf-exs`:
- `ConnectionCallbacks` is missing `onStopCapture` / `onFormComplete`, which
  `handleConfirmFieldRequest` reads (always `undefined` at runtime; the 4 TS2339
  errors in the file are these, part of the 24-error pre-existing baseline).
- `sendRecoveryPrompt` is plumbed through the `ConnectionManager` interface but no
  caller invokes it -- inert (compounded by the broken backend `recovery_prompt`,
  bd `polyglot-pdf-zy3`).
- `isFieldConfirmed` is now dead code (PR #111's detection hook, unused after #113).

## Doc freshness

- **Reviewed and left** every flagged doc. The flags attributable to this change are
  on `schema-forms.md`, `websocket-routing.md`, and `stateless-architecture.md`
  (they track the two files I touched). This change is two comment edits plus a
  three-line defense-in-depth reset -- it changes no documented behavior, so no doc
  prose is invalidated. The remaining flags are pre-existing mtimes from other PRs.

## Verification

- `vitest run` (jsdom): loop-breaker suite 5/5; full frontend suite **120 pass** +
  the **3 pre-existing DisclaimerModal** failures (Chinese-text `getByText`, bd
  polyglot-pdf-pwt), unchanged.
- Typecheck unchanged at the **24-error pre-existing baseline** (zero new errors;
  the errors in the two touched files are all pre-existing).
- NOT browser-verifiable: changes live entirely in the WS voice loop.
- Note: the worktree has no `frontend/node_modules`; the toolchain ran via a
  temporary junction to the main repo's install (not committed).

## Beads housekeeping

`polyglot-pdf-hrn` (P1 harness epic) again flagged stale in_progress -- another
track's active epic, left as-is (noted), same call as prior closeouts.

## Files touched

- `frontend/src/schema-forms/state/schemaFormState.ts` -- corrected the stale `confirmField` no-op comment.
- `frontend/src/webFormConnection.ts` -- added the loop-breaker reset to `handlePrepareSectionSwitchRequest`.
