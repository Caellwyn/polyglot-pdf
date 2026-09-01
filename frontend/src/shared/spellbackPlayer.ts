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
 * STALE-ARRIVAL GUARDS (bd polyglot-pdf-kvrfq). Holding the tool response
 * open does NOT actually park the model: under user barge-in pressure the
 * native-audio model keeps emitting further name_spellback calls while
 * earlier ones are unanswered, and those queue behind the backend's blocked
 * receive loop (wire-verified 2026-08-26: ten calls on one field, each read
 * 3-9ms after the previous response). Unguarded, each queued call replayed a
 * full clip AND re-engaged the mic hold -- silencing an ACTIVE PTT press
 * mid-sentence, so the model never heard the user's answer and kept calling.
 * play() therefore refuses stale arrivals up front, before any hold/fetch:
 * - while the user is holding PTT (level check -- the press-edge interrupt
 *   alone cannot catch a request that ARRIVES mid-hold): ack 'interrupted';
 * - within PTT_INTERRUPT_COOLDOWN_MS of the last real PTT interrupt (or
 *   held-refusal): ack 'interrupted', draining a queued backlog in
 *   milliseconds instead of one full clip per call. Cooldown refusals do
 *   not refresh the window, so the drain always converges;
 * - for a value+language delivered within DELIVERED_DEDUP_WINDOW_MS: ack
 *   'delivered' (the user HAS heard it) -- covers any caller with no held/
 *   pressed signal to report. The window is deliberately tight
 *   so a genuine "read it again" (several seconds later) still plays.
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
// cap scales with the value. Generous on purpose: the plain-text Chirp3 clip
// (bd 44ywm) is far shorter than the SSML one this bound was sized against,
// so the headroom now covers a slow voice rather than a slow format.
const PLAYBACK_TIMEOUT_PER_CHAR_MS = 1500
const PLAYBACK_TIMEOUT_FLOOR_MS = 15000
// The CLIENT's whole call -- drain wait + fetch + playback -- must settle
// BEFORE the backend's 90s round-trip cap (request_coordinator.py
// SPELLBACK_ROUNDTRIP_TIMEOUT): once that fires, the model is released to
// speak while a still-held mic would gate the user's reply to silence (Opus
// round 2, bd polyglot-pdf-9pnd3). So the playback watchdog is budgeted
// against the time the call has ALREADY spent, capped at this total.
const CLIENT_TOTAL_BUDGET_MS = 80000
// The auth-token fetch is a network call (Firebase getIdToken) with no
// timeout of its own -- bound it so it cannot eat the client budget
// (Opus round 3, bd polyglot-pdf-tk62w).
const TOKEN_TIMEOUT_MS = 10000
// Stale-arrival guards (bd polyglot-pdf-kvrfq; rationale in the header).
// Cooldown: requests arriving this soon after a real PTT interrupt are stale
// queue-drain, not fresh intent -- long enough to outlast the backlog (the
// incident's queued calls arrived 3-250ms apart once refusals were instant),
// short enough that a deliberate post-interrupt "read it back" still plays.
export const PTT_INTERRUPT_COOLDOWN_MS = 5000
// Dedup: a value the user JUST fully heard is not replayed. Tight on purpose:
// a genuine "read that again" needs the user to speak and the model to call,
// which takes well past this window; the queued duplicates it kills arrive
// within milliseconds.
export const DELIVERED_DEDUP_WINDOW_MS = 3000

/**
 * The playback watchdog's cap for a call that has already spent `elapsedMs`:
 * value-proportional and never past the remaining client budget. NO floor --
 * the budget invariant (the client settles before the backend's 90s cap,
 * else the model is released while the mic is still held) beats letting a
 * degenerate late start play; an exhausted budget kills the clip at arm time
 * (Opus round 3, bd polyglot-pdf-tk62w: a min-floor applied after the clamp
 * silently broke the invariant once elapsed passed budget-minus-floor).
 * Exported for the budget-arithmetic test.
 */
export function computePlaybackCapMs(valueLength: number, elapsedMs: number): number {
  const proportional = Math.max(
    PLAYBACK_TIMEOUT_FLOOR_MS, valueLength * PLAYBACK_TIMEOUT_PER_CHAR_MS)
  const remaining = CLIENT_TOTAL_BUDGET_MS - elapsedMs
  return Math.max(0, Math.min(proportional, remaining))
}

export interface SpellbackPlayerDeps {
  getAudioManager: () => AudioManager | null
  getHttpBase: () => string
  getToken?: () => Promise<string | undefined>
  // Whether the user is holding push-to-talk RIGHT NOW (bd kvrfq). Absent
  // reads as never-held (the delivered-dedup guard covers that case).
  isPttHeld?: () => boolean
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
  /**
   * Fetch + play the clip for `value`, spoken in `language` (the session's
   * spoken-language name; undefined -> en-US server-side). Resolves, never
   * rejects.
   */
  play: (value: string, language?: string) => Promise<SpellbackPlaybackResult>
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
  // Stale-arrival guard state (bd kvrfq). null (not 0) so a fake clock that
  // starts near 0 cannot read an unset marker as "just interrupted".
  let lastPttInterruptAt: number | null = null
  let lastDelivered: { value: string; language: string | undefined; at: number } | null = null

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
      // Arm the post-interrupt cooldown (bd kvrfq): requests already queued
      // behind this round-trip must drain as instant refusals, not replays.
      lastPttInterruptAt = now()
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
      // Same cooldown arming as the mid-clip branch (bd kvrfq): a press in
      // the pre-playback window is just as much a user interrupt.
      lastPttInterruptAt = now()
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

