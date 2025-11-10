/**
 * Audio Worklet Processor - Runs on separate audio thread
 * 
 * Handles:
 * - PCM16 conversion for microphone data
 * - RMS energy calculation
 * - Sends processed audio + energy metrics to main thread
 */

// Type definitions for AudioWorklet API
interface AudioWorkletProcessor {
	readonly port: MessagePort
	process(
		inputs: Float32Array[][],
		outputs: Float32Array[][],
		parameters: Record<string, Float32Array>
	): boolean
}

declare const AudioWorkletProcessor: {
	prototype: AudioWorkletProcessor
	new (options?: AudioWorkletNodeOptions): AudioWorkletProcessor
}

declare function registerProcessor(
	name: string,
	processorCtor: new () => AudioWorkletProcessor
): void

class VoiceFormFillerAudioProcessor extends AudioWorkletProcessor {
	private smoothedRMS = 0
	private readonly RMS_SMOOTHING_BETA = 0.6

	// HALLUCINATION_REDUCTION (Oct 30, 2025): Audio preprocessing filters
	// FIX (Nov 7, 2025): Lowered threshold from -40dB to -50dB for gentler gating
	// Noise gate: -50dB threshold (gentler - preserves quiet speech)
	private readonly NOISE_GATE_THRESHOLD = 0.00316 // -50dB in linear scale (10^(-50/20))

	// High-pass filter: 80Hz cutoff, Q=0.7 (removes low-frequency rumble)
	// Biquad filter state variables (stores previous samples for IIR filtering)
	private hpf_x1 = 0 // input sample at n-1
	private hpf_x2 = 0 // input sample at n-2
	private hpf_y1 = 0 // output sample at n-1
	private hpf_y2 = 0 // output sample at n-2

	// High-pass filter coefficients (calculated for 80Hz @ 16kHz sample rate, Q=0.7)
	private readonly hpf_b0: number
	private readonly hpf_b1: number
	private readonly hpf_b2: number
	private readonly hpf_a1: number
	private readonly hpf_a2: number

	// FIX (Nov 7, 2025): Track PTT mode to bypass noise gate when user explicitly controls audio
	private pttMode = false

	constructor() {
		super()
		
		// Listen for PTT mode changes from main thread
		this.port.onmessage = (event: MessageEvent) => {
			if (event.data.type === 'setPTTMode') {
				this.pttMode = event.data.enabled
				console.log('[AudioWorklet] PTT mode:', this.pttMode ? 'enabled (noise gate bypassed)' : 'disabled (noise gate active)')
			}
		}

		// Calculate high-pass filter coefficients
		// f0 = 80 Hz, Fs = 16000 Hz, Q = 0.7
		const f0 = 80
		const Fs = 16000 // Sample rate (must match getUserMedia constraints in audioManager.ts)
		const Q = 0.7

		const w0 = (2 * Math.PI * f0) / Fs
		const cosW0 = Math.cos(w0)
		const sinW0 = Math.sin(w0)
		const alpha = sinW0 / (2 * Q)

		// High-pass filter coefficients
		const b0 = (1 + cosW0) / 2
		const b1 = -(1 + cosW0)
		const b2 = (1 + cosW0) / 2
		const a0 = 1 + alpha
		const a1 = -2 * cosW0
		const a2 = 1 - alpha

		// Normalize by a0
		this.hpf_b0 = b0 / a0
		this.hpf_b1 = b1 / a0
		this.hpf_b2 = b2 / a0
		this.hpf_a1 = a1 / a0
		this.hpf_a2 = a2 / a0
	}

