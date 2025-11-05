/**
 * Connection Manager - Step S5
 * 
 * Manages WebSocket connection to backend using warmup → upgrade flow.
 * Reuses WebFormConnection logic from main app.
 */

// Extend Window interface for activity watchdog callbacks
declare global {
	interface Window {
		vffOnAudioPlaybackEnd?: () => void
		vffOnAudioPlaybackStart?: () => void  // Called when Gemini starts speaking (pause timer)
		// vffOnTurnComplete removed - now using audio silence detection (100ms threshold)
	}
}

import { WebFormConnection, type ConnectionCallbacks, type ConnectionStatus } from '../webFormConnection'
import type { FormSchema } from '../schema-forms/types/schema'
import { SchemaFormStateManager, type SchemaFormState } from '../schema-forms/state/schemaFormState'
import { createFieldManager, type FieldManager } from './fieldManager'
import { createAudioManager, type AudioManager } from './audioManager'
import { metrics } from './metrics'
import { getBackendUrl as getBackendUrlFromConfig, getCloudBackendUrl } from './config'

export interface ConnectionManager {
	connect: () => Promise<void>
	pause: () => void  // Pause recording but keep connection warm
	resume: () => Promise<void>  // Resume from pause
	disconnect: () => void  // True disconnect (cleanup everything)
	getStatus: () => ConnectionStatus
	sendAudio: (audioData: ArrayBuffer) => void
	sendActivityStart: () => void  // Send activity_start signal (user started speaking)
	sendActivityEnd: () => void    // Send activity_end signal (user stopped speaking)
	sendPrompt: (prompt: string) => void  // Send text prompt to Gemini (for recovery, nudges, etc.)
	sendRecoveryPrompt: (level: number, nextFieldHint?: string) => void  // Send recovery prompt (activity watchdog)
	endGeminiSession: () => void  // End Gemini session only (keep WebSocket alive)
	setPushToTalkMode: (enabled: boolean) => void  // Enable/disable PTT mode
	getFieldManager: () => FieldManager | null
	getAudioManager: () => AudioManager | null
	startRecording: () => Promise<void>
	stopRecording: () => void
	isRecording: () => boolean
	isPaused: () => boolean
	changeFillLanguage: (language: string) => Promise<void>
	changeSpokenLanguage: (language: string, nextFieldHint: string) => void  // Change spoken conversation language
	// Part management (Phase 4A: parts replace sections)
	startPart: (partId: string) => Promise<void>
	switchToPart: (partId: string) => Promise<void>
	completePart: () => Promise<void>
	getCurrentPartId: () => string | undefined
	getCompletedPartIds: () => Set<string>
	// DEPRECATED: Section management (kept for backward compatibility during migration)
	startSection: (sectionNumber: number) => Promise<void>
	switchSection: (target: number | string) => Promise<void>
	completeSection: () => Promise<void>
	getCurrentSection: () => number | undefined
	getCompletedSections: () => Set<number>
	// VAD-based barge-in callbacks
	onVADSpeechStart: () => void
	onVADSpeechEnd: () => void
}

/**
 * Restore DOM fields from sessionStorage on page load
 * Ensures DOM and sessionStorage stay in sync across page refreshes
 */
function restoreDOMFromSessionStorage(state: SchemaFormState, schema: FormSchema): void {
	console.log('[VFF Connection] 🔄 Restoring DOM from sessionStorage...')
	let restoredCount = 0
	
	for (const [fieldId, fieldValue] of Object.entries(state.fieldValues)) {
		const value = fieldValue.value
		if (value === null || value === undefined || value === '') continue
		
		// Find the field element
		let element = document.getElementById(fieldId) as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement | null
		
		// Try by name attribute
		if (!element) {
			const inputs = document.querySelectorAll(`input[name="${fieldId}"], textarea[name="${fieldId}"], select[name="${fieldId}"]`)
			if (inputs.length > 0) {
				element = inputs[0] as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
			}
		}
		
		if (!element) continue
		
		// Restore value to DOM
		if (element.tagName === 'SELECT') {
			(element as HTMLSelectElement).value = String(value)
		} else if (element.tagName === 'INPUT') {
			const inputEl = element as HTMLInputElement
			if (inputEl.type === 'checkbox') {
				inputEl.checked = Boolean(value)
			} else {
				inputEl.value = String(value)
			}
		} else if (element.tagName === 'TEXTAREA') {
			(element as HTMLTextAreaElement).value = String(value)
		}
		
		restoredCount++
	}
	
	console.log(`[VFF Connection] ✅ Restored ${restoredCount} fields from sessionStorage to DOM`)
}

