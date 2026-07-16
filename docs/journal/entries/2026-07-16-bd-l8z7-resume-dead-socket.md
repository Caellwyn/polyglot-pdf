---
date: 2026-07-16
bead: polyglot-pdf-l8z7
title: "resume() succeeded onto a dead socket: gating on stale status instead of the live socket state"
tags: [postmortem, hotfix]
---

## Trigger

Found while reproducing nm7z (the audio-dies-after-pause bug) on the local
stack, 2026-07-15 22:49Z. In the console mirror, an idle-timeout landed DURING
a pause (mic-drop logs: `status=idle_timeout socketOpen=false`), and clicking
Resume logged `Resuming...` -> `Resumed successfully` with no error -- onto a
socket that was already closed. The mic re-armed into a black hole (every chunk
dropped), the UI showed a healthy resumed state, and there was no recovery
affordance. This is plausibly the other half of the tester's "even refreshing
didn't help" experience (bugs 0/7).

## What shipped

Root cause: two status truths that can disagree. The mic-send gate
(`shouldSendMicChunk`) reads `connection.isSocketOpen()`; resume()'s old guard
read `connection.getStatus() !== 'connected'` alone. An idle-timeout can leave
those momentarily inconsistent (the socket is closed while the manager's
rendered status is stale), so resume() passed its guard and proceeded onto a
dead socket.

Fix (frontend/src/shared/connection.ts resume()): gate on
`connection.isSocketOpen()` -- the SAME truth the mic-send gate uses. A closed
socket cannot be resumed regardless of what status says, so resume() now
delegates to `manager.connect()`, which self-heals: on a dead socket its
`isWebSocketConnected` check is false and it runs a full WS reconnect. `paused`
is cleared first so connect() takes the connect path, not a re-entrant resume.

Two tests (connection.test.ts): a closed socket routes to reconnect
(`webFormConnectionMock.connect` called, `isPaused()` cleared); an open socket
still resumes in place with no spurious reconnect (the regression guard). Full
frontend suite 1004 green; tsc clean.

Exit criterion 2 ("a terminal status arriving mid-pause is not masked by the
paused render state") is met BEHAVIORALLY: whichever button the overlay shows,
clicking it now recovers (both call handleConnect; resume() self-heals). The
remaining COSMETIC residue -- the label can briefly read "Resume" before the
idle_timeout status reaches the parent-owned React `status` that drives the
button -- is a status-propagation-timing concern owned by the jf6w
connection-timeout-modal epic, and was deliberately NOT reworked here (the
overlay renders from parent-driven status; probing socket liveness per-render
would fight that architecture). Scoped out with a note on the bead rather than
silently narrowing the criterion.

## Lessons

- When two code paths make the same decision (here: "can audio flow?"), they
  must read the SAME source of truth. resume() and the mic-send gate both
  answer that question; they diverged because one trusted `status` and the
  other trusted `isSocketOpen()`. A recovery action ("resume") should gate on
  the same signal as the operation it is trying to restore.
- A "success" log on a path that did not actually succeed (`Resumed
  successfully` onto a dead socket) is worse than a failure log -- it hid the
  bug from the tester's console entirely. Recovery paths should verify the
  thing they claim to have restored.

## Doc freshness

voice-ai.md tracks connection.ts at the adapter level; the resume()/status
gating is client-internal and not described there. Reviewed, left as-is.

## Files touched

- frontend/src/shared/connection.ts -- resume() gates on isSocketOpen, routes dead socket to connect()
- frontend/src/shared/connection.test.ts -- 2 tests (closed->reconnect, open->resume-in-place)
