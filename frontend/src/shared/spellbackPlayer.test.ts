/**
 * Tests for the deterministic spell-back clip player (bd polyglot-pdf-22h1f).
 *
 * This module owns the feature's core safety invariant -- the mic stays gated
 * for the WHOLE clip, in every input mode -- and the two hazards fresh-eyes
 * round 2 found in the pre-extraction implementation:
 * - a STALE call's cleanup clearing the LIVE call's state / releasing the mic
 *   hold mid-clip (reentrancy after a hung fetch + retry);
 * - a call parked on its fetch when the session tears down going on to play
 *   audio into a dead session.
 * Every environment touchpoint is injected, so these tests drive the real
 * state machine with controllable fakes.
 */

import { describe, it, expect, vi } from 'vitest'
import { computePlaybackCapMs, createSpellbackPlayer, SPELLBACK_MAX_CHARS } from './spellbackPlayer'
import type { AudioManager } from './audioManager'

class FakeAudio {
  onended: (() => void) | null = null
  onerror: (() => void) | null = null
  paused = false
  play = vi.fn(async () => {})
  pause = vi.fn(() => { this.paused = true })
}

function fakeAudioManager(holdLog: boolean[]): AudioManager {
  return {
    setSpellbackHold: (active: boolean) => { holdLog.push(active) },
    getPlaybackBacklog: () => ({ aheadSec: 0, activeSources: 0, blocked: false }),
  } as unknown as AudioManager
}

function okResponse(): Response {
  return {
    ok: true,
    status: 200,
    blob: async () => ({ size: 3 } as Blob),
  } as unknown as Response
}

interface Harness {
  player: ReturnType<typeof createSpellbackPlayer>
  holdLog: boolean[]
  audios: FakeAudio[]
  fetchImpl: ReturnType<typeof vi.fn>
}

function makePlayer(overrides: {
  fetchImpl?: (...a: any[]) => Promise<Response>
  am?: AudioManager | null
  watchdogs?: Array<() => void>
} = {}): Harness {
  const holdLog: boolean[] = []
  const audios: FakeAudio[] = []
  let clock = 0
  const fetchImpl = vi.fn(overrides.fetchImpl ?? (async () => okResponse()))
  const am = overrides.am === undefined ? fakeAudioManager(holdLog) : overrides.am
  const player = createSpellbackPlayer({
    ...(overrides.watchdogs
      ? {
          watchdog: (_ms: number, fn: () => void) => {
            overrides.watchdogs!.push(fn)
            return () => {}
          },
        }
      : {}),
    getAudioManager: () => am,
    getHttpBase: () => 'http://test',
    fetchImpl: fetchImpl as unknown as typeof fetch,
    createAudio: () => {
      const a = new FakeAudio()
      audios.push(a)
      return a as unknown as HTMLAudioElement
    },
    makeClipUrl: () => 'blob:fake',
    revokeClipUrl: () => {},
    // Fake monotonic clock: every read advances 1s, so the drain-wait's
    // sustained-quiet window passes immediately without real timers.
    now: () => (clock += 1000),
    sleep: async () => {},
  })
  return { player, holdLog, audios, fetchImpl }
}

async function settleMicrotasks(): Promise<void> {
  for (let i = 0; i < 10; i++) await Promise.resolve()
}

