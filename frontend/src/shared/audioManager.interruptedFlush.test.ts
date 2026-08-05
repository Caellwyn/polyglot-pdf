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
  createBuffer(_ch: number, len: number, rate: number) {
    return {
      getChannelData: () => ({ set: () => {} }),
      length: len,
      duration: len / rate,
    }
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

// A chunk long enough to move the scheduling cursor by `seconds` of audio
// (PCM16 mono @ 24 kHz => 48000 bytes/second). First bytes are control chars
// so decodeGeminiFrame passes it through raw.
function pcmChunkSeconds(seconds: number): ArrayBuffer {
  const b = new Uint8Array(Math.round(seconds * 24000) * 2)
  b[0] = 1
  b[1] = 2
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
    // The cursor must ACCUMULATE past currentTime for this test to bite:
    // startAt = max(playbackTime, now + 0.01), so with a near-zero cursor the
    // now-term dominates and the reset is unobservable (the original form of
    // this test was vacuous -- Opus fresh-eyes gap 1). Three 1-second chunks
    // at currentTime=0 push the cursor to ~3s of queued backlog.
    const mgr = createAudioManager()
    await mgr.playAudio(pcmChunkSeconds(1))
    await mgr.playAudio(pcmChunkSeconds(1))
    await mgr.playAudio(pcmChunkSeconds(1))
    const ctx = FakeAudioContext.instances[0]
    expect(ctx.sources.length).toBe(3)
    // Backlog established: the third chunk is scheduled far in the future.
    expect(ctx.sources[2].startedAt as number).toBeGreaterThan(1.5)

    mgr.resetPlaybackClock()

    await mgr.playAudio(pcmChunkSeconds(1))
    const next = ctx.sources[3]
    // Scheduled at ~now (currentTime=0), NOT behind the dead ~3s backlog.
    expect(next.startedAt).not.toBeNull()
    expect(next.startedAt as number).toBeLessThan(1)
  })

  it('clears the tracked source array (a second drain does not re-stop old sources)', async () => {
    // Pins the activeAudioSources clear (Opus fresh-eyes gap 2): if the array
    // leaked, the SECOND drain would call stop() on the first source again.
    const mgr = createAudioManager()
    await mgr.playAudio(pcmChunk())
    const ctx = FakeAudioContext.instances[0]

    mgr.resetPlaybackClock()
    expect(ctx.sources[0].stop).toHaveBeenCalledTimes(1)

    await mgr.playAudio(pcmChunk())
    mgr.resetPlaybackClock()
    // First source stopped exactly once across BOTH drains; second stopped once.
    expect(ctx.sources[0].stop).toHaveBeenCalledTimes(1)
    expect(ctx.sources[1].stop).toHaveBeenCalledTimes(1)
    // And speaking state cleared by the drain.
    expect(mgr.isSpeaking()).toBe(false)
  })

  it('drops a chunk parked on the suspended-context resume when a drain intervenes', async () => {
    // The residual race (Opus fresh-eyes gap 3): a chunk awaiting ctx.resume()
    // when the drain lands belongs to the DEAD generation and must not
    // schedule after the drain returns.
    const mgr = createAudioManager()
    await mgr.playAudio(pcmChunk()) // creates the context
    const ctx = FakeAudioContext.instances[0]
    expect(ctx.sources.length).toBe(1)

    ctx.state = 'suspended'
    let releaseResume!: () => void
    ctx.resume = vi.fn(() => new Promise<void>((r) => {
      releaseResume = () => { ctx.state = 'running'; r() }
    }))

    const parked = mgr.playAudio(pcmChunk()) // parks on the resume() await
    mgr.resetPlaybackClock()                  // drain lands while parked
    releaseResume()
    await parked

    // The parked chunk was dropped -- no new source scheduled after the drain.
    expect(ctx.sources.length).toBe(1)

    // And a FRESH chunk (new generation) still plays normally afterward.
    await mgr.playAudio(pcmChunk())
    expect(ctx.sources.length).toBe(2)
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
