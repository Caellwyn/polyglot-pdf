---
date: 2026-09-16
bead: polyglot-pdf-bwevj
tags: [security, websocket, auth, sprint-23]
surfaces: [backend/routes/websocket_routes.py, frontend/src/webFormConnection.ts, backend/config.py, deploy/channels]
---

# C2: the WebSocket credential leaves the URL

Sprint 23 workstream C2 (`docs/sprint_23_security-audit_plan.md`, PF-1's
root cause; approved by the maintainer 2026-09-09). Every voice session
put its credential -- a staff Firebase ID token or a client magic-link
token -- on `/ws/fill?token=...`, and a URL is what every hop logs: uvicorn's
access line (B0 turned it off) and Cloud Run's own request log (B0's
exclusion filter). This change removes the cause.

## What changed

- **The credential rides the first frame.** `WebFormConnection` no longer
  appends `token=` to the socket URL; it sends `{...handshake, token}` as
  the first frame (all THREE handshake send sites: the connect path, the
  continuous-session section switch, and the legacy non-continuous section
  switch that builds its handshake by hand -- the fresh-eyes round caught
  that third one; a static pin now counts send sites against token sites). The backend pops `token` from the parsed handshake
  and verifies it (`_verify_ws_credential`, unchanged: link shape vs
  Firebase JWT by dot count) BEFORE anything else in the handshake is read
  and before any Gemini session starts; missing or invalid closes `1008`
  with the same fixed wire phrases as before. An accepted socket that sends
  nothing is closed `1008` after `WS_AUTH_TIMEOUT_SEC` (10s), so an
  unauthenticated peer cannot hold a connection open.
- **`?token=` is deprecated, not removed**: honoured for one deploy cycle
  (verified before `accept()` as before) behind a `ws_token_in_url_deprecated`
  warning, so a cached old bundle keeps working; the branch goes next deploy.
- **Origin allowlist before `accept()`**: a browser `Origin` outside the CORS
  list is refused `1008` ("Origin not allowed"); a request with no Origin (a
  non-browser client: the harness driver, tests) passes. The list is ONE
  list now -- `backend/config.py` `LOCAL_BROWSER_ORIGINS` +
  `parse_extra_origins(CORS_EXTRA_ORIGINS)` via `browser_origins()`, used by
  `main.py`'s CORS middleware and by the socket -- so the two cannot
  disagree. **Deploy consequence:** the voice app opens the socket from its
  Hosting site DIRECTLY (no rewrite for WebSockets), and the channel env
  files' `CORS_EXTRA_ORIGINS` listed only the editor's origins; they now
  carry the voice app's sites too (`deploy/channels/demo.env`,
  `staging.env`), pinned by a test that reads the env files. Without that,
  every production session would have been refused.
- **Frame cap**: any text frame over `WS_MAX_TEXT_FRAME_BYTES` (4 MB; the
  handshake carries a whole kit schema) closes `1009`; binary audio frames
  already had `WS_MAX_AUDIO_FRAME_BYTES`.
- **`/ws/echo` and `/ws/audio` fail closed on `K_SERVICE`** as well as the
  `.env.DEV` marker (the `/dev/console-log` pattern from C4).