describe('spellbackPlayer (bd polyglot-pdf-22h1f)', () => {
  it('delivers: holds the mic for the whole clip, releases after onended', async () => {
    const { player, holdLog, audios } = makePlayer()

    const done = player.play('NGUYEN')
    await settleMicrotasks()
    expect(holdLog).toEqual([true]) // held before/during playback
    expect(player.isPlaying()).toBe(true)

    audios[0].onended?.()
    const result = await done
    expect(result.status).toBe('delivered')
    expect(typeof result.playback_ms).toBe('number')
    expect(typeof result.fetch_ms).toBe('number')
    expect(holdLog).toEqual([true, false]) // released exactly once, after end
    expect(player.isPlaying()).toBe(false)
  })

  it('PTT interrupt: releases the hold FIRST, resolves interrupted', async () => {
    const { player, holdLog, audios } = makePlayer()

    const done = player.play('NGUYEN')
    await settleMicrotasks()

    expect(player.interruptForPtt()).toBe(true)
    const result = await done
    expect(result.status).toBe('interrupted')
    expect(audios[0].pause).toHaveBeenCalled()
    // Hold released by the interrupt path (first false), then the finally's
    // idempotent re-release.
    expect(holdLog[0]).toBe(true)
    expect(holdLog).toContain(false)
    // Idle interrupt is a no-op.
    expect(player.interruptForPtt()).toBe(false)
  })

  it('cancel() mid-playback stops the clip and resolves the error variant', async () => {
    const { player, audios } = makePlayer()

    const done = player.play('NGUYEN')
    await settleMicrotasks()

    player.cancel()
    const result = await done
    expect(result.status).toBe('error')
    expect(audios[0].pause).toHaveBeenCalled()
  })

  it('cancel() while parked on the fetch keeps the clip from ever playing (teardown safety)', async () => {
    let releaseFetch: (r: Response) => void = () => {}
    const { player, audios } = makePlayer({
      fetchImpl: () => new Promise<Response>(resolve => { releaseFetch = resolve }),
    })

    const done = player.play('NGUYEN')
    await settleMicrotasks()
    player.cancel() // teardown lands while the fetch is in flight

    releaseFetch(okResponse())
    const result = await done
    expect(result.status).toBe('error')
    expect(result.reason).toBe('cancelled')
    expect(audios).toHaveLength(0) // no Audio element was ever created
  })

  it('REENTRANCY: a stale call cannot release the live call\'s mic hold (fresh-eyes round 2)', async () => {
    let releaseFirstFetch: (r: Response) => void = () => {}
    let call = 0
    const { player, holdLog, audios } = makePlayer({
      fetchImpl: () => {
        call += 1
        if (call === 1) {
          return new Promise<Response>(resolve => { releaseFirstFetch = resolve })
        }
        return Promise.resolve(okResponse())
      },
    })

    const first = player.play('NGUYEN') // hangs on its fetch
    await settleMicrotasks()
    const second = player.play('OKAFOR') // supersedes; fast fetch; clip starts
    await settleMicrotasks()
    expect(player.isPlaying()).toBe(true)

    // The hung first fetch finally resolves; its cleanup must NOT touch the
    // live second call's state or hold.
    releaseFirstFetch(okResponse())
    const firstResult = await first
    expect(firstResult.status).toBe('error')
    await settleMicrotasks()

    expect(player.isPlaying()).toBe(true) // second clip still live
    // Mic hold is still HELD: releases (false) never outnumber the live
    // call's holds while its clip plays.
    expect(holdLog[holdLog.length - 1]).not.toBe(false)

    // And the second clip still finishes normally.
    audios[audios.length - 1].onended?.()
    const secondResult = await second
    expect(secondResult.status).toBe('delivered')
  })

  it('PTT press during the FETCH phase wins: hold released now, call resolves interrupted, no clip (fresh-eyes round 3)', async () => {
    let releaseFetch: (r: Response) => void = () => {}
    const { player, holdLog, audios } = makePlayer({
      fetchImpl: () => new Promise<Response>(resolve => { releaseFetch = resolve }),
    })

    const done = player.play('NGUYEN')
    await settleMicrotasks()
    expect(holdLog).toEqual([true]) // hold engaged, nothing audible yet

    // The press lands in the pre-playback window (drain-wait/fetch): it must
    // NOT be swallowed -- the hold releases immediately so the press's audio
    // flows, and the parked call resolves the interrupted variant.
    expect(player.interruptForPtt()).toBe(true)
    expect(holdLog).toEqual([true, false])

    releaseFetch(okResponse())
    const result = await done
    expect(result.status).toBe('interrupted')
    expect(audios).toHaveLength(0) // the clip never started over the user

    // After everything settled, an idle press is a no-op again.
    expect(player.interruptForPtt()).toBe(false)
  })

  it('playback watchdog: a stalled audio element cannot gate the mic forever (bd fjb2k)', async () => {
    const watchdogs: Array<() => void> = []
    const { player, holdLog, audios } = makePlayer({ watchdogs })

    const done = player.play('NGUYEN')
    await settleMicrotasks()
    expect(watchdogs).toHaveLength(1) // armed alongside playback
    expect(player.isPlaying()).toBe(true)

    // The element never fires onended/onerror (OS audio interruption). The
    // watchdog must stop it and resolve the error variant -- releasing the
    // mic hold even with no PTT press available (open-mic mode).
    watchdogs[0]()
    const result = await done
    expect(result.status).toBe('error')
    expect(audios[0].pause).toHaveBeenCalled()
    expect(holdLog[holdLog.length - 1]).toBe(false)
    expect(player.isPlaying()).toBe(false)
  })

  it('client budget arithmetic: elapsed + watchdog cap stays under the backend 90s round-trip cap (bd 9pnd3)', () => {
    // Worst legitimate pre-playback spend: drain-wait cap (8s) + fetch
    // timeout (20s). For EVERY value length up to the cap, the client call
    // must settle before the backend's 90s SPELLBACK_ROUNDTRIP_TIMEOUT --
    // otherwise the model is released to speak while the mic is still held.
    const BACKEND_CAP_MS = 90000
    const WORST_PRE_PLAYBACK_MS = 8000 + 20000
    for (let len = 1; len <= SPELLBACK_MAX_CHARS; len++) {
      const cap = computePlaybackCapMs(len, WORST_PRE_PLAYBACK_MS)
      expect(WORST_PRE_PLAYBACK_MS + cap, `len=${len}`).toBeLessThan(BACKEND_CAP_MS)
    }
    // And a fast call still gets the full value-proportional window.
    expect(computePlaybackCapMs(60, 1000)).toBeGreaterThanOrEqual(60000)
  })

  it('fails fast on over-length values without fetching', async () => {
    const { player, fetchImpl } = makePlayer()
    const result = await player.play('x'.repeat(SPELLBACK_MAX_CHARS + 1))
    expect(result).toEqual({ status: 'error', reason: 'value_too_long' })
    expect(fetchImpl).not.toHaveBeenCalled()
  })

  it('maps a non-OK TTS response and a missing audio manager to error variants', async () => {
    const bad = makePlayer({
      fetchImpl: async () => ({ ok: false, status: 503 } as unknown as Response),
    })
    expect((await bad.player.play('NGUYEN')).reason).toBe('tts_http_503')

    const noAm = makePlayer({ am: null })
    expect((await noAm.player.play('NGUYEN')).reason).toBe('no_audio_manager')
  })
})