  async function play(value: string, language?: string): Promise<SpellbackPlaybackResult> {
    const am = deps.getAudioManager()
    if (!am) return { status: 'error', reason: 'no_audio_manager' }
    if (value.length > SPELLBACK_MAX_CHARS) {
      return { status: 'error', reason: 'value_too_long' }
    }

    // Stale-arrival guards (bd kvrfq; rationale in the header). All three
    // run BEFORE the pre-emption below and BEFORE any mic hold, so a refused
    // request can neither kill a legitimately-playing clip nor steal an
    // active PTT press's audio.
    //
    // 1) Level check: the press-edge interrupt cannot catch a request that
    //    ARRIVES while the button is already down -- refuse it here. The
    //    refusal refreshes the cooldown (the user is audibly speaking at
    //    this instant, which is exactly what the cooldown marks), so the
    //    window effectively runs from the END of a long hold, not its press.
    if (deps.isPttHeld?.()) {
      lastPttInterruptAt = now()
      return { status: 'interrupted' }
    }
    // 2) Post-interrupt cooldown: drain queued stale calls as instant acks.
    //    Deliberately NOT refreshed by its own refusals, so the drain always
    //    converges ~PTT_INTERRUPT_COOLDOWN_MS after the user's last press.
    if (lastPttInterruptAt !== null &&
        now() - lastPttInterruptAt < PTT_INTERRUPT_COOLDOWN_MS) {
      return { status: 'interrupted' }
    }
    // 3) Delivered dedup: the user has ALREADY heard this exact value --
    //    'delivered' tells the model to wait for their yes/no, not replay.
    if (lastDelivered !== null &&
        lastDelivered.value === value &&
        lastDelivered.language === language &&
        now() - lastDelivered.at < DELIVERED_DEDUP_WINDOW_MS) {
      return { status: 'delivered' }
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
        // Race against a bound: getIdToken is a network call with no timeout
        // of its own, and every unbounded pre-playback phase is a hole in the
        // client-budget invariant (bd tk62w). Timeout -> proceed tokenless
        // (the request then 401s and maps to the error variant).
        //
        // The bound rides the same injectable `watchdog` seam the fetch abort
        // and playback timeout already use (bd polyglot-pdf-3o2uz), not a
        // bare sleep(): unlike those two, a bare setTimeout has no canceller,
        // so on the normal (fast) path where getToken() wins, the losing
        // timer used to survive uncancelled for the full 10s -- one dangling
        // timer per name_spellback call, worse under the tool's own retry
        // guidance. stopTokenWatchdog() clears it the instant getToken()
        // settles, matching the disposal the other two bounds already get.
        token = deps.getToken
          ? await new Promise<string | undefined>((resolve) => {
              let settled = false
              const settle = (v: string | undefined) => {
                if (!settled) {
                  settled = true
                  stopTokenWatchdog()
                  resolve(v)
                }
              }
              const stopTokenWatchdog = watchdog(TOKEN_TIMEOUT_MS, () => settle(undefined))
              deps.getToken!().then(settle, () => settle(undefined))
            })
          : undefined
      } catch {
        token = undefined
      }
      if (gen <= cancelledUpTo) return poisonResult()

      const fetchStart = now()
      let blob: Blob
      // AbortController (not AbortSignal.timeout, which is missing on older
      // mobile Safari -- bd tk62w: an unbounded fetch is a hole in the
      // client-budget invariant on exactly those browsers). The abort timer
      // rides the injectable watchdog seam.
      const controller = typeof AbortController !== 'undefined' ? new AbortController() : null
      const stopFetchWatchdog = watchdog(FETCH_TIMEOUT_MS, () => controller?.abort())
      try {
        const resp = await fetchImpl(deps.getHttpBase() + '/api/tts/spellback', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: 'Bearer ' + token } : {}),
          },
          body: JSON.stringify({ value, ...(language ? { language } : {}) }),
          ...(controller ? { signal: controller.signal } : {}),
        })
        if (!resp.ok) {
          return { status: 'error', reason: 'tts_http_' + resp.status }
        }
        blob = await resp.blob()
      } catch {
        return { status: 'error', reason: 'tts_fetch_failed' }
      } finally {
        stopFetchWatchdog()
      }
      const fetchMs = Math.round(now() - fetchStart)
      if (gen <= cancelledUpTo) return poisonResult()

      const url = makeClipUrl(blob)
      const audio = createAudio(url)
      // Route the clip through the playback graph so the avatar animates while
      // it speaks (bd polyglot-pdf-s1iex.4). Before this, a clip played on a
      // bare element bypassed the analyser AND never fired the vff* playback
      // globals, so Sol sat IDLE through every spell-back -- the state machine
      // was correct, it simply had no signal. Attaching AFTER the blob URL is
      // set matters: a cross-origin src would taint the element and Web Audio
      // would output silence.
      const releaseClip = deps.getAudioManager()?.attachClipElement?.(audio)
      const playStart = now()
      const playbackCapMs = computePlaybackCapMs(value.length, now() - callStart)
      let stopWatchdog: () => void = () => {}
      const outcome = await new Promise<'delivered' | 'interrupted' | 'error'>((resolve) => {
        let settled = false
        const settle = (o: 'delivered' | 'interrupted' | 'error') => {
          if (!settled) {
            settled = true
            // Release on EVERY settle path (ended, error, watchdog, PTT
            // interrupt, cancel), not just the happy one -- a leaked
            // attachment would strand Sol in `speaking` forever.
            releaseClip?.()
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
      if (outcome === 'delivered') {
        // Feed the dedup guard (bd kvrfq): a queued duplicate of THIS value
        // arriving within the window is acked 'delivered' instead of replayed.
        lastDelivered = { value, language, at: now() }
      }
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