/**
 * Scan DOM for pre-filled values and populate sessionStorage
 * Called before connecting to capture values user entered before activating voice
 */
function capturePreFilledValues(connection: WebFormConnection, schema: FormSchema): void {
	console.log('[VFF Connection] 🔍 Scanning DOM for pre-filled values...')
	let capturedCount = 0
	
	for (const field of schema.fields) {
		const fieldId = field.id
		
		// Try to find element by ID
		let element = document.getElementById(fieldId) as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement | null
		
		// Try by name attribute (for table fields, radio groups, checkbox groups)
		if (!element) {
			const inputs = document.querySelectorAll(`input[name="${fieldId}"], textarea[name="${fieldId}"], select[name="${fieldId}"]`)
			if (inputs.length > 0) {
				element = inputs[0] as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
			}
		}
		
		if (!element) continue
		
		// Get current value from DOM
		let value: string | boolean | null = null
		
		if (element.tagName === 'SELECT') {
			const selectEl = element as HTMLSelectElement
			value = selectEl.value || null
		} else if (element.tagName === 'INPUT') {
			const inputEl = element as HTMLInputElement
			if (inputEl.type === 'checkbox') {
				value = inputEl.checked
			} else if (inputEl.type === 'radio') {
				// For radio groups, only capture if checked
				if (inputEl.checked) {
					value = inputEl.value
				}
			} else {
				value = inputEl.value || null
			}
		} else if (element.tagName === 'TEXTAREA') {
			value = (element as HTMLTextAreaElement).value || null
		}
		
		// If field has a value, update sessionStorage
		if (value !== null && value !== '' && value !== false) {
			connection.updateField(fieldId, value, { confirmed: true, emit: false })
			capturedCount++
			console.log('[VFF Connection] ✓ Captured pre-filled:', fieldId, '=', value)
		}
	}
	
	console.log(`[VFF Connection] ✅ Captured ${capturedCount} pre-filled values from DOM`)
}

/**
 * Create connection manager for bookmarklet
 * 
 * @param sharedStream - Optional pre-created MediaStream to share with audioManager (for VAD coordination)
 */
