---
date: 2026-07-10
bead: polyglot-pdf-fn1m
title: "BUG: soft page-refresh mid-session leaves UI/voice desynced + stale field readback"
tags: [hotfix, testing]
---

## Trigger

Maintainer test-drive of the live demo (2026-07-06): after a section-switch audio
dropout prompted a manual page refresh (F5) mid-session, the app went "wonky" in
two ways. (1) The disclaimer/agree screen re-showed in the UI *while Gemini was
already speaking*, introducing a section -- the voice session resumed but the UI
reverted to a pre-session step. (2) The model asserted a stale value from a
PREVIOUS section (it claimed the user had said their name changed) that the client
never held and the UI showed differently. Scoped by the bead (maintainer note) to
SOFT-REFRESH (reload) rehydration only -- NOT the section-session-reset machinery
being retired.

## What shipped

Two distinct root causes, both in the reload path (the SPA fully re-mounts, so the
connection is rebuilt from scratch and the UI step must be re-derived from
persisted state):

1. **Disclaimer re-shows (symptom 1).** Both voice overlays' mount auto-connect
   effect has an `alreadyLive` guard (for a desktop<->mobile remount onto a live
   session) that already checks `disclaimerAccepted` before re-showing the agree
   step. But the FALL-THROUGH path -- the one that runs on a genuine reload, where
   the connection is not yet live -- called `setPendingDisclaimerRead(true)` +
   `setShowDisclaimerModal(true)` UNCONDITIONALLY. So on reload the disclaimer
   always re-surfaced (and was re-read aloud, since `pendingDisclaimerRead` drives
   `readDisclaimer`) even when already accepted. Fix (`VoiceOverlay.tsx`,
   `VoiceOverlayMobile.tsx`): gate the disclaimer step on
   `SchemaFormStateManager.load()?.disclaimerAccepted`, mirroring the `alreadyLive`
   branch -- still `handleConnect()` either way (to resume the session), but only
   show/read the disclaimer when NOT accepted.

2. **Stale field readback (symptom 2).** `webFormConnection.handleOpen` built the
   handshake from `this.state`, which is the constructor's `init()` snapshot. On a
   soft refresh a BRAND-NEW `WebFormConnection` is built and that snapshot can
   predate the latest `schema_form_state` save, so the stateless backend rebuilt
   context from a stale `currentSectionId` / `fieldValues`. Fix: call the existing
   `reloadState()` (re-read sessionStorage into `this.state`) BEFORE
   `getHandshakePayload`, after the `isSectionSwitching` early-return. `reloadState()`
   already existed but was wired only into the E2E test harness; this makes reload
   rehydration its primary production purpose (docstring updated to say so).

Fresh-eyes (Sonnet) assess: GAPS-FOUND (0), both exit criteria PASS. It traced the
disclaimer gate into its consumers (`readDisclaimer` effect, `DisclaimerModal`
`isOpen`) and confirmed every `this.state` mutator (`updateField`, `confirmField`,
`markFieldSkipped`, ...) calls `save()` synchronously -- so there is no
un-persisted in-flight mutation for `reloadState()` to clobber -- and that JIT
handshake state (`loadedFieldIds`/`jitModeEnabled`) survives the reload. It raised
three low/medium hardening notes; two were adopted (the stale "TEST-SUPPORT"
docstring on `reloadState`, now corrected to name the `handleOpen` production
caller; and a JIT-specific handshake test, added). One was rejected as unreachable
(no schema-identity guard in `reloadState()` -- the app locks the form after
onboarding, so a cross-form sessionStorage swap cannot occur; low-probability,
noted here rather than guarded).

Tests: +2 VoiceOverlay disclaimer tests (both overlays: an accepted soft-refresh
resume reconnects WITHOUT re-showing/re-reading the disclaimer) and +2
webFormConnection handshake-freshness tests (legacy + JIT: the handshake reflects
the current sessionStorage state, not the constructor snapshot). Frontend
typecheck clean; VoiceOverlay + webFormConnection families green (189 pre-existing
+ the new cases).

## Lessons

A per-connection copy of client state (`this.state` seeded at construction) is a
staleness trap whenever a NEW connection object can be built after the state has
moved on -- exactly what a page reload does. The fix is to re-read the
system-of-record (sessionStorage) at the point of use (handshake build), not to
trust the constructor snapshot. This generalizes to any "stateless backend rebuilt
from a client handshake" boundary: the handshake must serialize freshly-read
client state, or a resumed session silently diverges from the client. (Kept in
this entry; it is specific to the reload/handshake path, not a codebase-wide rule
warranting a `docs/standards` line.)

## Doc freshness

Bumped [`docs/components/websocket-routing.md`](../../components/websocket-routing.md):
added a "Soft page refresh (reload rehydration)" section (distinct from the
existing "Reconnect (no page refresh)" section) documenting the two invariants --
the `disclaimerAccepted`-gated UI-step restore and the `reloadState()`-before-
handshake fresh state. `closeout_prep.py` flagged the usual broad batch of STALE
docs; of those, four carry a `**Tracks:**` glob covering a file this branch touched
(`webFormConnection.ts` / `VoiceOverlay.tsx`): `websocket-routing.md` (bumped
above), `stateless-architecture.md`, `voice-and-vad.md`, `ws-protocol.md`. The
latter three describe contracts this change did NOT alter (the client-owns-state
invariant, VAD, and the wire message-type union are all unchanged -- the fix only
changes WHEN/what client state the handshake serializes, not any wire shape), so
they were already stale before this branch and are left untouched.

## Files touched

- `frontend/src/demo/VoiceOverlay.tsx` -- gate the mount-fall-through disclaimer
  step on `disclaimerAccepted`.
- `frontend/src/demo/VoiceOverlayMobile.tsx` -- same fix, mirrored.
- `frontend/src/webFormConnection.ts` -- `reloadState()` in `handleOpen` before the
  handshake; docstring corrected to name the production caller.
- `frontend/src/demo/VoiceOverlay.disclaimer.test.tsx` -- +2 accepted-resume tests.
- `frontend/src/webFormConnection.reconnect.test.ts` -- +2 handshake-freshness
  tests (legacy + JIT).
- `docs/components/websocket-routing.md` -- new "Soft page refresh" section + stamp.
