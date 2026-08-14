/**
 * useGeminiSpeaking -- reactive "is the assistant talking right now?"
 * (bd polyglot-pdf-2p4y).
 *
 * Sol needs a speaking state, and until now nothing in the UI did: the audio
 * manager tracks `geminiIsSpeaking` internally and exposes `isSpeaking()`, but
 * that is a plain getter with no subscription, used only for barge-in logic.
 *
 * What DOES exist is a pair of global hooks the audio manager already fires --
 * `window.vffOnAudioPlaybackStart` on the first audio chunk of a turn and
 * `window.vffOnAudioPlaybackEnd` when the queue drains naturally (deliberately
 * NOT during a barge-in flush).
 *
 * This hook claims them, but CHAINS any handler that was already installed
 * rather than overwriting it, and restores the previous value on unmount.
 *
 * The chaining is LOAD-BEARING, not defensive: the E2E voice harness
 * (`tests/e2e/voice-harness/harness.js`, `waitForGeminiQuestion`) installs its
 * own `vffOnAudioPlaybackEnd` subscriber to detect turn end. Overwriting instead
 * of chaining here would silently break that turn detection.
 *
 * Note the restore is the SUBTLER half, and it cuts the other way: the harness
 * installs its handler while this hook is already mounted, so it captures OUR
 * handler as its `prev` and restores it in `finish()`. Our own cleanup, by
 * contrast, writes back whatever was installed at OUR mount time -- so an
 * unmount landing mid-`waitForGeminiQuestion` (a desktop<->mobile breakpoint
 * flip during a turn) would discard the harness's handler. Narrow, and the
 * harness self-restores on its own timeout, but it is the reason to leave the
 * chain-and-restore symmetry exactly as it is rather than "simplifying" either
 * half.
 *
 * A polled fallback covers the gap the events cannot: `flushAudioQueue()` on a
 * barge-in stops playback WITHOUT firing the end event (by design -- firing it
 * there would spam the watchdog), so a purely event-driven flag would stick
 * "speaking" on forever after the user interrupts. Polling isSpeaking() at a
 * lazy 200ms only while we believe audio is playing costs nothing when idle and
 * closes that hole.
 */

import { useEffect, useState } from 'react'
import type { AudioManager } from './audioManager'

/** How often to reconcile against the audio manager while speaking. */
const RECONCILE_MS = 200

export function useGeminiSpeaking(audioManager: AudioManager | null | undefined): boolean {
	const [speaking, setSpeaking] = useState(false)

	useEffect(() => {
		// Chain, do not clobber -- see the note above.
		const prevStart = window.vffOnAudioPlaybackStart
		const prevEnd = window.vffOnAudioPlaybackEnd

		window.vffOnAudioPlaybackStart = () => {
			prevStart?.()
			setSpeaking(true)
		}
		window.vffOnAudioPlaybackEnd = () => {
			prevEnd?.()
			setSpeaking(false)
		}

		return () => {
			window.vffOnAudioPlaybackStart = prevStart
			window.vffOnAudioPlaybackEnd = prevEnd
		}
	}, [])

	// Barge-in safety net: a flush stops audio without an end event.
	useEffect(() => {
		if (!speaking) return
		// The manager went away (disconnect nulls it) while we believed audio was
		// playing. There is nothing left to reconcile against and no end event is
		// ever coming, so clear the flag rather than letting it stick true across a
		// reconnect -- which would leave Sol permanently "speaking" with flat,
		// zero-amplitude ray-breathing.
		if (!audioManager?.isSpeaking) {
			setSpeaking(false)
			return
		}
		const id = setInterval(() => {
			if (!audioManager.isSpeaking()) setSpeaking(false)
		}, RECONCILE_MS)
		return () => clearInterval(id)
	}, [speaking, audioManager])

	return speaking
}

/**
 * Reactive "is a synthesized CLIP audible right now?" (bd polyglot-pdf-s1iex.4).
 *
 * DELIBERATELY NARROWER than useGeminiSpeaking: that hook is true for the
 * model's own PCM too, and feeding it to `deriveSolState`'s `clipPlaying`
 * would animate Sol as `speaking` during `reconnecting` / `switching_section`
 * -- regressing the bd polyglot-pdf-bxng invariant that a live-but-transient
 * session stays visually distinct (measured: it did exactly that).
 *
 * A clip is the ONE case where audible speech legitimately has no live
 * session behind it, so only the clip-scoped flag may bypass the live gate.
 * The audio manager owns the ref-counted truth (`isClipPlaying()`); this
 * polls it on the same lazy cadence as the sibling hook rather than adding
 * another global, because clip start/end share the vff* events the sibling
 * already claims and a second claimant would have to re-solve the
 * chain-and-restore problem documented above.
 */
export function useClipPlaying(audioManager: AudioManager | null | undefined): boolean {
	const [clipPlaying, setClipPlaying] = useState(false)

	useEffect(() => {
		// Chain, do not clobber -- same rule as the sibling hook above.
		const prev = window.vffOnClipStateChange
		window.vffOnClipStateChange = (playing: boolean) => {
			prev?.(playing)
			setClipPlaying(playing)
		}
		return () => { window.vffOnClipStateChange = prev }
	}, [])

	useEffect(() => {
		if (!audioManager?.isClipPlaying) {
			setClipPlaying(false)
			return
		}
		// Safety net behind the event: reconciles a missed edge (a manager
		// swapped mid-clip, an unmount landing between attach and release) the
		// same way the sibling hook covers barge-in flushes.
		const id = setInterval(() => {
			setClipPlaying(audioManager.isClipPlaying())
		}, RECONCILE_MS)
		return () => clearInterval(id)
	}, [audioManager])

	return clipPlaying
}
