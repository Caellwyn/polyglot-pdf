/**
 * Sol animates for a synthesized clip's WHOLE duration (bd polyglot-pdf-s1iex.4).
 *
 * The defect this pins is shipped behavior: a clip played on a bare
 * HTMLAudioElement bypassed all three signals the avatar depends on --
 * `geminiIsSpeaking` (set only by playAudio), the AnalyserNode (on the playback
 * AudioContext an element bypasses), and the `vff*` playback globals (fired only
 * from the PCM path) -- so `deriveSolState` fell through to 'idle' and Sol sat
 * frozen through every spell-back clip. Nothing tested it.
 *
 * Three layers are pinned separately, because a fix at one layer alone leaves
 * the feature broken and any single-layer test would still pass:
 *   1. the audioManager splices the element into the playback graph and fires
 *      the start/end globals (the energy + event source);
 *   2. the spell-back player attaches on play and RELEASES on every settle
 *      path (a leaked attachment strands Sol in `speaking` forever);
 *   3. deriveSolState maps a playing clip to 'speaking' WITHOUT a live session
 *      (Sol's intro clip speaks before any session exists).
 */

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, it, expect, vi, afterEach } from 'vitest'
import { createSpellbackPlayer } from './spellbackPlayer'
import { deriveSolState } from './solState'
import { createAudioManager } from './audioManager'
import type { AudioManager } from './audioManager'

// --- Layer 1: the audioManager clip seam ----------------------------------

describe('audioManager.attachClipElement (bd s1iex.4)', () => {
  afterEach(() => {
    delete (window as any).vffOnAudioPlaybackStart
    delete (window as any).vffOnAudioPlaybackEnd
  })

  it('never throws into the caller and returns a callable release', () => {
    const am = createAudioManager()
    let release: (() => void) | undefined
    expect(() => { release = am.attachClipElement({} as HTMLAudioElement) })
      .not.toThrow()
    expect(typeof release).toBe('function')
    expect(() => release!()).not.toThrow()
    // Idempotent: onended and an explicit cancel can both fire.
    expect(() => release!()).not.toThrow()
  })

  it('is exposed on the manager interface', () => {
    // The seam bead s1iex.5's intro player will call. A rename or drop here
    // silently un-animates every clip, which is the defect this bead fixes.
    const am = createAudioManager()
    expect(typeof am.attachClipElement).toBe('function')
    expect(typeof am.isClipPlaying).toBe('function')
  })

  it('keeps the speaking flag while a clip plays, whatever the MODEL path does', () => {
    // The shared-flag invariant (fresh-eyes round 1). `geminiIsSpeaking` gates
    // getOutputEnergy, and FOUR code paths write it: the clip release, and
    // three model-audio paths (a PCM source ending, a playAudio error, and
    // resetPlaybackClock/flushAudioQueue). The clip's drain-wait is BOUNDED,
    // so a clip legitimately overlaps a model turn's tail -- and in
    // client-VAD mode a barge-in flush lands mid-clip. If any model-side
    // writer zeroes the flag while a clip is audible, Sol's state stays
    // 'speaking' but its amplitude flatlines for the rest of the clip.
    // jsdom has no Web Audio, so give attach a minimal context to splice
    // into -- without one it degrades to a no-op and never sets the flag,
    // which would make this test vacuous.
    const prevAC = (globalThis as any).AudioContext
    ;(globalThis as any).AudioContext = function () {
      return {
        state: 'running', currentTime: 0, destination: {},
        createAnalyser: () => ({ fftSize: 256, connect: () => {},
          getByteTimeDomainData: () => {} }),
        createMediaElementSource: () => ({ connect: () => {}, disconnect: () => {} }),
        resume: async () => {}, close: async () => {},
      }
    } as any
    const am = createAudioManager()
    const release = am.attachClipElement({} as HTMLAudioElement)
    try {
    expect(am.isSpeaking()).toBe(true)

    // The reachable model-side writers, driven through the PUBLIC surface.
    am.resetPlaybackClock()
    expect(am.isSpeaking()).toBe(true)   // clip still audible
    am.flushAudioQueue()
    expect(am.isSpeaking()).toBe(true)
    am.resumePlayback()
    expect(am.isSpeaking()).toBe(true)

    // Only the clip's OWN release ends it.
    release()
    expect(am.isSpeaking()).toBe(false)
    } finally {
      release()
      if (prevAC === undefined) delete (globalThis as any).AudioContext
      else (globalThis as any).AudioContext = prevAC
    }
  })

  it('lets the model path clear the flag normally when NO clip is playing', () => {
    // The other half: the gate must not strand `speaking` true after a
    // barge-in in the ordinary no-clip case.
    const am = createAudioManager()
    am.resetPlaybackClock()
    expect(am.isSpeaking()).toBe(false)
  })

  it('pins the COMPLETE set of geminiIsSpeaking clear-sites', () => {
    // Enumerate the set rather than trusting the three fixed sites (CLAUDE.md
    // scar #7): every `geminiIsSpeaking = false` in the module must be guarded
    // by an activeClipCount check, or a future writer silently reintroduces
    // the flatline. Read from source so a NEW unguarded writer fails here.
    // Resolve from THIS TEST FILE's own location, never process.cwd(): in
    // this repo a worktree vitest run is invoked from the MAIN checkout (the
    // node_modules junction workaround), so cwd points at main and a
    // cwd-relative read silently audits the WRONG copy -- it read 3 sites
    // while the branch had 4 (measured). vitest exposes the real path of the
    // running test file, which is always the copy under review.
    const here = expect.getState().testPath as string
    const src = readFileSync(resolve(here, '../audioManager.ts'), 'utf-8')
    const lines = src.split('\n')
    const clearSites = lines
      .map((line, i) => ({ line: line.trim(), i }))
      // Assignments only -- skip the `let geminiIsSpeaking = false` declaration.
      .filter(x => /^geminiIsSpeaking\s*=\s*false\b/.test(x.line))
    // 4 writers today: clip release, PCM onended, playAudio catch, reset.
    // A NEW clear-site (or a removed guard) fails this and must be reviewed
    // against the clip invariant rather than silently added.
    expect(clearSites.length).toBe(4)
    for (const site of clearSites) {
      // The guard sits within a few lines above each write.
      const window = lines.slice(Math.max(0, site.i - 6), site.i).join('\n')
      expect(window).toContain('activeClipCount')
    }
  })
})

