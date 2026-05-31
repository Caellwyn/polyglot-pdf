---
date: 2026-05-31
bead: polyglot-pdf-od1
title: "Reconcile WS_IDLE_TIMEOUT_SEC to 120 (value/comment/tests now agree)"
tags: [testing, conventions]
---

## Trigger

`polyglot-pdf-od1` (surfaced by Copilot on PR #16): `backend/config.py` set
`WS_IDLE_TIMEOUT_SEC = 120`, but its inline comment said "60s" and three test
assertions expect `== 60` (`test_idle_timeout.py:111`,
`test_idle_timeout_flow.py:49,81`). These three failures were the persistent red
in every test run across this session's earlier closeouts (4cm). The bead asked
to "decide the intended default, then make value+comment+tests consistent."

## What shipped

**Reconciled on 120 (not 60), as a deliberate decision informed by review.** The
documentary evidence pointed at 60 — `git blame -L` shows the value was originally
`60` and a single commit (`b9eac1e`, verified) bumped it to `120` without updating
the comment or tests, and other docs (`heartbeat_keepalive.md`, planning docs) say
60. The initial fix restored 60 on that basis.

But fresh-eyes review of the PR surfaced an **operational** argument the paper
trail missed: the idle clock (`last_rx` in `websocket_routes.py`) is reset only by
a *received* message, and when the user is silent the client stops sending audio
(VAD-gated — `audioManager.ts` skips silent chunks) with **no client keepalive
ping** on the fill socket. So the timeout fires after a flat wall-clock silence.
At 60s a user pausing to read or think gets disconnected; 120s gives a safer
margin. The disconnect is graceful (sends `idle_timeout`, shows a Reconnect
button), but the shorter window is a real UX regression. Maintainer decided to
**reconcile UP to 120** — keep the more-forgiving value, fix the comment + the
three tests to match. od1 still gets its single source of truth, just at 120.

Changes: `config.py` value stays 120, comment corrected to "120s … no received
message (audio/ping/control)"; the three test assertions updated 60 -> 120;
`technical_guide.md` prose states 120 and clarifies the clock is reset by any
received message (not only on `/ws/fill`).

**CI gap (separate finding).** While verifying the bead's "does the suite run in
CI?" question: **no CI runs the pytest suite at all** — no `.github/workflows/`
(only `.github/*-instructions.md`); `gh run list` shows only Copilot. That is why
the drift went unnoticed. Filed **bd polyglot-pdf-r19** to wire pytest into CI.

**Tests:** full non-external suite green with the new 120 assertions (see Step 4
of closeout). The idle-timeout suite collects and passes when run with
`PYTHONPATH=<repo-root>` (the bead's noted collection import-error did not
reproduce; bare `pytest tests/` from `backend/` mis-collects).

**Review (fresh-eyes + Copilot round 1):**
- **Adopted:** (1) the 60-vs-120 operational argument → reconciled up to 120
  (fresh-eyes F3, the substantive finding). (2) doc wording: "form-fill socket" →
  "WebSocket connection … any received message" since the timeout governs all WS
  endpoints, not just `/ws/fill` (fresh-eyes F1).
- **Verified, no change:** the journal's `b9eac1e` blame claim — confirmed correct
  (fresh-eyes F2).
- **Copilot:** round 1 produced an overview but **no inline comments** (3/3 files,
  no findings).
- **Deferred:** none beyond the pre-existing CI bead (`r19`). Fresh-eyes also noted
  pre-existing items it explicitly declined to flag (fill-watchdog uses
  `time.time()` vs the echo/audio watchdogs' `time.monotonic()`; a redundant
  `get_settings()`); not in scope for this PR.

## Lessons

- A constant whose **inline comment and tests both disagree with its value** is
  usually a drift introduced by an edit that moved the value alone — `git blame -L
  <line>,<line>:<file>` settles *intent* fast. But "intent per the paper trail" and
  "the right value operationally" can diverge: here the drift (120) turned out to
  be the better value once review weighed how the idle clock is actually fed.
  Reconcile to the *correct* value, not reflexively to the oldest one.
- **Tests that aren't in CI silently rot.** This drift survived because nothing ran
  the suite on a gate → `polyglot-pdf-r19`.

## Doc freshness

- `docs/technical_guide.md`: env-var prose previously cited `WS_IDLE_TIMEOUT_SEC`
  without a number (pending this bead) and called the disagreement open; now states
  `120` and clarifies what resets the idle clock. (No `**Tracks:**` line — bumped by
  hand; freshness checker skips it.)
- `check_doc_freshness.py`: clean for all tracked tier-1/tier-2 docs.

## Files touched

- `backend/config.py` — `WS_IDLE_TIMEOUT_SEC` comment corrected to 120s (value stays 120)
- `backend/tests/unit/test_idle_timeout.py` — assertion 60 -> 120
- `backend/tests/integration/test_idle_timeout_flow.py` — two assertions 60 -> 120
- `docs/technical_guide.md` — env-var prose: state 120, clarify idle-clock reset + scope
