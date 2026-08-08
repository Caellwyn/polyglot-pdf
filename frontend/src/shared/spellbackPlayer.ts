/**
 * Deterministic spell-back clip player (bd polyglot-pdf-22h1f).
 *
 * Owns the client half of the name_spellback tool round-trip: wait for the
 * model's own audio to drain, fetch the letter-by-letter Cloud TTS clip of
 * the STORED value from POST /api/tts/spellback, hold the mic in every input
 * mode (audioManager.setSpellbackHold), play the clip BLOCKING, and resolve
 * with the outcome. The returned promise resolving is what releases the
 * model's pending tool response -- nothing reaches the model, in either
 * direction, until playback truly ends.
 *
 * Extracted from connection.ts (fresh-eyes round 2) so the timing-sensitive
 * state machine is unit-testable, and hardened against the two hazards that
 * review found:
 * - REENTRANCY: a second play() while a prior invocation is still in flight
 *   (the backend's 90s cap can fire while a hung fetch keeps the client call
 *   alive, and the tool's error guidance invites a retry). A new call
 *   PRE-EMPTS the old one, and a per-call generation guard keeps the stale
 *   call's cleanup from clearing the live call's state or releasing the mic
 *   hold mid-clip.
 * - CANCELLATION between awaits: cancel() (disconnect/pause teardown) marks
 *   the current generation cancelled, so a call parked on the fetch when the
 *   session tears down never goes on to play audio into a dead session.
 *
 * All environment touchpoints (fetch, Audio, blob URLs, clock, sleep) are
 * injectable for tests; production callers pass only the first three deps.
 */

import type { AudioManager } from './audioManager'
import type { SpellbackPlaybackResult } from '../webFormConnection'

// Mirrors the backend's MAX_SPELLBACK_CHARS (backend/services/spellback_tts.py):
// an over-length value is a mis-targeted call (an address, a narrative) --
// fail fast without the network round-trip.
export const SPELLBACK_MAX_CHARS = 60

// The name_spellback tool call can arrive while the model's framing sentence
// for the SAME generation is still streaming, so require a SUSTAINED quiet
// window on the playback queue before starting the clip. Bounded: on timeout
// we play anyway (a rare overlap beats wedging the round-trip).
const DRAIN_WAIT_CAP_MS = 8000
const DRAIN_QUIET_MS = 600
// Well under the backend's 90s round-trip cap, so a hung TTS fetch resolves
// to the error variant while the tool response can still carry it.
const FETCH_TIMEOUT_MS = 20000
// Playback watchdog (Opus cross-surface review, bd polyglot-pdf-fjb2k): an
// <audio> element that stalls without firing onended/onerror (an OS audio
// interruption on mobile is the real case) would otherwise gate the mic
// FOREVER -- and in open-mic mode there is no PTT press to release it. The
// cap scales with the value (a 60-char clip runs ~55s at the SSML pacing).
const PLAYBACK_TIMEOUT_PER_CHAR_MS = 1500
const PLAYBACK_TIMEOUT_FLOOR_MS = 15000
// The CLIENT's whole call -- drain wait + fetch + playback -- must settle
// BEFORE the backend's 90s round-trip cap (request_coordinator.py
// SPELLBACK_ROUNDTRIP_TIMEOUT): once that fires, the model is released to
// speak while a still-held mic would gate the user's reply to silence (Opus
// round 2, bd polyglot-pdf-9pnd3). So the playback watchdog is budgeted
// against the time the call has ALREADY spent, capped at this total.
const CLIENT_TOTAL_BUDGET_MS = 80000
// Never squeeze the watchdog below this -- a degenerate remaining-budget must
// still allow a short clip to finish rather than killing it at arm time.
const PLAYBACK_TIMEOUT_MIN_MS = 5000

/**
 * The playback watchdog's cap for a call that has already spent `elapsedMs`:
 * value-proportional, floored, and never past the remaining client budget.
 * Exported for the budget-arithmetic test (the whole point is the SUM stays
 * under the backend's 90s cap).
 */
export function computePlaybackCapMs(valueLength: number, elapsedMs: number): number {
  const proportional = Math.max(
    PLAYBACK_TIMEOUT_FLOOR_MS, valueLength * PLAYBACK_TIMEOUT_PER_CHAR_MS)
  const remaining = CLIENT_TOTAL_BUDGET_MS - elapsedMs
  return Math.max(PLAYBACK_TIMEOUT_MIN_MS, Math.min(proportional, remaining))
}

