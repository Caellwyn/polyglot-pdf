---
date: 2026-07-02
bead: polyglot-pdf-puu8
title: "WS surface hardening: dev-only debug sockets + wire-protocol contract tests"
tags: [security, testing]
---

## Trigger

Follow-ups from the o0pc dead-code cleanup assessment, approved by the
maintainer: the two low-level debug sockets shipped ungated to the demo
(polyglot-pdf-puu8), and the WebSocket contract-test stub had zero tests
while ws-protocol.md documented a full frozen wire contract
(polyglot-pdf-ceyt). Bundled into one PR: both harden the same WS surface.

## What shipped

**puu8 -- dev-only debug sockets.** /ws/echo and /ws/audio now reject the
handshake (close 1008 before accept) unless the backend/.env.DEV marker
exists -- the same DEV_LOGGING_ENABLED gate the /dev/console-log route uses.
The product socket /ws/fill is untouched. New
backend/tests/integration/test_debug_socket_gate.py pins both directions
(monkeypatched, so results do not depend on the developer's .env.DEV).
technical_guide.md: route table marks the sockets dev-only; new Gotcha notes
the prod frontend build ships ONLY index.html (vite has no multi-page
rollupOptions.input -- vad-tuning.html and schema-form-demo.html are
dev-server-only).

**ceyt -- wire-protocol contract tests.** The empty
backend/tests/contract/test_websocket_protocol.py stub now holds 73 tests
(written by a Sonnet subagent, reviewed + adjusted by the orchestrator).
Instead of hand-listing types, the module parses the ws-protocol.md tables
AND regex-extracts the send/dispatch literals from websocket_routes.py (+
callback_handler/request_coordinator/form_filling_service), then diffs the
two sets both directions -- so renaming or dropping a wire type or handshake
key fails a test, which makes the deferred part_*->section_* wire rename
(polyglot-pdf-zun) test-driven. Also: live TestClient handshake ->
session_ready round-trips for legacy AND JIT modes, invalid-schema close,
ping/pong + unknown-control behavior.

**Contract catch, fixed in this PR:** session_ready sends dti_mode_enabled
(consumed by the frontend) but ws-protocol.md did not document it. The doc
row was added and the test pins BOTH sides.

**Filed:** polyglot-pdf-wbua -- webFormConnection.ts has dead inbound switch
cases (complete_section, ai_response) nothing sends; out of scope here.

**Also this session, before this PR:** polyglot-pdf-fi7p (make the freshness
checker git-based) was closed INVALID -- reading the code showed it already
uses git commit times (git log -1 --format=%ct), not fs mtimes; the o0pc
17-doc warn list was correct behavior on a wide diff.

## Lessons

- A contract test that PARSES the doc and DIFFS it against code-extracted
  literals is self-maintaining: it caught a real undocumented wire key
  (dti_mode_enabled) on its first run, and future drift fails loudly instead
  of rotting silently.
- Verify a bead's premise against the code before implementing it -- fi7p
  prescribed a fix for behavior the code already had; the bead was filed from
  a misread of the checker's output, and reading 40 lines of source killed it
  cheaply.

## Doc freshness

- Bumped + edited: docs/standards/ws-protocol.md (dti_mode_enabled row +
  contract-tests note), docs/technical_guide.md (dev-only socket rows,
  prod-build-ships-index-only gotcha).
- Other docs flagged STALE by the checker track files this branch touched
  only via the gate edit (websocket_routes.py) -- reviewed and left; no claim
  in them is affected by a dev-only handshake rejection.

## Files touched

- backend/routes/websocket_routes.py -- DEV_LOGGING_ENABLED gate on
  /ws/echo + /ws/audio (5 lines each).
- backend/tests/integration/test_debug_socket_gate.py -- new, 4 tests.
- backend/tests/contract/test_websocket_protocol.py -- filled the empty
  stub: 73 tests.
- docs/standards/ws-protocol.md, docs/technical_guide.md -- see Doc
  freshness.
