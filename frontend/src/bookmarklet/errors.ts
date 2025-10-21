/**
 * Error Catalog - Step S7
 * 
 * User-friendly, actionable error messages.
 * No technical jargon, clear next steps.
 */

export type ErrorCode =
	| 'CSP_BLOCKED'
	| 'MIC_DENIED'
	| 'NO_FIELDS'
	| 'WS_FAILED'
	| 'PARSE_FAILED'
	| 'INJECT_FAILED'
	| 'UNKNOWN'

export interface ErrorInfo {
	code: ErrorCode
	title: string
	message: string
	action?: string
	icon: string
}

/**
 * Get user-friendly error information
 */
export function getErrorInfo(code: ErrorCode, details?: string): ErrorInfo {
	const catalog: Record<ErrorCode, ErrorInfo> = {
		CSP_BLOCKED: {
			code: 'CSP_BLOCKED',
			icon: '🔒',
			title: 'Site Security Restriction',
			message: 'This website blocks external scripts for security.',
			action: 'Try a different demo site or use a local test page.',
		},
		MIC_DENIED: {
			code: 'MIC_DENIED',
			icon: '🎤',
			title: 'Microphone Access Denied',
			message: 'Voice filling requires microphone permission.',
			action: 'Click the 🎤 icon in your browser address bar → Allow → Retry',
		},
		NO_FIELDS: {
			code: 'NO_FIELDS',
			icon: '📝',
			title: 'No Form Fields Found',
			message: 'No fillable form fields detected on this page.',
			action: 'Navigate to a page with a form and try again.',
		},
		WS_FAILED: {
			code: 'WS_FAILED',
			icon: '🔌',
			title: 'Connection Lost',
			message: details || 'Lost connection to voice service.',
			action: 'Click Reconnect to try again.',
		},
		PARSE_FAILED: {
			code: 'PARSE_FAILED',
			icon: '⚠️',
			title: 'Form Parse Error',
			message: details || 'Could not analyze form fields.',
			action: 'Click Rescan or refresh the page.',
		},
		INJECT_FAILED: {
			code: 'INJECT_FAILED',
			icon: '❌',
			title: 'Injection Failed',
			message: details || 'Could not load voice form filler.',
			action: 'Refresh the page and try again.',
		},
		UNKNOWN: {
			code: 'UNKNOWN',
			icon: '❓',
			title: 'Unexpected Error',
			message: details || 'Something went wrong.',
			action: 'Refresh the page or contact support.',
		},
	}

	return catalog[code]
}

/**
 * Detect CSP violations
 * Returns true if CSP is blocking scripts
 */
export function detectCSP(): boolean {
	try {
		// Try to create a function - CSP with script-src restrictions will block this
		new Function('return true')()
		return false // No CSP blocking
	} catch (error) {
		console.warn('[VFF CSP] Content Security Policy detected:', error)
		return true // CSP is blocking
	}
}

/**
 * Format error for logging
 */
export function formatErrorForLog(error: unknown, context?: string): string {
	const prefix = context ? `[${context}] ` : ''
	
	if (error instanceof Error) {
		return `${prefix}${error.message} (${error.name})`
	}
	
	if (typeof error === 'string') {
		return `${prefix}${error}`
	}
	
	return `${prefix}${String(error)}`
}