// --- Layer 2: the spell-back player attaches + releases ----------------------

class FakeAudio {
  onended: (() => void) | null = null
  onerror: (() => void) | null = null
  play = vi.fn(async () => {})
  pause = vi.fn()
}

function playerHarness(opts: { failPlay?: boolean } = {}) {
  const attached: HTMLAudioElement[] = []
  const releases: Array<ReturnType<typeof vi.fn>> = []
  const audios: FakeAudio[] = []
  // The element is created deep inside play(); this resolves as soon as it
  // exists so a test can drive onended without polling (vi.waitFor against an
  // un-awaited promise deadlocks under this player's drain-wait).
  let announceAudio: (a: FakeAudio) => void = () => {}
  const firstAudio = new Promise<FakeAudio>(resolve => { announceAudio = resolve })
  let clock = 0

  const am = {
    setSpellbackHold: vi.fn(),
    getPlaybackBacklog: () => ({ aheadSec: 0, activeSources: 0, blocked: false }),
    attachClipElement: vi.fn((el: HTMLAudioElement) => {
      attached.push(el)
      const release = vi.fn()
      releases.push(release)
      return release
    }),
  } as unknown as AudioManager

  const player = createSpellbackPlayer({
    getAudioManager: () => am,
    getHttpBase: () => 'http://backend',
    fetchImpl: vi.fn(async () => ({
      ok: true, status: 200, blob: async () => ({ size: 3 } as Blob),
    } as unknown as Response)),
    createAudio: () => {
      const a = new FakeAudio()
      if (opts.failPlay) a.play = vi.fn(async () => { throw new Error('blocked') })
      audios.push(a)
      announceAudio(a)
      return a as unknown as HTMLAudioElement
    },
    makeClipUrl: () => 'blob:clip',
    revokeClipUrl: () => {},
    // The clock MUST advance: the pre-clip drain-wait returns only once the
    // backlog has been quiet for DRAIN_QUIET_MS, measured with now(). A
    // frozen clock spins that loop forever (measured: it wedges the vitest
    // worker rather than failing).
    now: () => (clock += 50),
    sleep: async () => {},
    watchdog: () => () => {},
  })
  return { player, attached, releases, audios, firstAudio }
}

