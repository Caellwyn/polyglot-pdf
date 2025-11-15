/**
 * Unit tests for half-cascade state management
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import {
	createHalfCascadeState,
	loadHalfCascadeState,
	saveHalfCascadeState,
	clearHalfCascadeState,
	updateProcessingStatus,
	updateLanguageStatus,
	updateWithTranscript,
	updateWithError,
	setAudioBuffer,
	resetProcessingState,
	shouldShowLatencyWarning,
	getCurrentLatency,
	formatLatency
} from './halfCascadeState'
import type {
	ProcessingStatusMessage,
	LanguageStatusMessage,
	TranscriptMessage,
	HalfCascadeError
} from './halfCascadeTypes'

describe('Half-Cascade State Initialization', () => {
	beforeEach(() => {
		sessionStorage.clear()
	})

	afterEach(() => {
		sessionStorage.clear()
	})

	it('should create empty state', () => {
		const state = createHalfCascadeState()

		expect(state.isProcessing).toBe(false)
		expect(state.currentStage).toBeNull()
		expect(state.processingProgress).toBeNull()
		expect(state.detectedLanguage).toBeNull()
		expect(state.currentLanguage).toBeNull()
		expect(state.languageConfidence).toBeNull()
		expect(state.conversationHistory).toEqual([])
		expect(state.audioBuffer).toBeNull()
		expect(state.isBuffering).toBe(false)
		expect(state.lastError).toBeNull()
	})

	it('should load empty state when none exists', () => {
		const state = loadHalfCascadeState()
		expect(state).toEqual(createHalfCascadeState())
	})

	it('should save and load state', () => {
		const state = createHalfCascadeState()
		state.detectedLanguage = 'es-ES'
		state.currentLanguage = 'en-US'

		saveHalfCascadeState(state)

		const loaded = loadHalfCascadeState()
		expect(loaded.detectedLanguage).toBe('es-ES')
		expect(loaded.currentLanguage).toBe('en-US')
	})

	it('should clear state', () => {
		const state = createHalfCascadeState()
		state.detectedLanguage = 'es-ES'
		saveHalfCascadeState(state)

		clearHalfCascadeState()

		const loaded = loadHalfCascadeState()
		expect(loaded).toEqual(createHalfCascadeState())
	})
})

describe('Half-Cascade Processing Status', () => {
	beforeEach(() => {
		sessionStorage.clear()
	})

	afterEach(() => {
		sessionStorage.clear()
	})

	it('should update processing status', () => {
		let state = createHalfCascadeState()

		const message: ProcessingStatusMessage = {
			type: 'processing_status',
			stage: 'transcribing',
			progress: 50
		}

		state = updateProcessingStatus(state, message)

		expect(state.currentStage).toBe('transcribing')
		expect(state.processingProgress).toBe(50)
		expect(state.isProcessing).toBe(true)
	})

	it('should start processing timer on buffering stage', () => {
		let state = createHalfCascadeState()

		const message: ProcessingStatusMessage = {
			type: 'processing_status',
			stage: 'buffering'
		}

		state = updateProcessingStatus(state, message)

		expect(state.isProcessing).toBe(true)
		expect(state.lastProcessingStartTime).not.toBeNull()
	})

	it('should end processing timer on synthesis complete', () => {
		let state = createHalfCascadeState()

		// Start processing
		state = updateProcessingStatus(state, {
			type: 'processing_status',
			stage: 'transcribing'
		})

		const startTime = state.lastProcessingStartTime

		// Complete synthesis
		state = updateProcessingStatus(state, {
			type: 'processing_status',
			stage: 'synthesizing',
			progress: 100
		})

		expect(state.isProcessing).toBe(false)
		expect(state.lastProcessingEndTime).not.toBeNull()
		expect(state.averageLatency).not.toBeNull()
	})

	it('should calculate exponential moving average latency', () => {
		let state = createHalfCascadeState()

		// First processing cycle (100ms)
		state.lastProcessingStartTime = Date.now()
		setTimeout(() => {
			state = updateProcessingStatus(state, {
				type: 'processing_status',
				stage: 'synthesizing',
				progress: 100
			})

			const firstLatency = state.averageLatency

			// Second processing cycle (200ms)
			state = updateProcessingStatus(state, {
				type: 'processing_status',
				stage: 'transcribing'
			})

			setTimeout(() => {
				state = updateProcessingStatus(state, {
					type: 'processing_status',
					stage: 'synthesizing',
					progress: 100
				})

				// Average should be between first and second latency
				// Formula: 0.3 * new + 0.7 * old
				expect(state.averageLatency).not.toEqual(firstLatency)
			}, 100)
		}, 100)
	})
})

describe('Half-Cascade Language Status', () => {
	beforeEach(() => {
		sessionStorage.clear()
	})

	afterEach(() => {
		sessionStorage.clear()
	})

	it('should update language status', () => {
		let state = createHalfCascadeState()

		const message: LanguageStatusMessage = {
			type: 'language_status',
			detected: 'es-ES',
			current: 'en-US',
			confidence: 0.95
		}

		state = updateLanguageStatus(state, message)

		expect(state.detectedLanguage).toBe('es-ES')
		expect(state.currentLanguage).toBe('en-US')
		expect(state.languageConfidence).toBe(0.95)
	})
})

describe('Half-Cascade Transcript Handling', () => {
	beforeEach(() => {
		sessionStorage.clear()
	})

	afterEach(() => {
		sessionStorage.clear()
	})

	it('should update state with transcript', () => {
		let state = createHalfCascadeState()

		// Set processing state
		state.isProcessing = true
		state.currentStage = 'synthesizing'

		const message: TranscriptMessage = {
			type: 'transcript',
			user_transcript: 'Hello',
			assistant_response: 'Hi there!',
			language: 'en-US'
		}

		state = updateWithTranscript(state, message)

		expect(state.isProcessing).toBe(false)
		expect(state.currentStage).toBeNull()
		expect(state.processingProgress).toBeNull()
	})
})

describe('Half-Cascade Error Handling', () => {
	beforeEach(() => {
		sessionStorage.clear()
	})

	afterEach(() => {
		sessionStorage.clear()
	})

	it('should update state with error', () => {
		let state = createHalfCascadeState()

		state.isProcessing = true
		state.currentStage = 'transcribing'

		const error: HalfCascadeError = {
			type: 'half_cascade_error',
			error_code: 'ASR_FAILED',
			message: 'ASR processing failed',
			fallback_activated: true,
			recoverable: false
		}

		state = updateWithError(state, error)

		expect(state.lastError).toEqual(error)
		expect(state.isProcessing).toBe(false)
		expect(state.currentStage).toBeNull()
	})
})

describe('Half-Cascade Audio Buffer', () => {
	it('should set audio buffer', () => {
		let state = createHalfCascadeState()

		const buffer = new ArrayBuffer(1024)
		state = setAudioBuffer(state, buffer)

		expect(state.audioBuffer).toBe(buffer)
		expect(state.isBuffering).toBe(true)
	})

	it('should clear audio buffer', () => {
		let state = createHalfCascadeState()

		const buffer = new ArrayBuffer(1024)
		state = setAudioBuffer(state, buffer)
		expect(state.isBuffering).toBe(true)

		state = setAudioBuffer(state, null)
		expect(state.audioBuffer).toBeNull()
		expect(state.isBuffering).toBe(false)
	})
})

describe('Half-Cascade State Reset', () => {
	beforeEach(() => {
		sessionStorage.clear()
	})

	afterEach(() => {
		sessionStorage.clear()
	})

	it('should reset processing state', () => {
		let state = createHalfCascadeState()

		// Set various processing state
		state.isProcessing = true
		state.currentStage = 'transcribing'
		state.processingProgress = 50
		state.lastProcessingStartTime = Date.now()
		state.lastError = {
			type: 'half_cascade_error',
			error_code: 'TEST',
			message: 'Test error',
			fallback_activated: false,
			recoverable: true
		}

		state = resetProcessingState(state)

		expect(state.isProcessing).toBe(false)
		expect(state.currentStage).toBeNull()
		expect(state.processingProgress).toBeNull()
		expect(state.lastProcessingStartTime).toBeNull()
		expect(state.lastProcessingEndTime).toBeNull()
		expect(state.lastError).toBeNull()
	})
})

describe('Half-Cascade Latency Tracking', () => {
	it('should not show warning when not processing', () => {
		const state = createHalfCascadeState()
		expect(shouldShowLatencyWarning(state)).toBe(false)
	})

	it('should not show warning when latency is low', () => {
		const state = createHalfCascadeState()
		state.lastProcessingStartTime = Date.now() - 1000  // 1 second ago
		expect(shouldShowLatencyWarning(state)).toBe(false)
	})

	it('should show warning when latency exceeds 2 seconds', () => {
		const state = createHalfCascadeState()
		state.lastProcessingStartTime = Date.now() - 3000  // 3 seconds ago
		expect(shouldShowLatencyWarning(state)).toBe(true)
	})

	it('should get current latency', () => {
		const state = createHalfCascadeState()
		state.lastProcessingStartTime = Date.now() - 1500
		state.isProcessing = true

		const latency = getCurrentLatency(state)
		expect(latency).toBeGreaterThanOrEqual(1400)  // Allow for timing variance
		expect(latency).toBeLessThan(1700)
	})

	it('should return null latency when not processing', () => {
		const state = createHalfCascadeState()
		expect(getCurrentLatency(state)).toBeNull()
	})

	it('should format latency in milliseconds', () => {
		expect(formatLatency(500)).toBe('500ms')
		expect(formatLatency(999)).toBe('999ms')
	})

	it('should format latency in seconds', () => {
		expect(formatLatency(1000)).toBe('1.0s')
		expect(formatLatency(1500)).toBe('1.5s')
		expect(formatLatency(2345)).toBe('2.3s')
	})

	it('should format null latency', () => {
		expect(formatLatency(null)).toBe('N/A')
	})
})
