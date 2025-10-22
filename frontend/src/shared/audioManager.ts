/**
 * Audio Manager - Microphone Recording & AI Audio Playback
 * 
 * Handles:
 * - Microphone permission and recording
 * - PCM16 conversion for Gemini (16kHz mono)
 * - AI audio playback (24kHz PCM16)
 * - Audio context lifecycle
 */

const RECORDING_SAMPLE_RATE = 16000 // Gemini input
const PLAYBACK_SAMPLE_RATE = 24000  // Gemini output

export interface AudioManager {
	startRecording: (onAudioData: (data: ArrayBuffer) => void) => Promise<void>
	stopRecording: () => void
	playAudio: (audioData: ArrayBuffer) => Promise<void>
	flushAudioQueue: () => void // Stop all queued audio immediately
	resumePlayback: () => void // Resume audio after barge-in
	isRecording: () => boolean
	isSpeaking: () => boolean // Is Gemini currently speaking?
	muteInput: () => void // Mute mic input (send silence)
	unmuteInput: () => void // Unmute mic input (send real audio)
	getStream: () => MediaStream | null // Get the active microphone stream (for sharing with VAD)
	setVADActive: (active: boolean) => void // Privacy gate: control audio flow based on VAD state
	destroy: () => void
}

interface AudioNodes {
	recordingContext: AudioContext | null
	playbackContext: AudioContext | null
	stream: MediaStream | null
	workletNode: AudioWorkletNode | null
	source: MediaStreamAudioSourceNode | null
}

/**
 * Create audio manager for bookmarklet
 * 
 * @param existingStream - Optional pre-created MediaStream to reuse (for sharing with VAD)
 *                         If provided, the manager won't create its own stream via getUserMedia
 */
