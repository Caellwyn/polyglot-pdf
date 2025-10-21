/**
 * Overlay UI - Step S3 (Minimal Overlay UI)
 * 
 * Creates the floating panel with Shadow DOM for style isolation.
 */

import type { InjectOptions } from './index'
import type { ParseResult } from './parser'
import { createConnectionManager, type ConnectionManager } from '../shared/connection'
import { WebFormStateManager } from '../webFormState'
import { SUPPORTED_FILL_LANGUAGES } from '../shared/languages'

// Store active connection
// Module-level connection manager
let connectionManager: ConnectionManager | null = null

/**
 * Get connection manager (for testing)
 */
export function getConnectionManager(): ConnectionManager | null {
	return connectionManager
}

/**
 * Create the overlay UI with Shadow DOM
 */
export function createOverlay(
	container: HTMLElement,
	options: InjectOptions,
	parseResult: ParseResult
): void {
	// Create shadow root for style isolation
	const shadowRoot = container.attachShadow({ mode: 'open' })

	// Create overlay panel
	const panel = document.createElement('div')
	panel.className = 'vff-panel'

	// Add styles to shadow DOM
	const styles = document.createElement('style')
	styles.textContent = getOverlayStyles()
	shadowRoot.appendChild(styles)

	// Create panel content
	panel.innerHTML = `
		<div class="vff-panel-header">
			<span class="vff-title">🎤 Voice Form Filler</span>
			<button class="vff-close" aria-label="Close">×</button>
		</div>
		<div class="vff-panel-body">
			<div class="vff-status">
				<span class="vff-status-icon">✅</span>
				<span class="vff-status-text">Found ${parseResult.stats.fieldCount} fields</span>
			</div>
			<div class="vff-language-selector">
				<label for="vff-fill-language">Fill fields in:</label>
				<select id="vff-fill-language" class="vff-language-dropdown">
					${SUPPORTED_FILL_LANGUAGES.map(lang => 
						`<option value="${lang}" ${lang === 'English' ? 'selected' : ''}>${lang}</option>`
					).join('')}
				</select>
			</div>
			<div class="vff-controls">
				<button class="vff-button vff-connect">Connect to Voice</button>
				<button class="vff-button vff-rescan">Rescan Form</button>
				<button class="vff-button vff-clear-form">🗑️ Clear Form</button>
			</div>
			<div class="vff-error" style="display: none;"></div>
			<div class="vff-info">
				<small>
					Fields: ${parseResult.stats.fieldCount} 
					(${parseResult.stats.requiredCount} required)<br>
					Parse time: ${parseResult.stats.parseTime.toFixed(0)}ms
				</small>
			</div>
		</div>
	`

	shadowRoot.appendChild(panel)

	// Make panel draggable
	makeDraggable(panel)

	// Create connection manager
	if (parseResult.schema) {
		connectionManager = createConnectionManager(parseResult.schema, (status) => {
			updateStatus(shadowRoot, status)
		})
	}

	// Set up event handlers
	setupEventHandlers(shadowRoot, options, parseResult, connectionManager)
}

/**
 * Get CSS styles for the overlay (scoped to Shadow DOM)
 */
