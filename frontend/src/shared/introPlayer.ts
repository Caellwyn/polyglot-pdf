/**
 * Sol's scripted intro+disclaimer clip player (bd polyglot-pdf-s1iex.5).
 *
 * Fetches the synthesized clip from POST /api/tts/intro, plays it while the
 * disclaimer modal is up, and stops the instant the user clicks Agree. Unlike
 * the spell-back clip this runs with NO Gemini session behind it -- the whole
 * point of the epic's lifecycle change -- so it owns its own AudioContext
 * resume and cannot lean on a live connection for anything.
 *
 * Reuses the spell-back player's STRUCTURE deliberately (bd 22h1f's scar
 * tissue): a monotonic `generation` counter, `cancelledUpTo` poison marks so a
 * call parked on its fetch never plays into a dismissed modal, and fully
 * injectable environment seams. It does NOT reuse the spell-back TIMING model:
 * that budget exists because a Gemini tool round-trip is waiting on the far
 * side (80s client cap vs the backend's 90s). Nothing waits on this clip, so
 * the only bounds here are a generous fetch timeout and an onended/onerror
 * watchdog.
 *
 * THREE things this player must get right, each a measured trap:
 * - PLAY FROM THE FETCHED BLOB, never the Cloud Run URL. A cross-origin media
 *   element is CORS-tainted and Web Audio then outputs SILENCE with no error --
 *   killing the audio AND Sol's animation. (We fetch anyway for the auth
 *   header, so this costs nothing.)
 * - RESUME THE AUDIOCONTEXT INSIDE THE USER GESTURE. The clip starts from the
 *   language-pick tap; a context created later, off-gesture, may start
 *   suspended and never play.
 * - A COLD SYNTHESIS TAKES ~20 SECONDS (measured, bd s1iex.3: the backend
 *   cache is per-instance and Cloud Run scales to zero). The fetch timeout and
 *   the caller's loading state must both survive that, and `onFetchStart` lets
 *   the UI say something honest while it waits.
 *
 * The clip is cached in-memory per (language, formNumber) so "Listen Again"
 * replays instantly with no network round trip -- provably the same audio the
 * user just heard.
 */

import type { AudioManager } from './audioManager'

// A cold synthesis measured ~20s (bd s1iex.3), so this must clear it with
// room for a slow network on top. Nothing is waiting on this clip, so a
// generous bound costs only a longer worst-case spinner.
export const INTRO_FETCH_TIMEOUT_MS = 45000
// Playback watchdog: an <audio> element that stalls without firing
// onended/onerror would otherwise leave the modal's "playing" state stuck
// forever. The measured clip runs ~95s worst case (English 94.3s, German
// 120.2s), so this is sized for the longest language plus slack.
export const INTRO_PLAYBACK_TIMEOUT_MS = 180000
// The auth-token fetch is a network call with no timeout of its own.
const TOKEN_TIMEOUT_MS = 10000

export type IntroPlaybackStatus =
  | 'delivered'    // played to its natural end
  | 'stopped'      // Agree / teardown stopped it deliberately
  | 'blocked'      // autoplay refused -- the caller shows "tap to play"
  | 'error'        // fetch or playback failed

export interface IntroPlaybackResult {
  status: IntroPlaybackStatus
  /** Set on 'error' only, for the caller's diagnostics. Never user-facing. */
  reason?: string
}

export interface IntroPlayerDeps {
  getAudioManager: () => AudioManager | null
  getHttpBase: () => string
  getToken?: () => Promise<string | undefined>
  /** Fires when the network fetch starts, so the UI can show a loading state
   *  through a cold ~20s synthesis. Not fired on a cache hit. */
  onFetchStart?: () => void
  // Test seams; production uses the defaults.
  fetchImpl?: typeof fetch
  createAudio?: (url: string) => HTMLAudioElement
  makeClipUrl?: (blob: Blob) => string
  revokeClipUrl?: (url: string) => void
  watchdog?: (ms: number, fn: () => void) => () => void
}

