---
date: 2026-06-14
beads: [polyglot-pdf-s3zv]
pr: TBD
tags: [testing]
---

# s3zv: live mic-energy meter in the demo voice overlay

## Trigger

Maintainer request (2026-06-11): there was no reliable indication that the client
is actually *sending* audio to the backend -- so a dead mic or a noisy room looked
the same as a working one. The bead asked for a small energy meter / glow near the
connection status, reusing the worklet RMS energy that already exists (the
vad-tuning dashboard renders it), NOT a new AnalyserNode.

## What shipped

A small meter in the connection-status row of both overlays (desktop +
VoiceOverlayMobile), showing live mic energy and whether audio is actually reaching
the backend.

- **`audioManager.ts` -- the missing wire.** The worklet
  (`audio-processor.worklet.ts`) already computed a smoothed RMS energy (0-100, EMA)
  and posted it on every frame, but the manager's `port.onmessage` handler
  destructured only `{type, pcmData}` and **dropped `energy`** -- the
  `AudioEnergyCallback` interface existed but was never wired. Added
  `setEnergyCallback(cb | null)` and an `emitEnergy(sending)` helper inside the
  handler that forwards `energy` to the subscriber on EVERY frame, tagging it with
  whether the frame actually passed the send gate (`sending`). So the UI can
  distinguish "mic alive but gated" (muted PTT / idle client VAD / all-silence
  skip) from "audio being sent" (client VAD active, or native-VAD continuous). No
  new audio analysis -- it's purely the worklet's existing stream. Cleared on
  teardown.
- **Overlays -- subscribe + render.** Each overlay subscribes in a `useEffect` via
  `connectionManager.getAudioManager()?.setEnergyCallback(...)`, stashes each frame
  in a ref (the worklet fires ~50x/sec), and flushes to React state on a `rAF` loop
  -- one re-render per animation frame, not 50/sec. The meter bar's width tracks
  energy; it's **green** when sending, **grey** when the mic is live but gated, and
  decays to 0 after ~250ms of no frames so a flat meter reads as "no audio reaching
  the backend" -- the diagnostic this feature is for. Gated on `isConnected` so it
  only shows during a live session.

## Pre-PR assess + verification

Rubric (acceptance criterion: "overlay shows a live indicator of mic energy /
audio-send state, both overlays, reusing the worklet RMS"): PASS.

- **Unit tests (6, new `audioEnergyCallback.test.ts`):** drive the REAL
  `createAudioManager` with minimal AudioContext/AudioWorkletNode stubs and fire
  synthetic worklet messages, asserting the callback fires with the correct
  `(energy, sending)` per path -- sent frame (client VAD active), gated frame (VAD
  idle), all-silence skip, native-VAD continuous, the non-numeric-energy guard, and
  unsubscribe. The gate decision itself is already covered by `audioGate.test.ts`.
- **Live-verified in the running app** (local stack via `dev-local.sh`, driven via
  Chrome MCP): meter renders in the connected status bar; the **real worklet energy
  flows** end-to-end into the overlay's ref (observed `energy: 0.145` with live
  timestamps, `sending: false` correctly reflecting the muted-PTT gate); a
  pinned-loud drive through the overlay's own rAF path rendered the bar **green at
  78%** with title "Sending audio (energy 78)"; and the meter correctly **hides** on
  disconnect.
- tsc clean; full frontend suite green (382, +6 new).

Fresh-eyes: see the closeout assess (run after this entry).

## Lessons

The `AudioEnergyCallback` interface had been defined but never wired -- a "designed
but dead" seam. When a feature asks to "reuse existing data," check whether the
producer actually delivers it to a consumer; here the worklet produced energy on
every frame but the manager silently discarded it. The fix was a 3-line tap, not a
new pipeline.

Driving a connected voice overlay headless (Chrome MCP) is fiddly: the session
idle-times-out in ~30-60s with no audio sent (default PTT muted), and the overlay
re-mounts on reconnect, so cached React fiber/ref handles go stale between tool
calls. Re-acquire handles each pass and inspect in as few calls as possible.
Captured this (and the `dev-local.sh`-over-`.ps1` preference) in the run-local
skill in this same PR.

## Doc freshness

`docs/components/voice-ai.md` tracks `audioManager.ts` + the overlays. Reviewed:
the energy-callback addition is a new opt-in subscriber, no change to the adapter /
audio-routing behavior it documents; bumped its date with a note. The run-local
SKILL.md was edited as part of this work (bash runner preference).

## Files touched

- `frontend/src/shared/audioManager.ts` -- setEnergyCallback + worklet energy tap
- `frontend/src/shared/audioEnergyCallback.test.ts` (new) -- 6 wiring tests
- `frontend/src/demo/VoiceOverlay.tsx` + `VoiceOverlayMobile.tsx` -- subscription, rAF flush, meter JSX + CSS
- `.claude/skills/run-local/SKILL.md` -- prefer dev-local.sh; idle-timeout/stale-fiber note
