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

	constructor() {
		super()
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

		// Calculate RMS energy
		let sumSquares = 0
		for (let i = 0; i < inputData.length; i++) {
			sumSquares += inputData[i] * inputData[i]
		}
		const instantRMS = Math.sqrt(sumSquares / inputData.length)
		const instantEnergy = instantRMS * 100 // Scale to 0-100 range

		// Apply RMS smoothing (EMA) to reduce jitter
		if (this.smoothedRMS === 0) {
			this.smoothedRMS = instantEnergy
		} else {
			this.smoothedRMS =
				this.RMS_SMOOTHING_BETA * instantEnergy +
				(1 - this.RMS_SMOOTHING_BETA) * this.smoothedRMS
		}

		// Convert Float32Array to Int16Array (PCM 16-bit)
		const pcmData = new Int16Array(inputData.length)
		for (let i = 0; i < inputData.length; i++) {
			const s = Math.max(-1, Math.min(1, inputData[i]))
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