export interface IntroPlayer {
  /**
   * Fetch (or reuse) and play the intro clip. Resolves, never rejects.
   * Call from inside the user gesture that opens the modal so the
   * AudioContext resume is allowed.
   */
  play: (language: string, formNumber: string) => Promise<IntroPlaybackResult>
  /**
   * Stop immediately -- Agree, or modal teardown. Poisons an in-flight fetch
   * so it never starts playing afterwards. Safe to call when idle.
   */
  stop: () => void
  /** Whether a clip is audible right now. */
  isPlaying: () => boolean
  /** Whether a clip for this key is already cached (Listen Again is instant). */
  isCached: (language: string, formNumber: string) => boolean
  /**
   * The hash of the exact script text the backend synthesized, taken from the
   * response's X-Intro-Script-Version header (bd polyglot-pdf-s1iex.7). The
   * acceptance record echoes this so the audit trail names WHICH text the user
   * agreed to. Undefined before any successful fetch, or if the header is
   * missing (an older backend, or CORS not exposing it).
   */
  scriptVersion: () => string | undefined
  /** Release cached blobs + object URLs. For unmount. */
  dispose: () => void
}

export function createIntroPlayer(deps: IntroPlayerDeps): IntroPlayer {
  const fetchImpl = deps.fetchImpl ?? ((...a: Parameters<typeof fetch>) => fetch(...a))
  const createAudio = deps.createAudio ?? ((url: string) => new Audio(url))
  const makeClipUrl = deps.makeClipUrl ?? ((blob: Blob) => URL.createObjectURL(blob))
  const revokeClipUrl = deps.revokeClipUrl ?? ((url: string) => URL.revokeObjectURL(url))
  const watchdog = deps.watchdog ?? ((ms: number, fn: () => void) => {
    const t = setTimeout(fn, ms)
    return () => clearTimeout(t)
  })

  // Monotonic call counter; generations <= cancelledUpTo are poisoned.
  let generation = 0
  let cancelledUpTo = 0
  let activeAudio: HTMLAudioElement | null = null
  let activeSettle: ((s: IntroPlaybackStatus) => void) | null = null
  let releaseClip: (() => void) | undefined

  // (language, formNumber) -> object URL. Cached so Listen Again replays with
  // no network round trip -- and provably the SAME bytes the user just heard.
  const clipUrls = new Map<string, string>()
  // Set from the response header; the backend owns the hash so the two cannot
  // drift into recording a version it never synthesized.
  let lastScriptVersion: string | undefined
  const cacheKey = (language: string, formNumber: string) =>
    `${language}|${formNumber}`

  function isPlaying(): boolean {
    return activeAudio !== null
  }

  function isCached(language: string, formNumber: string): boolean {
    return clipUrls.has(cacheKey(language, formNumber))
  }

  function stop(): void {
    cancelledUpTo = generation
    const audio = activeAudio
    const settle = activeSettle
    activeAudio = null
    activeSettle = null
    if (audio) {
      try {
        audio.pause()
      } catch {
        // Element already torn down -- nothing to stop.
      }
    }
    releaseClip?.()
    releaseClip = undefined
    settle?.('stopped')
  }

  function dispose(): void {
    stop()
    for (const url of clipUrls.values()) revokeClipUrl(url)
    clipUrls.clear()
  }

  async function fetchToken(): Promise<string | undefined> {
    if (!deps.getToken) return undefined
    return new Promise<string | undefined>((resolve) => {
      let settled = false
      const settle = (v: string | undefined) => {
        if (settled) return
        settled = true
        stopWatch()
        resolve(v)
      }
      const stopWatch = watchdog(TOKEN_TIMEOUT_MS, () => settle(undefined))
      deps.getToken!().then(settle, () => settle(undefined))
    })
  }

  async function play(
    language: string,
    formNumber: string,
  ): Promise<IntroPlaybackResult> {
    // A new call pre-empts any previous one, exactly like the spell-back
    // player: the modal reopening must not leave two clips talking.
    stop()
    const gen = ++generation
    const poisoned = () => gen <= cancelledUpTo

    const key = cacheKey(language, formNumber)
    let url = clipUrls.get(key)

    if (!url) {
      deps.onFetchStart?.()
      let blob: Blob
      try {
        const token = await fetchToken()
        if (poisoned()) return { status: 'stopped' }

        const stopFetchWatch = watchdog(INTRO_FETCH_TIMEOUT_MS, () => {
          // Poison this generation so the response, if it lands late, is
          // discarded rather than played into a modal the user has left.
          cancelledUpTo = Math.max(cancelledUpTo, gen)
        })
        try {
          const headers: Record<string, string> = {
            'Content-Type': 'application/json',
          }
          if (token) headers['Authorization'] = `Bearer ${token}`
          const resp = await fetchImpl(`${deps.getHttpBase()}/api/tts/intro`, {
            method: 'POST',
            headers,
            body: JSON.stringify({ language, form_number: formNumber }),
          })
          if (poisoned()) return { status: 'stopped' }
          if (!resp.ok) {
            // 503 = the backend flag is off (the ON/OFF skew quadrant): the
            // modal still shows its text and Agree still works. Silent, not
            // an error the user sees.
            return {
              status: 'error',
              reason: resp.status === 503 ? 'intro_disabled' : `http_${resp.status}`,
            }
          }
          lastScriptVersion =
            resp.headers.get('X-Intro-Script-Version') ?? lastScriptVersion
          blob = await resp.blob()
        } finally {
          stopFetchWatch()
        }
      } catch {
        return { status: 'error', reason: 'fetch_failed' }
      }
      if (poisoned()) return { status: 'stopped' }
      url = makeClipUrl(blob)
      clipUrls.set(key, url)
    }

    let audio: HTMLAudioElement
    try {
      audio = createAudio(url)
      // Route through the shared playback graph so Sol animates for the clip's
      // whole duration (bd polyglot-pdf-s1iex.4). Attach AFTER the blob URL is
      // set -- a cross-origin src would taint the element into silence.
      releaseClip = deps.getAudioManager()?.attachClipElement?.(audio)
    } catch {
      // `play()` promises it RESOLVES, never rejects (callers await it and
      // clear UI timers off that resolution). A synchronous throw here would
      // break that promise and strand the caller's loading state.
      releaseClip?.()
      releaseClip = undefined
      return { status: 'error', reason: 'audio_init_failed' }
    }

    return new Promise<IntroPlaybackResult>((resolve) => {
      let settled = false
      const settle = (status: IntroPlaybackStatus) => {
        if (settled) return
        settled = true
        stopPlaybackWatch()
        // Release on EVERY path (ended, error, watchdog, stop) -- a leaked
        // attachment would strand Sol in `speaking` forever.
        releaseClip?.()
        releaseClip = undefined
        if (activeAudio === audio) {
          activeAudio = null
          activeSettle = null
        }
        resolve({ status })
      }

      activeAudio = audio
      activeSettle = settle
      const stopPlaybackWatch = watchdog(INTRO_PLAYBACK_TIMEOUT_MS, () => {
        try {
          audio.pause()
        } catch {
          // Nothing to pause.
        }
        settle('error')
      })

      audio.onended = () => settle('delivered')
      audio.onerror = () => settle('error')
      audio.play().catch(() => {
        // Autoplay refused: a reload with the disclaimer unaccepted reopens
        // the modal with NO user gesture, and transient activation can expire
        // during a cold ~20s synthesis. The caller shows "tap to play" and
        // calls play() again from that tap -- the clip is cached by then, so
        // the retry is instant.
        settle('blocked')
      })
    })
  }

  return {
    play, stop, isPlaying, isCached, dispose,
    scriptVersion: () => lastScriptVersion,
  }
}