	process(
		inputs: Float32Array[][],
		outputs: Float32Array[][],
		parameters: Record<string, Float32Array>
	): boolean {
		const input = inputs[0]
		if (!input || !input[0]) {
			return true
		}

		const inputData = input[0] // Mono channel

		// HALLUCINATION_REDUCTION (Oct 30, 2025): Apply audio preprocessing filters
		// Create a copy for processing (avoid mutating input buffer)
		const filteredData = new Float32Array(inputData.length)

		// Step 1: Apply high-pass filter (80Hz) to remove low-frequency rumble
		for (let i = 0; i < inputData.length; i++) {
			const x0 = inputData[i]

			// Biquad IIR filter: y[n] = b0*x[n] + b1*x[n-1] + b2*x[n-2] - a1*y[n-1] - a2*y[n-2]
			const y0 =
				this.hpf_b0 * x0 +
				this.hpf_b1 * this.hpf_x1 +
				this.hpf_b2 * this.hpf_x2 -
				this.hpf_a1 * this.hpf_y1 -
				this.hpf_a2 * this.hpf_y2

			// Update state variables for next iteration
			this.hpf_x2 = this.hpf_x1
			this.hpf_x1 = x0
			this.hpf_y2 = this.hpf_y1
			this.hpf_y1 = y0

			filteredData[i] = y0
		}

		// Step 2: Apply noise gate (-50dB threshold) - BUT ONLY IN VAD MODE
		// FIX (Nov 7, 2025): Skip noise gate in PTT mode - user explicitly controls when to send audio
		// In PTT mode, aggressive gating can clip quiet speech (consonants, pauses, quiet speakers)
		if (!this.pttMode) {
			// Calculate RMS of filtered audio first to determine if it's above threshold
			let sumSquaresFiltered = 0
			for (let i = 0; i < filteredData.length; i++) {
				sumSquaresFiltered += filteredData[i] * filteredData[i]
			}
			const rmsFiltered = Math.sqrt(sumSquaresFiltered / filteredData.length)

			// If RMS is below noise gate threshold, replace with silence (VAD mode only)
			if (rmsFiltered < this.NOISE_GATE_THRESHOLD) {
				filteredData.fill(0)
			}
		}

		// Use filtered data for all downstream processing
		const processedData = filteredData

		// Calculate RMS energy (from processed audio)
		let sumSquares = 0
		for (let i = 0; i < processedData.length; i++) {
			sumSquares += processedData[i] * processedData[i]
		}
		const instantRMS = Math.sqrt(sumSquares / processedData.length)
		const instantEnergy = instantRMS * 100 // Scale to 0-100 range

		// Apply RMS smoothing (EMA) to reduce jitter
		if (this.smoothedRMS === 0) {
			this.smoothedRMS = instantEnergy
		} else {
			this.smoothedRMS =
				this.RMS_SMOOTHING_BETA * instantEnergy +
				(1 - this.RMS_SMOOTHING_BETA) * this.smoothedRMS
		}

		// FIX #3 (Oct 22, 2025): Audio quality diagnostics
		// Sample 0.1% of frames to detect audio corruption without spamming logs
		// FIX (Nov 10, 2025): Reduced sampling rate from 0.1% to 0.01% (10x less frequent)
		// These logs are for diagnosing audio quality issues, not for monitoring audio flow
		if (Math.random() < 0.0001) {
			const clippedCount = processedData.filter(s => Math.abs(s) > 0.99).length
			// Check if this frame would trigger noise gate (only relevant in VAD mode)
			let sumSquaresFiltered = 0
			for (let i = 0; i < filteredData.length; i++) {
				sumSquaresFiltered += filteredData[i] * filteredData[i]
			}
			const rmsFiltered = Math.sqrt(sumSquaresFiltered / filteredData.length)
			
			console.log('[AudioWorklet] Quality check (post-filter):', {
				samples: processedData.length,
				rms: instantRMS.toFixed(4),
				energy: instantEnergy.toFixed(2),
				firstSample: processedData[0].toFixed(4),
				lastSample: processedData[processedData.length - 1].toFixed(4),
				clippedSamples: clippedCount,
				clippingRate: (clippedCount / processedData.length * 100).toFixed(2) + '%',
				pttMode: this.pttMode,
				noiseGateActive: !this.pttMode && rmsFiltered < this.NOISE_GATE_THRESHOLD,
				note: 'Worklet processes all audio - filtering happens in audioManager.ts'
			})
		}

		// Convert Float32Array to Int16Array (PCM 16-bit)
		// Use PROCESSED data (after high-pass filter + noise gate)
		const pcmData = new Int16Array(processedData.length)
		for (let i = 0; i < processedData.length; i++) {
			const s = Math.max(-1, Math.min(1, processedData[i]))
			pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7fff
		}

		// Send PCM data + energy to main thread
		this.port.postMessage({
			type: 'audio',
			pcmData: pcmData.buffer,
			energy: this.smoothedRMS,
		}, [pcmData.buffer]) // Transfer ownership for zero-copy

		return true // Keep processor alive
	}
}

registerProcessor('voice-form-filler-audio-processor', VoiceFormFillerAudioProcessor)
