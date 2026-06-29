---
date: 2026-06-29
bead: polyglot-pdf-b2yj
title: "Reconnect button missing on 'disconnected' status (error tells user to click Reconnect but no button exists)"
tags: [hotfix, testing]
---

## Trigger

The maintainer hit a dead end in the live demo: the voice panel showed status
`disconnected` with the red banner "Connection lost - please click Reconnect",
but there was no Reconnect button anywhere in the panel. The user was instructed
to click a button that did not exist. Filed and fixed as bd polyglot-pdf-b2yj.

## What shipped

The voice overlay has three "you must act to recover" states, but only two of
them rendered a recovery affordance:

- `idle_timeout` -> inline "Reconnect" button (present).
- `reconnect_failed` -> ConnectionTimeoutModal with a reconnect button (present).
- `disconnected` -> **nothing** (the bug).

The generic `disconnected` status is reached by an ordinary drop
(`handleClose:no-auto-reconnect` in `webFormConnection.ts`) and by the
post-disclaimer reconnect-timeout path, which calls
`setError('Connection lost - please click Reconnect')` while status is not
connected. In both cases the controls row fell through to `null` because the
inline button was gated on `status === 'idle_timeout'` alone.

The fix widens that gate to `status === 'idle_timeout' || status ===
'disconnected'` in BOTH overlays (desktop `VoiceOverlay.tsx` and mobile
`VoiceOverlayMobile.tsx`). The button is wired to the existing `handleConnect`
path, which is the same connect/restore the idle-timeout button already used;
the client owns all field state, so reconnecting resumes at the current field.
The `paused`, `reconnect_failed`, connected, and other states are unchanged.

Added `VoiceOverlay.reconnectbutton.test.tsx`: renders each real overlay with
`status="disconnected"` and asserts a Reconnect button appears and, on click,
calls `connectionManager.connect()`. The mobile case taps the FAB to expand the
panel first (its action buttons live in the expanded panel). Rendering without
`initialLanguage` keeps the mount-time auto-connect effect from overwriting the
injected `disconnected` status.

Exit-criteria scorecard (both PASS):
1. When status is `disconnected`, both overlays render a Reconnect button wired
   to `handleConnect` -- PASS (new test asserts button present + `connect()`
   called, both overlays).
2. The `idle_timeout` / `paused` / `reconnect_failed` / connected affordances are
   unchanged -- PASS (gate only ADDS `|| status === 'disconnected'`; the existing
   12 demo tests still pass).

Fresh-eyes assess: NO-GAPS (see below). No out-of-scope beads filed.

## Lessons

Recovery UI must be driven off the SAME state that produces the recovery
*instruction*. Here the error string "please click Reconnect" was emitted for
the `disconnected` state, but the button that satisfies it was gated on a
different state (`idle_timeout`). Whenever code tells the user to take an action,
the control for that action must render under exactly the conditions that emit
the instruction -- a narrower gate strands the user. Not generalized to a
standards doc: it is a single-surface UI invariant, not a cross-cutting rule.

## Doc freshness

No doc content update needed. The freshness checker flagged
`docs/standards/voice-and-vad.md` as stale and listed `VoiceOverlay.tsx` among
its tracked files, but (a) that doc documents native VAD / PTT turn-taking and
the Hold-to-Talk affordance -- not the connection-status / Reconnect button row
this change touched -- and (b) it was already stale before this branch (last
updated 2026-06-17, flagged off several backend files dated 2026-06-25/28 that
this branch never touched). Reviewed and left as-is. Every other stale doc the
checker listed tracks only backend/other files this branch did not touch.

## Files touched

- `frontend/src/demo/VoiceOverlay.tsx` -- widen inline Reconnect button gate to include `disconnected`.
- `frontend/src/demo/VoiceOverlayMobile.tsx` -- same gate widening for the mobile overlay.
- `frontend/src/demo/VoiceOverlay.reconnectbutton.test.tsx` -- new regression test (both overlays).
- `docs/journal/entries/2026-06-29-bd-b2yj-reconnect-button-on-disconnected.md` -- this entry.
