---
date: 2026-07-11
bead: polyglot-pdf-hc4b
title: "Soft page refresh mid-form no longer re-greets: resume:true is now derived from persisted in-progress state, not the instance flag"
tags: [hotfix, testing]
---

## Trigger

On a soft page refresh (F5) mid-session, a brand-new `WebFormConnection` is
constructed with `hasConnectedOnce=false`. `handleOpen` computed
`isResume = this.hasConnectedOnce`, so the FIRST handshake after a reload carried
`resume:false`. The stateless backend
(`websocket_routes.py` -> `is_reconnect=false` -> `form_filling_service.send_initiating_message`)
then selected `INITIATING_MESSAGE` ("Greet user warmly, state section name, ask
for {field}") instead of `RESUME_INITIATING_MESSAGE`. Net effect: after a soft
refresh the resumed voice session GREETED the user and re-introduced the current
section, even though they were mid-form. The `vmxx` resume mechanism that
suppresses this on an in-memory reconnect did not fire, because it is keyed to
the instance-scoped `hasConnectedOnce`, which a fresh post-reload instance lacks.

## Fix (frontend-only)

`handleOpen` already calls `reloadState()` before building the handshake, so
`this.state` reflects the freshest persisted sessionStorage. New predicate
`SchemaFormStateManager.hasInProgressSession(state)` returns true when the
persisted state shows a started form -- disclaimer accepted AND at least one
filled field. `isResume` is now
`this.hasConnectedOnce || hasInProgressSession(this.state)`, so a genuine
mid-form soft refresh sends `resume:true` and the backend uses the resume
template.

No backend change: `websocket_routes.py:902` already maps the handshake's
`resume` flag to `is_reconnect` -> `_is_resume_session` ->
`RESUME_INITIATING_MESSAGE` (`form_filling_service.py:623-627`). The bug was
purely that the frontend never SET `resume:true` on the soft-refresh path.

## Reconciling the fn1m journal claim

Bead `polyglot-pdf-fn1m` (the disclaimer half of this same soft-refresh path) has
a journal note that "the backend resume:true path skips greeting/disclaimer."
That was inaccurate for a *genuine soft refresh*: before this fix `resume` was
`false` there (the instance flag was fresh), so the resume path did NOT fire and
the greeting was NOT skipped. With hc4b the soft-refresh handshake now genuinely
carries `resume:true`, so the fn1m description finally matches reality.

The existing fn1m regression test
(`webFormConnection.reconnect.test.ts` -> "builds the handshake from the CURRENT
sessionStorage state") set up exactly this in-progress soft-refresh state yet
asserted `resume:false` -- it had encoded the pre-fix behavior. Updated honestly
to assert `resume:true` (the setup IS a mid-form refresh), with a comment
pointing at hc4b; its original purpose (handshake reflects fresh sessionStorage,
not the stale constructor snapshot) is unchanged and still asserted.

## Verification

- New `hasInProgressSession()` unit tests: false on a fresh session, false with
  disclaimer-but-no-values, false with values-but-no-disclaimer, true mid-form;
  plus a test that the derived flag drives `resume:true` through
  `getHandshakePayload`.
- Updated fn1m reconnect test now asserts `resume:true` on the in-progress
  soft-refresh open.
- Full frontend suite green (56 files / 911 tests, default forks pool); `tsc`
  clean.
