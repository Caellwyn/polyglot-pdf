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
import {
  computePlaybackCapMs,
  createSpellbackPlayer,
  DELIVERED_DEDUP_WINDOW_MS,
  PTT_INTERRUPT_COOLDOWN_MS,
  SPELLBACK_MAX_CHARS,
} from './spellbackPlayer'
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
  /** Jump the fake clock forward (bd kvrfq: crossing guard windows). */
  advance: (ms: number) => void
}

function makePlayer(overrides: {
  fetchImpl?: (...a: any[]) => Promise<Response>
  am?: AudioManager | null
  watchdogs?: Array<{ ms: number; fn: () => void; cancel: ReturnType<typeof vi.fn> }>
  getToken?: () => Promise<string | undefined>
  isPttHeld?: () => boolean
} = {}): Harness {
  const holdLog: boolean[] = []
  const audios: FakeAudio[] = []
  let clock = 0
  const fetchImpl = vi.fn(overrides.fetchImpl ?? (async () => okResponse()))
  const am = overrides.am === undefined ? fakeAudioManager(holdLog) : overrides.am
  const player = createSpellbackPlayer({
    ...(overrides.watchdogs
      ? {
          watchdog: (ms: number, fn: () => void) => {
            const cancel = vi.fn()
            overrides.watchdogs!.push({ ms, fn, cancel })
            return cancel
          },
        }
      : {}),
    ...(overrides.getToken ? { getToken: overrides.getToken } : {}),
    ...(overrides.isPttHeld ? { isPttHeld: overrides.isPttHeld } : {}),
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
    // advance() adds a one-off jump on top (guard-window boundary tests).
    now: () => (clock += 1000),
    sleep: async () => {},
  })
  return { player, holdLog, audios, fetchImpl, advance: (ms: number) => { clock += ms } }
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
    const watchdogs: Array<{ ms: number; fn: () => void; cancel: ReturnType<typeof vi.fn> }> = []
    const { player, holdLog, audios } = makePlayer({ watchdogs })

    const done = player.play('NGUYEN')
    await settleMicrotasks()
    // Two watchdogs armed: the fetch abort timer, then the playback cap.
    expect(watchdogs).toHaveLength(2)
    expect(player.isPlaying()).toBe(true)

    // The element never fires onended/onerror (OS audio interruption). The
    // playback watchdog must stop it and resolve the error variant --
    // releasing the mic hold even with no PTT press available (open-mic mode).
    watchdogs[1].fn()
    const result = await done
    expect(result.status).toBe('error')
    expect(audios[0].pause).toHaveBeenCalled()
    expect(holdLog[holdLog.length - 1]).toBe(false)
    expect(player.isPlaying()).toBe(false)
  })

  it('token bound: a resolved getToken() clears its watchdog timer (bd polyglot-pdf-3o2uz)', async () => {
    // The regression: getToken() raced a bare, uncancellable sleep(). On the
    // normal (fast) path where getToken() wins, the losing timer survived
    // uncancelled for the full 10s -- one dangling timer per call, unlike the
    // fetch-abort and playback bounds, which ARE disposed in a finally/settle.
    const watchdogs: Array<{ ms: number; fn: () => void; cancel: ReturnType<typeof vi.fn> }> = []
    const getToken = vi.fn(async () => 'tok-123')
    const { player, audios } = makePlayer({ watchdogs, getToken })

    const done = player.play('NGUYEN')
    await settleMicrotasks()
    audios[0]?.onended?.()
    await done

    // Three watchdogs total: the token bound (armed first), then the fetch
    // abort timer, then the playback cap.
    expect(watchdogs).toHaveLength(3)
    const tokenWatchdog = watchdogs[0]
    expect(tokenWatchdog.ms).toBe(10000) // TOKEN_TIMEOUT_MS
    // The whole point: the winning getToken() must have cleared ITS OWN
    // timer, not left it to fire 10s later into a completed call.
    expect(tokenWatchdog.cancel).toHaveBeenCalledTimes(1)
  })

  it('token bound: a timed-out getToken() proceeds tokenless without hanging (bd 3o2uz)', async () => {
    // The watchdog firing (not getToken() itself) must be what unblocks the
    // call -- confirms the bound is load-bearing, not just present.
    const watchdogs: Array<{ ms: number; fn: () => void; cancel: ReturnType<typeof vi.fn> }> = []
    let neverResolves: () => void = () => {}
    const getToken = vi.fn(() => new Promise<string | undefined>((_resolve) => {
      neverResolves = () => {} // deliberately never called
    }))
    const { player, audios, fetchImpl } = makePlayer({ watchdogs, getToken })
    void neverResolves

    const done = player.play('NGUYEN')
    await settleMicrotasks()
    expect(watchdogs).toHaveLength(1) // only the token watchdog so far -- fetch has not started
    expect(watchdogs[0].ms).toBe(10000)

    // Fire the token watchdog: the call must proceed (tokenless) into the
    // fetch phase rather than hanging forever on the unresolved getToken().
    watchdogs[0].fn()
    await settleMicrotasks()
    audios[0]?.onended?.()
    await done

    expect(fetchImpl).toHaveBeenCalledTimes(1)
    const [, init] = fetchImpl.mock.calls[0]
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined()
  })

  it('client budget arithmetic: elapsed + watchdog cap NEVER exceeds the 80s client budget (bd 9pnd3/tk62w)', () => {
    // The invariant is unconditional (Opus round 3): whatever the call has
    // already spent -- including degenerate elapsed values past the budget --
    // the playback cap never lets the total pass the 80s client budget, which
    // sits under the backend's 90s SPELLBACK_ROUNDTRIP_TIMEOUT. A floor
    // applied after the clamp used to break this once elapsed passed
    // budget-minus-floor.
    const CLIENT_BUDGET_MS = 80000
    for (const elapsed of [0, 1000, 28000, 38000, 75000, 79000, 80000, 120000]) {
      for (let len = 1; len <= SPELLBACK_MAX_CHARS; len++) {
        const cap = computePlaybackCapMs(len, elapsed)
        expect(cap, `len=${len} elapsed=${elapsed}`).toBeLessThanOrEqual(
          Math.max(0, CLIENT_BUDGET_MS - elapsed))
        expect(cap).toBeGreaterThanOrEqual(0)
      }
    }
    // Worst REACHABLE pre-playback spend with every phase now bounded
    // (drain 8s + token 10s + fetch 20s = 38s) still leaves a real window.
    expect(computePlaybackCapMs(SPELLBACK_MAX_CHARS, 38000)).toBeGreaterThanOrEqual(42000 - 1)
    // And a fast call still gets a full value-proportional window.
    expect(computePlaybackCapMs(60, 1000)).toBeGreaterThanOrEqual(60000)
  })

  it('sends the session language in the TTS request body (bd 44ywm)', async () => {
    const { player, fetchImpl, audios } = makePlayer()

    const done = player.play('NGUYEN', 'Spanish')
    await settleMicrotasks()
    audios[0].onended?.()
    await done

    const [, init] = fetchImpl.mock.calls[0]
    expect(JSON.parse(init.body)).toEqual({ value: 'NGUYEN', language: 'Spanish' })

    // And omits the key entirely when no language is known.
    const p2 = makePlayer()
    const d2 = p2.player.play('NGUYEN')
    await settleMicrotasks()
    p2.audios[0].onended?.()
    await d2
    expect(JSON.parse(p2.fetchImpl.mock.calls[0][1].body)).toEqual({ value: 'NGUYEN' })
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

  // Stale-arrival guards (bd polyglot-pdf-kvrfq). Wire-verified incident
  // 2026-08-26: the model does NOT stay parked on the held-open tool
  // response -- it queued ten name_spellback calls on one field behind the
  // blocked backend receive loop, and each unguarded arrival replayed a
  // full clip and re-engaged the mic hold OVER the user's active PTT press.
  describe('stale-arrival guards (bd polyglot-pdf-kvrfq)', () => {
    it('a request arriving while PTT is held is refused: no fetch, no clip, and the mic hold is NEVER engaged', async () => {
      const { player, holdLog, audios, fetchImpl } = makePlayer({ isPttHeld: () => true })

      const result = await player.play('NGUYEN')

      expect(result).toEqual({ status: 'interrupted' })
      expect(fetchImpl).not.toHaveBeenCalled()
      expect(audios).toHaveLength(0)
      // The pinned invariant: the spell-back hold must never engage while
      // the user is holding PTT (the worklet gate would silence their own
      // press mid-sentence).
      expect(holdLog).toEqual([])
    })

    it('a held-arrival refusal cannot pre-empt a clip that is already playing', async () => {
      let held = false
      const { player, audios, fetchImpl } = makePlayer({ isPttHeld: () => held })

      const first = player.play('NGUYEN') // starts while NOT held
      await settleMicrotasks()
      expect(player.isPlaying()).toBe(true)

      // The press lands, and a stale queued request races in behind it
      // BEFORE the press-edge interrupt is delivered: the refusal must not
      // cancel the live clip (guards run ahead of the pre-emption).
      held = true
      const second = await player.play('NGUYEN')
      expect(second).toEqual({ status: 'interrupted' })
      expect(player.isPlaying()).toBe(true)
      expect(audios).toHaveLength(1)
      expect(fetchImpl).toHaveBeenCalledTimes(1)

      audios[0].onended?.()
      expect((await first).status).toBe('delivered')
    })

    it('a held-arrival arms the cooldown, so the guard covers the release tail of a long hold', async () => {
      let held = true
      const { player, fetchImpl } = makePlayer({ isPttHeld: () => held })

      expect((await player.play('NGUYEN')).status).toBe('interrupted')
      held = false // the user releases; queued stragglers keep arriving

      const result = await player.play('NGUYEN')
      expect(result).toEqual({ status: 'interrupted' })
      expect(fetchImpl).not.toHaveBeenCalled()
    })

    it('requests inside the post-interrupt cooldown are refused instantly; one after the window plays', async () => {
      const { player, holdLog, audios, fetchImpl, advance } = makePlayer()

      const first = player.play('NGUYEN')
      await settleMicrotasks()
      expect(player.interruptForPtt()).toBe(true)
      expect((await first).status).toBe('interrupted')

      // A queued stale call lands moments later: instant refusal, no fetch,
      // no new clip, no touch on the mic hold.
      const holdsBefore = holdLog.length
      const stale = await player.play('NGUYEN')
      expect(stale).toEqual({ status: 'interrupted' })
      expect(fetchImpl).toHaveBeenCalledTimes(1)
      expect(audios).toHaveLength(1)
      expect(holdLog.length).toBe(holdsBefore)

      // Past the window (plus slack for the fake clock's 1s-per-read tick),
      // a fresh request plays normally.
      advance(PTT_INTERRUPT_COOLDOWN_MS + 5000)
      const done = player.play('NGUYEN')
      await settleMicrotasks()
      expect(fetchImpl).toHaveBeenCalledTimes(2)
      audios[1].onended?.()
      expect((await done).status).toBe('delivered')
    })

    it('a PTT interrupt in the pre-playback (fetch) window arms the cooldown too', async () => {
      let releaseFetch: (r: Response) => void = () => {}
      let call = 0
      const { player, fetchImpl } = makePlayer({
        fetchImpl: () => {
          call += 1
          return call === 1
            ? new Promise<Response>(resolve => { releaseFetch = resolve })
            : Promise.resolve(okResponse())
        },
      })

      const first = player.play('NGUYEN')
      await settleMicrotasks()
      expect(player.interruptForPtt()).toBe(true) // press during the fetch
      releaseFetch(okResponse())
      expect((await first).status).toBe('interrupted')

      const stale = await player.play('NGUYEN')
      expect(stale).toEqual({ status: 'interrupted' })
      expect(fetchImpl).toHaveBeenCalledTimes(1)
    })

    it('cooldown refusals do NOT refresh the window, so a queued backlog always converges', async () => {
      const { player, audios, fetchImpl, advance } = makePlayer()

      const first = player.play('NGUYEN')
      await settleMicrotasks()
      expect(player.interruptForPtt()).toBe(true) // arms the cooldown: marker = T
      expect((await first).status).toBe('interrupted')

      // Tick accounting (the fake clock advances 1000 per now() read): the
      // settled first call reads once after the arming (T+1000), and each
      // refused play() reads exactly once (its cooldown check). So:
      //   B checks at T+2000 -> inside the 5000 window, refused;
      //   C checks at T+2000+1500+1000 = T+4500 -> LATE in the window, refused;
      //   D checks at T+4500+1000+1000 = T+6500 -> past the ORIGINAL window,
      //     plays. If refusals refreshed the marker (marker = T+4500), D's
      //     delta would be 2000 and it would wrongly be refused.
      // Refusals resolve instantly, so assert via the fetch count first --
      // a mis-predicted tick then fails fast instead of hanging on a clip.
      const b = player.play('NGUYEN')
      await settleMicrotasks()
      expect(fetchImpl).toHaveBeenCalledTimes(1)
      expect((await b).status).toBe('interrupted')

      advance(1500)
      const c = player.play('NGUYEN')
      await settleMicrotasks()
      expect(fetchImpl).toHaveBeenCalledTimes(1)
      expect((await c).status).toBe('interrupted')

      advance(1000)
      const done = player.play('NGUYEN')
      await settleMicrotasks()
      expect(fetchImpl).toHaveBeenCalledTimes(2)
      audios[audios.length - 1].onended?.()
      expect((await done).status).toBe('delivered')
    })

    it('a value just delivered is deduped to an instant delivered ack; a different value plays, and so does the same value after the window', async () => {
      const { player, audios, fetchImpl, advance } = makePlayer()

      const first = player.play('NGUYEN')
      await settleMicrotasks()
      audios[0].onended?.()
      expect((await first).status).toBe('delivered')

      // The queued duplicate: acked 'delivered' (the user HAS heard it),
      // nothing fetched, nothing replayed.
      const dup = await player.play('NGUYEN')
      expect(dup).toEqual({ status: 'delivered' })
      expect(fetchImpl).toHaveBeenCalledTimes(1)
      expect(audios).toHaveLength(1)

      // A DIFFERENT value inside the window is a fresh request.
      const other = player.play('OKAFOR')
      await settleMicrotasks()
      expect(fetchImpl).toHaveBeenCalledTimes(2)
      audios[1].onended?.()
      expect((await other).status).toBe('delivered')

      // The same value again PAST the window is a deliberate re-read.
      advance(DELIVERED_DEDUP_WINDOW_MS + 5000)
      const reread = player.play('OKAFOR')
      await settleMicrotasks()
      expect(fetchImpl).toHaveBeenCalledTimes(3)
      audios[2].onended?.()
      expect((await reread).status).toBe('delivered')
    })

    it('delivered dedup is language-sensitive (a language switch re-plays)', async () => {
      const { player, audios, fetchImpl } = makePlayer()

      const first = player.play('NGUYEN', 'Spanish')
      await settleMicrotasks()
      audios[0].onended?.()
      expect((await first).status).toBe('delivered')

      const other = player.play('NGUYEN')
      await settleMicrotasks()
      expect(fetchImpl).toHaveBeenCalledTimes(2)
      audios[1].onended?.()
      expect((await other).status).toBe('delivered')
    })

    it('cancel() (teardown) does not arm the cooldown -- a fresh request after pause/unpause still plays', async () => {
      const { player, audios, fetchImpl } = makePlayer()

      const first = player.play('NGUYEN')
      await settleMicrotasks()
      player.cancel()
      expect((await first).status).toBe('error')

      const done = player.play('NGUYEN')
      await settleMicrotasks()
      expect(fetchImpl).toHaveBeenCalledTimes(2)
      audios[audios.length - 1].onended?.()
      expect((await done).status).toBe('delivered')
    })
  })
})
