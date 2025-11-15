/**
 * Half-Cascade Message Types
 *
 * TypeScript definitions for half-cascade WebSocket protocol.
 * Mirrors backend/models/websocket_messages.py
 */

// ============================================================================
// Half-Cascade Message Types (New)
// ============================================================================

export interface AudioEndMessage {
	type: "audio_end"
	audio_data: string  // base64 encoded complete audio buffer
	form_state: string  // "field_id:value|field_id2:value2" format
	current_field: string  // Current field ID
	current_part: string  // Current part ID
	conversation_history: Array<{ role: string; content: string }>
}

export interface ProcessingStatusMessage {
	type: "processing_status"
	stage: "buffering" | "transcribing" | "generating" | "synthesizing"
	progress?: number  // 0-100 percentage (optional)
}

export interface LanguageStatusMessage {
	type: "language_status"
	detected: string  // Detected language code (e.g., "es-ES")
	current: string  // Currently active language
	confidence: number  // Detection confidence (0.0-1.0)
}

export interface TranscriptMessage {
	type: "transcript"
	user_transcript: string  // User's spoken words (transcribed)
	assistant_response: string  // AI's text response (before TTS)
	language: string  // Language code
}

export interface AudioResponseChunk {
	type: "audio_response"
	data: string  // base64 encoded audio chunk
	language: string  // Language of this segment
	is_final: boolean  // True for last chunk
}

export interface HalfCascadeError {
	type: "half_cascade_error"
	error_code: string
	message: string
	fallback_activated: boolean  // True if falling back to Live API
	recoverable: boolean  // True if retry possible
}

// ============================================================================
// Half-Cascade State
// ============================================================================

export interface HalfCascadeState {
	// Processing state
	isProcessing: boolean
	currentStage: ProcessingStatusMessage["stage"] | null
	processingProgress: number | null

	// Language state
	detectedLanguage: string | null
	currentLanguage: string | null
	languageConfidence: number | null

	// Conversation history (stored in sessionStorage)
	conversationHistory: Array<{ role: string; content: string }>

	// Audio buffering
	audioBuffer: ArrayBuffer | null
	isBuffering: boolean

	// Error state
	lastError: HalfCascadeError | null

	// Latency tracking
	lastProcessingStartTime: number | null
	lastProcessingEndTime: number | null
	averageLatency: number | null
}

// ============================================================================
// BCP 47 Language Codes
// ============================================================================

/**
 * Supported languages with BCP 47 codes
 * Source: backend/config.py::HALF_CASCADE_SUPPORTED_LANGUAGES
 */
export const SUPPORTED_LANGUAGE_CODES = [
	"en-US", "es-ES", "zh-CN", "zh-TW", "ko-KR",
	"ar-SA", "fr-FR", "pt-BR", "ru-RU", "ja-JP",
	"hi-IN", "de-DE", "it-IT", "vi-VN", "tl-PH",
	"bn-BD", "ur-PK", "fa-IR", "tr-TR", "pl-PL"
] as const

export type LanguageCode = typeof SUPPORTED_LANGUAGE_CODES[number]

/**
 * Language display names mapped to BCP 47 codes
 */
export const LANGUAGE_DISPLAY_NAMES: Record<LanguageCode, string> = {
	"en-US": "English (US)",
	"es-ES": "Spanish (Spain)",
	"zh-CN": "Chinese (Simplified)",
	"zh-TW": "Chinese (Traditional)",
	"ko-KR": "Korean",
	"ar-SA": "Arabic (Saudi Arabia)",
	"fr-FR": "French (France)",
	"pt-BR": "Portuguese (Brazil)",
	"ru-RU": "Russian",
	"ja-JP": "Japanese",
	"hi-IN": "Hindi",
	"de-DE": "German",
	"it-IT": "Italian",
	"vi-VN": "Vietnamese",
	"tl-PH": "Tagalog (Philippines)",
	"bn-BD": "Bengali (Bangladesh)",
	"ur-PK": "Urdu (Pakistan)",
	"fa-IR": "Persian (Iran)",
	"tr-TR": "Turkish",
	"pl-PL": "Polish"
}

/**
 * Helper to check if a language code is supported
 */
export function isSupportedLanguageCode(code: string): code is LanguageCode {
	return SUPPORTED_LANGUAGE_CODES.includes(code as LanguageCode)
}

/**
 * Get display name for a language code (with fallback)
 */
export function getLanguageDisplayName(code: string): string {
	if (isSupportedLanguageCode(code)) {
		return LANGUAGE_DISPLAY_NAMES[code]
	}
	return code  // Fallback to raw code
}

// ============================================================================
// Conversation History Management
// ============================================================================

const CONVERSATION_HISTORY_KEY = "vff_half_cascade_conversation_history"
const MAX_CONVERSATION_HISTORY = 20  // Keep last 20 turns (10 exchanges)

/**
 * Load conversation history from sessionStorage
 */
export function loadConversationHistory(): Array<{ role: string; content: string }> {
	try {
		const stored = sessionStorage.getItem(CONVERSATION_HISTORY_KEY)
		if (!stored) return []
		return JSON.parse(stored)
	} catch (error) {
		console.error("[HalfCascade] Failed to load conversation history:", error)
		return []
	}
}

/**
 * Save conversation history to sessionStorage (keeps last N turns)
 */
export function saveConversationHistory(history: Array<{ role: string; content: string }>): void {
	try {
		// Keep only the most recent entries
		const trimmed = history.slice(-MAX_CONVERSATION_HISTORY)
		sessionStorage.setItem(CONVERSATION_HISTORY_KEY, JSON.stringify(trimmed))
	} catch (error) {
		console.error("[HalfCascade] Failed to save conversation history:", error)
	}
}

/**
 * Append to conversation history (user + assistant pair)
 */
export function appendToConversationHistory(
	userTranscript: string,
	assistantResponse: string
): void {
	const history = loadConversationHistory()
	history.push({ role: "user", content: userTranscript })
	history.push({ role: "assistant", content: assistantResponse })
	saveConversationHistory(history)
}

/**
 * Clear conversation history
 */
export function clearConversationHistory(): void {
	sessionStorage.removeItem(CONVERSATION_HISTORY_KEY)
}

// ============================================================================
// Form State Serialization for Half-Cascade
// ============================================================================

/**
 * Serialize form state to compact pipe-separated format
 * Format: "field_id:value|field_id2:value2"
 */
export function serializeFormState(fieldValues: Record<string, any>): string {
	const pairs: string[] = []

	for (const [fieldId, fieldValue] of Object.entries(fieldValues)) {
		// Extract actual value (handle FieldValue wrapper)
		const value = fieldValue?.value ?? fieldValue

		// Skip null/undefined/empty values
		if (value === null || value === undefined || value === '') continue

		// Escape pipe and colon characters
		const escapedValue = String(value)
			.replace(/\|/g, '\\|')
			.replace(/:/g, '\\:')

		pairs.push(`${fieldId}:${escapedValue}`)
	}

	return pairs.join('|')
}

/**
 * Helper to create audio_end message
 */
export function createAudioEndMessage(
	audioData: string,
	formState: string,
	currentField: string,
	currentPart: string,
	conversationHistory: Array<{ role: string; content: string }>
): AudioEndMessage {
	return {
		type: "audio_end",
		audio_data: audioData,
		form_state: formState,
		current_field: currentField,
		current_part: currentPart,
		conversation_history: conversationHistory
	}
}
