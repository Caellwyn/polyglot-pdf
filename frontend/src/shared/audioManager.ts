/**
 * Audio Manager - Microphone Recording & AI Audio Playback
 * 
 * Handles:
 * - Microphone permission and recording
 * - PCM16 conversion for Gemini (16kHz mono)
 * - AI audio playback (24kHz PCM16)
 * - Audio context lifecycle
 */

import { MIC_AUDIO_CONSTRAINTS } from './audioConstraints'

const RECORDING_SAMPLE_RATE = 16000 // Gemini input
const PLAYBACK_SAMPLE_RATE = 24000  // Gemini output

/**
 * Callback bundle consumed by the dev-only VAD-tuning tool (src/vad-tuning) to
 * observe live mic energy + calibration. `reason` is an optional human-readable
 * tag for why the active state changed (e.g. a VAD transition); it is advisory.
 */
export interface AudioEnergyCallback {
  onEnergyChange: (energy: number, isActive: boolean, reason?: string) => void
  onCalibrationComplete: (baseline: number) => void
}

export interface AudioManager {
	startRecording: (onAudioData: (data: ArrayBuffer) => void) => Promise<void>
	stopRecording: () => void
	playAudio: (audioData: ArrayBuffer) => Promise<void>
	flushAudioQueue: () => void // Stop all queued audio immediately (full barge-in)
	resumePlayback: () => void // Resume audio after barge-in (unblock new chunks)
	pauseAudioContext: () => void // Pause audio context (tentative pause for VAD)
	resumeAudioContext: () => void // Resume audio context (resume after false positive)
	isRecording: () => boolean
	isSpeaking: () => boolean // Is Gemini currently speaking?
	muteInput: () => void // Mute mic input (send silence - push-to-talk mode only)
	unmuteInput: () => void // Unmute mic input (send real audio)
	getStream: () => MediaStream | null // Get the active microphone stream (for sharing with VAD)
	setVADActive: (active: boolean) => void // Privacy gate: control audio flow based on VAD state
	setPTTMode: (enabled: boolean) => void // FIX (Nov 7, 2025): Notify worklet about PTT mode
	setNativeVad: (enabled: boolean) => void // bd polyglot-pdf-333: stream continuous ungated audio for Gemini's own VAD
	// Subscribe to the live mic-energy stream the worklet already posts (bd
	// polyglot-pdf-s3zv). Reuses the worklet's smoothed RMS (0-100) rather than
	// adding an AnalyserNode on the CAPTURE path. `sending` is whether THIS frame
	// actually passed the send gate (so a UI can distinguish "mic alive but
	// gated/silent" from a dead mic). Pass null to unsubscribe.
	// (The PLAYBACK path has no worklet, so output level does use an analyser --
	// see getOutputEnergy below.)
	setEnergyCallback: (callback: ((energy: number, sending: boolean) => void) | null) => void
	// Instantaneous amplitude of the AI's OUTPUT audio, 0-100, on the same scale
	// as the mic energy above (bd polyglot-pdf-2p4y). Returns 0 when nothing is
	// playing. Unlike the mic path there is no worklet here, so this reads an
	// AnalyserNode on the playback chain; it is a pull API (call it from a rAF
	// loop) rather than a subscription, because the only consumer is an avatar
	// that already animates per-frame.
	getOutputEnergy: () => number
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
 * Mode-level gate: given the current audio-routing flags, should this captured
 * chunk be sent to Gemini at all? This is the routing decision ONLY -- the
 * caller still applies the all-zero silence skip (which depends on chunk
 * content) separately. Extracted as a pure function so the three-way logic is
 * unit-testable (bd polyglot-pdf -- PTT-as-a-gate over native VAD).
 *
 * The three modes:
 * - NATIVE VAD on: Gemini's own VAD drives turns, so SOMETHING is always sent to
 *   keep the stream continuous (Gemini needs trailing audio to close a turn).
 *   This gate therefore returns true for native VAD regardless of PTT/mute --
 *   when PTT is muted the CALLER substitutes a silence frame (so the mic is not
 *   leaked) rather than dropping the chunk. Stopping the stream on PTT mute would
 *   strand native VAD and Gemini "stops responding" after release (bd
 *   polyglot-pdf-zivv). Native VAD and the manual turn signals (activity_start,
 *   activity_end, audio_stream_end) are mutually exclusive, so under native VAD
 *   PTT is ONLY an audio gate.
 * - NATIVE VAD off, PTT on: send only while the button is held.
 * - NATIVE VAD off, PTT off (client Silero VAD): send only when NOT muted AND the
 *   VAD has detected speech (vadActive).
 */
export function shouldSendAudioChunk(flags: {
	nativeVadEnabled: boolean
	pttModeEnabled: boolean
	inputMuted: boolean
	vadActive: boolean
}): boolean {
	const { nativeVadEnabled, pttModeEnabled, inputMuted, vadActive } = flags
	if (nativeVadEnabled) {
		// Always send under native VAD -- the stream must stay continuous. PTT-mute
		// is handled by the caller substituting silence, NOT by withholding here.
		return true
	}
	if (pttModeEnabled) {
		// PTT mode: only while the button is held.
		return !inputMuted
	}
	// Client Silero VAD mode: require not-muted AND speech detected.
	return !inputMuted && vadActive
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
	// In-flight arming guard (bd polyglot-pdf-z9bc). `recording` is only set true
	// at the END of startRecording, AFTER getUserMedia + AudioContext + addModule
	// all await; so a plain `if (recording) return` does NOT stop a SECOND
	// concurrent startRecording that begins while the first is still in that await
	// chain (both would run getUserMedia + worklet setup and clobber
	// nodes.source/workletNode). This can happen when two callers race to arm on
	// the same tick (e.g. an overlay status-poll and a session-ready callback both
	// calling startRecording). Hold the in-flight promise so a concurrent call
	// awaits it instead of starting a duplicate setup.
	let arming: Promise<void> | null = null
	let playbackTime = 0
	let playbackChunkCount = 0 // Track playback chunks for debugging
	let onAudioDataCallback: ((data: ArrayBuffer) => void) | null = null
	// Live mic-energy subscriber (bd polyglot-pdf-s3zv). The worklet posts a
	// smoothed RMS energy on every frame; we forward it (plus whether the frame
	// was actually sent) to an optional UI subscriber.
	let onEnergyCallback: ((energy: number, sending: boolean) => void) | null = null
	let inputMuted = false // Track if input should be muted (send silence)
	let pttModeEnabled = false // FIX (Nov 7, 2025): Track PTT mode state
	// Native-VAD mode (bd polyglot-pdf-333): when true, stream ALL audio (incl.
	// silence) ungated so Gemini's own VAD can detect turn boundaries. Bypasses
	// the inputMuted/vadActive gate AND the all-zero silence skip below, and puts
	// the worklet noise gate into bypass (via the setPTTMode worklet message).
	let nativeVadEnabled = false

	// Privacy gate: VAD-controlled audio flow
	let vadActive = false // When false, don't send audio; when true, send real audio
	
	// Circular pre-buffer for speech start capture
	// Purpose: Captures audio BEFORE VAD detects speech to prevent clipping
	// Size must be >= minSpeechMs + redemptionMs from VAD config
	// Current VAD defaults: minSpeechMs=250ms, redemptionMs=400ms
	// FIX #2 (Oct 22, 2025): Increased from 600ms to 700ms
	// Pre-buffer: 700ms = 250 + 400 + 50ms safety margin
	const PREBUFFER_DURATION_MS = 700
	const PREBUFFER_SIZE_SAMPLES = Math.ceil((PREBUFFER_DURATION_MS / 1000) * RECORDING_SAMPLE_RATE)
	const audioPreBuffer: Int16Array[] = [] // Rolling buffer of PCM16 chunks
	let preBufferSampleCount = 0 // Track total samples in buffer
	
	// Track active audio sources for flushing
	const activeAudioSources: AudioBufferSourceNode[] = []

	// Barge-in state: block new audio playback during user interruption
	let playbackBlocked = false
	// Count chunks discarded while blocked (bd polyglot-pdf-nm7z): a STALE block
	// (a flush whose paired resumePlayback never ran) silently killed all AI audio
	// with zero console evidence, making tester bugs 0/7 undiagnosable from logs.
	// A periodic warning keeps the console quiet in a normal barge-in (a handful
	// of discards) but makes a runaway discard loop visible.
	let blockedDiscardCount = 0

	// Flag to suppress onended callbacks during flush (prevents spurious watchdog triggers)
	let isFlushing = false

	// Track if Gemini is currently speaking (for barge-in detection)
	let geminiIsSpeaking = false

	/**
	 * Output-amplitude tap for the avatar (bd polyglot-pdf-2p4y).
	 *
	 * The mic path gets its RMS free from the capture worklet, but the playback
	 * path has no worklet -- chunks are scheduled straight onto BufferSources --
	 * so measuring the AI's voice needs an AnalyserNode spliced between the
	 * sources and the destination. Without it Sol's "speaking" state would be
	 * driven by MIC energy, which is near-silent precisely when the assistant is
	 * talking, leaving the state visually dead.
	 *
	 * Lazily built against whichever playback context is live, and rebuilt if
	 * that context is replaced (it is recreated after a close/destroy).
	 */
	let outputAnalyser: AnalyserNode | null = null
	let outputAnalyserCtx: AudioContext | null = null
	// Explicitly backed by ArrayBuffer (not ArrayBufferLike): getByteTimeDomainData
	// rejects a possibly-SharedArrayBuffer view under the DOM lib's typings.
	let outputBuf: Uint8Array<ArrayBuffer> | null = null

	function getOutputAnalyser(ctx: AudioContext): AnalyserNode {
		if (outputAnalyser && outputAnalyserCtx === ctx) return outputAnalyser
		const analyser = ctx.createAnalyser()
		// Small FFT: we only want a level, not a spectrum, and this keeps the
		// per-frame copy cheap.
		analyser.fftSize = 256
		analyser.connect(ctx.destination)
		outputAnalyser = analyser
		outputAnalyserCtx = ctx
		outputBuf = new Uint8Array(new ArrayBuffer(analyser.fftSize))
		return analyser
	}

	/**
	 * Instantaneous output level, 0-100, matching the mic-energy scale so a UI can
	 * feed either into the same visualisation. Returns 0 when nothing is playing,
	 * so a consumer polling every frame does not need its own silence check.
	 */
	function getOutputEnergy(): number {
		if (!geminiIsSpeaking || !outputAnalyser || !outputBuf) return 0
		outputAnalyser.getByteTimeDomainData(outputBuf)
		let sum = 0
		for (let i = 0; i < outputBuf.length; i++) {
			const v = (outputBuf[i] - 128) / 128
			sum += v * v
		}
		// Same *100 scaling the capture worklet applies to its RMS.
		return Math.min(100, Math.sqrt(sum / outputBuf.length) * 100)
	}

	/**
	 * Start recording audio from microphone
	 */
	async function startRecording(onAudioData: (data: ArrayBuffer) => void): Promise<void> {
		// Fast path: already fully armed.
		if (recording) {
			return
		}
		// A setup is already in flight (a concurrent caller began arming and has not
		// finished its await chain yet) -- await THAT one instead of starting a
		// duplicate getUserMedia/worklet setup (bd polyglot-pdf-z9bc).
		if (arming) {
			return arming
		}
		arming = _startRecordingImpl(onAudioData)
		try {
			await arming
		} finally {
			arming = null
		}
	}

	async function _startRecordingImpl(onAudioData: (data: ArrayBuffer) => void): Promise<void> {
		try {
			// Only create stream if we don't already have one (from constructor)
			if (!nodes.stream) {
				// Request microphone access with optimal settings
				// These match the VAD stream to ensure consistency
				nodes.stream = await navigator.mediaDevices.getUserMedia({
					// Canonical AEC/mic constraints (bd polyglot-pdf-gnmo) plus the
					// recording rate this site pins.
					audio: { ...MIC_AUDIO_CONSTRAINTS, sampleRate: RECORDING_SAMPLE_RATE },
				})
				console.log('[AudioManager] [mic] Created new microphone stream')
			} else {
				console.log('[AudioManager] [link] Reusing existing microphone stream (shared with VAD)')
			}

			// FIX #5: AudioContext Pooling - reuse contexts instead of creating new ones
			// Browsers limit AudioContext instances (6-8 on desktop, 2-4 on mobile)
			// Creating new contexts on each startRecording() causes failures on reconnect
			if (!nodes.recordingContext) {
				console.log('[AudioManager] [note] Creating AudioContext for recording (first time)')
				nodes.recordingContext = new AudioContext({ sampleRate: RECORDING_SAMPLE_RATE })
			} else {
				console.log('[AudioManager] [recycle] Reusing existing recording AudioContext')
				// Resume if suspended (browsers may suspend contexts to save power)
				if (nodes.recordingContext.state === 'suspended') {
					await nodes.recordingContext.resume()
				}
			}

			nodes.source = nodes.recordingContext.createMediaStreamSource(nodes.stream)

			if (!nodes.playbackContext) {
				console.log('[AudioManager] [note] Creating AudioContext for playback (eager initialization)')
				nodes.playbackContext = new AudioContext({ sampleRate: PLAYBACK_SAMPLE_RATE })
				playbackTime = 0
			} else {
				console.log('[AudioManager] [recycle] Reusing existing playback AudioContext')
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

			// bd polyglot-pdf-333: a freshly-created worklet defaults to
			// noise-gate-ON. If native-VAD mode is active (e.g. after a
			// reconnect/recording restart), re-apply the gate bypass so silence
			// keeps streaming -- otherwise the gate silently re-arms mid-session.
			if (nativeVadEnabled) {
				nodes.workletNode.port.postMessage({ type: 'setPTTMode', enabled: true })
			}

			// Handle messages from AudioWorklet
			nodes.workletNode.port.onmessage = (event: MessageEvent) => {
				if (!recording || !onAudioDataCallback) return

				const { type, pcmData, energy } = event.data
				if (type !== 'audio') return

				// Forward the worklet's live energy to an optional UI subscriber
				// (bd polyglot-pdf-s3zv). Emitted on EVERY frame -- even when the
				// gate drops it -- so a meter shows the mic is alive while gated
				// (muted PTT / idle VAD / silence). `sending` is true only on the
				// paths below that actually forward the chunk, letting the UI tell
				// "mic alive but gated" from "audio being sent". `energy` is the
				// worklet's smoothed RMS (0-100); guard the type defensively.
				const emitEnergy = (sending: boolean) => {
					if (onEnergyCallback && typeof energy === 'number') {
						onEnergyCallback(energy, sending)
					}
				}

			// NATIVE-VAD mode: Gemini's own VAD owns turn detection and needs a
			// CONTINUOUS stream to find boundaries. PTT here is ONLY a client-side
			// audio gate (noisy-room support) -- it must NEVER stop the stream or send
			// a manual turn signal (activity_*/audio_stream_end are suppressed in the
			// overlay; the two systems are mutually exclusive -- bd polyglot-pdf-zivv).
			// So when PTT is muted we send SILENCE (a zeroed frame), not nothing:
			// stopping the stream would leave native VAD with no trailing audio and
			// the turn would never close (Gemini "stops responding" after PTT release).
			if (nativeVadEnabled) {
				if (pttModeEnabled && inputMuted) {
					// Muted under PTT: keep the stream alive with silence so native VAD
					// keeps detecting boundaries, but do not leak the muted mic.
					const silence = new ArrayBuffer((pcmData as ArrayBuffer).byteLength)
					emitEnergy(false)
					onAudioDataCallback(silence)
				} else {
					emitEnergy(true)
					onAudioDataCallback(pcmData)
				}
				return
			}

			// Manual-VAD / client-VAD routing gate (PTT held, or Silero speech).
			if (!shouldSendAudioChunk({ nativeVadEnabled, pttModeEnabled, inputMuted, vadActive })) {
				emitEnergy(false)
				return
			}

			const pcmChunk = new Int16Array(pcmData)

				// Update pre-buffer for VAD mode (allows capturing speech start)
				// In PTT mode, pre-buffer isn't used, but it's harmless to maintain it
				audioPreBuffer.push(pcmChunk)
				preBufferSampleCount += pcmChunk.length

				// Trim pre-buffer to maintain 700ms window
				while (preBufferSampleCount > PREBUFFER_SIZE_SAMPLES) {
					const removed = audioPreBuffer.shift()
					if (removed) {
						preBufferSampleCount -= removed.length
					}
				}

				// CRITICAL: Never send all-zero chunks (silence) to Gemini
				// Check if chunk contains any non-zero samples
				let hasSignal = false
				for (let i = 0; i < pcmChunk.length; i++) {
					if (pcmChunk[i] !== 0) {
						hasSignal = true
						break
					}
				}
				if (!hasSignal) {
					// Skip silent chunks - Gemini doesn't need keepalive audio
					emitEnergy(false)
					return
				}

				// At this point: PTT unmuted OR VAD active, AND chunk has audio signal
				// Send real audio to Gemini
				emitEnergy(true)
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
			// Track playback chunks for debugging
			if (!playbackChunkCount) {
				playbackChunkCount = 0
			}
			playbackChunkCount++
			
			if (playbackChunkCount === 1) {
				console.log(`[AudioManager] [sound] Playing first audio chunk (${audioData.byteLength} bytes)`)
			}
			
			// CRITICAL: Block new audio playback during barge-in
			if (playbackBlocked) {
				// Discard chunks during barge-in. Quiet for a normal barge-in, but a
				// periodic warning so a STALE block (bd polyglot-pdf-nm7z) is visible:
				// 50 chunks is far beyond any legitimate barge-in window.
				blockedDiscardCount++
				if (blockedDiscardCount % 50 === 0) {
					console.warn(
						`[AudioManager] [warn] ${blockedDiscardCount} audio chunks discarded ` +
						`while playback is blocked -- if no barge-in is in progress, the ` +
						`block is stale (bd polyglot-pdf-nm7z)`)
				}
				return
			}

			// Playback context should already exist (created eagerly in startRecording)
			// But keep fallback for safety
			if (!nodes.playbackContext) {
				console.log('[AudioManager] [note] Creating AudioContext for playback (lazy fallback)')
				nodes.playbackContext = new AudioContext({ sampleRate: PLAYBACK_SAMPLE_RATE })
				playbackTime = 0
			}

			const ctx = nodes.playbackContext

			// Resume context if suspended (browser autoplay policy)
			if (ctx.state === 'suspended') {
				console.log('[AudioManager] [pause] Resuming suspended AudioContext')
				await ctx.resume()
			}

			// Decode audio data
			const decoded = decodeGeminiFrame(audioData)
			const int16Array = new Int16Array(decoded)

			if (int16Array.length === 0) {
				console.warn(`[AudioManager] [warn] Chunk #${playbackChunkCount} decoded to 0 samples`)
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
			// Through the analyser rather than straight to the destination, so the
			// avatar can read the AI's real output level (bd polyglot-pdf-2p4y). The
			// analyser is a pass-through -- it does not alter the signal -- and is
			// itself connected to ctx.destination.
			source.connect(getOutputAnalyser(ctx))
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
		blockedDiscardCount = 0
	}

	/**
	 * Pause audio context (tentative pause during VAD uncertainty)
	 *
	 * Suspends the playback AudioContext, which immediately pauses all audio.
	 * Audio can be resumed seamlessly with resumeAudioContext().
	 * Used for instant barge-in feedback before confirming speech duration.
	 */
	async function pauseAudioContext(): Promise<void> {
		if (nodes.playbackContext && nodes.playbackContext.state === 'running') {
			try {
				await nodes.playbackContext.suspend()
				console.log('[AudioManager] [mute] Audio context paused (tentative barge-in)')
			} catch (e) {
				console.error('[AudioManager] Failed to pause audio context:', e)
			}
		}
	}

	/**
	 * Resume audio context (resume after false positive)
	 *
	 * Resumes the playback AudioContext, continuing audio where it left off.
	 * Used when VAD detects short noise that doesn't meet barge-in threshold.
	 */
	async function resumeAudioContext(): Promise<void> {
		if (nodes.playbackContext && nodes.playbackContext.state === 'suspended') {
			try {
				await nodes.playbackContext.resume()
				console.log('[AudioManager] [sound] Audio context resumed (false positive)')
			} catch (e) {
				console.error('[AudioManager] Failed to resume audio context:', e)
			}
		}
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

		// The analyser belonged to the context we just closed; drop it so the next
		// playback rebuilds one against the fresh context (bd polyglot-pdf-2p4y).
		outputAnalyser = null
		outputAnalyserCtx = null
		outputBuf = null

		// Drop the energy subscriber on teardown so a destroyed manager holds no
		// reference into the overlay (bd polyglot-pdf-s3zv).
		onEnergyCallback = null

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
		console.log('[AudioManager] [mute] Muting input - audio processing stopped')
		inputMuted = true
	}

	function unmuteInput(): void {
		console.log('[AudioManager] [sound] Unmuting input - audio processing active')
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
	 * Set PTT mode (enables/disables noise gate in audio worklet)
	 * FIX (Nov 7, 2025): In PTT mode, user explicitly controls audio flow,
	 * so aggressive noise gating is counterproductive and can clip quiet speech
	 * 
	 * @param enabled - true for PTT mode (noise gate disabled), false for VAD mode (noise gate enabled)
	 */
	function setPTTMode(enabled: boolean): void {
		console.log('[AudioManager] setPTTMode:', enabled)
		pttModeEnabled = enabled

		// Notify worklet about PTT mode change (bypasses the RMS noise gate). The
		// worklet gate must ALSO stay bypassed whenever native VAD is on -- Gemini's
		// VAD needs the raw continuous stream (incl. quiet speech) and the RMS gate
		// would clip it -- so the bypass is (PTT on) OR (native VAD on). Turning PTT
		// off under native VAD therefore does NOT re-arm the gate; PTT gating happens
		// at the JS layer via inputMuted, not the worklet RMS gate.
		if (nodes.workletNode) {
			nodes.workletNode.port.postMessage({
				type: 'setPTTMode',
				enabled: enabled || nativeVadEnabled
			})
		}
	}

	/**
	 * Set native-VAD mode (bd polyglot-pdf-333).
	 *
	 * When enabled, audio streams continuously and ungated (the worklet onmessage
	 * handler short-circuits past the privacy gate + all-zero skip) so Gemini's own
	 * VAD has a stream -- including silence -- to detect turns on.
	 *
	 * It ALSO bypasses the worklet's RMS noise gate by reusing the existing
	 * `setPTTMode` worklet message (the worklet only knows "noise gate on/off"):
	 * without this the worklet would zero sub-threshold audio before JS ever sees
	 * it, starving Gemini's VAD of the silence it needs. The JS-side `pttModeEnabled`
	 * var stays false (the native short-circuit handles JS gating) -- the worklet's
	 * internal pttMode and the JS one are intentionally decoupled here.
	 *
	 * @param enabled - true for native Gemini VAD, false to restore manual-VAD gating
	 */
	function setNativeVad(enabled: boolean): void {
		console.log('[AudioManager] setNativeVad:', enabled)
		nativeVadEnabled = enabled

		// Bypass (enabled) / restore (disabled) the worklet noise gate so silence
		// is streamed in native mode. On disable we hand control back to the normal
		// PTT state so manual mode behaves exactly as before.
		if (nodes.workletNode) {
			nodes.workletNode.port.postMessage({
				type: 'setPTTMode',
				enabled: enabled ? true : pttModeEnabled
			})
		}
	}

	/**
	 * Subscribe to the live mic-energy stream (bd polyglot-pdf-s3zv). The worklet
	 * already posts a smoothed RMS energy on every frame; this just forwards it to
	 * an optional UI subscriber, so no extra audio analysis is added. Pass null to
	 * unsubscribe. The subscription survives stop/rearm cycles (the overlay sets it
	 * once on mount); the onmessage `if (!recording || !onAudioDataCallback)` guard
	 * already stops emission while not recording (both are nulled together in
	 * stopRecording, so energy never fires once recording has stopped).
	 *
	 * NOTE: the callback is captured against the CURRENT manager instance. If a
	 * caller ever destroys the inner audioManager and creates a fresh one WITHOUT the
	 * connectionManager reference changing, the new manager has no subscriber and the
	 * meter would go dark until the consumer re-subscribes. Today the only
	 * destroy/recreate happens on overlay unmount (which re-subscribes on remount via
	 * its [connectionManager] effect), so this holds -- but a future mid-session
	 * disconnect()/connect() flow MUST re-call setEnergyCallback (bd s3zv fresh-eyes).
	 */
	function setEnergyCallback(callback: ((energy: number, sending: boolean) => void) | null): void {
		onEnergyCallback = callback
	}

	/**
	 * Set VAD activity state (controls audio flow to backend)
	 * 
	 * When VAD detects speech start:
	 * 1. Flush pre-buffer (last 400ms of audio) to prevent clipping
	 * 2. Enable live audio flow
	 * 
	 * When VAD detects speech end:
	 * - Disable live audio flow (no audio sent, no keepalive needed)
	 * 
	 * @param active - true to enable audio flow, false to stop sending audio
	 */
	function setVADActive(active: boolean): void {
		const wasActive = vadActive
		vadActive = active
		
		if (active && !wasActive && onAudioDataCallback) {
			// VAD just activated: flush pre-buffer to capture start of speech
			console.log(`[AudioManager] VAD activated - flushing ${preBufferSampleCount} samples (${(preBufferSampleCount / RECORDING_SAMPLE_RATE * 1000).toFixed(0)}ms) from pre-buffer`)
			
			// Send all buffered chunks in order, but skip all-zero chunks
			let skippedSilence = 0
			for (const chunk of audioPreBuffer) {
				// Check if chunk is all zeros (silence)
				let hasSignal = false
				for (let i = 0; i < chunk.length; i++) {
					if (chunk[i] !== 0) {
						hasSignal = true
						break
					}
				}
				
				if (!hasSignal) {
					skippedSilence++
					continue // Skip silent chunks
				}
				
				// Create new ArrayBuffer copy to ensure correct type
				const buffer = new ArrayBuffer(chunk.byteLength)
				const view = new Int16Array(buffer)
				view.set(chunk)
				onAudioDataCallback(buffer)
			}
			
			if (skippedSilence > 0) {
				console.log(`[AudioManager] Skipped ${skippedSilence} silent chunks from pre-buffer`)
			}
			console.log('[AudioManager] Pre-buffer flushed, now sending live audio')
		} else if (!active && wasActive) {
			// VAD deactivated: stop sending audio (no keepalive needed)
			// Audio flow stops automatically - see line ~195
			console.log('[AudioManager] VAD deactivated - stopping audio stream')
		}
	}

	return {
		startRecording,
		stopRecording,
		playAudio,
		flushAudioQueue,
		resumePlayback,
		pauseAudioContext,
		resumeAudioContext,
		isRecording,
		isSpeaking,
		muteInput,
		unmuteInput,
		getStream,
		setVADActive,
		setPTTMode,
		setNativeVad,
		setEnergyCallback,
		getOutputEnergy,
		destroy,
	}
}
