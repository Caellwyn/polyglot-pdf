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
 * (`tests/e2e/voice-harness/harness.js`) installs its own
 * `vffOnAudioPlaybackEnd` subscriber to detect turn end, and itself
 * chains-and-restores. Overwriting instead of chaining here would silently break
 * the harness's turn detection; dropping the restore would break it after the
 * first desktop<->mobile breakpoint remount.
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
		// reconnect -- which would leave Sol permanently "speaking" with a flat,
		// zero-amplitude halo.
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