describe('spellbackPlayer clip routing (bd s1iex.4)', () => {
  it('attaches the clip element and releases when it ends', async () => {
    const h = playerHarness()
    const done = h.player.play('JOSE')
    const audio = await h.firstAudio
    expect(h.attached.length).toBe(1)
    // Mid-clip: still attached, so Sol is still animating.
    expect(h.releases[0]).not.toHaveBeenCalled()
    audio.onended!()
    await done
    expect(h.releases[0]).toHaveBeenCalled()
  })

  it('releases when playback fails, not just on the happy path', async () => {
    // A leaked attachment on the error path would strand Sol in `speaking`.
    const h = playerHarness({ failPlay: true })
    await h.player.play('JOSE')
    expect(h.releases[0]).toHaveBeenCalled()
  })

  it('releases when a PTT press interrupts the clip', async () => {
    const h = playerHarness()
    const done = h.player.play('JOSE')
    await h.firstAudio
    h.player.interruptForPtt()
    await done
    expect(h.releases[0]).toHaveBeenCalled()
  })
})

// --- Layer 3: the state machine ---------------------------------------------

describe('deriveSolState with a clip playing (bd s1iex.4)', () => {
  it('is speaking for a clip even with NO live session', () => {
    // Sol's intro clip plays before any Gemini session exists -- the whole
    // point of the epic's lifecycle change.
    expect(deriveSolState({ status: 'Ready', clipPlaying: true })).toBe('speaking')
    expect(deriveSolState({ status: 'connecting', clipPlaying: true })).toBe('speaking')
  })

  it('is idle for the same status once the clip stops', () => {
    expect(deriveSolState({ status: 'Ready', clipPlaying: false })).toBe('idle')
    expect(deriveSolState({ status: 'Ready' })).toBe('idle')
  })

  it('still yields to paused and offline', () => {
    // A clip must never animate over an explicit pause or a broken session.
    expect(deriveSolState({ status: 'paused', clipPlaying: true })).toBe('paused')
    expect(deriveSolState({ status: 'disconnected', clipPlaying: true })).toBe('offline')
    expect(deriveSolState({ status: 'error', clipPlaying: true })).toBe('offline')
  })

  it('leaves the live-session paths unchanged', () => {
    expect(deriveSolState({ status: 'connected', speaking: true })).toBe('speaking')
    expect(deriveSolState({ status: 'connected', thinking: true })).toBe('thinking')
    expect(deriveSolState({ status: 'connected', micSending: true })).toBe('listening')
    // The pre-existing stale-flag guard survives: `speaking` alone, with no
    // session and no clip, is still not enough to animate.
    expect(deriveSolState({ status: 'Ready', speaking: true })).toBe('idle')
  })

  it('does NOT let a stale model-speaking flag animate a transient session', () => {
    // The bd polyglot-pdf-bxng invariant. This is the regression an earlier
    // revision of THIS bead shipped: the overlays passed the model's speaking
    // flag as `clipPlaying`, so every reconnect state rendered `speaking`
    // instead of `connecting`. Enumerated over the whole isConnecting set,
    // not one sample, so a future widening fails here.
    for (const status of ['reconnecting', 'reconnecting (2)', 'switching_section',
                          'connecting', 'warming up', 'Setting up audio...']) {
      expect(deriveSolState({ status, speaking: true })).toBe('connecting')
      expect(deriveSolState({ status, thinking: true })).toBe('connecting')
    }
  })

  it('animates a CLIP during those same transient states', () => {
    // The flip side, and why the two signals must stay distinct: a real clip
    // IS audible then (a spell-back can outlive a socket blip), so it should
    // animate -- which is exactly what the model's stale flag must not do.
    for (const status of ['reconnecting', 'switching_section', 'connecting']) {
      expect(deriveSolState({ status, clipPlaying: true })).toBe('speaking')
    }
  })
})
