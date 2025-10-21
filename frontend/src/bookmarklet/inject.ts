/**
 * Injection Logic - Step S2 (Idempotent Injection) + S7 (Error Handling)
 * 
 * Handles safe, repeatable injection and initialization with error handling.
 */

import type { InjectOptions } from './index'
import { createOverlay } from './overlay'
import { detectCSP } from './csp-detection'
import { parsePageForms, getLargeFormWarning } from './parser'
import { getErrorInfo, formatErrorForLog } from './errors'
import { WebFormStateManager } from '../webFormState'

// Global mutex key
const MUTEX_KEY = '__VFF_ACTIVE__'
const CONTAINER_ID = 'voice-form-filler-root'

/**
 * Inject the voice form filler overlay.
 * Idempotent - safe to call multiple times.
 */
export function inject(options: InjectOptions = {}): void {
	// Step 1: Check mutex - no-op if already active
	if ((window as any)[MUTEX_KEY]) {
		console.log('[VoiceFormFiller] Already active, ignoring inject() call')
		return
	}

	// Step 2: Detect CSP restrictions (S7)
	const cspResult = detectCSP()
	if (!cspResult.allowed) {
		const errorInfo = getErrorInfo('CSP_BLOCKED')
		console.error('[VoiceFormFiller] CSP restriction detected:', cspResult.reason)
		showErrorMessage(errorInfo)
		return
	}

	try {
		// Step 3: Parse form fields (S4)
		const parseResult = parsePageForms()

		// Handle no fields scenario (S7)
		if (!parseResult.success && parseResult.error === 'NO_FIELDS') {
			const errorInfo = getErrorInfo('NO_FIELDS')
			console.warn('[VoiceFormFiller] No form fields found on page')
			showErrorMessage(errorInfo)
			return
		}

		// Handle parse failure (S7)
		if (!parseResult.success) {
			const errorInfo = getErrorInfo('PARSE_FAILED', parseResult.error)
			console.error('[VoiceFormFiller] Form parsing failed:', parseResult.error)
			showErrorMessage(errorInfo)
			return
		}

		// Log parse stats
		console.log('[VoiceFormFiller] Form parsed:', parseResult.stats)

		// Check for large form warnings
		const warning = getLargeFormWarning(parseResult.stats.fieldCount)
		if (warning) {
			console.warn('[VoiceFormFiller]', warning)
		}

		// Step 3.5: Restore DOM from sessionStorage if available (Bug Fix: Oct 9, 2025)
		restoreFormFieldsFromStorage()
		console.log('[VoiceFormFiller] Restored form fields from sessionStorage')

		// Step 4: Create container element
		const container = document.createElement('div')
		container.id = CONTAINER_ID
		container.style.cssText = `
			position: fixed;
			top: 0;
			left: 0;
			width: 100%;
			height: 100%;
			pointer-events: none;
			z-index: ${options.zIndex || 9999};
		`

		// Step 5: Attach to DOM
		document.body.appendChild(container)

		// Step 6: Create overlay with Shadow DOM
		createOverlay(container, options, parseResult)

		// Step 7: Set mutex
		;(window as any)[MUTEX_KEY] = true

		console.log('[VoiceFormFiller] Injection successful')
	} catch (error) {
		console.error('[VoiceFormFiller] Injection failed:', error)
		// Show error message (S7)
		const errorInfo = getErrorInfo('INJECT_FAILED', formatErrorForLog(error))
		showErrorMessage(errorInfo)
		
		// Clean up on failure
		const existingContainer = document.getElementById(CONTAINER_ID)
		if (existingContainer) {
			existingContainer.remove()
		}
	}
}

/**
 * Show error message to user (S7)
 */
