# 5j3im -- a live session SURVIVES a long frame-free gap (MEASURED)

**Verdict: CONFIRMED SAFE.** A deploy-shaped Gemini Live session survives at
least **3 minutes** with **zero audio frames sent**, and answers the turn after
the gap. 6/6 arms survived; no session closed.

**Date:** 2026-09-03. **Model:** `gemini-live-2.5-flash-native-audio` (Vertex,
production default). **SDK:** google-genai 2.8.0 (post-cutover, so not stale).
**Actual spend: ~$0.04** (estimate was ~$0.05; came in under).
Maintainer-approved 2026-09-03.

---

## Results

| gap | rep | turn 1 answered | turn 2 answered | verdict | wall-clock | close |
|---|---|---|---|---|---|---|
| 30 s | 1 | yes | yes | **SURVIVED** | 41.8 s | none |
| 30 s | 2 | yes | yes | **SURVIVED** | 41.0 s | none |
| 90 s | 1 | yes | yes | **SURVIVED** | 103.5 s | none |
| 90 s | 2 | yes | yes | **SURVIVED** | 102.2 s | none |
| 180 s | 1 | yes | yes | **SURVIVED** | 191.1 s | none |
| 180 s | 2 | yes | yes | **SURVIVED** | 191.6 s | none |

`close_reason` was `None` on every arm -- no 1011, no 1006, no GoAway during any
gap. Raw data: `scripts/spikes/data/idle_gap_5j3im.json`.
Script: `scripts/spikes/diag_idle_gap_5j3im.py`.

---

## What was actually tested

Each arm is ONE live session doing:

```
connect -> turn 1 (activity_start, ~1.2s audio, activity_end, await reply)
        -> GAP of N seconds sending ZERO bytes
        -> turn 2 (same) -> was it answered?
```

"Answered" means real reply audio arrived from the model -- not merely that the
socket looked open, which a dead-but-not-yet-closed session would also satisfy.

### Deploy fidelity (the requirement that makes this transferable)

This drove the **real `LiveAIGemini` adapter**, not a hand-rolled config:

- the production system instruction (`DTI_SYSTEM_INSTRUCTION`, ~15.2k chars);
- the production tool declarations, via `FormFillingService._build_tool_declarations()`;
- the adapter's own `_build_live_config()` and session loop;
- audio streamed in 20 ms chunks at 16 kHz, real-time paced, inside
  `activity_start`/`activity_end` brackets exactly as PTT does.

Corroboration that the session was genuinely production-shaped: the model made
real tool calls during the runs (`get_form_status`, `ask_secretary`). Those
`tool_callback_error` lines in the log are the PROBE's no-op callbacks refusing
the call, not an adapter defect -- the probe deliberately does not implement the
tool surface, since it measures session survival rather than fill behaviour.

This mattered: a stripped-down probe config previously produced a week of false
"2.5 is unstable" verdicts (bd `h04c`), which is why deploy fidelity is
mandatory here.

---

## Why this question was open

We ship the frame-free idle stream TODAY. Since bd `polyglot-pdf-v1m8g` retired
Gemini's automatic activity detection, the client sends **nothing** between turns
(measured in bd `polyglot-pdf-h7atc`: 0 silent frames across a 350 ms gap, both
senders; backend gap-fill pinned `False`).

Gap-fill originally existed because a starved stream was believed to trigger
1011 closes (bd `polyglot-pdf-7f7m`). Re-reading that bead for this probe's
prior-work audit: **its exit criteria verified the MECHANISM** (cadence
maintained across a simulated stutter; silence never fights real audio) -- they
never demonstrated that starvation causes a 1011. The stated basis was
"Google-forum analyses", and the claim was explicitly scoped to NATIVE VAD:

> Native-VAD mode requires a CONTINUOUS audio stream to Gemini (silence
> included) -- Gemini's server-side VAD drives turn boundaries and the server
> clocks keepalive off a steady cadence of binary frames.

With automatic activity detection disabled and turns bracketed explicitly, that
reasoning should not apply. This probe confirms it does not.

**The removal of gap-fill in v1m8g was correct**, and is now measured rather than
merely reasoned.

---

## Scope and limits (do not over-read this)

- **Measured to 180 s.** Longer gaps are untested. Nothing suggests a cliff, but
  this does not prove a session idles indefinitely.
- **Single model.** `gemini-live-2.5-flash-native-audio` on Vertex, the
  production default. Not verified on 3.1 (which is not on Vertex; see
  `docs/standards/ai-models.md`).
- **Does not test the reconnect path.** It confirms reconnect is not NEEDED for
  an idle gap of this length; the existing GoAway/auto-drop machinery remains the
  net for genuine drops, and is unaffected either way.
- **Does not bear on session DURATION limits.** Context-window compression and
  GoAway still bound total session length; this is only about audio cadence.

## Already ruled out (so it need not be re-derived)

- **The WS idle watchdog is not the hazard.** `last_rx`
  (`backend/routes/websocket_routes.py`) is bumped by CONTROL messages, and PTT
  brackets arrive as control messages. Verified during v1m8g's review; this probe
  drives the adapter directly and so does not exercise that layer at all.

---

## Probe-quality notes (two bugs caught by piloting first)

Both were found by running ONE cheap pilot arm before the sweep, which is exactly
what the experimentation skill's staged approach is for. Had they gone unnoticed,
all six arms would have produced meaningless results -- and the first one would
have looked like a scary negative.

1. **`is_session_active()` is not a readiness signal.** It reports only that the
   background task exists, which is true the instant the task is created and long
   before the socket is up. Waiting on it fired turn 1 into a `None` session
   (`ACTIVITY_START called but session is None`) and scored a false
   `INCONCLUSIVE_TURN1`. The real signal is `_session_ready`, set on
   setup-complete.
2. **`on_audio` must be `async`.** The adapter `await`s it
   (`_handle_session -> await self._on_audio(...)`); a sync callback raises
   `TypeError` inside the receive loop, which the adapter logs and swallows -- so
   the arm still scored SURVIVED, but via a noisier path than production takes.

Generalisable: **a probe's own scaffolding is as likely to be wrong as the thing
it measures** (bd memory `g3-cost-harness-unreliable-for-fill-accuracy`). When a
live probe returns a surprising negative, suspect the probe first.