export interface SpellbackPlayerDeps {
  getAudioManager: () => AudioManager | null
  getHttpBase: () => string
  getToken?: () => Promise<string | undefined>
  // Test seams; production uses the defaults.
  fetchImpl?: typeof fetch
  createAudio?: (url: string) => HTMLAudioElement
  makeClipUrl?: (blob: Blob) => string
  revokeClipUrl?: (url: string) => void
  now?: () => number
  sleep?: (ms: number) => Promise<void>
  // Playback watchdog seam: schedule fn after ms, return a canceller.
  watchdog?: (ms: number, fn: () => void) => () => void
}

export interface SpellbackPlayer {
  /** Fetch + play the clip for `value`. Resolves, never rejects. */
  play: (value: string) => Promise<SpellbackPlaybackResult>
  /**
   * Teardown-path stop (disconnect/pause): stops any in-flight clip AND
   * poisons a call still parked on its fetch, resolving the round-trip as
   * the error variant. Safe to call when idle.
   */
  cancel: () => void
  /**
   * PTT-press interrupt: stops the clip, releases the mic hold FIRST so the
   * press's own audio flows, and resolves 'interrupted'. Returns whether a
   * clip was actually interrupted (false when idle).
   */
  interruptForPtt: () => boolean
  /** Whether a clip is currently audible (playback started, not settled). */
  isPlaying: () => boolean
}

