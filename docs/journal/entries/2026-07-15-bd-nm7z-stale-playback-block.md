---
date: 2026-07-15
bead: polyglot-pdf-nm7z
title: "Audio output dies after pause/unpause: stale barge-in playback block orphaned by a mid-pause idle timeout"
tags: [postmortem, hotfix]
---

## Trigger

Tester bugs 0 (7/9) and 7 (7/15): after pausing and unpausing, the AI's voice
never came back -- Gemini still heard her and filled fields, but audio output
was dead, and a page refresh did not reliably recover it. Intermittent, which
had made it look fixed once already.

## What shipped

Root cause, proven against the tester's own bug-7 console log rather than a
local guess: pause() flushes the AI audio queue, which sets
audioManager.playbackBlocked=true; the warm connection idle-timed out DURING
her pause (her log shows 'Pausing (keeping connection warm)' immediately
followed by 'Idle timeout received from backend, idle_seconds: 122'); she then
reconnected via connect() -- and resume(), the ONLY code path that clears the
block on the default PTT/native-VAD configuration, never ran. The reconnect
reuses the same audioManager, so playAudio() silently discarded every AI chunk
from then on (the discard branch deliberately logged nothing "to reduce
spam"). Intermittency = whether the pause outlasts the idle window.

Fix:
- frontend/src/shared/connection.ts rehydrateAudio() -- the one funnel every
  session-(re)establishment path passes through (onSessionReady,
  onSessionRestarted, resume, startSection, switchToSection) -- now clears the
  stale block via resumePlayback(). No legitimate barge-in flush can span a
  session swap (the old session's audio died with its socket), and the
  routine's paused guard keeps a mid-pause block intact.
- frontend/src/shared/audioManager.ts playAudio() blocked-discard branch now
  warns every 50th discarded chunk, so a stuck block can never again be
  invisible in a tester's console log (50 chunks is far beyond any legitimate
  barge-in window). resumePlayback() resets the counter.
- Two connection.test.ts tests pin the kill chain (pause -> idle-timeout ->
  connect() -> session-ready must unblock) and the guard (a mid-pause
  session-ready must NOT unblock).

Found while attempting the live repro and filed separately with evidence:
polyglot-pdf-l8z7 -- resume() consults a status source that said 'connected'
while the socket was closed (status=idle_timeout, socketOpen=false), logs
"Resumed successfully" onto a dead socket, and leaves the UI showing a healthy
paused/resumed state while every mic chunk drops. That second bug blocked
replaying the tester's exact click path locally; the unit tests pin the fixed
logic instead.

## Lessons

- A deliberately silent failure branch ("no logging to reduce spam") in a
  media pipeline makes field bugs undiagnosable -- the tester's 23KB console
  log contained zero evidence of the discard loop that was the entire bug.
  Rate-limited logging (every Nth) keeps the quiet case quiet and the stuck
  case visible.
- Paired state flags (flush sets, resume clears) break when a session
  teardown can interleave between the pair. The fix pattern: clear
  interaction-scoped state at the session-establishment funnel, not only in
  the interaction's own happy path.

## Doc freshness

voice-ai.md tracks connection.ts/audioManager.ts at the adapter level; the
barge-in block is client-internal state not described there. Reviewed, left
as-is.

## Files touched

- frontend/src/shared/connection.ts -- rehydrateAudio clears the stale playback block
- frontend/src/shared/audioManager.ts -- blocked-discard visibility counter
- frontend/src/shared/connection.test.ts -- 2 new kill-chain/guard tests