- **Staff kit scope** (C1's matrix finding, bd fr20a): a staff token's
  handshake `kit_id` now goes through `kit_gates.require_visible`, the same
  gate as the HTTP kit routes -- a private kit outside the caller's firm
  closes `1008` ("Kit not available") before any session; a store error
  fails closed. The matrix test that documented the gap is inverted, plus a
  positive case.
- **Pins**: `backend/tests/unit/test_ws_first_frame_credential.py` (14
  cases); the wire close-reason tables in `test_ws_close_events.py` and
  `test_no_pii_logging.py` gained the four new fixed phrases;
  `webFormConnection.token.test.ts` inverted (no `token=` on the URL, the
  token in the first frame, both handshake sites).
- Docs: `ws-protocol.md` (the `token` key), `websocket-routing.md`,
  `auth.md`, `technical_guide.md` (`/ws/fill` + dev-socket rows),
  `config-deployment.md` (the access-log paragraph; the channel env change),
  `hipaa-pii-policy.md` (the access-log row).

## Verification

- Scar #9, one interpreter each, all RED: the first-frame verification
  short-circuited; the Origin check removed; the frame cap removed; the
  `K_SERVICE` gate removed; the auth timeout removed; the staff scope gate
  removed (the inverted matrix test); the deprecation log removed; `pop` ->
  `get` on the token; the voice app's origins dropped from a channel env.
  Client side: the token back on the URL (6 cases red); the token dropped
  from the handshake (6 red).
- Backend socket suites + matrix + route-auth + PII guard: 153 green;
  frontend full suite: 2362 green; `tsc` clean. The first full backend run
  caught four pins describing the old shape: the protocol contract test
  wants every documented handshake key read via `handshake.get(...)` (the
  route now gets then pops `token`); the auth-lifecycle test's verifier
  stub returns None, which the `claims is None` fall-through misread as
  "unverified" -- a `credential_verified` flag now records which transport
  verified, independent of the claims value; a bare test double had no
  `headers` (the Origin read is tolerant); and channel parity, now that the
  two channel files legitimately differ in `CORS_EXTRA_ORIGINS` (each names
  its OWN app site only; added to `CHANNEL_SPECIFIC` with the reason).
  Full backend suite on the final commit: 6560 passed, 264 skipped (both services + repo-level); frontend 2369 passed; `tsc` clean.
- Harness (exit criterion 1): local stack (backend on 127.0.0.1:8000 with the auth bypass, Vertex; the
  demo-mode frontend on 127.0.0.1:5174; the harness mock user), driven from
  the in-app browser. The real app opened `/ws/fill`, the backend logged
  `jit_handshake_received` + `web_session_starting` and a Gemini session
  went live (first audio chunk received), with ZERO
  `ws_token_in_url_deprecated` lines -- the credential came in the frame.
  Raw sockets from the same page: a handshake WITHOUT a token -> close
  1008 "Authentication failed" after accept; a 4.1 MB first frame ->
  1009 "Frame too large"; a socket that sends nothing -> 1008 after the
  10s auth timeout; the deprecated `?token=` form -> `session_ready` and
  exactly one `ws_token_in_url_deprecated` log line. No
  `websocket_auth_failed` / `websocket_origin_refused` for the real app
  (its Origin is a local dev origin on the list).

Fresh-eyes (Sonnet, read-only): criteria 1 and 2 PASS (3 deploy-gated);
one gap -- the legacy `CONTINUOUS_SESSION=false` section-switch handshake
was built by hand without the token (fixed + pinned); it also noted the
staging origin list carrying the demo app (already narrowed in the same
amend) and the uncached per-connect metadata read the staff gate adds (the
same read the HTTP kit routes and the client-link path already do). Opus
cross-surface: round 1 traced every consumer and found two tier-2 doc
passages the change falsified (`config-deployment.md`'s
`CORS_EXTRA_ORIGINS` bullet still pointed at the inline list `main.py` no
longer has and did not mention the socket's Origin role; the parity
exception list was three keys, the test has four) -- fixed; and two
behavioural points folded in: the socket's staff gate now runs
`require_published` before `require_visible`, exactly like every HTTP kit
read (a draft/reverted kit must not open a voice session), pinned; and
on the client a 1008/1009 close is TERMINAL (no five-retry burn on a
policy refusal that now arrives after accept; `lastPolicyRefusal` keeps
the wire phrase for the UI), pinned. Filed: `polyglot-pdf-0j8e5` (remove
the deprecated `?token=` transport one deploy later -- ~54 test call
sites enumerated -- and retire B0's exclusion filter) and
`polyglot-pdf-nb9tx` (binary frames on the socket are uncapped,
pre-existing). The `--no-access-log` comment and its test docstring
now say "until C2". Round 2 closed all eight and found four more:
the new 1009 close was unclassified in `WS_CLOSE_SEVERITY` (logged as
ERROR; WARNING now, pinned); the socket's kit gate collapsed a TRANSIENT
store failure into the terminal 1008 -- it closes 1013 `kit_unavailable`
now (the client's ordinary retry path, the budget_unavailable shape),
pinned; `logging-and-cost.md` and the voice-harness skill still described
the URL credential / the inline origin list (fixed); plus two nits folded
in: the frame cap counts UTF-8 bytes (pinned with a non-ASCII case) and
the channel env pin now also asserts neither channel names the OTHER's
app site. Its larger flag -- a fully translated kit schema on the
handshake could cross the 4 MB cap on the ~90-language roadmap, and a
policy refusal has no on-screen message yet -- is filed as
`polyglot-pdf-4uub0`. Round 3 closed all seven and found what the terminal
`disconnected` status did to two untouched consumers: the client save
nudge (its `voiceEnding` list did not know the status, so a mid-session
refusal no longer nudged a client to save -- the exact regression the
save-nudge test exists for) and the Reconnect button (rendered for
`disconnected`, so a refusal offered a retry that cannot work). A policy
refusal now has its OWN status, `policy_refused`, wired everywhere
`budget_exhausted` is: the save nudge fires, both overlays' connect polls
stop and show the backend's phrase (`lastPolicyRefusal`) instead of a
timeout, Sol leaves, no Reconnect button; pinned in the save-nudge test
and the policy-refusal test. Also: the technical guide's handshake
contract (Surface contract 2) lists the `token` key and the Origin check;
the severity docstring lists 1009; the 1013 metric now also counting
kit-store failures is `polyglot-pdf-5bbj1`. Round 4: NO-GAPS; two nits folded in (the status
joins `setStatus`'s dropped-reconnect clear list like `budget_exhausted`; a
stale extractor comment in the protocol contract test) and one pre-existing
gap filed (`polyglot-pdf-6jezt`: `solState.test.ts` pins neither terminal
status).

## Files

`backend/routes/websocket_routes.py`, `backend/config.py`, `backend/main.py`,
`deploy/channels/demo.env`, `deploy/channels/staging.env`,
`backend/tests/unit/test_ws_first_frame_credential.py`,
`backend/tests/integration/test_access_matrix.py`,
`backend/tests/unit/test_ws_close_events.py`, `backend/tests/test_no_pii_logging.py`,
`frontend/src/webFormConnection.ts`, `frontend/src/webFormConnection.token.test.ts`,
six docs, `docs/freshness/*.ack`.