function getOverlayStyles(): string {
	return `
		.vff-panel {
			position: fixed;
			top: 20px;
			right: 20px;
			width: 320px;
			background: white;
			border-radius: 12px;
			box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
			font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
			pointer-events: auto;
			user-select: none;
			z-index: 10000;
		}

		.vff-panel-header {
			display: flex;
			justify-content: space-between;
			align-items: center;
			padding: 16px;
			border-bottom: 1px solid #e0e0e0;
			cursor: move;
			background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
			color: white;
			border-radius: 12px 12px 0 0;
		}

		.vff-title {
			font-weight: 600;
			font-size: 16px;
		}

		.vff-close {
			background: none;
			border: none;
			color: white;
			font-size: 24px;
			cursor: pointer;
			padding: 0;
			width: 24px;
			height: 24px;
			line-height: 1;
			opacity: 0.8;
			transition: opacity 0.2s;
		}

		.vff-close:hover {
			opacity: 1;
		}

		.vff-panel-body {
			padding: 16px;
		}

		.vff-status {
			display: flex;
			align-items: center;
			gap: 8px;
			margin-bottom: 16px;
			padding: 12px;
			background: #f5f5f5;
			border-radius: 8px;
		}

		.vff-status-icon {
			font-size: 20px;
		}

		.vff-status-text {
			font-size: 14px;
			font-weight: 500;
		}

		.vff-language-selector {
			margin-bottom: 16px;
			padding: 12px;
			background: #f5f5f5;
			border-radius: 8px;
		}

		.vff-language-selector label {
			display: block;
			font-size: 13px;
			font-weight: 500;
			margin-bottom: 6px;
			color: #333;
		}

		.vff-language-dropdown {
			width: 100%;
			padding: 8px 12px;
			border: 1px solid #ddd;
			border-radius: 6px;
			font-size: 14px;
			font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
			background: white;
			cursor: pointer;
			transition: border-color 0.2s;
		}

		.vff-language-dropdown:hover {
			border-color: #667eea;
		}

		.vff-language-dropdown:focus {
			outline: none;
			border-color: #667eea;
			box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
		}

		.vff-controls {
			display: flex;
			flex-direction: column;
			gap: 8px;
		}

		.vff-button {
			padding: 10px 16px;
			border: none;
			border-radius: 6px;
			font-size: 14px;
			font-weight: 500;
			cursor: pointer;
			transition: all 0.2s;
			background: #667eea;
			color: white;
		}

		.vff-button:hover:not(:disabled) {
			background: #5568d3;
			transform: translateY(-1px);
		}

		.vff-button:disabled {
			opacity: 0.5;
			cursor: not-allowed;
			transform: none;
		}

		.vff-button.vff-recording {
			background: #dc2626;
			animation: pulse 2s ease-in-out infinite;
		}

		.vff-button.vff-recording:hover:not(:disabled) {
			background: #b91c1c;
		}
		
		.vff-button.vff-clear-form {
			background: #dc2626;
		}
		
		.vff-button.vff-clear-form:hover:not(:disabled) {
			background: #b91c1c;
		}

		@keyframes pulse {
			0%, 100% {
				opacity: 1;
			}
			50% {
				opacity: 0.8;
			}
		}

		.vff-error {
			margin-top: 12px;
			padding: 12px;
			background: #ffebee;
			color: #c62828;
			border-radius: 6px;
			font-size: 13px;
			line-height: 1.4;
		}

		.vff-info {
			margin-top: 12px;
			text-align: center;
			color: #666;
			font-size: 12px;
		}

		/* Field confirmation styles (injected into page DOM) */
	`
}

/**
 * Make panel draggable
 */
function makeDraggable(panel: HTMLElement): void {
	const header = panel.querySelector('.vff-panel-header') as HTMLElement
	let isDragging = false
	let currentX = 0
	let currentY = 0
	let initialX = 0
	let initialY = 0

	header.addEventListener('mousedown', (e) => {
		isDragging = true
		initialX = e.clientX - currentX
		initialY = e.clientY - currentY
		panel.style.cursor = 'grabbing'
	})

	document.addEventListener('mousemove', (e) => {
		if (!isDragging) return

		e.preventDefault()
		currentX = e.clientX - initialX
		currentY = e.clientY - initialY

		panel.style.transform = `translate(${currentX}px, ${currentY}px)`
	})

	document.addEventListener('mouseup', () => {
		isDragging = false
		panel.style.cursor = 'default'
	})
}

/**
 * Set up event handlers
 */