export function createAudioManager(existingStream?: MediaStream): AudioManager {
	const nodes: AudioNodes = {
		recordingContext: null,
		playbackContext: null,
		stream: existingStream || null, // Use existing stream if provided
		workletNode: null,
		source: null,
	}

	let recording = false
	let playbackTime = 0
	let playbackChunkCount = 0 // Track playback chunks for debugging
	let onAudioDataCallback: ((data: ArrayBuffer) => void) | null = null
	let inputMuted = false // Track if input should be muted (send silence)

	// Privacy gate: VAD-controlled audio flow
	let vadActive = false // When false, don't send audio; when true, send real audio
	
	// Circular pre-buffer for speech start capture
	// Purpose: Captures audio BEFORE VAD detects speech to prevent clipping
	// Size must be >= minSpeechMs + redemptionMs from VAD config
	// Current VAD defaults: minSpeechMs=150ms, redemptionMs=300ms
	// Pre-buffer: 500ms = 150 + 300 + 50ms safety margin
	const PREBUFFER_DURATION_MS = 600
	const PREBUFFER_SIZE_SAMPLES = Math.ceil((PREBUFFER_DURATION_MS / 1000) * RECORDING_SAMPLE_RATE)
	const audioPreBuffer: Int16Array[] = [] // Rolling buffer of PCM16 chunks
	let preBufferSampleCount = 0 // Track total samples in buffer
	
	// Track active audio sources for flushing
	const activeAudioSources: AudioBufferSourceNode[] = []

	// Barge-in state: block new audio playback during user interruption
	let playbackBlocked = false

	// Flag to suppress onended callbacks during flush (prevents spurious watchdog triggers)
	let isFlushing = false

	// Track if Gemini is currently speaking (for barge-in detection)
	let geminiIsSpeaking = false

	/**
	 * Start recording audio from microphone
	 */
	async function startRecording(onAudioData: (data: ArrayBuffer) => void): Promise<void> {
		if (recording) {
			return
		}

		try {
			// Only create stream if we don't already have one (from constructor)
			if (!nodes.stream) {
				// Request microphone access with optimal settings
				// These match the VAD stream to ensure consistency
				nodes.stream = await navigator.mediaDevices.getUserMedia({
					audio: {
						channelCount: 1,
						sampleRate: RECORDING_SAMPLE_RATE,
						echoCancellation: true,      // Prevents Gemini's audio from being recorded
						noiseSuppression: true,       // Reduces background noise
						autoGainControl: true,        // Normalizes microphone volume
					},
				})
				console.log('[AudioManager] 🎤 Created new microphone stream')
			} else {
				console.log('[AudioManager] 🔗 Reusing existing microphone stream (shared with VAD)')
			}

			// FIX #5: AudioContext Pooling - reuse contexts instead of creating new ones
			// Browsers limit AudioContext instances (6-8 on desktop, 2-4 on mobile)
			// Creating new contexts on each startRecording() causes failures on reconnect
			if (!nodes.recordingContext) {
				console.log('[AudioManager] 🎵 Creating AudioContext for recording (first time)')
				nodes.recordingContext = new AudioContext({ sampleRate: RECORDING_SAMPLE_RATE })
			} else {
				console.log('[AudioManager] ♻️ Reusing existing recording AudioContext')
				// Resume if suspended (browsers may suspend contexts to save power)
				if (nodes.recordingContext.state === 'suspended') {
					await nodes.recordingContext.resume()
				}
			}

			nodes.source = nodes.recordingContext.createMediaStreamSource(nodes.stream)

			if (!nodes.playbackContext) {
				console.log('[AudioManager] 🎵 Creating AudioContext for playback (eager initialization)')
				nodes.playbackContext = new AudioContext({ sampleRate: PLAYBACK_SAMPLE_RATE })
				playbackTime = 0
			} else {
				console.log('[AudioManager] ♻️ Reusing existing playback AudioContext')
				// Resume if suspended
				if (nodes.playbackContext.state === 'suspended') {
					await nodes.playbackContext.resume()
				}
			}

		// Load AudioWorklet module
		// In production (deployed to GCS), worklet is at ../shared/ relative to demo/
		// In dev, use public directory path (worklet must be in public/shared/)
		const isProduction = !window.location.hostname.includes('localhost') && 
			!window.location.hostname.includes('127.0.0.1')
		
		const workletUrl = isProduction
			? new URL('../shared/audio-processor.worklet.js', window.location.href).href
			: '/shared/audio-processor.worklet.js'  // Served from public/ in dev
		
		console.log('[VFF Audio] Loading worklet from:', workletUrl)
		await nodes.recordingContext.audioWorklet.addModule(workletUrl)			// Create AudioWorklet node
			nodes.workletNode = new AudioWorkletNode(
				nodes.recordingContext,
				'voice-form-filler-audio-processor'
			)

			onAudioDataCallback = onAudioData

			// Handle messages from AudioWorklet
			nodes.workletNode.port.onmessage = (event: MessageEvent) => {
				if (!recording || !onAudioDataCallback) return

				const { type, pcmData } = event.data
				if (type !== 'audio') return

				// Privacy Gate: VAD-controlled audio flow with pre-buffering
				// When VAD inactive: DON'T send audio (Gemini's automatic VAD requires no keepalive)
				// When VAD active: send real audio
				// On transition to active: flush pre-buffer first (prevents speech clipping)

				const pcmChunk = new Int16Array(pcmData)

				// Always update pre-buffer with recent audio (rolling window)
				audioPreBuffer.push(pcmChunk)
				preBufferSampleCount += pcmChunk.length

				// Trim pre-buffer to maintain 600ms window
				while (preBufferSampleCount > PREBUFFER_SIZE_SAMPLES) {
					const removed = audioPreBuffer.shift()
					if (removed) {
						preBufferSampleCount -= removed.length
					}
				}

				// Determine what to send based on VAD state and mute status
				if (inputMuted) {
					// Push-to-talk mode: muted, send silence to keep connection alive
					const silenceBuffer = new Int16Array(pcmChunk.length) // zeros
					onAudioDataCallback(silenceBuffer.buffer)
				} else if (vadActive) {
					// VAD active: send real audio
					onAudioDataCallback(pcmData)
				}
				// else: VAD inactive - don't send anything (no keepalive needed)
			}

			// Connect audio nodes
			nodes.source.connect(nodes.workletNode)
			nodes.workletNode.connect(nodes.recordingContext.destination)

			recording = true

		} catch (error) {
			console.error('[VFF Audio] Failed to start recording:', error)
			cleanup()
			throw error
		}
	}

	/**
	 * Stop recording audio
	 */
	function stopRecording(): void {
		if (!recording) {
			return
		}

		recording = false
		onAudioDataCallback = null

		// Disconnect audio nodes
		if (nodes.workletNode) {
			try {
				nodes.workletNode.disconnect()
				nodes.workletNode.port.close()
			} catch (e) {
				// Ignore disconnect errors
			}
			nodes.workletNode = null
		}

		if (nodes.source) {
			try {
				nodes.source.disconnect()
			} catch (e) {
				// Ignore disconnect errors
			}
			nodes.source = null
		}

		// Close recording context
		if (nodes.recordingContext) {
			try {
				nodes.recordingContext.close()
			} catch (e) {
				// Ignore close errors
			}
			nodes.recordingContext = null
		}

		// Stop media stream tracks
		if (nodes.stream) {
			nodes.stream.getTracks().forEach(track => track.stop())
			nodes.stream = null
		}
	}

	/**
	 * Play audio from AI (PCM16 24kHz)
	 */
	async function playAudio(audioData: ArrayBuffer): Promise<void> {
		try {
			// Track playback chunks for debugging
			if (!playbackChunkCount) {
				playbackChunkCount = 0
			}
			playbackChunkCount++
			
			if (playbackChunkCount === 1) {
				console.log(`[AudioManager] 🔊 Playing first audio chunk (${audioData.byteLength} bytes)`)
			}
			
			// CRITICAL: Block new audio playback during barge-in
			if (playbackBlocked) {
				// Silently discard chunks during barge-in
				console.log(`[AudioManager] 🚫 Discarding chunk #${playbackChunkCount} (barge-in active)`)
				return
			}

			// Playback context should already exist (created eagerly in startRecording)
			// But keep fallback for safety
			if (!nodes.playbackContext) {
				console.log('[AudioManager] 🎵 Creating AudioContext for playback (lazy fallback)')
				nodes.playbackContext = new AudioContext({ sampleRate: PLAYBACK_SAMPLE_RATE })
				playbackTime = 0
			}

			const ctx = nodes.playbackContext

			// Resume context if suspended (browser autoplay policy)
			if (ctx.state === 'suspended') {
				console.log('[AudioManager] ⏸️ Resuming suspended AudioContext')
				await ctx.resume()
			}

			// Decode audio data
			const decoded = decodeGeminiFrame(audioData)
			const int16Array = new Int16Array(decoded)

			if (int16Array.length === 0) {
				console.warn(`[AudioManager] ⚠️ Chunk #${playbackChunkCount} decoded to 0 samples`)
				return
			}

			// Convert Int16 to Float32
			const float32 = new Float32Array(int16Array.length)
			for (let i = 0; i < int16Array.length; i++) {
				float32[i] = int16Array[i] / 32768.0
			}

			// Create audio buffer
			const audioBuffer = ctx.createBuffer(1, float32.length, PLAYBACK_SAMPLE_RATE)
			audioBuffer.getChannelData(0).set(float32)

			// Schedule playback - use current time if playback was interrupted
			const now = ctx.currentTime
			const startAt = Math.max(playbackTime, now + 0.01)

			const source = ctx.createBufferSource()
			source.buffer = audioBuffer
			source.connect(ctx.destination)
			source.start(startAt)

			// Track this source so it can be stopped during barge-in
			activeAudioSources.push(source)
			
			// Mark as speaking AFTER we know chunk will play
			const wasNotSpeaking = !geminiIsSpeaking
			geminiIsSpeaking = true
			
			// Notify activity watchdog that Gemini STARTED speaking (pause timer)
			// Only fire on first chunk, not every chunk
			if (wasNotSpeaking && window.vffOnAudioPlaybackStart) {
				window.vffOnAudioPlaybackStart()
			}

			// Update playback time for next chunk
			playbackTime = startAt + audioBuffer.duration

			source.onended = () => {
				// Update playback time if it's in the past
				if (playbackTime < ctx.currentTime) {
					playbackTime = ctx.currentTime
				}
				
				// Remove from active sources
				const index = activeAudioSources.indexOf(source)
				if (index > -1) {
					activeAudioSources.splice(index, 1)
				}
				
				// Only mark as not speaking if no more active sources
				if (activeAudioSources.length === 0) {
					geminiIsSpeaking = false
					
					// CRITICAL: Only notify activity watchdog when ALL chunks finished playing naturally
					// Do NOT fire callback during flush (barge-in) - that would spam the watchdog
					// This is used for Level 3 farewell disconnect timing (100ms audio silence detection)
					if (!isFlushing && window.vffOnAudioPlaybackEnd) {
						window.vffOnAudioPlaybackEnd()
					}
				}
			}

		} catch (error) {
			geminiIsSpeaking = false
			console.error('[VFF Audio] Playback failed:', error)
		}
	}

	/**
	 * Decode Gemini audio frame (may be base64-encoded)
	 */
	function decodeGeminiFrame(buffer: ArrayBuffer): ArrayBuffer {
		// Check if this is base64-encoded
		try {
			const text = new TextDecoder().decode(buffer)
			if (text.match(/^[A-Za-z0-9+/]+=*$/)) {
				// Looks like base64
				const binaryString = atob(text)
				const bytes = new Uint8Array(binaryString.length)
				for (let i = 0; i < binaryString.length; i++) {
					bytes[i] = binaryString.charCodeAt(i)
				}
				return bytes.buffer
			}
		} catch (e) {
			// Not base64, use as-is
		}
		return buffer
	}

	/**
	 * Flush audio queue - Stop all pending/playing audio immediately (for barge-in)
	 */
	function flushAudioQueue(): void {
		// CRITICAL: Block new audio playback from arriving chunks
		playbackBlocked = true
		
		// Set flag to suppress onended callbacks during flush
		isFlushing = true
		
		// Stop all active audio sources
		activeAudioSources.forEach(source => {
			try {
				source.stop()
				source.disconnect()
			} catch (e) {
				// Ignore errors from already-stopped sources
			}
		})
		
		// Clear the array
		activeAudioSources.length = 0
		
		// Reset playback time to now (don't queue new audio in the past)
		if (nodes.playbackContext) {
			playbackTime = nodes.playbackContext.currentTime
		}
		
		geminiIsSpeaking = false
		
		// Clear flag after flush completes
		isFlushing = false
	}
	
	/**
	 * Resume audio playback after barge-in (call when user stops speaking)
	 */
	function resumePlayback(): void {
		playbackBlocked = false
	}

	/**
	 * Check if currently recording
	 */
	function isRecording(): boolean {
		return recording
	}

	/**
	 * Cleanup all audio resources
	 */
	function cleanup(): void {
		stopRecording()

		if (nodes.playbackContext) {
			try {
				nodes.playbackContext.close()
			} catch (e) {
				// Ignore close errors
			}
			nodes.playbackContext = null
		}

		playbackTime = 0
	}

	/**
	 * Destroy audio manager
	 */
	function destroy(): void {
		cleanup()
	}

	/**
	 * Check if Gemini is currently speaking
	 */
	function isSpeaking(): boolean {
		return geminiIsSpeaking
	}

	function muteInput(): void {
		console.log('[AudioManager] Muting input - sending silence')
		inputMuted = true
	}

	function unmuteInput(): void {
		console.log('[AudioManager] Unmuting input - sending real audio')
		inputMuted = false
	}

	/**
	 * Get the active microphone stream (for sharing with VAD)
	 * This allows VAD to use the same stream instead of creating a duplicate
	 */
	function getStream(): MediaStream | null {
		return nodes.stream
	}

	/**
	 * Privacy Gate: Control audio flow based on VAD state
	 * 
	 * When VAD detects speech start:
	 * 1. Flush pre-buffer (last 400ms of audio) to prevent clipping
	 * 2. Enable live audio flow
	 * 
	 * When VAD detects speech end:
	 * - Disable live audio (send silence for privacy)
	 * 
	 * @param active - true to enable audio flow, false to send silence
	 */
	function setVADActive(active: boolean): void {
		const wasActive = vadActive
		vadActive = active
		
		if (active && !wasActive && onAudioDataCallback) {
			// VAD just activated: flush pre-buffer to capture start of speech
			console.log(`[AudioManager] VAD activated - flushing ${preBufferSampleCount} samples (${(preBufferSampleCount / RECORDING_SAMPLE_RATE * 1000).toFixed(0)}ms) from pre-buffer`)
			
			// Send all buffered chunks in order
			for (const chunk of audioPreBuffer) {
				// Create new ArrayBuffer copy to ensure correct type
				const buffer = new ArrayBuffer(chunk.byteLength)
				const view = new Int16Array(buffer)
				view.set(chunk)
				onAudioDataCallback(buffer)
			}
			
			console.log('[AudioManager] Pre-buffer flushed, now sending live audio')
		} else if (!active && wasActive) {
			// VAD deactivated: switch to sending silence (privacy)
			console.log('[AudioManager] VAD deactivated - sending silence')
		}
	}

	return {
		startRecording,
		stopRecording,
		playAudio,
		flushAudioQueue,
		resumePlayback,
		isRecording,
		isSpeaking,
		muteInput,
		unmuteInput,
		getStream,
		setVADActive,
		destroy,
	}
}
