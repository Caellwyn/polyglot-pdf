/**
 * Tests for the live mic-energy callback wiring in audioManager (bd
 * polyglot-pdf-s3zv).
 *
 * The worklet already posts a smoothed RMS `energy` on every audio frame;
 * createAudioManager forwards it to an optional UI subscriber via
 * setEnergyCallback, tagging each frame with whether it actually passed the send
 * gate (`sending`). This file drives a REAL createAudioManager with minimal
 * AudioContext / AudioWorkletNode stubs so we can fire synthetic worklet messages
 * and assert the callback fires with the right (energy, sending) per mode -- the
 * wiring is what could regress; the gate decision itself is covered by
 * audioGate.test.ts.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createAudioManager } from './audioManager'

// --- Minimal Web Audio stubs -------------------------------------------------
// Capture the worklet node so the test can fire port.onmessage by hand.
let lastWorkletNode: FakeWorkletNode | null = null

class FakePort {
  onmessage: ((e: MessageEvent) => void) | null = null
  postMessage = vi.fn()
  close = vi.fn()
}

class FakeWorkletNode {
  port = new FakePort()
  connect = vi.fn()
  disconnect = vi.fn()
  constructor() {
    lastWorkletNode = this
  }
}

class FakeAudioContext {
  state = 'running'
  destination = {}
  audioWorklet = { addModule: vi.fn(async () => {}) }
  createMediaStreamSource = vi.fn(() => ({ connect: vi.fn() }))
  resume = vi.fn(async () => {})
  close = vi.fn()
}

function fireFrame(energy: unknown, pcm: Int16Array): void {
  lastWorkletNode?.port.onmessage?.({
    data: { type: 'audio', energy, pcmData: pcm.buffer },
  } as MessageEvent)
}

// A chunk with at least one non-zero sample (passes the "never send silence" skip).
const SIGNAL = Int16Array.from([0, 0, 1234, 0])
const SILENCE = new Int16Array(4) // all zero

describe('audioManager energy callback (bd polyglot-pdf-s3zv)', () => {
  beforeEach(() => {
    lastWorkletNode = null
    // Stub the Web Audio + mic APIs for the node test env via vi.stubGlobal -- a
    // plain `global.navigator = ...` THROWS under Node 24 / Vitest ESM, where
    // navigator/window are read-only accessors with no setter (Codex PR #203, P0).
    // vi.stubGlobal handles that and vi.unstubAllGlobals() restores in afterEach.
    vi.stubGlobal('AudioContext', FakeAudioContext)
    vi.stubGlobal('AudioWorkletNode', FakeWorkletNode)
    vi.stubGlobal('navigator', {
      mediaDevices: { getUserMedia: vi.fn(async () => ({ id: 'fake-stream' })) },
    })
    vi.stubGlobal('window', {
      location: { hostname: 'localhost', href: 'http://localhost/' },
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  async function startedManager() {
    // Pass an existing stream so getUserMedia isn't required and the manager is
    // ready immediately.
    const mgr = createAudioManager({ id: 'fake' } as unknown as MediaStream)
    await mgr.startRecording(vi.fn())
    return mgr
  }

  it('forwards worklet energy to the subscriber on a SENT frame (PTT held)', async () => {
    const mgr = await startedManager()
    const onEnergy = vi.fn()
    mgr.setEnergyCallback(onEnergy)
    // Open the gate the only way there is now: PTT held (bd polyglot-pdf-v1m8g).
    // setVADActive no longer opens it -- client Silero VAD does not gate audio
    // under push-to-talk.
    mgr.setPTTMode(true)
    mgr.unmuteInput()

    fireFrame(42, SIGNAL)

    expect(onEnergy).toHaveBeenCalledWith(42, true)
  })

  it('still reports energy with sending=false when the frame is GATED (VAD idle)', async () => {
    const mgr = await startedManager()
    const onEnergy = vi.fn()
    mgr.setEnergyCallback(onEnergy)
    // native off, PTT off, vadActive false -> shouldSendAudioChunk returns false,
    // so the frame is dropped but the mic is still alive: energy must report,
    // sending=false (this is the "mic alive but not sending" diagnostic).
    fireFrame(17, SIGNAL)

    expect(onEnergy).toHaveBeenCalledWith(17, false)
  })

  it('reports energy with sending=false on an all-silence frame (silence skip)', async () => {
    const mgr = await startedManager()
    const onEnergy = vi.fn()
    mgr.setEnergyCallback(onEnergy)
    mgr.setVADActive(true) // gate would pass, but the chunk is all zeros

    fireFrame(3, SILENCE)

    expect(onEnergy).toHaveBeenCalledWith(3, false)
  })

  it('PTT muted: reports energy with sending=false and forwards NOTHING', async () => {
    // The energy meter must still show the mic is alive while the gate withholds
    // -- that is how the UI tells "mic alive but gated" from "no mic". Under PTT
    // a released button DROPS the frame (nothing is forwarded).
    //
    // This replaces a native-VAD pair (bd polyglot-pdf-zivv) that asserted a
    // ZEROED frame was forwarded instead of nothing: that mode needed the stream
    // kept continuous or Gemini's VAD would never close the turn. With PTT owning
    // activation there is no such requirement (bd polyglot-pdf-v1m8g).
    const sent: ArrayBuffer[] = []
    const mgr = createAudioManager({ id: 'fake' } as unknown as MediaStream)
    await mgr.startRecording((data: ArrayBuffer) => { sent.push(data) })
    const onEnergy = vi.fn()
    mgr.setEnergyCallback(onEnergy)
    mgr.setPTTMode(true)
    mgr.muteInput() // button released

    fireFrame(7, SIGNAL) // real mic has signal, but the button is not held

    expect(onEnergy).toHaveBeenCalledWith(7, false)
    expect(sent).toHaveLength(0) // withheld -- the muted mic is never forwarded
  })

  it('PTT held (not muted): sends the REAL frame through, sending=true', async () => {
    const sent: ArrayBuffer[] = []
    const mgr = createAudioManager({ id: 'fake' } as unknown as MediaStream)
    await mgr.startRecording((data: ArrayBuffer) => { sent.push(data) })
    const onEnergy = vi.fn()
    mgr.setEnergyCallback(onEnergy)
    mgr.setPTTMode(true)
    mgr.unmuteInput() // button held

    fireFrame(9, SIGNAL)

    expect(onEnergy).toHaveBeenCalledWith(9, true)
    expect(sent).toHaveLength(1)
    const forwarded = new Int16Array(sent[0])
    expect(Array.from(forwarded)).toEqual(Array.from(SIGNAL)) // real mic, unchanged
  })

  it('does not throw when energy is missing/non-numeric, and skips the callback', async () => {
    const mgr = await startedManager()
    const onEnergy = vi.fn()
    mgr.setEnergyCallback(onEnergy)
    mgr.setVADActive(true)

    fireFrame(undefined, SIGNAL)
    fireFrame('loud' as unknown, SIGNAL)

    expect(onEnergy).not.toHaveBeenCalled()
  })

  it('unsubscribes when the callback is set to null', async () => {
    const mgr = await startedManager()
    const onEnergy = vi.fn()
    mgr.setEnergyCallback(onEnergy)
    // Open the gate so a frame actually flows (was setNativeVad before that mode
    // was retired, bd polyglot-pdf-v1m8g -- this test is about unsubscribing, not
    // about which gate is open).
    mgr.setPTTMode(true)
    mgr.unmuteInput()

    fireFrame(50, SIGNAL)
    expect(onEnergy).toHaveBeenCalledTimes(1)

    mgr.setEnergyCallback(null)
    fireFrame(60, SIGNAL)
    expect(onEnergy).toHaveBeenCalledTimes(1) // no new call after unsubscribe
  })
})