function setupEventHandlers(
	shadowRoot: ShadowRoot,
	options: InjectOptions,
	parseResult: ParseResult,
	connectionMgr: ConnectionManager | null
): void {
	const closeBtn = shadowRoot.querySelector('.vff-close') as HTMLElement
	closeBtn.addEventListener('click', () => {
		// Disconnect before destroying
		if (connectionMgr) {
			connectionMgr.disconnect()
		}
		// Call destroy from global API
		;(window as any).VoiceFormFiller?.destroy()
	})

	// Connect button - Does everything: WebSocket + Microphone + Recording
	const connectBtn = shadowRoot.querySelector('.vff-connect') as HTMLButtonElement
	console.log('[VoiceFormFiller] Setting up connect button, manager exists:', !!connectionMgr)
	
	let isActive = false
	
	connectBtn.addEventListener('click', async () => {
		console.log('[VoiceFormFiller] Connect button clicked! Active:', isActive)
		
		if (!connectionMgr) {
			console.error('[VoiceFormFiller] No connection manager available')
			showError(shadowRoot, 'No connection manager - please refresh page')
			return
		}

		// Toggle recording on/off
		if (isActive) {
			// Stop recording
			console.log('[VoiceFormFiller] Stopping recording...')
			connectionMgr.stopRecording()
			connectBtn.textContent = '🎤 Connect to Voice'
			connectBtn.classList.remove('vff-recording')
			updateStatus(shadowRoot, 'connected')
			isActive = false
			console.log('[VoiceFormFiller] Recording stopped')
			return
		}

		// Start connection + recording
		try {
			console.log('[VoiceFormFiller] Disabling button and starting connection...')
			connectBtn.disabled = true
			connectBtn.textContent = 'Connecting...'
			
			// Step 1: Connect WebSocket
			console.log('[VoiceFormFiller] Step 1: Connecting WebSocket...')
			await connectionMgr.connect()
			console.log('[VoiceFormFiller] WebSocket connected!')
			
			// Step 2: Request microphone and start recording
			console.log('[VoiceFormFiller] Step 2: Starting microphone...')
			connectBtn.textContent = 'Starting microphone...'
			await connectionMgr.startRecording()
			console.log('[VoiceFormFiller] Microphone active!')
			
			// Success - update UI
			connectBtn.disabled = false
			connectBtn.textContent = '⏹ Stop Recording'
			connectBtn.classList.add('vff-recording')
			updateStatus(shadowRoot, 'recording')
			isActive = true
			console.log('[VoiceFormFiller] Voice connection fully active!')
			
		} catch (error) {
			console.error('[VoiceFormFiller] Connection/Recording failed:', error)
			
			// Show user-friendly error
			let errorMessage = 'Connection failed. '
			if (error instanceof Error) {
				if (error.message.includes('Permission denied') || error.message.includes('NotAllowedError')) {
					errorMessage = 'Microphone permission denied. Please allow microphone access and try again.'
				} else if (error.message.includes('NotFoundError')) {
					errorMessage = 'No microphone found. Please connect a microphone and try again.'
				} else {
					errorMessage = error.message
				}
			}
			
			showError(shadowRoot, errorMessage)
			connectBtn.disabled = false
			connectBtn.textContent = '🎤 Connect to Voice (Retry)'
			connectBtn.classList.remove('vff-recording')
			isActive = false
		}
	})

	// Rescan button (S4 - rescan form fields)
	const rescanBtn = shadowRoot.querySelector('.vff-rescan') as HTMLButtonElement
	rescanBtn.addEventListener('click', () => {
		console.log('[VoiceFormFiller] Rescan clicked - reloading page to rescan')
		// Simple implementation: just reload
		// For SPAs, this would trigger a re-parse without page reload
		window.location.reload()
	})
	
	// Clear Form button - Clear sessionStorage, DOM, and trigger state reload
	const clearFormBtn = shadowRoot.querySelector('.vff-clear-form') as HTMLButtonElement
	clearFormBtn.addEventListener('click', () => {
		console.log('[VoiceFormFiller] 🧹 Clear Form clicked')
		console.log('[VoiceFormFiller] BEFORE CLEAR - sessionStorage has:', sessionStorage.getItem('web_form_state') ? 'DATA' : 'NOTHING')
		
		// Confirm before clearing
		const confirmed = confirm('Clear all form fields and saved data? This cannot be undone.')
		if (!confirmed) {
			console.log('[VoiceFormFiller] ❌ Clear cancelled by user')
			return
		}
		
		// STEP 1: Clear sessionStorage (this will clear the persisted state)
		console.log('[VoiceFormFiller] Step 1: Clearing sessionStorage...')
		WebFormStateManager.clear()
		console.log('[VoiceFormFiller] ✅ sessionStorage cleared')
		console.log('[VoiceFormFiller] AFTER CLEAR - sessionStorage has:', sessionStorage.getItem('web_form_state') ? 'DATA (BUG!)' : 'NOTHING (CORRECT)')
		
		// STEP 2: Clear all DOM fields
		console.log('[VoiceFormFiller] Step 2: Clearing DOM fields...')
		const inputs = document.querySelectorAll('input, textarea, select')
		let clearedCount = 0
		
		inputs.forEach((element) => {
			const el = element as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
			
			if (el.tagName === 'INPUT') {
				const inputEl = el as HTMLInputElement
				if (inputEl.type === 'checkbox' || inputEl.type === 'radio') {
					inputEl.checked = false
				} else if (inputEl.type !== 'submit' && inputEl.type !== 'button' && inputEl.type !== 'hidden') {
					inputEl.value = ''
				}
				clearedCount++
			} else if (el.tagName === 'TEXTAREA') {
				(el as HTMLTextAreaElement).value = ''
				clearedCount++
			} else if (el.tagName === 'SELECT') {
				(el as HTMLSelectElement).selectedIndex = 0
				clearedCount++
			}
			
			// Remove AI confirmation markers
			el.removeAttribute('data-vff-confirmed')
			el.style.outline = ''
			el.style.outlineOffset = ''
		})
		
		// STEP 3: Remove all checkmark badges
		document.querySelectorAll('.vff-field-badge').forEach(badge => badge.remove())
		
		console.log(`[VoiceFormFiller] ✅ Cleared ${clearedCount} DOM fields`)
		
		// STEP 4: Verify sessionStorage is still clear (check for race condition)
		setTimeout(() => {
			const stillClear = !sessionStorage.getItem('web_form_state')
			if (stillClear) {
				console.log('[VoiceFormFiller] ✅ sessionStorage STILL clear after DOM clear (good!)')
			} else {
				console.error('[VoiceFormFiller] ❌ BUG: sessionStorage REFILLED after DOM clear!')
				console.error('[VoiceFormFiller] sessionStorage now contains:', sessionStorage.getItem('web_form_state')?.substring(0, 200))
			}
			
			// Force page reload to reinitialize state
			console.log('[VoiceFormFiller] 🔄 Reloading page NOW...')
			window.location.reload()
		}, 100)  // Small delay to catch any async saves
	})
	
	// Language selector change handler
	const languageSelect = shadowRoot.querySelector('#vff-fill-language') as HTMLSelectElement
	if (languageSelect && connectionMgr) {
		languageSelect.addEventListener('change', async () => {
			const newLanguage = languageSelect.value
			console.log('[VoiceFormFiller] Language changed to:', newLanguage)
			
			// Send language change to connection manager
			if (connectionMgr) {
				await connectionMgr.changeFillLanguage(newLanguage)
			}
		})
	}
}

