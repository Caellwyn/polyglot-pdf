/**
 * Types for VAD Tuning Dashboard
 */

export interface VADConfig {
	// VAD library params (from useDemoVAD.ts)
	positiveSpeechThreshold: number  // 0.0 - 1.0
	negativeSpeechThreshold: number  // 0.0 - 1.0
	minSpeechMs: number              // milliseconds
	redemptionMs: number             // milliseconds
}

export interface EnergyDataPoint {
	timestamp: number         // Unix timestamp (ms)
	energy: number           // 0-100 from audio worklet
	userSpeaking: boolean    // VAD detected user speech
	geminiSpeaking: boolean  // AI is playing audio
}

export type VADEventType = 
	| 'speech_start'
	| 'speech_end'
	| 'vad_misfire'
	| 'calibration_complete'

export interface VADEvent {
	timestamp: number
	type: VADEventType
	energy: number
	metadata?: {
		duration?: number      // For speech_end events
		baselineEnergy?: number // For calibration_complete
	}
}

export interface VADMetrics {
	// Speech detection stats
	totalSpeechEvents: number
	totalMisfires: number
	averageSpeechDuration: number  // ms
	
	// False positive/negative tracking
	falsePositiveRate: number      // % (0-100)
	falseNegativeRate: number      // % (0-100)
	
	// Timing stats
	lastSpeechStartTime: number | null
	lastSpeechEndTime: number | null
	currentSpeechDuration: number  // ms (if currently speaking)
	
	// Energy stats
	currentEnergy: number
	baselineEnergy: number
	peakEnergy: number
}

export interface VADConfigPreset {
	name: string
	description: string
	config: VADConfig
}

// Preset configurations for different scenarios
export const VAD_PRESETS: VADConfigPreset[] = [
	{
		name: 'Default',
		description: 'Balanced settings for general use',
		config: {
			positiveSpeechThreshold: 0.95,
			negativeSpeechThreshold: 0.75,
			minSpeechMs: 250,
			redemptionMs: 400,
		}
	},
	{
		name: 'Sensitive',
		description: 'Catches quiet speech, may have false positives',
		config: {
			positiveSpeechThreshold: 0.85,
			negativeSpeechThreshold: 0.65,
			minSpeechMs: 150,
			redemptionMs: 300,
		}
	},
	{
		name: 'Conservative',
		description: 'Reduces false positives, may miss quiet speech',
		config: {
			positiveSpeechThreshold: 0.98,
			negativeSpeechThreshold: 0.85,
			minSpeechMs: 400,
			redemptionMs: 500,
		}
	},
	{
		name: 'Fast Response',
		description: 'Quick barge-in, may be choppy',
		config: {
			positiveSpeechThreshold: 0.90,
			negativeSpeechThreshold: 0.70,
			minSpeechMs: 100,
			redemptionMs: 200,
		}
	}
]
