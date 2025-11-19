/**
 * Tests for useDemoVAD hook
 * 
 * Verifies the VAD library integration exposes the correct interface
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useDemoVAD } from './useDemoVAD'

// Mock the @ricky0123/vad-react library
vi.mock('@ricky0123/vad-react', () => ({
	useMicVAD: vi.fn(() => ({
		userSpeaking: false,
		loading: false,
		errored: false,
		listening: false,
		pause: vi.fn(),
		start: vi.fn(),
		toggle: vi.fn(),
	})),
}))

describe('useDemoVAD Hook', () => {
	beforeEach(() => {
		// Reset mock before each test
		vi.clearAllMocks()
	})

	it('should initialize with correct default state', () => {
		const { result } = renderHook(() => useDemoVAD())

		expect(result.current.userSpeaking).toBe(false)
		expect(result.current.loading).toBe(false)
		expect(result.current.errored).toBe(false)
		expect(typeof result.current.pause).toBe('function')
		expect(typeof result.current.start).toBe('function')
	})

	it('should expose pause and start functions', () => {
		const { result } = renderHook(() => useDemoVAD())

		// Functions should be defined
		expect(result.current.pause).toBeDefined()
		expect(result.current.start).toBeDefined()
		
		// Should be callable without throwing
		expect(() => result.current.pause()).not.toThrow()
		expect(() => result.current.start()).not.toThrow()
	})

	it('should accept optional callbacks without throwing', () => {
		const onSpeechStart = vi.fn()
		const onSpeechEnd = vi.fn()
		const onVADMisfire = vi.fn()

		// Should not throw when providing callbacks
		expect(() => {
			renderHook(() => useDemoVAD({
				onSpeechStart,
				onSpeechEnd,
				onVADMisfire,
			}))
		}).not.toThrow()
	})

	it('should work without any callbacks', () => {
		// Should not throw when callbacks are not provided
		expect(() => {
			renderHook(() => useDemoVAD())
		}).not.toThrow()
	})

	it('should pass configuration to useMicVAD', async () => {
		const { useMicVAD } = await import('@ricky0123/vad-react')
		
		renderHook(() => useDemoVAD())

		// Verify useMicVAD was called at least once
		expect(useMicVAD).toHaveBeenCalled()
		
		// Verify it was called with a config object
		const callArgs = vi.mocked(useMicVAD).mock.calls[0]
		expect(callArgs).toBeDefined()
		expect(callArgs[0]).toBeTypeOf('object')
	})
})