/**
 * Update status display
 */
function updateStatus(shadowRoot: ShadowRoot, status: string): void {
	const statusIcon = shadowRoot.querySelector('.vff-status-icon')
	const statusText = shadowRoot.querySelector('.vff-status-text')

	if (statusIcon && statusText) {
		const states: Record<string, { icon: string; text: string }> = {
			disconnected: { icon: '⭕', text: 'Disconnected' },
			connecting: { icon: '🔄', text: 'Connecting...' },
			connected: { icon: '✅', text: 'Connected - Ready for voice' },
			recording: { icon: '🎤', text: 'Listening... Speak now!' },
			error: { icon: '❌', text: 'Connection error' },
			ready: { icon: '⚡', text: 'Warmed up - Click Connect' },
		}

		const state = states[status] || states.disconnected
		statusIcon.textContent = state.icon
		statusText.textContent = state.text
	}
}

/**
 * Show error message
 */
function showError(shadowRoot: ShadowRoot, message: string): void {
	const errorDiv = shadowRoot.querySelector('.vff-error') as HTMLElement
	if (errorDiv) {
		errorDiv.textContent = message
		errorDiv.style.display = 'block'

		// Auto-hide after 5 seconds
		setTimeout(() => {
			errorDiv.style.display = 'none'
		}, 5000)
	}
}
