/**
 * Intro clip player (bd polyglot-pdf-s1iex.5).
 *
 * Pins the bead's behavioral criteria: Agree stops the clip IMMEDIATELY (the
 * maintainer's decision, preserving bd zq9l), Listen Again replays the cached
 * blob with NO second network round trip, and the backend-flag-off skew
 * quadrant degrades quietly instead of breaking the modal.
 *
 * Every environment touchpoint is injected, so these drive the real state
 * machine with controllable fakes -- no network, no real audio. NOTE the
 * clock: unlike the spell-back player there is no drain-wait here, so no
 * advancing `now()` is needed (that frozen-clock trap wedged the runner on bd
 * s1iex.4 and is called out in docs/standards/testing.md).
 */

import { describe, it, expect, vi } from 'vitest'
import { createIntroPlayer } from './introPlayer'
import type { AudioManager } from './audioManager'

class FakeAudio {
  onended: (() => void) | null = null
  onerror: (() => void) | null = null
  play = vi.fn(async () => {})
  pause = vi.fn()
}

function harness(opts: {
  status?: number
  failPlay?: boolean
  onFetchStart?: () => void
} = {}) {
  const audios: FakeAudio[] = []
  const attached: HTMLAudioElement[] = []
  const releases: Array<ReturnType<typeof vi.fn>> = []
  const revoked: string[] = []
  let announce: (a: FakeAudio) => void = () => {}
  const firstAudio = new Promise<FakeAudio>(r => { announce = r })

  const am = {
    attachClipElement: vi.fn((el: HTMLAudioElement) => {
      attached.push(el)
      const release = vi.fn()
      releases.push(release)
      return release
    }),
  } as unknown as AudioManager

  const fetchImpl = vi.fn(async () => ({
    ok: (opts.status ?? 200) < 400,
    status: opts.status ?? 200,
    blob: async () => ({ size: 42 } as Blob),
  } as unknown as Response))

  let urlSeq = 0
  const player = createIntroPlayer({
    getAudioManager: () => am,
    getHttpBase: () => 'http://backend',
    getToken: async () => 'tok',
    onFetchStart: opts.onFetchStart,
    fetchImpl,
    createAudio: () => {
      const a = new FakeAudio()
      if (opts.failPlay) a.play = vi.fn(async () => { throw new Error('blocked') })
      audios.push(a)
      announce(a)
      return a as unknown as HTMLAudioElement
    },
    makeClipUrl: () => `blob:clip${++urlSeq}`,
    revokeClipUrl: (u: string) => { revoked.push(u) },
    watchdog: () => () => {},
  })
  return { player, audios, attached, releases, fetchImpl, firstAudio, revoked }
}

describe('introPlayer: Agree stops the clip (bd s1iex.5)', () => {
  it('stops audio immediately and resolves as stopped', async () => {
    const h = harness()
    const playing = h.player.play('English', 'I-90')
    const audio = await h.firstAudio
    expect(h.player.isPlaying()).toBe(true)

    h.player.stop()   // what Agree calls

    const result = await playing
    expect(result.status).toBe('stopped')
    expect(audio.pause).toHaveBeenCalled()
    expect(h.player.isPlaying()).toBe(false)
    // The avatar attachment is released, or Sol animates forever.
    expect(h.releases[0]).toHaveBeenCalled()
  })

  it('poisons an in-flight FETCH so a late clip never plays', async () => {
    // Agree during a cold ~20s synthesis must not be followed by audio
    // starting after the modal is gone.
    let releaseFetch: (r: Response) => void = () => {}
    const pending = new Promise<Response>(r => { releaseFetch = r })
    const h = harness()
    const player = createIntroPlayer({
      getAudioManager: () => ({ attachClipElement: () => () => {} } as unknown as AudioManager),
      getHttpBase: () => 'http://backend',
      fetchImpl: vi.fn(() => pending) as unknown as typeof fetch,
      createAudio: () => new FakeAudio() as unknown as HTMLAudioElement,
      makeClipUrl: () => 'blob:late',
      revokeClipUrl: () => {},
      watchdog: () => () => {},
    })
    const playing = player.play('English', 'I-90')
    player.stop()
    releaseFetch({
      ok: true, status: 200, blob: async () => ({ size: 9 } as Blob),
    } as unknown as Response)
    expect((await playing).status).toBe('stopped')
    expect(player.isPlaying()).toBe(false)
    void h
  })
})