export function createConnectionManager(
	schema: FormSchema,
	onStatusChange: (status: string) => void,
	initialFillLanguage: string = 'English',
	sharedStream?: MediaStream
): ConnectionManager {
	// Get production backend URL from environment or default
	const wsUrl = getBackendUrl()
	
	let connection: WebFormConnection | null = null
	let fieldManager: FieldManager | null = null
	let audioManager: AudioManager | null = null
	let fillLanguage: string = initialFillLanguage
	let paused: boolean = false
	let connectedUrl: string = wsUrl  // Track the actual URL we connected to
	let pushToTalkMode: boolean = false  // Track if PTT mode is enabled (disables energy-based barge-in)
	
	// Initialize sessionStorage state immediately
	const state = SchemaFormStateManager.init(schema)
	
	// Restore DOM fields from sessionStorage (if any values exist from previous session)
	restoreDOMFromSessionStorage(state, schema)
	
	// Create audio manager immediately (doesn't need WebSocket to be ready)
	// Pass shared stream if provided (for VAD coordination)
	audioManager = createAudioManager(sharedStream)
	if (sharedStream) {
		console.log('[VFF Connection] 🔗 Audio manager using shared stream (VAD coordination)')
	}
	
	// Create field manager immediately to listen for manual edits from the start
	// This captures any fields the user fills BEFORE clicking Connect
	fieldManager = createFieldManager({
		schema: schema,
		onManualEdit: (fieldId, value) => {
			console.log('[VFF Connection] 🖊️ Manual edit detected:', fieldId, '=', value)
			
			// Update sessionStorage immediately using SchemaFormStateManager
			// Manual edits are marked as confirmed (user explicitly filled them)
			const updatedState = SchemaFormStateManager.updateField(
				state, 
				fieldId, 
				value, 
				{ confirmed: true }
			)
			// Update the reference (though SchemaFormStateManager.updateField already saves)
			Object.assign(state, updatedState)
			console.log('[VFF Connection] ✓ Updated sessionStorage for:', fieldId)
			
			// If connected, also notify Gemini
			if (connection) {
				const field = schema.fields.find(f => f.id === fieldId)
				const fieldName = field?.name || fieldId
				connection.sendManualFieldUpdate(fieldId, fieldName, value)
				console.log('[VFF Connection] ✓ Notified Gemini about:', fieldId)
			}
		}
	})
	console.log('[VFF Connection] ✅ Field manager created - listening for manual edits')

	const callbacks: ConnectionCallbacks = {
		onStatusChange: (status) => {
			onStatusChange(status)
		},
		onSessionReady: (sessionId) => {
			onStatusChange('connected')
			
			// Initialize metrics for this session
			metrics.startSession(sessionId)
			
			// Field manager already created at initialization
			// Now it will start syncing manual edits to Gemini
		},
		onSessionRestarted: () => {
			// Backend confirms Gemini session has been restarted
			console.log('[VFF Connection] ✅ Gemini session restarted - updating status')
			onStatusChange('connected')
		},
		onFieldUpdate: (updates) => {
			console.log('[VFF Connection] 📥 Tool call received: update_form_fields with', updates.length, 'field(s)')
			updates.forEach((update, idx) => {
				console.log(`  [${idx + 1}] fieldId:`, update.fieldId, '→ value:', update.value)
			})
			
			// Track tool calls in metrics and filter out hallucinations
			const acceptedUpdates: typeof updates = []
			const rejectedUpdates: typeof updates = []
			
			for (const update of updates) {
				// Generate a pseudo-call-id from field ID and timestamp
				const callId = `field_${update.fieldId}_${Date.now()}`
				const decision = metrics.recordToolCall('update_form_fields', callId)
				
				if (decision === 'reject') {
					// Don't apply this update - it's a hallucination from interrupted generation
					rejectedUpdates.push(update)
					continue
				}
				
				// Update accepted - add to list
				acceptedUpdates.push(update)
			}
			
			if (rejectedUpdates.length > 0) {
				console.warn('[VFF Connection] ⚠️ Rejected', rejectedUpdates.length, 'hallucinated update(s):', 
					rejectedUpdates.map(u => u.fieldId))
			}
			
			console.log('[VFF Connection] ✅ Accepted', acceptedUpdates.length, 'update(s) for processing')
			
			// S6: Apply ONLY accepted field updates to DOM
			if (fieldManager && acceptedUpdates.length > 0) {
				fieldManager.applyUpdates(acceptedUpdates)
			}
		},
		onAudioData: async (audioData) => {
			// Play AI audio
			// NOTE: Activity watchdog callback (vffOnAudioPlaybackEnd) is now called
			// from audioManager.playAudio() -> source.onended, not here.
			// This ensures we detect when audio FINISHES PLAYING, not when chunks arrive.
			if (audioManager) {
				await audioManager.playAudio(audioData)
			}
		},
		onError: (error) => {
			console.error('[VFF Connection] Error:', error)
			onStatusChange('error')
		},
	}

	return {
		async connect() {
			// Check if WebSocket is connected but Gemini is closed (post-Level 3 scenario)
			const isWebSocketConnected = connection && connection.getStatus() === 'connected'
			
			if (isWebSocketConnected && connection) {
				console.log('[VFF Connection] 🔄 WebSocket alive - restarting Gemini session')
				// Compute next field hint for smooth progression
				const nextFieldHint = connection.getNextFieldHint()
				// Send restart message to backend with hint
				try {
					onStatusChange('reconnecting')  // Set status to reconnecting while waiting
					connection.send({ 
						type: 'restart_gemini_session',
						next_field_hint: nextFieldHint 
					})
					console.log('[VFF Connection] ⏳ Gemini session restart requested', { nextFieldHint })
					// Status will be updated to 'connected' when backend confirms restart
					// (via gemini_session_restarted message handler)
					return
				} catch (error) {
					console.error('[VFF Connection] Failed to restart Gemini:', error)
					onStatusChange('disconnected')
					// Fall through to full reconnect
				}
			}

			try {
				console.log('[VFF Connection] Attempting to connect to:', wsUrl)
				onStatusChange('connecting')
				
				// Reinitialize audio manager if destroyed (reconnect scenario)
				if (!audioManager) {
					console.log('[VFF Connection] 🔄 Reinitializing audio manager (reconnect)')
					audioManager = createAudioManager(sharedStream)
				}
				
				// Reinitialize field manager if destroyed (reconnect scenario)
				if (!fieldManager) {
					console.log('[VFF Connection] 🔄 Reinitializing field manager (reconnect)')
					fieldManager = createFieldManager({
						schema: schema,
						onManualEdit: (fieldId, value) => {
							console.log('[VFF Connection] 🖊️ Manual edit detected:', fieldId, '=', value)
							
							// Update sessionStorage immediately using SchemaFormStateManager
							const updatedState = SchemaFormStateManager.updateField(
								state, 
								fieldId, 
								value, 
								{ confirmed: true }
							)
							Object.assign(state, updatedState)
							console.log('[VFF Connection] ✓ Updated sessionStorage for:', fieldId)
							
							// If connected, also notify Gemini
							if (connection) {
								const field = schema.fields.find(f => f.id === fieldId)
								const fieldName = field?.name || fieldId
								connection.sendManualFieldUpdate(fieldId, fieldName, value)
								console.log('[VFF Connection] ✓ Notified Gemini about:', fieldId)
							}
						}
					})
				}
				
				// Create connection if not exists
				if (!connection) {
					connection = new WebFormConnection(schema, callbacks, fillLanguage)
				}
				
				// Capture any pre-filled values from DOM before connecting
				capturePreFilledValues(connection, schema)
				
				// Try to connect to localhost first
				try {
					console.log('[VFF Connection] Trying localhost...')
					await connection.connect(wsUrl)
					connectedUrl = wsUrl  // Track successful connection
					console.log('[VFF Connection] ✅ Connected to localhost')
				} catch (localError) {
					// Localhost failed, try cloud fallback
					const cloudUrl = getCloudBackendUrl()
					console.log('[VFF Connection] Localhost failed, trying cloud:', cloudUrl)
					console.log('[VFF Connection] Local error was:', localError)
					
					// Create new connection for cloud attempt
					connection.disconnect()
					connection = new WebFormConnection(schema, callbacks, fillLanguage)
					capturePreFilledValues(connection, schema)
					
					await connection.connect(cloudUrl)
					connectedUrl = cloudUrl  // Track successful connection
					console.log('[VFF Connection] ✅ Connected to cloud')
				}
				
			} catch (error) {
				console.error('[VFF Connection] Connection failed:', error)
				console.error('[VFF Connection] Error details:', {
					message: error instanceof Error ? error.message : String(error),
					stack: error instanceof Error ? error.stack : undefined,
					wsUrl,
				})
				onStatusChange('error')
				throw error
			}
		},

		pause() {
			console.log('[VFF Connection] Pausing (keeping connection warm)...')
			paused = true
			
			// Stop recording
			if (audioManager?.isRecording()) {
				audioManager.stopRecording()
			}
			
			// Flush any queued audio
			if (audioManager) {
				audioManager.flushAudioQueue()
			}
			
			onStatusChange('paused')
		},

		async resume() {
			console.log('[VFF Connection] Resuming...')
			
			if (!connection || connection.getStatus() !== 'connected') {
				console.error('[VFF Connection] Cannot resume - not connected')
				onStatusChange('error')
				return
			}

			paused = false
			onStatusChange('connected')
			
			// Restart recording
			if (audioManager && !audioManager.isRecording()) {
				await this.startRecording()
			}
			
			// Audio will automatically resume when user starts speaking again
			// The connection stayed warm, so Gemini is still ready
			console.log('[VFF Connection] Resumed successfully')
		},

		disconnect() {
			// End metrics session and print summary
			metrics.endSession()
			
			if (connection) {
				connection.disconnect()
				connection = null
			}
			if (fieldManager) {
				fieldManager.destroy()
				fieldManager = null
			}
			if (audioManager) {
				audioManager.destroy()
				audioManager = null
			}
			onStatusChange('disconnected')
		},

		getStatus() {
			return connection?.getStatus() ?? 'disconnected'
		},

		sendAudio(audioData: ArrayBuffer) {
			if (connection) {
				connection.sendAudio(audioData)
			}
		},

		sendActivityStart() {
			if (connection) {
				connection.sendActivityStart()
			}
		},

		sendActivityEnd() {
			if (connection) {
				connection.sendActivityEnd()
			}
		},

		sendPrompt(prompt: string) {
			if (connection) {
				connection.sendPrompt(prompt)
			}
		},

		sendRecoveryPrompt(level: number, nextFieldHint?: string) {
			if (connection) {
				connection.sendRecoveryPrompt(level, nextFieldHint)
			}
		},

		endGeminiSession() {
			if (connection) {
				connection.endGeminiSession()
			}
		},

		setPushToTalkMode(enabled: boolean) {
			console.log(`[VFF Connection] Setting push-to-talk mode: ${enabled}`)
			pushToTalkMode = enabled
		},

		getFieldManager() {
			return fieldManager
		},

		getAudioManager() {
			return audioManager
		},

		async startRecording() {
			console.log('[VFF Connection] startRecording called')
			
			if (!audioManager) {
				console.error('[VFF Connection] Audio manager not initialized')
				return
			}
			
			console.log('[VFF Connection] Requesting microphone access...')
			
			await audioManager.startRecording((audioData) => {
				// Send audio to backend
				if (connection && connection.getStatus() === 'connected') {
					connection.sendAudio(audioData)
				}
			})
		},

		stopRecording() {
			if (audioManager) {
				audioManager.stopRecording()
			}
		},

		isRecording() {
			return audioManager?.isRecording() ?? false
		},

		isPaused() {
			return paused
		},

		async changeFillLanguage(language: string) {
			// Update stored language
			fillLanguage = language

			if (connection && connection.getStatus() === 'connected') {
				// Send language change message to backend
				await connection.changeFillLanguage(language)
			} else {
				console.log('[VFF Connection] Language preference saved, will be used on next connect')
			}
		},

		changeSpokenLanguage(language: string, nextFieldHint: string) {
			// Send spoken language change message to backend
			if (connection && connection.getStatus() === 'connected') {
				connection.send({
					type: 'change_spoken_language',
					spoken_language: language,
					next_field_hint: nextFieldHint
				})
				console.log('[VFF Connection] ✓ Sent spoken language change to backend:', language)
			} else {
				console.warn('[VFF Connection] Cannot change spoken language - not connected')
			}
		},

		// Phase 3: Section management methods
		async startSection(sectionNumber: number) {
			if (!connection) {
				throw new Error('Connection not initialized')
			}
			
			// Stop recording if active
			if (audioManager?.isRecording()) {
				audioManager.stopRecording()
			}
			
			await connection.startSection(sectionNumber, wsUrl)
			
			// Restart recording if we were recording before
			if (!paused && audioManager) {
				await audioManager.startRecording((data) => {
					if (connection) {
						connection.sendAudio(data)
					}
				})
			}
		},
		
		async switchSection(target: number | string) {
			if (!connection) {
				throw new Error('Connection not initialized')
			}
			
			// Stop recording if active (buffer draining handled by WebFormConnection)
			if (audioManager?.isRecording()) {
				audioManager.stopRecording()
			}
			
			await connection.switchSection(target, connectedUrl)
			
			// Restart recording if we were recording before
			if (!paused && audioManager) {
				await audioManager.startRecording((data) => {
					if (connection) {
						connection.sendAudio(data)
					}
				})
			}
		},
		
		async completeSection() {
			if (!connection) {
				throw new Error('Connection not initialized')
			}
			
		await connection.completeSection(wsUrl)
	},
	
	getCurrentSection() {
		return connection?.getCurrentSection()
	},
	
	getCompletedSections() {
		return connection?.getCompletedSections() || new Set()
	},
	
	// Phase 4A: Part management methods (parts replace sections)
	async startPart(partId: string) {
		const state = SchemaFormStateManager.load()
		if (!state) {
			throw new Error('No form state found')
		}
		
		// Find the part to get its order number
		const part = state.schema.parts?.find(p => p.id === partId)
		if (!part) {
			throw new Error(`Part not found: ${partId}`)
		}
		
		// Delegate to section-based method (uses order number)
		await this.startSection(part.order)
	},
	
	async switchToPart(partId: string) {
		const state = SchemaFormStateManager.load()
		if (!state) {
			throw new Error('No form state found')
		}
		
		// Find the part to get its order number
		const part = state.schema.parts?.find(p => p.id === partId)
		if (!part) {
			throw new Error(`Part not found: ${partId}`)
		}
		
		// Delegate to section-based method (uses order number)
		await this.switchSection(part.order)
	},
	
	async completePart() {
		// Delegate to section-based method
		await this.completeSection()
	},
	
	getCurrentPartId(): string | undefined {
		const state = SchemaFormStateManager.load()
		return state?.currentPartId
	},
	
	getCompletedPartIds(): Set<string> {
		const state = SchemaFormStateManager.load()
		return state?.completedParts || new Set()
	},
	
	// VAD-based barge-in: Called when VAD detects speech start
	// Sends activity_start signal before audio chunks begin streaming
	onVADSpeechStart() {
		if (!audioManager) return			// PUSH-TO-TALK MODE: Disable VAD-based barge-in
			if (pushToTalkMode) return

			// Send activity_start signal to Gemini (user started speaking)
			if (connection) {
				connection.sendActivityStart()
			}

			const geminiSpeaking = audioManager.isSpeaking()

			// BARGE-IN: If Gemini is currently talking, flush audio queue for instant UX
			if (geminiSpeaking) {
				console.log('[VFF Connection] 🎤 VAD detected speech - flushing audio queue')

				// Record metrics
				metrics.recordMicActivity()

				// IMMEDIATELY flush audio queue (instant UX feedback)
				audioManager.flushAudioQueue()
				metrics.recordTTSPaused()
				metrics.recordCancelSent()
			}
		},
		
		// VAD-based speech end: Called when VAD detects speech end
		// Sends activity_end signal to flush Gemini's audio buffer
		onVADSpeechEnd() {
			if (!audioManager) return

			// PUSH-TO-TALK MODE: Disable VAD-based barge-in
			if (pushToTalkMode) return

			const geminiSpeaking = audioManager.isSpeaking()

			// Resume audio playback if Gemini stopped (allow Gemini to respond)
			// CRITICAL: This unblocks new audio chunks AND resumes the audio context
			// if it was suspended during tentative pause
			if (!geminiSpeaking) {
				audioManager.resumePlayback()
				audioManager.resumeAudioContext() // Resume context if it was paused
			}

			// Send activity_end signal to flush Gemini's cached audio buffer
			if (connection) {
				connection.sendActivityEnd()
			}

			console.log('[VFF Connection] 🎤 VAD speech ended - sent activity_end, audio playback resumed')
		},
	}
}

/**
 * Get backend WebSocket URL
 * Delegates to config module for production/local dev switching
 */
function getBackendUrl(): string {
	return getBackendUrlFromConfig()
}