function showErrorMessage(errorInfo: ReturnType<typeof getErrorInfo>): void {
	const message = document.createElement('div')
	const isBlocking = ['CSP_BLOCKED', 'NO_FIELDS'].includes(errorInfo.code)
	
	message.style.cssText = `
		position: fixed;
		top: ${isBlocking ? '50%' : '20px'};
		left: ${isBlocking ? '50%' : 'auto'};
		right: ${isBlocking ? 'auto' : '20px'};
		transform: ${isBlocking ? 'translate(-50%, -50%)' : 'none'};
		background: ${isBlocking ? '#ff9800' : '#f44336'};
		color: white;
		padding: 24px 32px;
		border-radius: 8px;
		font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
		font-size: 16px;
		z-index: 999999;
		max-width: 500px;
		box-shadow: 0 4px 12px rgba(0,0,0,0.3);
		text-align: ${isBlocking ? 'center' : 'left'};
	`
	
	message.innerHTML = `
		<div style="font-size: 24px; margin-bottom: 8px;">${errorInfo.icon}</div>
		<strong style="display: block; margin-bottom: 8px;">${errorInfo.title}</strong>
		<div style="font-size: 14px; opacity: 0.9; margin-bottom: ${errorInfo.action ? '12px' : '0'};">
			${errorInfo.message}
		</div>
		${errorInfo.action ? `<div style="font-size: 13px; font-weight: 500;">${errorInfo.action}</div>` : ''}
	`

	document.body.appendChild(message)

	// Auto-remove after delay (longer for blocking errors)
	setTimeout(() => {
		message.remove()
	}, isBlocking ? 10000 : 7000)
}

/**
 * Restore form fields from sessionStorage (Bug Fix: Oct 9, 2025)
 * 
 * When page is refreshed, DOM is cleared but sessionStorage persists.
 * This restores the DOM to match what the model sees.
 */
function restoreFormFieldsFromStorage(): void {
	console.log('[VoiceFormFiller] 🔍 Checking sessionStorage for saved state...')
	const storageData = sessionStorage.getItem('web_form_state')
	console.log('[VoiceFormFiller] sessionStorage contains:', storageData ? `DATA (${storageData.length} chars)` : 'NOTHING')
	
	const state = WebFormStateManager.load()
	
	if (!state || !state.current_values || Object.keys(state.current_values).length === 0) {
		console.log('[VoiceFormFiller] ✅ No saved form state to restore (form will be empty)')
		return
	}
	
	console.log('[VoiceFormFiller] 📦 Found saved state with', Object.keys(state.current_values).length, 'fields')
	let restoredCount = 0
	
	// Iterate through saved values and restore to DOM
	for (const [fieldId, fieldValue] of Object.entries(state.current_values)) {
		if (!fieldValue.value) continue // Skip empty values
		
		const element = document.getElementById(fieldId) as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
		
		if (!element) {
			console.warn('[VoiceFormFiller] Saved field not found in DOM:', fieldId)
			continue
		}
		
		// Restore value based on field type
		if (element.tagName === 'SELECT') {
			const selectEl = element as HTMLSelectElement
			const value = String(fieldValue.value)
			
			// Find matching option
			for (let i = 0; i < selectEl.options.length; i++) {
				const option = selectEl.options[i]
				if (option.value === value || option.text === value) {
					selectEl.selectedIndex = i
					restoredCount++
					break
				}
			}
		} else if (element.tagName === 'INPUT' && (element as HTMLInputElement).type === 'checkbox') {
			(element as HTMLInputElement).checked = Boolean(fieldValue.value)
			restoredCount++
		} else if (element.tagName === 'INPUT' && (element as HTMLInputElement).type === 'radio') {
			if ((element as HTMLInputElement).value === fieldValue.value) {
				(element as HTMLInputElement).checked = true
				restoredCount++
			}
		} else {
			// Text, textarea, etc.
			(element as HTMLInputElement | HTMLTextAreaElement).value = String(fieldValue.value)
			restoredCount++
		}
		
		// If field was AI-confirmed, add visual indicator
		if (fieldValue.confirmed) {
			element.setAttribute('data-vff-confirmed', 'true')
			element.style.outline = '2px solid #10b981'
			element.style.outlineOffset = '2px'
		}
	}
	
	if (restoredCount > 0) {
		console.log(`[VoiceFormFiller] ✅ Restored ${restoredCount} fields from sessionStorage`)
	}
}