describe('introPlayer: Listen Again replays the cached blob (bd s1iex.5)', () => {
  it('does not re-fetch on replay', async () => {
    const h = harness()
    const first = h.player.play('English', 'I-90')
    ;(await h.firstAudio).onended!()
    expect((await first).status).toBe('delivered')
    expect(h.fetchImpl).toHaveBeenCalledTimes(1)
    expect(h.player.isCached('English', 'I-90')).toBe(true)

    const replay = h.player.play('English', 'I-90')
    await vi.waitFor(() => expect(h.audios.length).toBe(2))
    h.audios[1].onended!()
    expect((await replay).status).toBe('delivered')
    // THE point of the cache: instant replay, provably the same audio.
    expect(h.fetchImpl).toHaveBeenCalledTimes(1)
  })

  it('fetches separately for a different language', async () => {
    const h = harness()
    const a = h.player.play('English', 'I-90')
    ;(await h.firstAudio).onended!()
    await a
    const b = h.player.play('Spanish', 'I-90')
    await vi.waitFor(() => expect(h.audios.length).toBe(2))
    h.audios[1].onended!()
    await b
    expect(h.fetchImpl).toHaveBeenCalledTimes(2)
  })
})

describe('introPlayer: failure modes degrade quietly (bd s1iex.5)', () => {
  it('reports intro_disabled on a 503 (the flag-skew quadrant)', async () => {
    // Frontend ON / backend OFF: no audio, but the modal still renders and
    // Agree still works. It must NOT fall back to the deleted read_disclaimer.
    const h = harness({ status: 503 })
    const result = await h.player.play('English', 'I-90')
    expect(result.status).toBe('error')
    expect(result.reason).toBe('intro_disabled')
    expect(h.player.isPlaying()).toBe(false)
  })

  it('reports blocked when autoplay is refused, so the UI can offer a tap', async () => {
    const h = harness({ failPlay: true })
    const result = await h.player.play('English', 'I-90')
    expect(result.status).toBe('blocked')
    // Cached despite the refusal, so the tap-to-play retry is instant.
    expect(h.player.isCached('English', 'I-90')).toBe(true)
    expect(h.releases[0]).toHaveBeenCalled()
  })

  it('signals fetch start so the UI can cover a ~20s cold synthesis', async () => {
    const onFetchStart = vi.fn()
    const h = harness({ onFetchStart })
    const p = h.player.play('English', 'I-90')
    ;(await h.firstAudio).onended!()
    await p
    expect(onFetchStart).toHaveBeenCalledTimes(1)
    // A cache hit is instant -- no spinner flash on replay.
    const replay = h.player.play('English', 'I-90')
    await vi.waitFor(() => expect(h.audios.length).toBe(2))
    h.audios[1].onended!()
    await replay
    expect(onFetchStart).toHaveBeenCalledTimes(1)
  })

  it('releases the avatar attachment on the error path too', async () => {
    const h = harness()
    const p = h.player.play('English', 'I-90')
    ;(await h.firstAudio).onerror!()
    expect((await p).status).toBe('error')
    expect(h.releases[0]).toHaveBeenCalled()
  })

  it('dispose revokes cached object URLs', async () => {
    const h = harness()
    const p = h.player.play('English', 'I-90')
    ;(await h.firstAudio).onended!()
    await p
    h.player.dispose()
    expect(h.revoked.length).toBe(1)
    expect(h.player.isCached('English', 'I-90')).toBe(false)
  })
})
