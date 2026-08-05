/**
 * resetPlaybackClock vs flushAudioQueue (bd polyglot-pdf-s7uf).
 *
 * resetPlaybackClock is the drain for a Gemini `interrupted` event: it must
 * stop the scheduled sources and reset the playback clock WITHOUT setting
 * playbackBlocked -- the model is about to speak a NEW generation on the same
 * connection, and an unpaired block is the nm7z all-audio-killed trap.
 * flushAudioQueue (pause/section-switch) keeps its blocking behavior and
 * delegates the drain.
 *
 * The block flag is observed BEHAVIORALLY: playAudio discards chunks while
 * playbackBlocked is set, so "does a subsequent playAudio schedule a source"
 * is the ground truth.
 *
 * ASCII only. jsdom env (vite.config test.environment).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createAudioManager } from './audioManager'

class FakeSource {
  buffer: unknown = null
  startedAt: number | null = null
  connect = vi.fn()
  stop = vi.fn()
  disconnect = vi.fn()
  onended: (() => void) | null = null
  start(at: number) { this.startedAt = at }
}

class FakeAudioContext {
  static instances: FakeAudioContext[] = []
  state: 'running' | 'suspended' = 'running'
  currentTime = 0
  destination = {}
  sources: FakeSource[] = []
  constructor() { FakeAudioContext.instances.push(this) }
  createBuffer(_ch: number, len: number, _rate: number) {
    return { getChannelData: () => ({ set: () => {} }), length: len }
  }
  createBufferSource() {
    const s = new FakeSource()
    this.sources.push(s)
    return s
  }
  createAnalyser() {
    return {
      connect: vi.fn(),
      fftSize: 0,
      frequencyBinCount: 16,
      getByteTimeDomainData: vi.fn(),
    }
  }
  resume = vi.fn(async () => { this.state = 'running' })
  suspend = vi.fn(async () => { this.state = 'suspended' })
  close = vi.fn(async () => {})
}

// A PCM-ish chunk whose bytes do NOT read as base64 text (control chars), so
// decodeGeminiFrame passes it through as raw PCM16.
function pcmChunk(): ArrayBuffer {
  const b = new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8])
  return b.buffer
}

describe('audioManager resetPlaybackClock (bd polyglot-pdf-s7uf)', () => {
  beforeEach(() => {
    FakeAudioContext.instances = []
    ;(globalThis as any).AudioContext = FakeAudioContext
    ;(globalThis as any).window = (globalThis as any).window || globalThis
  })

  it('drains scheduled sources and does NOT block subsequent audio', async () => {
    const mgr = createAudioManager()
    await mgr.playAudio(pcmChunk())
    const ctx = FakeAudioContext.instances[0]
    expect(ctx.sources.length).toBe(1)

    mgr.resetPlaybackClock()
    expect(ctx.sources[0].stop).toHaveBeenCalled()

    // The critical contrast with flushAudioQueue: the NEXT generation's audio
    // must still schedule -- no playbackBlocked was set.
    await mgr.playAudio(pcmChunk())
    expect(ctx.sources.length).toBe(2)
  })

  it('resets the scheduling clock to now (no stale future cursor)', async () => {
    const mgr = createAudioManager()
    await mgr.playAudio(pcmChunk())
    const ctx = FakeAudioContext.instances[0]

    // Simulate time passing while a long backlog was queued, then interrupt.
    ctx.currentTime = 7
    mgr.resetPlaybackClock()

    await mgr.playAudio(pcmChunk())
    const next = ctx.sources[1]
    // Scheduled at ~now, not at the old accumulated cursor position.
    expect(next.startedAt).not.toBeNull()
    expect(next.startedAt as number).toBeGreaterThanOrEqual(7)
    expect(next.startedAt as number).toBeLessThan(8)
  })

  it('flushAudioQueue still BLOCKS until resumePlayback (delegation intact)', async () => {
    const mgr = createAudioManager()
    await mgr.playAudio(pcmChunk())
    const ctx = FakeAudioContext.instances[0]
    expect(ctx.sources.length).toBe(1)

    mgr.flushAudioQueue()
    expect(ctx.sources[0].stop).toHaveBeenCalled()

    // Blocked: chunk discarded, no new source.
    await mgr.playAudio(pcmChunk())
    expect(ctx.sources.length).toBe(1)

    // Paired unblock restores playback.
    mgr.resumePlayback()
    await mgr.playAudio(pcmChunk())
    expect(ctx.sources.length).toBe(2)
  })
})
