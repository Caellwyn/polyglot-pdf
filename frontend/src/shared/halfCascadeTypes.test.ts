/**
 * Unit tests for half-cascade types and utilities
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import {
	SUPPORTED_LANGUAGE_CODES,
	LANGUAGE_DISPLAY_NAMES,
	isSupportedLanguageCode,
	getLanguageDisplayName,
	loadConversationHistory,
	saveConversationHistory,
	appendToConversationHistory,
	clearConversationHistory,
	serializeFormState,
	createAudioEndMessage
} from './halfCascadeTypes'

describe('Half-Cascade Language Support', () => {
	it('should have 20 supported language codes', () => {
		expect(SUPPORTED_LANGUAGE_CODES).toHaveLength(20)
	})

	it('should have display names for all supported languages', () => {
		for (const code of SUPPORTED_LANGUAGE_CODES) {
			expect(LANGUAGE_DISPLAY_NAMES[code]).toBeDefined()
			expect(LANGUAGE_DISPLAY_NAMES[code]).not.toBe('')
		}
	})

	it('should validate supported language codes', () => {
		expect(isSupportedLanguageCode('en-US')).toBe(true)
		expect(isSupportedLanguageCode('es-ES')).toBe(true)
		expect(isSupportedLanguageCode('invalid')).toBe(false)
		expect(isSupportedLanguageCode('en')).toBe(false)  // Must be BCP 47 format
	})

	it('should get display name for valid language code', () => {
		expect(getLanguageDisplayName('en-US')).toBe('English (US)')
		expect(getLanguageDisplayName('es-ES')).toBe('Spanish (Spain)')
	})

	it('should return fallback for invalid language code', () => {
		expect(getLanguageDisplayName('invalid-CODE')).toBe('invalid-CODE')
	})
})

describe('Half-Cascade Conversation History', () => {
	beforeEach(() => {
		// Clear sessionStorage before each test
		sessionStorage.clear()
	})

	afterEach(() => {
		sessionStorage.clear()
	})

	it('should return empty array when no history exists', () => {
		const history = loadConversationHistory()
		expect(history).toEqual([])
	})

	it('should save and load conversation history', () => {
		const history = [
			{ role: 'user', content: 'Hello' },
			{ role: 'assistant', content: 'Hi there!' }
		]

		saveConversationHistory(history)

		const loaded = loadConversationHistory()
		expect(loaded).toEqual(history)
	})

	it('should append to conversation history', () => {
		// Start with empty history
		expect(loadConversationHistory()).toEqual([])

		// Append first exchange
		appendToConversationHistory('Hello', 'Hi there!')

		const history1 = loadConversationHistory()
		expect(history1).toHaveLength(2)
		expect(history1[0]).toEqual({ role: 'user', content: 'Hello' })
		expect(history1[1]).toEqual({ role: 'assistant', content: 'Hi there!' })

		// Append second exchange
		appendToConversationHistory('How are you?', 'I am doing well!')

		const history2 = loadConversationHistory()
		expect(history2).toHaveLength(4)
		expect(history2[2]).toEqual({ role: 'user', content: 'How are you?' })
		expect(history2[3]).toEqual({ role: 'assistant', content: 'I am doing well!' })
	})

	it('should limit conversation history to max entries', () => {
		// Append 15 exchanges (30 turns) - max is 20
		for (let i = 0; i < 15; i++) {
			appendToConversationHistory(`User message ${i}`, `Assistant response ${i}`)
		}

		const history = loadConversationHistory()
		expect(history).toHaveLength(20)  // Should be trimmed to 20

		// Should keep the most recent entries
		expect(history[0].content).toContain('User message 5')  // Oldest kept
		expect(history[history.length - 1].content).toContain('Assistant response 14')  // Newest
	})

	it('should clear conversation history', () => {
		appendToConversationHistory('Test', 'Response')
		expect(loadConversationHistory()).toHaveLength(2)

		clearConversationHistory()
		expect(loadConversationHistory()).toEqual([])
	})
})

describe('Half-Cascade Form State Serialization', () => {
	it('should serialize empty field values', () => {
		const result = serializeFormState({})
		expect(result).toBe('')
	})

	it('should serialize single field value', () => {
		const fieldValues = {
			firstName: { value: 'John' }
		}

		const result = serializeFormState(fieldValues)
		expect(result).toBe('firstName:John')
	})

	it('should serialize multiple field values', () => {
		const fieldValues = {
			firstName: { value: 'John' },
			lastName: { value: 'Smith' },
			age: { value: 30 }
		}

		const result = serializeFormState(fieldValues)

		// Should contain all fields (order may vary)
		expect(result).toContain('firstName:John')
		expect(result).toContain('lastName:Smith')
		expect(result).toContain('age:30')

		// Should be pipe-separated
		expect(result.split('|')).toHaveLength(3)
	})

	it('should skip null/undefined/empty values', () => {
		const fieldValues = {
			firstName: { value: 'John' },
			middleName: { value: null },
			lastName: { value: undefined },
			suffix: { value: '' }
		}

		const result = serializeFormState(fieldValues)
		expect(result).toBe('firstName:John')
	})

	it('should escape pipe and colon characters', () => {
		const fieldValues = {
			notes: { value: 'Text with | pipes and : colons' }
		}

		const result = serializeFormState(fieldValues)
		expect(result).toBe('notes:Text with \\| pipes and \\: colons')
	})

	it('should handle FieldValue wrapper objects', () => {
		const fieldValues = {
			firstName: { value: 'John', confirmed: true },
			lastName: { value: 'Smith', confirmed: false }
		}

		const result = serializeFormState(fieldValues)
		expect(result).toContain('firstName:John')
		expect(result).toContain('lastName:Smith')
	})

	it('should handle primitive values without wrapper', () => {
		const fieldValues = {
			firstName: 'John',
			age: 30,
			active: true
		}

		const result = serializeFormState(fieldValues)
		expect(result).toContain('firstName:John')
		expect(result).toContain('age:30')
		expect(result).toContain('active:true')
	})
})

describe('Half-Cascade Message Helpers', () => {
	it('should create audio_end message', () => {
		const message = createAudioEndMessage(
			'base64AudioData',
			'field1:value1|field2:value2',
			'currentFieldId',
			'part_1',
			[
				{ role: 'user', content: 'Hello' },
				{ role: 'assistant', content: 'Hi!' }
			]
		)

		expect(message.type).toBe('audio_end')
		expect(message.audio_data).toBe('base64AudioData')
		expect(message.form_state).toBe('field1:value1|field2:value2')
		expect(message.current_field).toBe('currentFieldId')
		expect(message.current_part).toBe('part_1')
		expect(message.conversation_history).toHaveLength(2)
	})
})
