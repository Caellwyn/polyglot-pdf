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

export type EnergyChangeReason = 'attack' | 'release' | 'debounce_timeout' | 'tts_bleed_guard' | 'calibration'

export interface AudioEnergyCallback {
	onEnergyChange?: (energy: number, isActive: boolean, reason?: EnergyChangeReason) => void
	onCalibrationComplete?: (baselineEnergy: number) => void
}

export interface AudioManager {
	startRecording: (onAudioData: (data: ArrayBuffer) => void, energyCallbacks?: AudioEnergyCallback) => Promise<void>
	stopRecording: () => void
	playAudio: (audioData: ArrayBuffer) => Promise<void>
	flushAudioQueue: () => void // Stop all queued audio immediately
	resumePlayback: () => void // Resume audio after barge-in
	isRecording: () => boolean
	isSpeaking: () => boolean // Is Gemini currently speaking?
	getUserSpeaking: () => boolean // Is user mic currently active?
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
 */
export function createAudioManager(): AudioManager {
	const nodes: AudioNodes = {
		recordingContext: null,
		playbackContext: null,
		stream: null,
		workletNode: null,
		source: null,
	}

	let recording = false
	let playbackTime = 0
	let onAudioDataCallback: ((data: ArrayBuffer) => void) | null = null
	let energyCallbacks: AudioEnergyCallback | null = null
	
	// Track active audio sources for flushing
	const activeAudioSources: AudioBufferSourceNode[] = []
	
	// Barge-in state: block new audio playback during user interruption
	let playbackBlocked = false
	
	// Energy monitoring state with hysteresis & debouncing
	let baselineEnergy = 0
	let calibrationSamples: number[] = []
	let userIsSpeaking = false
	let geminiIsSpeaking = false
	let smoothedRMS = 0 // EMA smoothing for RMS
	
	// Hysteresis thresholds (prevents flapping)
	const ATTACK_MULTIPLIER = 2.5  // Start speech detection
	const RELEASE_MULTIPLIER = 1.7 // End speech detection
	const TTS_BLEED_BOOST = 1.4    // Extra margin when Gemini is speaking
	
	// Debounce timings (prevents spurious triggers)
	const MIN_SPEECH_DURATION_MS = 45    // Must be above attack for 60ms (reduced for faster barge-in)
	const MIN_SILENCE_DURATION_MS = 200  // Must be below release for 200ms
	let speechStartTime = 0
	let silenceStartTime = 0
	
	// Baseline adaptation
	const BASELINE_EMA_ALPHA = 0.9       // Slow baseline updates (only during non-speech)
	const RMS_SMOOTHING_BETA = 0.6       // RMS smoothing across frames
	const MIN_BASELINE_FLOOR = 0.5       // Prevent baseline from going to zero
	
	const CALIBRATION_DURATION_MS = 2000
	const FRAME_SIZE_MS = 20 // Approximate frame duration

	/**
	 * Start recording audio from microphone
	 */
	async function startRecording(onAudioData: (data: ArrayBuffer) => void, callbacks?: AudioEnergyCallback): Promise<void> {
		if (recording) {
			return
		}

		try {
			// Request microphone access
			nodes.stream = await navigator.mediaDevices.getUserMedia({
				audio: {
					channelCount: 1,
					sampleRate: RECORDING_SAMPLE_RATE,
					echoCancellation: true,
					noiseSuppression: true,
				},
			})

			// Create audio context for processing
		nodes.recordingContext = new AudioContext({ sampleRate: RECORDING_SAMPLE_RATE })
		nodes.source = nodes.recordingContext.createMediaStreamSource(nodes.stream)

		// Load AudioWorklet module from shared directory
		// Using ../shared/ resolves correctly for both dev (served from /src) and prod (assets/)
		const workletUrl = new URL('../shared/audio-processor.worklet.js', import.meta.url).href
		await nodes.recordingContext.audioWorklet.addModule(workletUrl)

			// Create AudioWorklet node
			nodes.workletNode = new AudioWorkletNode(
				nodes.recordingContext,
				'voice-form-filler-audio-processor'
			)

			onAudioDataCallback = onAudioData
			energyCallbacks = callbacks || null

			// Reset energy monitoring state
			baselineEnergy = 0
			calibrationSamples = []
			userIsSpeaking = false
			smoothedRMS = 0
			speechStartTime = 0
			silenceStartTime = 0
			const calibrationStartTime = Date.now()

			// Handle messages from AudioWorklet
			nodes.workletNode.port.onmessage = (event: MessageEvent) => {
				if (!recording || !onAudioDataCallback) return

				const { type, pcmData, energy } = event.data
				if (type !== 'audio') return

				// Update smoothed RMS from worklet
				smoothedRMS = energy

				// Calibration phase: collect baseline samples
				if (baselineEnergy === 0) {
					const elapsed = Date.now() - calibrationStartTime
					if (elapsed < CALIBRATION_DURATION_MS) {
						calibrationSamples.push(smoothedRMS)
					} else {
						// Calibration complete: calculate baseline as average, apply floor
						const sum = calibrationSamples.reduce((a, b) => a + b, 0)
						baselineEnergy = Math.max((sum / calibrationSamples.length) || MIN_BASELINE_FLOOR, MIN_BASELINE_FLOOR)
						smoothedRMS = baselineEnergy // Initialize smoothed RMS to baseline
						
						if (energyCallbacks?.onCalibrationComplete) {
							energyCallbacks.onCalibrationComplete(baselineEnergy)
						}
					}
				}

				// Adaptive threshold detection with hysteresis & debouncing
				if (baselineEnergy > 0) {
					const now = Date.now()
					
					// TTS bleed guard: raise attack threshold when Gemini is speaking
					const attackBoost = geminiIsSpeaking ? TTS_BLEED_BOOST : 1.0
					const attackThreshold = baselineEnergy * ATTACK_MULTIPLIER * attackBoost
					const releaseThreshold = baselineEnergy * RELEASE_MULTIPLIER
					
					// Hysteresis state machine
					if (!userIsSpeaking) {
						// Currently silent - check for speech attack
						if (smoothedRMS > attackThreshold) {
							if (speechStartTime === 0) {
								// First frame above attack threshold
								speechStartTime = now
							} else if (now - speechStartTime >= MIN_SPEECH_DURATION_MS) {
								// Sustained above attack for minimum duration
								userIsSpeaking = true
								silenceStartTime = 0
								
								const reason: EnergyChangeReason = geminiIsSpeaking ? 'tts_bleed_guard' : 'attack'
								if (energyCallbacks?.onEnergyChange) {
									energyCallbacks.onEnergyChange(smoothedRMS, true, reason)
								}
							}
						} else {
							// Dropped below attack, reset speech timer
							speechStartTime = 0
						}
					} else {
						// Currently speaking - check for speech release
						if (smoothedRMS < releaseThreshold) {
							if (silenceStartTime === 0) {
								// First frame below release threshold
								silenceStartTime = now
							} else if (now - silenceStartTime >= MIN_SILENCE_DURATION_MS) {
								// Sustained below release for minimum duration
								userIsSpeaking = false
								speechStartTime = 0
								
								if (energyCallbacks?.onEnergyChange) {
									energyCallbacks.onEnergyChange(smoothedRMS, false, 'release')
								}
							}
						} else {
							// Still above release, reset silence timer
							silenceStartTime = 0
						}
					}
					
					// Update baseline during non-speech periods only (slow EMA)
					if (!userIsSpeaking && smoothedRMS < releaseThreshold) {
						const newBaseline = (BASELINE_EMA_ALPHA * baselineEnergy) + ((1 - BASELINE_EMA_ALPHA) * smoothedRMS)
						baselineEnergy = Math.max(newBaseline, MIN_BASELINE_FLOOR)
					}
				}

				// Send PCM16 audio data (already converted in worklet)
				onAudioDataCallback(pcmData)
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
			// CRITICAL: Block new audio playback during barge-in
			if (playbackBlocked) {
				// Important: Don't update playbackTime or geminiIsSpeaking for blocked chunks
				return
			}

			// Create playback context if needed
			if (!nodes.playbackContext) {
				nodes.playbackContext = new AudioContext({ sampleRate: PLAYBACK_SAMPLE_RATE })
				playbackTime = 0
			}

			const ctx = nodes.playbackContext

			// Resume context if suspended
			if (ctx.state === 'suspended') {
				await ctx.resume()
			}

			// Decode audio data
			const decoded = decodeGeminiFrame(audioData)
			const int16Array = new Int16Array(decoded)

			if (int16Array.length === 0) {
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
			geminiIsSpeaking = true

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

	/**
	 * Check if user mic is currently active (speaking detected)
	 */
	function getUserSpeaking(): boolean {
		return userIsSpeaking
	}

	return {
		startRecording,
		stopRecording,
		playAudio,
		flushAudioQueue,
		resumePlayback,
		isRecording,
		isSpeaking,
		getUserSpeaking,
		destroy,
	}
}
