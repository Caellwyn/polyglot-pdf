/**
 * Bookmarklet Entry Point
 * 
 * Exposes global API:
 * - window.VoiceFormFiller.inject(options?)
 * - window.VoiceFormFiller.destroy()
 * 
 * This file is the entry point for the IIFE bundle.
 */

import { inject } from './inject'
import { destroy } from './lifecycle'
import { getVersion } from './version'
import { getConnectionManager } from './overlay'

// Define the public API interface
export interface VoiceFormFillerAPI {
	inject: (options?: InjectOptions) => void
	destroy: () => void
	getVersion: () => string
	isActive: () => boolean
	// Test helper (S6 - expose for test suite)
	_test_getConnectionManager?: () => any
}

export interface InjectOptions {
	// Backend WebSocket URL (defaults to production)
	wsUrl?: string
	// Enable debug logging
	debug?: boolean
	// Custom z-index for overlay
	zIndex?: number
}

// Create the public API object
const VoiceFormFillerAPI: VoiceFormFillerAPI = {
	inject,
	destroy,
	getVersion,
	isActive: () => !!(window as any).__VFF_ACTIVE__,
	// Test helper (S6 - expose for test suite)
	_test_getConnectionManager: getConnectionManager,
}

// Expose on window object
if (typeof window !== 'undefined') {
	(window as any).VoiceFormFiller = VoiceFormFillerAPI
}

// Export for module systems (though IIFE won't use this)
export default VoiceFormFillerAPI
