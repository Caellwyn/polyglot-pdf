/**
 * Lifecycle Management - Teardown Logic
 * 
 * Handles clean destruction of the voice form filler.
 */

import { getConnectionManager } from './overlay'

const MUTEX_KEY = '__VFF_ACTIVE__'
const CONTAINER_ID = 'voice-form-filler-root'

// Track active resources for cleanup
interface ActiveResources {
	websocket?: WebSocket
	audioContext?: AudioContext
	mediaStream?: MediaStream
	timers: number[]
	listeners: Array<{ element: EventTarget; event: string; handler: EventListener }>
}

const activeResources: ActiveResources = {
	timers: [],
	listeners: [],
}

/**
 * Register a resource for cleanup
 */
export function registerResource(
	type: keyof ActiveResources,
	resource: any
): void {
	if (type === 'timers' || type === 'listeners') {
		;(activeResources[type] as any[]).push(resource)
	} else {
		activeResources[type] = resource
	}
}

/**
 * Destroy the voice form filler.
 * Idempotent - safe to call even if not active.
 */
export function destroy(): void {
	// Check if active
	if (!(window as any)[MUTEX_KEY]) {
		console.log('[VoiceFormFiller] Not active, nothing to destroy')
		return
	}

	console.log('[VoiceFormFiller] Starting teardown...')

	try {
		// Step 0: Disconnect connection manager first (closes WebSocket, stops audio, etc.)
		// This is CRITICAL - without this, the Gemini session stays active!
		const connectionManager = getConnectionManager()
		if (connectionManager) {
			console.log('[VoiceFormFiller] Disconnecting connection manager...')
			connectionManager.disconnect()
		}

		// Step 1: Close WebSocket (fallback if not closed by connection manager)
		if (activeResources.websocket) {
			activeResources.websocket.close()
			activeResources.websocket = undefined
		}

		// Step 2: Close AudioContext
		if (activeResources.audioContext) {
			activeResources.audioContext.close()
			activeResources.audioContext = undefined
		}

		// Step 3: Stop MediaStream
		if (activeResources.mediaStream) {
			activeResources.mediaStream.getTracks().forEach((track) => track.stop())
			activeResources.mediaStream = undefined
		}

		// Step 4: Clear timers
		activeResources.timers.forEach((timerId) => clearTimeout(timerId))
		activeResources.timers = []

		// Step 5: Remove event listeners
		activeResources.listeners.forEach(({ element, event, handler }) => {
			element.removeEventListener(event, handler)
		})
		activeResources.listeners = []

		// Step 6: Remove container from DOM
		const container = document.getElementById(CONTAINER_ID)
		if (container) {
			container.remove()
		}

		// Step 7: Clear mutex
		delete (window as any)[MUTEX_KEY]

		console.log('[VoiceFormFiller] Teardown complete')
	} catch (error) {
		console.error('[VoiceFormFiller] Error during teardown:', error)
		// Force clear mutex even on error
		delete (window as any)[MUTEX_KEY]
	}
}

/**
 * Add event listener and track for cleanup
 */
export function addTrackedListener(
	element: EventTarget,
	event: string,
	handler: EventListener
): void {
	element.addEventListener(event, handler)
	registerResource('listeners', { element, event, handler })
}

/**
 * Set timeout and track for cleanup
 */
export function setTrackedTimeout(
	callback: () => void,
	delay: number
): number {
	const timerId = window.setTimeout(callback, delay)
	registerResource('timers', timerId)
	return timerId
}
