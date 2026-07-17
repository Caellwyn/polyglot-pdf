---
date: 2026-07-17
bead: polyglot-pdf-m77y
title: "fix(voice): render a Reconnect button on 'error' status (both overlays)"
tags: [hotfix, testing]
---

## Trigger

Follow-up bug filed 2026-07-16 by the fresh-eyes review of bd polyglot-pdf-l8z7
(resume() gating on a live socket). Tracing l8z7's new resume()->connect()
delegation into its failure path surfaced a pre-existing dead end: both voice
overlays gate their inline recovery button on a Reconnect/Resume/Pause ternary
that has no arm for a bare `error` status.

## What shipped

`frontend/src/demo/VoiceOverlay.tsx` and `VoiceOverlayMobile.tsx` render exactly
one control from a ternary: Reconnect for `idle_timeout`/`disconnected`, Resume
for paused, Pause when connected -- else `null`. A status of `error` (set by
`connect()`'s catch in `frontend/src/shared/connection.ts` when BOTH the
localhost and the cloud WebSocket attempts fail -- a completely-failed initial
connect, or a resume that funnels through `manager.connect()` and fails
outright) matched none of those arms, so the overlay rendered NO button. The
only escape was a full page refresh.

The fix adds `status === 'error'` to the Reconnect arm in both overlays;
`handleConnect` (the same handler the disconnected/idle_timeout Reconnect already
uses) retries the connection from scratch. `error` is not paused, so
`handleConnect` takes its `connect()` path, which is the correct recovery for a
failed connect.

`reconnect_failed` -- the sibling terminal state -- is deliberately NOT added to
this arm: it already has its own recovery surface, the `ConnectionTimeoutModal`
(gated on `status === 'reconnect_failed'`), so it is not a dead end and adding it
here would double up the affordance.

**Hardening (fresh-eyes finding).** The Opus fresh-eyes round traced a sibling
re-exposure of the same dead end: the desktop `handleConnect` catch set the
status to the FREEFORM string `'Connection failed'` (not a `ConnectionStatus`
union value), which matches no controls-ternary arm. So a RE-failed Reconnect
(user clicks Reconnect while both backends are still down) would fall back to no
button, recovering only if the parent prop-sync effect won a render race. Fixed
by setting the union status `'error'` in that catch instead -- the Reconnect
button then renders deterministically. The user-facing message is unchanged
(still set via `setError`). The MOBILE overlay's catch never set a status here,
so it was already immune; this aligns desktop with it. This is in scope: it makes
the bead's own "no dead-end on total connection failure" fix robust rather than
ordering-dependent.

Test: extended `VoiceOverlay.reconnectbutton.test.tsx` (the bd b2yj regression
test that already parameterizes both overlays) with a `status` argument and two
new cases asserting a Reconnect button renders at `status='error'` and is wired
to `connectionManager.connect()`, for desktop and mobile. Verified non-vacuous:
reverting the desktop ternary arm fails the new desktop case. `tsc --noEmit`
clean; all demo overlay tests pass.

Note on the hardening's test coverage: the freeform->`'error'` catch change is
NOT covered by a dedicated re-fail test. A render test cannot isolate the catch's
local `setStatus` from the injected `status` prop's sync effect (the prop keeps
overriding local state, so such a test passes regardless of the catch value --
i.e. it is vacuous). Rather than ship a vacuous test that gives false confidence,
the hardening rests on the existing `status='error'` render test (which proves
the ternary arm shows the button) plus the direct reasoning that the catch now
emits that exact union status. A candidate follow-up would be to extract the
status-reconciliation so the catch path is unit-testable in isolation.

## Lessons

A single-control status ternary that ends in `null` is a dead-end risk for every
status value not explicitly listed -- the safe shape is an explicit recovery arm
for each terminal/failure state, or a default recovery affordance. Noted here
rather than in a standards doc because it is specific to these two overlay
components, not a codebase-wide rule.

## Doc freshness

No component/standards doc documents the overlay button ternary at the level this
change touches (the surfaces docs describe status semantics and the
connection-timeout modal, not the per-status control matrix), so none needed a
bump for this change. Any freshness-checker STALE flags on docs tracking
`connection.ts` / overlay files are from other recent commits' mtimes, not this
branch -- noted at closeout.

## Files touched

- `frontend/src/demo/VoiceOverlay.tsx` -- add `error` to the Reconnect ternary
  arm; harden the `handleConnect` catch to set the union status `error` instead
  of the freeform `Connection failed` string.
- `frontend/src/demo/VoiceOverlayMobile.tsx` -- add `error` to the Reconnect
  ternary arm (its catch already set no status).
- `frontend/src/demo/VoiceOverlay.reconnectbutton.test.tsx` -- parameterize by
  status; add desktop + mobile `error`-status cases.
