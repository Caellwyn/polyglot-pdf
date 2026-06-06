---
date: 2026-06-05
bead: polyglot-pdf-wq0
title: "WS reconnect dropped the auth token -> HTTP 403 on the post-disclaimer first-section connect"
tags: [bug, websocket-routing, auth, frontend, schema-forms]
---

## Trigger

Live demo: the disclaimer read through fine, but the instant the app pivoted to
filling form fields it "lost connection to the backend." Frontend console showed
a clean WebSocket up through disclaimer acceptance, then `switching to first
section (restarts Gemini session)` immediately followed by a close and five
failed reconnects (code 1006).

## Root cause

The drop was not a mid-session disconnect -- it was a **brand-new connection
being rejected at the auth gate**.

The disclaimer-accept flow calls `switchToFirstSection` -> `startSection`, which
is the only navigation path that tears down the WebSocket and opens a fresh one
with a new handshake (mid-form section changes use `switchToSection`, which keeps
the socket alive). That fresh connection was opened **without the auth token**:

- `webFormConnection.connect(wsUrl, timeoutMs, token?)` appended `?token=` only
  when a `token` argument was passed, and the token was never stored on the
  instance.
- The initial connect (in `shared/connection.ts`) passed the token, so the
  disclaimer connection worked.
- Both reconnect paths called `connect()` with **no** token:
  - `startSection()` -> `await this.connect(wsUrl)` (the post-disclaimer switch)
  - `attemptReconnect()` -> `this.connect(this.connectedUrl)` (auto-reconnect)

Backend `verify_token` (`backend/services/auth.py`, gated in
`websocket_routes.py` `/ws/fill`) therefore saw no/invalid token and the request
was rejected. Confirmed in Cloud Run logs: six `GET /ws/fill -> HTTP 403` in
~20 ms each (rejected before the WS upgrade), with backoff timing matching the
browser's five reconnect attempts. The browser surfaces the failed handshake as
close code 1006.

Latent since the auth layer landed (`aa66f45`, 2026-01-21) -- the
disclaimer -> first-section switch is simply the first reconnect that exercises
the auth gate.

## Fix

Plumb a **fresh-token callback** instead of a one-shot token:

- `WebFormConnection` holds `getToken?: () => Promise<string | undefined>` (set
  via `setGetToken`) and a `lastToken` fallback. `connect()` resolves the token
  for *every* (re)connect: explicit arg (back-compat) > fresh `getToken()` >
  `lastToken`. It also strips any stale token already baked into the URL before
  appending the fresh one.
- `createConnectionManager` takes `getToken` (was `token`) and registers it on
  the connection instance(s), including the cloud-fallback instance.
- `SchemaForm.tsx` passes `() => user?.getIdToken()` instead of a token fetched
  once at manager creation.

Fetching fresh on each connect fixes the immediate tokenless-reconnect 403 **and**
covers ~1h Firebase ID token expiry on long sessions (caching the original token
would only have moved the failure to the one-hour mark).

## Verification

- `tsc --noEmit`: zero net new type errors (24 -> 24; the only deltas are four
  pre-existing `onStopCapture`/`onFormComplete` errors shifting line numbers
  because lines were added above them). All remaining errors pre-date this change
  on `dev`.
- New regression test `frontend/src/webFormConnection.token.test.ts` (5 cases):
  token is appended when `connect()` is called with no explicit token (the
  reconnect path), token is re-fetched on each reconnect, a stale baked-in token
  is stripped, `getToken` failure falls back to the last-known token, and an
  explicit token argument still wins.
- Full suite: the only failures are three pre-existing `DisclaimerModal`
  Chinese-text assertions (fail identically on baseline).

## Review triage (PR #94)

Fresh-eyes (Sonnet) raised 2 blockers + 3 nits; Copilot posted only its overview
(no inline findings -> clean).

- **Adopted:** the URL-token strip was a regex (`replace(/([?&])token=[^&]*/, ...)`)
  that left a dangling `?&` when the token was the first of several query params.
  Replaced with a `stripToken()` helper that splits/filters params (handles token
  alone/first/middle/last/none) and now store the token-LESS base URL in
  `connectedUrl` so the reconnect path re-resolves a fresh token instead of
  replaying a stripped stale one. Added a regression case + 5 `stripToken` unit
  tests.
- **Deferred (filed `polyglot-pdf-d0k`):** the standalone branches of
  `VoiceOverlay`/`VoiceOverlayMobile` create a manager without `getToken`. Not a
  production regression -- `SchemaForm` always renders both overlays with the
  shared token-registered manager, so the standalone branch (legacy
  bookmarklet/demo, no Firebase auth) is unreachable from the authed flow. Out of
  scope for this bead.
- **Rejected:** the "`user` is null when the effect runs" race -- `AuthProvider`
  renders `{!loading && children}`, so `SchemaForm` does not mount until auth has
  resolved; `user` is already settled when the `getToken` closure is created.
- **Rejected (folded instead):** "store base URL not finalUrl" was a design nit;
  adopted as part of the blocker fix above rather than left as a nit.

## Doc-freshness review

`check_doc_freshness.py` flags a large set of stale tier-2 docs, but nearly all
of that staleness is a pre-existing backlog from unrelated 2026-06-04 backend
changes (config, adapters, deploy scripts) that this PR does not touch. The docs
that newly list this branch's files -- `websocket-routing.md`, `voice-ai.md`,
`schema-forms.md`, `stateless-architecture.md` -- describe the WS routing
contract, handshake shape, and stateless model, none of which this internal
token-plumbing fix changes (the documented behavior is unchanged; only how the
token reaches `connect()` differs). Reviewed: no tier-2 doc is made factually
wrong by this change, so no doc bump is warranted here. The 06-04 backlog is out
of scope for this bead.

## Scar tissue

A WebSocket that closes with **1006 right after a deliberate reconnect** is far
more likely an auth/handshake rejection on the *new* connection than a dropped
*existing* one -- check the server for a fast `40x` on the upgrade request before
assuming a network or session-lifecycle problem. Any per-connection credential
(token, header) must be re-supplied on *every* `connect()`, not captured once;
the reconnect path is the one that bites, and it bites late.
