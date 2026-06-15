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

### Review trail (Codex x2 + confirming fresh-eyes)

Codex (credits briefly back this session) reviewed in two rounds, both of which
found REAL issues -- not re-litigation:

- Round 1 (2 P1): the meter could show green "sending" during `reconnecting` (the
  worklet `sending` flag means the audio-routing gate passed, but the CONNECTION
  send gate `shouldSendMicChunk` drops bytes then); and the rAF loop ran perpetually
  even when the meter wasn't rendered. Both fixed.
- Round 2 (2 P0 CI-breakers + 1 P1): `global.navigator = ...` throws under Node 24 /
  Vitest ESM (read-only accessor) -- would have failed the whole frontend suite on
  CI; `Array.prototype.at(-1)` isn't typed under the ES2020 tsconfig lib -- would
  have failed `npm run typecheck`; and my round-1 grey-for-all-non-`connected` fix
  was too aggressive (`switching_section` + open socket legitimately sends). Fixed by
  `vi.stubGlobal`, `[length-1]` indexing, and a new `ConnectionManager.isSendingMicAudio()`
  -- the single source of truth (`shouldSendMicChunk` over live status + socket
  state) that `sendMicChunkToBackend` already uses; both overlays now derive the
  green state from it. `npm run typecheck` confirmed clean.

Codex quota then exhausted, so a **local fresh-eyes confirming round** (Sonnet) ran
on the round-2 fixes -> NO-GAPS (verified `isSendingMicAudio` delegates correctly +
is read-only, the rAF gates match each overlay's render condition, the test-env
stubs are non-vacuous). Lesson: local Node passing != CI Node passing -- the
`global.navigator` assignment and the `.at()` lib-target mismatch both passed
locally but would have broken CI; `npm run typecheck` (the exact CI gate) is the
check to trust, not a bare local run.

The PRE-PR fresh-eyes (Sonnet, 1 round -> NO-GAPS) had already passed: all 3 rubric
criteria PASS; send paths unchanged (only `emitEnergy` calls added), no new
AnalyserNode, both overlays covered. Three informational notes (not rubric gaps),
all addressed:
(1) the energy subscription captures the manager instance, so a future mid-session
`disconnect()/connect()` that swaps the inner manager without changing the
`connectionManager` ref would silently stop the meter -- added a JSDoc invariant
note on `setEnergyCallback` (re-architecting for a non-existent flow would be
over-engineering); (2) the JSDoc described only the `!recording` guard when the real
guard is `!recording || !onAudioDataCallback` -- corrected; (3) the existing overlay
test stubs lacked `setEnergyCallback`, so nothing asserted the OVERLAY subscribes --
added `setEnergyCallback` to both stubs and two new tests
(`assertEnergySubscribed`) pinning subscribe-on-mount + unsubscribe-on-unmount for
both overlays. Also caught (pre-PR, via the tsc gate) two unused `@ts-expect-error`
directives in the new test that would have failed CI's `tsc --noEmit` -- removed.

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

Bumped the two docs that track files this branch changed: `voice-ai.md`
(audioManager.ts) and `voice-and-vad.md` (audioManager.ts + VoiceOverlay.tsx) --
each noting the energy-callback is a new opt-in subscriber that reads the send gate
but does not alter audio routing / VAD behavior. Left three docs flagged-but-stale
because they track BACKEND files this branch did NOT touch (other-session work on
dev): `context-compression.md` + `tool-call-flow.md` (form_filling_service.py /
callback_handler.py / request_coordinator.py) and `confirmation-and-audit.md`
(callback_handler.py). Per the doc-freshness rule, a doc stale on a file this branch
didn't change is not this PR's to bump. The run-local SKILL.md was edited as part of
this work (bash-runner preference + headless-drive note).

## Files touched

- `frontend/src/shared/audioManager.ts` -- setEnergyCallback + worklet energy tap
- `frontend/src/shared/audioEnergyCallback.test.ts` (new) -- 6 wiring tests
- `frontend/src/demo/VoiceOverlay.tsx` + `VoiceOverlayMobile.tsx` -- subscription, rAF flush, meter JSX + CSS
- `.claude/skills/run-local/SKILL.md` -- prefer dev-local.sh; idle-timeout/stale-fiber note
