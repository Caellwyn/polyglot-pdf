/**
 * Tests for the spell-back mic hold in audioManager (bd polyglot-pdf-22h1f).
 *
 * While the deterministic letter-by-letter TTS clip plays, NOTHING from the
 * mic may reach the model, in ANY input mode -- otherwise the clip (or room
 * echo of it) can leak back in as user speech and trigger a turn. This mic
 * hold does NOT mean the model is parked, though (bd polyglot-pdf-kvrfq,
 * wire-verified 2026-08-26): under barge-in pressure the model can keep
 * emitting further name_spellback calls while earlier ones are unanswered,
 * queueing behind the in-flight round-trip (see
 * docs/components/voice-ai.md's name_spellback bullet). Two distinct
 * behaviors, one per streaming discipline:
 * - native VAD: the stream must stay CONTINUOUS, so a held frame is replaced
 *   with a zeroed buffer of the same length (the bd zivv silence pattern);
 * - manual/client-VAD modes: the stream is bursty anyway, so a held frame is
 *   simply dropped.
 * Releasing the hold restores normal flow (the PTT-interrupt path depends on
 * that: press releases the hold so the user's barge-in audio flows).
 *
 * Reuses the audioEnergyCallback.test.ts harness: a REAL createAudioManager
 * driven by synthetic worklet messages.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createAudioManager } from './audioManager'

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

function fireFrame(pcm: Int16Array): void {
  lastWorkletNode?.port.onmessage?.({
    data: { type: 'audio', energy: 25, pcmData: pcm.buffer },
  } as MessageEvent)
}

const SIGNAL = Int16Array.from([0, 0, 1234, 0])

function isAllZero(buf: ArrayBuffer): boolean {
  return new Int16Array(buf).every(v => v === 0)
}

describe('audioManager spell-back hold (bd polyglot-pdf-22h1f)', () => {
  beforeEach(() => {
    lastWorkletNode = null
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

  async function startedManager(sent: ArrayBuffer[]) {
    const mgr = createAudioManager({ id: 'fake' } as unknown as MediaStream)
    await mgr.startRecording((data: ArrayBuffer) => { sent.push(data) })
    return mgr
  }

  it('native VAD open mic: hold substitutes zeroed frames, release restores real audio', async () => {
    const sent: ArrayBuffer[] = []
    const mgr = await startedManager(sent)
    mgr.setNativeVad(true) // open mic: continuous ungated stream

    mgr.setSpellbackHold(true)
    fireFrame(SIGNAL)
    // The stream must stay alive (native VAD needs it) but carry NO mic audio.
    expect(sent).toHaveLength(1)
    expect(isAllZero(sent[0])).toBe(true)
    expect(sent[0].byteLength).toBe(SIGNAL.buffer.byteLength)

    mgr.setSpellbackHold(false)
    fireFrame(SIGNAL)
    expect(sent).toHaveLength(2)
    expect(isAllZero(sent[1])).toBe(false)
  })

  it('native VAD + PTT HELD (unmuted): hold still silences -- the clip must not leak in mid-hold', async () => {
    const sent: ArrayBuffer[] = []
    const mgr = await startedManager(sent)
    mgr.setNativeVad(true)
    mgr.setPTTMode(true)
    mgr.unmuteInput() // button held down

    mgr.setSpellbackHold(true)
    fireFrame(SIGNAL)
    expect(sent).toHaveLength(1)
    expect(isAllZero(sent[0])).toBe(true)
  })

  it('client-VAD mode: hold drops frames entirely, release restores flow', async () => {
    const sent: ArrayBuffer[] = []
    const mgr = await startedManager(sent)
    mgr.setVADActive(true) // client VAD says speech -- gate would pass

    mgr.setSpellbackHold(true)
    fireFrame(SIGNAL)
    expect(sent).toHaveLength(0) // bursty mode: dropped, not silence-substituted

    mgr.setSpellbackHold(false)
    fireFrame(SIGNAL)
    expect(sent).toHaveLength(1)
    expect(isAllZero(sent[0])).toBe(false)
  })
})
