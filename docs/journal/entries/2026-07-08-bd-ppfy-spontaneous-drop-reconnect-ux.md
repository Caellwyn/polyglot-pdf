---
date: 2026-07-08
bead: polyglot-pdf-ppfy
title: "Detect spontaneous Gemini drop (1011) -> notify client -> reconnect + 'reconnecting' modal; disable thinking tokens"
tags: [bugfix, voice-ai, frontend]
---

## Trigger

A machine-observed continuous-mode I-90 voice run (the first turn-by-turn
verification of x8rt continuous DTI on Vertex) surfaced an intermittent Gemini
2.5 native-audio `1011` "Input data processing failed" close -- ~2 of 5
continuous sessions died right after the initiating message with `Response: 0
tokens`, before any field filled. This is a KNOWN, pre-existing 2.5 instability
(bd 3v5m references demo 1011s in production-like traffic), NOT introduced by
continuous mode -- but continuous mode raises the stakes: a drop kills the whole
FORM's session, not one section.

The maintainer chose to ship continuous anyway and mitigate the 1011 in the UI.
On Vertex a 2.5->3.1 failover is impossible (there is no Vertex 3.1; 3.1 is
AI-Studio-only), so failover (bd 3v5m) was PARKED and graceful recovery chosen
instead.

## Root cause (the real bug)

A code trace found the actual user-facing defect behind "the AI just stops
responding": on a spontaneous 1011 the backend caught the drop in the adapter's
`_run_session_loop` and set `_closed_event` -- but NOTHING listened for a
spontaneous drop (`_closed_event` was only awaited in the section-switch path).
The client-facing WebSocket stayed OPEN behind a dead Gemini, the client stayed
frozen on status `connected`, and the user's mic audio was silently swallowed
(`AUDIO_SEND_FAILED`, `pass`). The only net was the 120s idle watchdog. So a modal
keyed on a `reconnecting` status would never fire -- the client never left
`connected`.

## What shipped

A 3-layer fix (bd ppfy) + a thinking-token change (bd 3v5m), one PR:

- **L1 detect+notify** (`live_ai_gemini.py`, `callback_handler.py`,
  `form_filling_service.py`): the receive-loop catch records the drop and its WS
  close code; a genuine error-drop (code in `{1011, 1006}`, and NOT an intentional
  finalize / section-switch shutdown) forwards a new `on_session_dropped` callback
  which sends `{"type":"gemini_session_dropped"}` to the client (mirrors
  `on_go_away`). A benign normal/GoAway close is excluded by the code gate.
- **L2 client reconnect** (`webFormConnection.ts`): the new message drives the
  existing GoAway pre-emptive reconnect (close + reconnect `resume:true`, coalesced
  via `goAwayReconnectInFlight`) but surfaces a `reconnecting` status.
- **L3 modal** (`ConnectionTimeoutModal.tsx`, `connectionTimeoutTranslations.ts`,
  `VoiceOverlay.tsx`): a passive `variant="reconnecting"` (spinner, no buttons)
  with copy in all 18 languages, shown while `reconnecting` AND the reconnect is
  drop-driven (`isDroppedReconnect()`), auto-cleared on `connected`, escalating to
  the existing terminal modal on `reconnect_failed` (reached via the normal
  socket-level `handleClose:max-retries` path).
- **thinking tokens off** (`config.py`, `live_ai_gemini.py`): `thinking_config
  thinking_budget=0` for 2.5-family models (explicit `== "2.5"` allowlist), gated
  `DISABLE_MODEL_THINKING` (default on). Safe-if-ignored on native-audio.

### Watchdog: built, then removed (deliberate)

A pre-PR reviewer asked for a client watchdog to escalate a "silent hang" (the
reconnect socket opens but `session_ready` never arrives) to the terminal modal
instead of sitting on the transient one. It was built -- but it turned out to be a
complexity magnet: across ~5 adversarial-review rounds it spawned a chain of
edge-case fixes (stand-down-during-backoff, re-arm-on-reopen, close-the-hung-socket,
guard-the-close-reentrancy), each one exposing the next interaction with the
reconnect state machine. The maintainer's call (2026-07-08): **rip the watchdog out**
and ship the twice-cleared core. A silent hang now stays on the transient
"reconnecting" modal until the user refreshes -- an accepted degradation for an
ultra-rare failure-within-a-failure. Beads `polyglot-pdf-vqbm` and
`polyglot-pdf-yigb` (both watchdog-only edge cases) are closed obsolete. If graceful
silent-hang recovery is ever wanted, it belongs in its own properly-scoped bead, not
bolted onto this state machine.

## Where the notify fires (the race fix)

The spontaneous-drop notify fires from INSIDE `_run_session_loop` at the
drop catch -- NOT from the bg-task done-callback. An earlier draft scheduled it
from the done-callback reading live instance fields; pre-PR review (bd bcrn)
proved a `restart_gemini_session()` could observe `task.done()==True` in the
window before the done-callback ran and reset the drop markers, swallowing the
notify. Firing in-loop (this-session's async context, completes before the task
finishes) eliminates the race. `bcrn` closed with this PR.

## Scar tissue

- On a spontaneous Gemini drop the backend does NOT close the client WS (verified:
  the only `websocket.close()` calls are auth/idle/bad-frame/disconnect). So the
  client freezes with no signal unless the backend forwards one -- and a
  `handleClose`-based reconnect never fires (the socket stays open). This is why L1
  is load-bearing and why there is no double-reconnect (only the new message drives
  it).
- `model_family()` is a PRICING fallback that maps ANY unrecognized model string to
  `"2.5"`, so the thinking-config `== "2.5"` allowlist still matches an unknown
  model. The change from `!= "3.1"` is clarity, not a behavior fix for unknowns; a
  test pins the fallback so a future `model_family` change is caught.
- Verification honesty: the full turn-by-turn continuous fill + the "real 1011 ->
  modal appears" path is unit-tested end to end (backend forwards -> client
  reconnects -> modal on status), NOT eyeballed live (the headless harness froze
  under Gemini audio and the browser automation was flaky this session).
