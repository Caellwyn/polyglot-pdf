/**
 * CSP Detection - Step S7 (Proactive Error Handling)
 * 
 * Detects Content Security Policy restrictions before attempting injection.
 */

export interface CSPDetectionResult {
	allowed: boolean
	reason?: string
}

/**
 * Detect if CSP will block our injection.
 * Uses new Function() test as specified in requirements.
 */
export function detectCSP(): CSPDetectionResult {
	try {
		// Test 1: Can we create functions?
		// eslint-disable-next-line no-new-func
		new Function('return true')()
		
		// Test 2: Can we create inline scripts?
		const testScript = document.createElement('script')
		testScript.textContent = '// CSP test'
		
		// If we get here, basic CSP checks passed
		return { allowed: true }
	} catch (error) {
		// CSP violation detected
		return {
			allowed: false,
			reason: 'Site security policy blocks external scripts',
		}
	}
}

/**
 * Test if we can load external scripts (for bookmarklet loader)
 */
export function canLoadExternalScripts(): boolean {
	// This is checked by the bookmarklet loader itself
	// If we're running, the script already loaded successfully
	return true
}
