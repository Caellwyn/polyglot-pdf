/**
 * Demo VAD Hook - Voice Activity Detection using @ricky0123/vad-react
 * 
 * This integrates the professional VAD library for speech detection.
 * The library handles all the complex VAD logic we were doing manually.
 * 
 * NOTE: This runs in parallel with the existing audio recording system.
 * The VAD library detects when to send activity_start/activity_end to Gemini,
 * while the existing audioManager continues to capture and send audio data.

 * Voice Activity Detection using Silero VAD
 * 
 * ISC License

Copyright (c) 2022-present ricky0123

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

---

The file silero_vad.onnx falls under the following license:

---

MIT License

Copyright (c) 2020-present Silero Team

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
 */

import { useRef, useEffect } from 'react'
import * as VAD from "@ricky0123/vad-react"

/**
 * Get VAD asset base URL (uses CDN for reliability)
 * CDN works for both dev and production (no CORS issues)
 */
function getVADAssetBase(): string {
	// Use CDN for both dev and production (reliable, no CORS issues)
	return 'https://cdn.jsdelivr.net/npm/@ricky0123/vad-web@0.0.28/dist/'
}

/**
 * Get ONNX Runtime WASM base URL (uses CDN for reliability)
 * CDN works for both dev and production (no CORS issues)
 */
function getORTAssetBase(): string {
	// Use CDN for both dev and production (reliable, no CORS issues)
	return 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.23.0/dist/'
}

const VAD_ASSET_BASE = getVADAssetBase()
const ORT_ASSET_BASE = getORTAssetBase()

/**
 * Default VAD configuration values
 * These represent the production-tuned settings after optimization
 * Export for use in vad-tuning dashboard as baseline
 */
export const DEFAULT_VAD_CONFIG = {
	positiveSpeechThreshold: 0.85,
	negativeSpeechThreshold: 0.65,
	minSpeechMs: 250,
	redemptionMs: 400,
} as const

export interface VADCallbacks {
	onSpeechStart?: () => void
	onSpeechEnd?: (audio: Float32Array) => void
	onVADMisfire?: () => void
	/** NEW: Called on every audio frame with VAD probability score (0.0 - 1.0) */
	onFrameProcessed?: (probability: number, frame: Float32Array) => void
}

export interface VADOptions {
	callbacks?: VADCallbacks
	/** Optional shared stream from audioManager (prevents duplicate getUserMedia calls) */
	sharedStream?: MediaStream | null
	/** Optional VAD sensitivity overrides - if omitted, sensible defaults are used */
	sensitivity?: {
		positiveSpeechThreshold?: number
		negativeSpeechThreshold?: number
		minSpeechMs?: number
		redemptionMs?: number
	}
}

export interface DemoVAD {
	userSpeaking: boolean
	loading: boolean
	errored: string | false
	pause: () => void
	start: () => void
}

/**
 * Hook for voice activity detection in the demo
 * 
 * Uses @ricky0123/vad-react for professional VAD.
 * 
 * Configuration:
 * - positiveSpeechThreshold: Confidence needed to start speech (0.9 = 90%)
 * - negativeSpeechThreshold: Hysteresis threshold to end speech (0.65 = 65%) 
 * - minSpeechMs: Minimum duration to confirm speech (100ms prevents TTS bleed)
 * - redemptionMs: Grace period before ending speech (300ms prevents choppy cutoffs)
 * - sharedStream: Optional stream from audioManager (CRITICAL for echo prevention!)
 * 
 * IMPORTANT: If sharedStream is provided, VAD will use that instead of creating
 * a new getUserMedia() call. This is essential for echo cancellation to work properly.
 */
export function useDemoVAD(options?: VADOptions): DemoVAD {
	const callbacks = options?.callbacks
	const sharedStream = options?.sharedStream
	const sensitivity = options?.sensitivity || {}

	// CRITICAL: Store stream in a ref so getStream can access the LATEST value
	// even after the component updates with a new stream
	const streamRef = useRef<MediaStream | null | undefined>(sharedStream)

	// Update ref whenever sharedStream changes
	useEffect(() => {
		streamRef.current = sharedStream
		console.log('[useDemoVAD] Stream updated:', !!sharedStream)
	}, [sharedStream])

	const vad = VAD.useMicVAD({
		// Don't start automatically - wait for user to click "Connect"
		startOnLoad: false,

		// Serve model + worklet assets from self-hosted location (faster, more reliable)
		baseAssetPath: VAD_ASSET_BASE,
		onnxWASMBasePath: ORT_ASSET_BASE,

		// Browser-level audio processing (matches recording stream settings)
		// These constraints ensure consistency with the recording system
		// and prevent Gemini's voice from triggering false VAD events
		// 
		// CRITICAL: Use a dynamic getter that reads from streamRef to get the
		// LATEST stream value, not the value captured at hook initialization.
		// This ensures VAD uses the shared stream created by the dashboard.
		getStream: async () => {
			console.log('[useDemoVAD] getStream called, streamRef.current:', !!streamRef.current)
			if (streamRef.current) {
				console.log('[useDemoVAD] Using shared stream')
				return streamRef.current
			}
			console.log('[useDemoVAD] Creating new stream')
			return await navigator.mediaDevices.getUserMedia({
				audio: {
					echoCancellation: true,      // Browser AEC prevents echo feedback
					noiseSuppression: true,       // Reduces background noise
					autoGainControl: true,        // Normalizes microphone volume
					channelCount: 1,              // Mono audio (matches recording)
				},
			})
		},

		// VAD sensitivity tuning (Phase 1 optimization)
		// Higher threshold = less sensitive (fewer false positives from echo)
		// Lower threshold = more sensitive (catches quiet speech)
		// Allow overrides from options.sensitivity for live tuning during tests.
		// Use safer, more permissive defaults here to make it easier to get started
		// during manual testing. Users can tighten these later via the dashboard.
		// FIX #1 (Oct 22, 2025): Lowered from 0.98/0.85 to 0.90/0.70
		// Previous values were too aggressive, causing speech clipping and missed words
		// 0.85 = 85% confidence (standard threshold, balances accuracy vs false positives)
		// 0.65 = 65% to end (better hysteresis, prevents choppy cutoffs)
		positiveSpeechThreshold: sensitivity.positiveSpeechThreshold ?? DEFAULT_VAD_CONFIG.positiveSpeechThreshold,
		negativeSpeechThreshold: sensitivity.negativeSpeechThreshold ?? DEFAULT_VAD_CONFIG.negativeSpeechThreshold,

		// Timing parameters
		minSpeechMs: sensitivity.minSpeechMs ?? DEFAULT_VAD_CONFIG.minSpeechMs,
		redemptionMs: sensitivity.redemptionMs ?? DEFAULT_VAD_CONFIG.redemptionMs,

		// Model files - use default CDN (library will handle this automatically)
		// The library uses jsdelivr CDN by default for model files

		// Callbacks
		onSpeechStart: () => {
			callbacks?.onSpeechStart?.()
		},

		onSpeechEnd: (audio) => {
			callbacks?.onSpeechEnd?.(audio)
		},

		onVADMisfire: () => {
			callbacks?.onVADMisfire?.()
		},

		onFrameProcessed: (probabilities, frame) => {
			// probabilities is an object with { isSpeech: number } where isSpeech is 0.0-1.0
			const probability = probabilities.isSpeech
			callbacks?.onFrameProcessed?.(probability, frame)
		},
	})

	// Expose simplified interface
	return {
		userSpeaking: vad.userSpeaking,
		loading: vad.loading,
		errored: vad.errored,
		pause: vad.pause,
		start: vad.start,
	}
}
