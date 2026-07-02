---
date: 2026-07-02
bead: polyglot-pdf-6job
title: "fix(frontend): section-switch race kills session at a section boundary"
tags: [hotfix, testing]
---

## Trigger

Reported from the deployed demo (I-90, English): the voice session DIED right
after the first section completed and switched to `part_1_2_addresses`. The AI
prompted for the first field of the new section, then stopped responding. The
browser console showed an uncaught `Error: A section switch is already in
progress` thrown from `switchToSection` (via `doSectionSwitch` <-
`proceedSectionSwitch` <- `handleConfirmFieldRequest`), immediately after a
`handlePrepareSectionSwitchRequest` had already completed the same boundary.
Backend logs (Cloud Run) showed NO error -- the switch ran cleanly server-side --
confirming the fault is entirely frontend-side.

The original bead bundled two symptoms: (A) this section-switch race, and (B)
no-audio-after-reconnect. Bug B was split into its own bead
(polyglot-pdf-z9bc) at closeout so this PR closes a bead whose criteria it fully
meets; investigation strongly suggests B was a downstream consequence of A (see
Lessons). This bead is now scoped to bug A only.

## What shipped

The root cause is two independent section-switch mechanisms colliding at a
boundary, both keyed on the single `switchInFlight` guard:

1. **Client auto-advance:** confirming the last field of a section runs
   `handleConfirmFieldRequest -> proceedSectionSwitch`, which PARKS on the B5
   validator gate (`pendingSectionSwitch` set, but `switchInFlight` NOT yet set)
   awaiting the `validation_result`.
2. **AI-initiated switch:** while parked, Gemini calls `switch_section` ->
   backend `prepare_section_switch` -> `handlePrepareSectionSwitchRequest`, which
   sees `switchInFlight === false` and claims it for the SAME boundary (same
   socket, authoritative, in place).

When the validator gate then resolves clean, the parked client path proceeds to
`doSectionSwitch -> switchToSection`, finds `switchInFlight === true`, and throws
as an uncaught promise rejection -> the session dies. The pre-existing guard in
the confirm handler only checked `switchInFlight` BEFORE the park, so it could
not see a guard claimed DURING the await. Prior fixes (Codex PR #137/#271)
covered same-path duplicate confirms and the reverse-order manual-then-AI case,
but not this park-then-AI cross-path ordering.

The fix (`frontend/src/webFormConnection.ts`), the minimal two-point change:

- `handlePrepareSectionSwitchRequest`: when it claims the guard, if a client
  switch is PARKED (`pendingSectionSwitch`), it now calls
  `cancelPendingSectionSwitch()` -- the AI path is authoritative for that
  boundary, so the parked client reconnect-switch must not also fire. The parked
  `proceedSectionSwitch` then unblocks via the gate's `cancelled` flag and
  returns without switching.
- `proceedSectionSwitch`: after the gate await, it re-checks `switchInFlight` and
  skips cleanly (no audio teardown, no throw) if an AI switch claimed the
  boundary during the wait. This is defense-in-depth for the ordering where the
  gate had already resolved clean before the AI path arrived.

Tests: two regression tests added to
`frontend/src/webFormConnection.switchdurability.test.ts` -- one exercises the
cancel path (park -> AI supersedes -> parked switch resolves without throwing and
sends no `manual_section_switch`), one the post-await `switchInFlight` re-check.
Full frontend suite green (461 tests); `tsc --noEmit` clean; backend suite green
(571 passed) via closeout prep.

Verified live locally via the voice-harness `runMultiSectionScenario` against the
real local stack + real Gemini on the I-90 form (legacy SI, native VAD): section 1
voice-filled + confirmed -> clean auto-advance into section 2 (order reached, old
section finalized, `section_switched` fired) -> section-2 field voice-filled across
the boundary. Zero console errors; no "already in progress". Audio resumed on the
new section (relevant to bug B / z9bc). Caveat: that run took the client
`switchToSection` path -- Gemini did not also fire `switch_section` that turn, so
the exact dual-path race was not forced live; the two unit tests reproduce that
collision deterministically, which is the stronger proof.

Fresh-eyes (Step 5.5): see the assess breakdown recorded at closeout.

## Lessons

A single boolean reentrancy guard is insufficient when there are TWO distinct
entry paths that both perform the "same" logical operation but with different
side effects (here: the AI path keeps the socket open and switches in place; the
client path tears down audio and reconnects). The guard must be checked not just
at each path's entry but AFTER any `await` that can yield to the other path -- and
the authoritative path should proactively cancel the other's parked work rather
than letting it discover the collision and throw. This generalizes to any
place two async paths share a claim flag across an await boundary.

Bug B (no-audio-after-reconnect) was almost certainly a downstream consequence of
bug A: `doSectionSwitch` runs its audio teardown (`audioQueue=[]`,
`onStopCapture`) and THEN `switchToSection` threw before the reconnect re-armed
playback -- leaving the pipeline half-torn-down. With the race fixed that path no
longer runs, and audio resumed cleanly in the post-fix harness run. The honest
move was to split B (z9bc) and confirm on the live demo rather than patch the
audio layer speculatively.

## Doc freshness

Reviewed the three stale docs whose `Tracks:` globs cover
`frontend/src/webFormConnection.ts`
(`docs/standards/ws-protocol.md`, `docs/standards/voice-and-vad.md`,
`docs/components/websocket-routing.md`) and left them as-is: they were already
stale from unrelated 2026-06-29 edits, and this change is a purely internal
client-side reentrancy-guard refinement -- no wire message, route dispatch, or
VAD behavior changed, so their current-state prose still holds. The other stale
docs flagged by prep track backend files this branch did not touch.

Beads housekeeping: no orphans. The stale IN_PROGRESS beads flagged
(`polyglot-pdf-hrn`, `jf6w`, `ue5s`) are unrelated long-running epics/tasks owned
elsewhere; `6job` itself is legitimately in-progress and closes with this PR.

## Files touched

- `frontend/src/webFormConnection.ts` -- cancel a parked client switch when the
  AI path claims the boundary; re-check `switchInFlight` after the validator-gate
  await.
- `frontend/src/webFormConnection.switchdurability.test.ts` -- two regression
  tests for the cancel path and the post-await re-check.
