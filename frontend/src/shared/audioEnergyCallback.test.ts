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
    // @ts-expect-error -- stub the Web Audio + mic APIs for the node test env
    global.AudioContext = FakeAudioContext
    // @ts-expect-error
    global.AudioWorkletNode = FakeWorkletNode
    global.navigator = global.navigator || ({} as Navigator)
    // @ts-expect-error -- jsdom navigator.mediaDevices is read-only/absent; stub it
    global.navigator.mediaDevices = {
      getUserMedia: vi.fn(async () => ({ id: 'fake-stream' })),
    }
    global.window = global.window || ({} as Window & typeof globalThis)
    // @ts-expect-error -- replace the read-only window.location with a minimal stub
    global.window.location = { hostname: 'localhost', href: 'http://localhost/' }
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  async function startedManager() {
    // Pass an existing stream so getUserMedia isn't required and the manager is
    // ready immediately.
    const mgr = createAudioManager({ id: 'fake' } as unknown as MediaStream)
    await mgr.startRecording(vi.fn())
    return mgr
  }

  it('forwards worklet energy to the subscriber on a SENT frame (client VAD active)', async () => {
    const mgr = await startedManager()
    const onEnergy = vi.fn()
    mgr.setEnergyCallback(onEnergy)
    // Default mode: native VAD off, PTT off. Activate client VAD so a signal frame
    // passes the gate.
    mgr.setVADActive(true)

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

  it('reports energy with sending=true in native-VAD mode (continuous stream)', async () => {
    const mgr = await startedManager()
    const onEnergy = vi.fn()
    mgr.setEnergyCallback(onEnergy)
    mgr.setNativeVad(true) // streams continuously, even silence

    fireFrame(8, SILENCE)

    expect(onEnergy).toHaveBeenCalledWith(8, true)
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
    mgr.setNativeVad(true)

    fireFrame(50, SIGNAL)
    expect(onEnergy).toHaveBeenCalledTimes(1)

    mgr.setEnergyCallback(null)
    fireFrame(60, SIGNAL)
    expect(onEnergy).toHaveBeenCalledTimes(1) // no new call after unsubscribe
  })
})