export function createSpellbackPlayer(deps: SpellbackPlayerDeps): SpellbackPlayer {
  const fetchImpl = deps.fetchImpl ?? ((...a: Parameters<typeof fetch>) => fetch(...a))
  const createAudio = deps.createAudio ?? ((url: string) => new Audio(url))
  const makeClipUrl = deps.makeClipUrl ?? ((blob: Blob) => URL.createObjectURL(blob))
  const revokeClipUrl = deps.revokeClipUrl ?? ((url: string) => URL.revokeObjectURL(url))
  const now = deps.now ?? (() => performance.now())
  const sleep = deps.sleep ?? ((ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms)))
  const watchdog = deps.watchdog ?? ((ms: number, fn: () => void) => {
    const t = setTimeout(fn, ms)
    return () => clearTimeout(t)
  })

  // Monotonic call counter. The finally-cleanup and cancel() compare against
  // it so only the LIVE call can clear shared state or release the mic hold.
  let generation = 0
  // Generations <= this value are cancelled: a call parked on an await checks
  // after resuming and bails instead of playing into a dead/preempted session.
  let cancelledUpTo = 0
  // Generations <= this value were cancelled BY A PTT PRESS specifically, so
  // the parked call resolves the 'interrupted' variant (model: listen to the
  // user) rather than the error variant (fresh-eyes round 3: a press during
  // the drain-wait/fetch phase -- up to ~28s -- must win exactly like a press
  // mid-clip, not be silently swallowed).
  let interruptedUpTo = 0
  // Whether a play() call is anywhere in flight (pre-playback phases
  // included; activeResolve alone only covers audible playback).
  let callInFlight = false
  let activeAudio: HTMLAudioElement | null = null
  let activeResolve: ((o: 'delivered' | 'interrupted' | 'error') => void) | null = null

  function settleActive(outcome: 'interrupted' | 'error'): void {
    if (activeResolve) {
      activeAudio?.pause()
      activeResolve(outcome)
    }
  }

  function cancel(): void {
    cancelledUpTo = generation
    settleActive('error')
  }

  function interruptForPtt(): boolean {
    if (activeResolve) {
      activeAudio?.pause()
      // Release the hold BEFORE resolving so the press's own audio flows the
      // instant the user starts speaking; the live call's finally re-clearing
      // it is an idempotent no-op.
      deps.getAudioManager()?.setSpellbackHold(false)
      settleActive('interrupted')
      return true
    }
    if (callInFlight) {
      // Pre-playback window (drain-wait / token / fetch): nothing is audible
      // yet, but the mic hold is engaged and the round-trip is pending. The
      // press wins here too: release the hold NOW so the user's audio flows,
      // and poison the in-flight call so it resolves 'interrupted' when it
      // resumes instead of starting a clip over the user's speech.
      interruptedUpTo = generation
      cancelledUpTo = generation
      deps.getAudioManager()?.setSpellbackHold(false)
      return true
    }
    return false
  }

  function isPlaying(): boolean {
    return activeResolve !== null
  }

  async function waitForModelAudioDrain(am: AudioManager): Promise<void> {
    const deadline = now() + DRAIN_WAIT_CAP_MS
    let quietSince: number | null = null
    while (now() < deadline) {
      const b = am.getPlaybackBacklog()
      const quiet = b.activeSources === 0 && b.aheadSec <= 0.05
      if (quiet) {
        if (quietSince === null) quietSince = now()
        if (now() - quietSince >= DRAIN_QUIET_MS) return
      } else {
        quietSince = null
      }
      await sleep(100)
    }
  }

  async function play(value: string): Promise<SpellbackPlaybackResult> {
    const am = deps.getAudioManager()
    if (!am) return { status: 'error', reason: 'no_audio_manager' }
    if (value.length > SPELLBACK_MAX_CHARS) {
      return { status: 'error', reason: 'value_too_long' }
    }

    // A new call supersedes any in-flight one: settle the old round-trip as
    // an error (its tool response has almost certainly timed out server-side
    // already) and poison its pending awaits.
    if (callInFlight || activeResolve) {
      cancel()
    }
    const gen = ++generation
    callInFlight = true
    const callStart = now()
    // A parked call that was poisoned resolves 'interrupted' when the poison
    // came from a PTT press (the user is speaking -- the model must listen),
    // and the plain error variant otherwise (teardown / pre-emption).
    const poisonResult = (): SpellbackPlaybackResult =>
      gen <= interruptedUpTo
        ? { status: 'interrupted' }
        : { status: 'error', reason: 'cancelled' }

    am.setSpellbackHold(true)
    try {
      await waitForModelAudioDrain(am)
      if (gen <= cancelledUpTo) return poisonResult()

      let token: string | undefined
      try {
        token = deps.getToken ? await deps.getToken() : undefined
      } catch {
        token = undefined
      }
      if (gen <= cancelledUpTo) return poisonResult()

      const fetchStart = now()
      let blob: Blob
      try {
        const resp = await fetchImpl(deps.getHttpBase() + '/api/tts/spellback', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: 'Bearer ' + token } : {}),
          },
          body: JSON.stringify({ value }),
          // Guarded: AbortSignal.timeout is missing on older mobile Safari;
          // without it the fetch simply has no client-side timeout (the
          // backend's 90s cap still bounds the round-trip).
          signal:
            typeof AbortSignal !== 'undefined' && typeof AbortSignal.timeout === 'function'
              ? AbortSignal.timeout(FETCH_TIMEOUT_MS)
              : undefined,
        })
        if (!resp.ok) {
          return { status: 'error', reason: 'tts_http_' + resp.status }
        }
        blob = await resp.blob()
      } catch {
        return { status: 'error', reason: 'tts_fetch_failed' }
      }
      const fetchMs = Math.round(now() - fetchStart)
      if (gen <= cancelledUpTo) return poisonResult()

      const url = makeClipUrl(blob)
      const audio = createAudio(url)
      const playStart = now()
      const playbackCapMs = computePlaybackCapMs(value.length, now() - callStart)
      let stopWatchdog: () => void = () => {}
      const outcome = await new Promise<'delivered' | 'interrupted' | 'error'>((resolve) => {
        let settled = false
        const settle = (o: 'delivered' | 'interrupted' | 'error') => {
          if (!settled) {
            settled = true
            resolve(o)
          }
        }
        activeAudio = audio
        activeResolve = settle
        // Watchdog: a stalled element that never fires onended/onerror must
        // not gate the mic forever (bd polyglot-pdf-fjb2k).
        stopWatchdog = watchdog(playbackCapMs, () => {
          audio.pause()
          settle('error')
        })
        audio.onended = () => settle('delivered')
        audio.onerror = () => settle('error')
        audio.play().catch(() => settle('error'))
      })
      stopWatchdog()
      const playbackMs = Math.round(now() - playStart)
      revokeClipUrl(url)
      return { status: outcome, playback_ms: playbackMs, fetch_ms: fetchMs }
    } finally {
      // Generation guard (fresh-eyes round 2): a STALE call's cleanup must
      // not clear the live call's state or drop the mic hold mid-clip.
      if (gen === generation) {
        callInFlight = false
        activeAudio = null
        activeResolve = null
        deps.getAudioManager()?.setSpellbackHold(false)
      }
    }
  }

  return { play, cancel, interruptForPtt, isPlaying }
}
