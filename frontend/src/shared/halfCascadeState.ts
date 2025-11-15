/**
 * Half-Cascade State Manager
 *
 * Manages state for half-cascade processing pipeline.
 * Tracks processing stages, language detection, and latency metrics.
 */

import type {
	HalfCascadeState,
	ProcessingStatusMessage,
	LanguageStatusMessage,
	TranscriptMessage,
	HalfCascadeError
} from "./halfCascadeTypes"

const HALF_CASCADE_STATE_KEY = "vff_half_cascade_state"

/**
 * Initialize empty half-cascade state
 */
export function createHalfCascadeState(): HalfCascadeState {
	return {
		// Processing state
		isProcessing: false,
		currentStage: null,
		processingProgress: null,

		// Language state
		detectedLanguage: null,
		currentLanguage: null,
		languageConfidence: null,

		// Conversation history (stored separately in sessionStorage)
		conversationHistory: [],

		// Audio buffering
		audioBuffer: null,
		isBuffering: false,

		// Error state
		lastError: null,

		// Latency tracking
		lastProcessingStartTime: null,
		lastProcessingEndTime: null,
		averageLatency: null
	}
}

/**
 * Load half-cascade state from sessionStorage
 */
export function loadHalfCascadeState(): HalfCascadeState {
	try {
		const stored = sessionStorage.getItem(HALF_CASCADE_STATE_KEY)
		if (!stored) return createHalfCascadeState()

		const parsed = JSON.parse(stored) as HalfCascadeState
		// Don't persist audio buffer (it's binary data)
		parsed.audioBuffer = null
		return parsed
	} catch (error) {
		console.error("[HalfCascadeState] Failed to load state:", error)
		return createHalfCascadeState()
	}
}

/**
 * Save half-cascade state to sessionStorage
 */
export function saveHalfCascadeState(state: HalfCascadeState): void {
	try {
		// Clone state without audio buffer (can't serialize ArrayBuffer)
		const toSave = { ...state, audioBuffer: null }
		sessionStorage.setItem(HALF_CASCADE_STATE_KEY, JSON.stringify(toSave))
	} catch (error) {
		console.error("[HalfCascadeState] Failed to save state:", error)
	}
}

/**
 * Clear half-cascade state
 */
export function clearHalfCascadeState(): void {
	sessionStorage.removeItem(HALF_CASCADE_STATE_KEY)
}

/**
 * Update state with processing status message
 */
export function updateProcessingStatus(
	state: HalfCascadeState,
	message: ProcessingStatusMessage
): HalfCascadeState {
	const updated = { ...state }

	updated.currentStage = message.stage
	updated.processingProgress = message.progress ?? null

	// Start processing timer on first stage
	if (message.stage === "buffering" || message.stage === "transcribing") {
		updated.isProcessing = true
		if (!updated.lastProcessingStartTime) {
			updated.lastProcessingStartTime = Date.now()
		}
	}

	// End processing timer on synthesis stage
	if (message.stage === "synthesizing" && message.progress === 100) {
		updated.isProcessing = false
		updated.lastProcessingEndTime = Date.now()

		// Calculate latency if we have start time
		if (updated.lastProcessingStartTime) {
			const latency = updated.lastProcessingEndTime - updated.lastProcessingStartTime

			// Update average latency (exponential moving average, alpha = 0.3)
			if (updated.averageLatency === null) {
				updated.averageLatency = latency
			} else {
				updated.averageLatency = Math.round(0.3 * latency + 0.7 * updated.averageLatency)
			}
		}

		// Reset for next turn
		updated.lastProcessingStartTime = null
	}

	saveHalfCascadeState(updated)
	return updated
}

/**
 * Update state with language status message
 */
export function updateLanguageStatus(
	state: HalfCascadeState,
	message: LanguageStatusMessage
): HalfCascadeState {
	const updated = { ...state }

	updated.detectedLanguage = message.detected
	updated.currentLanguage = message.current
	updated.languageConfidence = message.confidence

	saveHalfCascadeState(updated)
	return updated
}

/**
 * Update state with transcript message
 */
export function updateWithTranscript(
	state: HalfCascadeState,
	message: TranscriptMessage
): HalfCascadeState {
	const updated = { ...state }

	// Transcript is saved to sessionStorage by halfCascadeTypes.ts
	// We just track that processing completed
	updated.isProcessing = false
	updated.currentStage = null
	updated.processingProgress = null

	saveHalfCascadeState(updated)
	return updated
}

/**
 * Update state with error message
 */
export function updateWithError(
	state: HalfCascadeState,
	error: HalfCascadeError
): HalfCascadeState {
	const updated = { ...state }

	updated.lastError = error
	updated.isProcessing = false
	updated.currentStage = null
	updated.processingProgress = null

	saveHalfCascadeState(updated)
	return updated
}

/**
 * Set audio buffer (for PTT mode)
 */
export function setAudioBuffer(
	state: HalfCascadeState,
	buffer: ArrayBuffer | null
): HalfCascadeState {
	const updated = { ...state }
	updated.audioBuffer = buffer
	updated.isBuffering = buffer !== null
	// Don't save to sessionStorage (can't serialize ArrayBuffer)
	return updated
}

/**
 * Reset processing state (called when starting new turn)
 */
export function resetProcessingState(state: HalfCascadeState): HalfCascadeState {
	const updated = { ...state }

	updated.isProcessing = false
	updated.currentStage = null
	updated.processingProgress = null
	updated.lastProcessingStartTime = null
	updated.lastProcessingEndTime = null
	updated.lastError = null

	saveHalfCascadeState(updated)
	return updated
}

/**
 * Get latency warning threshold (milliseconds)
 * Returns true if latency exceeds 2 seconds
 */
export function shouldShowLatencyWarning(state: HalfCascadeState): boolean {
	if (!state.lastProcessingStartTime) return false

	const currentLatency = Date.now() - state.lastProcessingStartTime
	return currentLatency > 2000  // 2 second threshold
}

/**
 * Get current latency (milliseconds)
 */
export function getCurrentLatency(state: HalfCascadeState): number | null {
	if (!state.lastProcessingStartTime) return null
	if (!state.isProcessing) return null

	return Date.now() - state.lastProcessingStartTime
}

/**
 * Format latency for display
 */
export function formatLatency(latencyMs: number | null): string {
	if (latencyMs === null) return "N/A"
	if (latencyMs < 1000) return `${latencyMs}ms`
	return `${(latencyMs / 1000).toFixed(1)}s`
}
