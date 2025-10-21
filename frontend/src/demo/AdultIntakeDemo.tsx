/**
 * Adult Intake Demo - Voice Form Filling Demo
 * 
 * This component loads the adult intake form HTML and initializes
 * the voice form filler with a pre-defined schema (production-style).
 * 
 * PRODUCTION APPROACH: Schema is hand-crafted during installation,
 * not parsed from DOM. This is how real clients will integrate.
 */

import React, { useEffect, useRef, useState } from 'react'
import { createConnectionManager, type ConnectionManager } from '../shared/connection'
import { WebFormStateManager } from '../webFormState'
import { VoiceOverlay } from './VoiceOverlay'
import { VoiceOverlayMobile } from './VoiceOverlayMobile'
import type { FormSchema, SectionIndex } from '../webFormState'

export function AdultIntakeDemo() {
	const formContainerRef = useRef<HTMLDivElement>(null)
	const [schema, setSchema] = useState<FormSchema | null>(null)
	const [sectionIndex, setSectionIndex] = useState<SectionIndex | null>(null)
	const [isFormLoaded, setIsFormLoaded] = useState(false)
	const [isMobile, setIsMobile] = useState(false)
	const [isSubmitting, setIsSubmitting] = useState(false) // Track if form is being submitted
	
	// Shared connection manager state (persists across mobile/desktop switches)
	const [connectionManager, setConnectionManager] = useState<ConnectionManager | null>(null)
	const connectionManagerRef = useRef<ConnectionManager | null>(null)
	const [status, setStatus] = useState<string>('Ready')

	// FIX #1: Shared audio stream (created BEFORE React rendering to prevent race conditions)
	const [sharedStream, setSharedStream] = useState<MediaStream | null>(null)
	const [streamError, setStreamError] = useState<string | null>(null)
	const [streamReady, setStreamReady] = useState(false)

	// Detect mobile on mount
	useEffect(() => {
		const checkMobile = () => {
			setIsMobile(window.innerWidth <= 768)
		}
		checkMobile()
		window.addEventListener('resize', checkMobile)
		return () => window.removeEventListener('resize', checkMobile)
	}, [])

	// FIX #1: Create shared audio stream EARLY (before overlays render)
	// This prevents race conditions where VAD initializes before stream is ready
	useEffect(() => {
		let mounted = true

		async function initSharedStream() {
			try {
				console.log('[AdultIntakeDemo] 🎤 Creating shared audio stream early...')
				const stream = await navigator.mediaDevices.getUserMedia({
					audio: {
						echoCancellation: true,      // Browser AEC (critical for preventing echo)
						noiseSuppression: true,       // Reduces background noise
						autoGainControl: true,        // Normalizes microphone volume
						channelCount: 1,              // Mono audio
						sampleRate: 16000,            // Match recording sample rate
					},
				})

				if (mounted) {
					setSharedStream(stream)
					setStreamReady(true)
					console.log('[AdultIntakeDemo] ✅ Shared stream ready (AEC enabled)')
				} else {
					// Component unmounted during async operation, clean up
					stream.getTracks().forEach(track => track.stop())
				}
			} catch (err) {
				console.error('[AdultIntakeDemo] ❌ Failed to create shared stream:', err)
				if (mounted) {
					const errorMsg = err instanceof Error ? err.message : 'Microphone access denied'
					setStreamError(errorMsg)
					setStreamReady(true) // Still set ready so overlays can render (they'll show error)
				}
			}
		}

		initSharedStream()

		return () => {
			mounted = false
			// Clean up stream on unmount
			if (sharedStream) {
				console.log('[AdultIntakeDemo] 🧹 Cleaning up shared stream')
				sharedStream.getTracks().forEach(track => track.stop())
			}
		}
	}, []) // Only run once on mount

	// Add tab close warning if form has data
	useEffect(() => {
		const handleBeforeUnload = (e: BeforeUnloadEvent) => {
			// Don't show warning if form is being submitted
			if (isSubmitting) return
			
			// Check if any form fields have been filled
			const inputs = document.querySelectorAll('input, textarea, select')
			let hasData = false
			
			for (const element of inputs) {
				const el = element as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
				
				if (el.tagName === 'INPUT') {
					const inputEl = el as HTMLInputElement
					if (inputEl.type === 'checkbox' || inputEl.type === 'radio') {
						if (inputEl.checked) hasData = true
					} else if (inputEl.type !== 'submit' && inputEl.type !== 'button' && inputEl.type !== 'hidden') {
						if (inputEl.value.trim()) hasData = true
					}
				} else if (el.tagName === 'TEXTAREA') {
					if ((el as HTMLTextAreaElement).value.trim()) hasData = true
				} else if (el.tagName === 'SELECT') {
					if ((el as HTMLSelectElement).selectedIndex > 0) hasData = true
				}
				
				if (hasData) break
			}
			
			// Show warning if form has data
			if (hasData) {
				e.preventDefault()
				e.returnValue = '' // Required for Chrome
			}
		}

		window.addEventListener('beforeunload', handleBeforeUnload)
		return () => window.removeEventListener('beforeunload', handleBeforeUnload)
	}, [isFormLoaded, isSubmitting])

	// Load the form HTML and schema
	useEffect(() => {
		const loadFormAndSchema = async () => {
			try {
				// Load form HTML (relative path for deployment flexibility)
				const formResponse = await fetch('./adult_intake_demo.html')
				const htmlText = await formResponse.text()
				
				// Parse the HTML to extract content
				const parser = new DOMParser()
				const doc = parser.parseFromString(htmlText, 'text/html')
				
				// Extract styles
				const styles = doc.querySelector('style')?.textContent || ''
				
				// Extract form and clinic header
				const clinicHeader = doc.querySelector('.clinic-header')?.outerHTML || ''
				const formContainer = doc.querySelector('.form-container')?.outerHTML || ''
				
				if (formContainerRef.current) {
					// Inject styles
					const styleElement = document.createElement('style')
					styleElement.textContent = styles
					document.head.appendChild(styleElement)
					
					// Inject HTML content
					formContainerRef.current.innerHTML = clinicHeader + formContainer
					
					setIsFormLoaded(true)
				}

				// Load the hand-crafted schema from JSON (relative path)
				const schemaResponse = await fetch('./adult_intake_demo_schema.json')
				const schemaData = await schemaResponse.json() as FormSchema
				
				// Update URL to current location
				schemaData.form_metadata.url = window.location.href
				
				// Phase 3: Load section index
				const indexResponse = await fetch('./adult_intake_sections_index.json')
				const indexData = await indexResponse.json() as SectionIndex
				
				setSchema(schemaData)
				setSectionIndex(indexData)
				
				// Handle form submission - redirect to thank you page
				setTimeout(() => {
					const form = document.querySelector('form')
					if (form) {
					form.addEventListener('submit', (e) => {
						e.preventDefault()
						
						// Set flag to prevent beforeunload warning
						setIsSubmitting(true)							// Redirect to thank you page
							window.location.href = 'thank-you.html'
							return false
						})
						
						// Handle Enter key on form fields
						form.addEventListener('keydown', (e) => {
							if (e.key === 'Enter') {
								const target = e.target as HTMLElement
							if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {
								e.preventDefault()
								target.blur() // Blur the field instead of submitting
							}
							}
						})
					}
				}, 100) // Small delay to ensure form is in DOM
				
			} catch (error) {
				console.error('Failed to load form, schema, or section index:', error)
			}
		}

		loadFormAndSchema()
	}, [])

	// Initialize shared connection manager when schema is loaded AND stream is ready
	// FIX #1: Wait for stream to be ready before creating connection manager
	useEffect(() => {
		if (!schema || !sectionIndex) return
		if (!streamReady) return // Wait for stream initialization to complete
		if (connectionManagerRef.current) return // Already initialized

		const state = WebFormStateManager.initWithSections(schema, sectionIndex)

		// Pass shared stream to connection manager (prevents duplicate getUserMedia calls)
		const manager = createConnectionManager(
			state.schema,
			(newStatus) => {
				setStatus(newStatus)
			},
			'English',
			sharedStream || undefined // Pass stream if available (undefined if permission denied)
		)

		connectionManagerRef.current = manager
		setConnectionManager(manager)

		return () => {
			if (connectionManagerRef.current) {
				connectionManagerRef.current.disconnect()
				connectionManagerRef.current = null
			}
			setConnectionManager(null)
		}
	}, [schema, sectionIndex, streamReady, sharedStream])

	const wsUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws/fill'

	return (
		<div className="demo-container">
			{/* Form Content (loaded from HTML) */}
			<div ref={formContainerRef} className="form-content"></div>

			{/* Voice Overlay (mobile vs desktop) */}
			{/* FIX #1: Only render overlays when stream is ready (prevents race conditions) */}
			{isFormLoaded && schema && sectionIndex && connectionManager && streamReady && (
				isMobile ? (
					<VoiceOverlayMobile 
						schema={schema} 
						sectionIndex={sectionIndex} 
						wsUrl={wsUrl}
						connectionManager={connectionManager}
						sharedStream={sharedStream}
						streamError={streamError}
						status={status}
					/>
				) : (
					<VoiceOverlay 
						schema={schema} 
						sectionIndex={sectionIndex} 
						wsUrl={wsUrl}
						connectionManager={connectionManager}
						status={status}
						sharedStream={sharedStream}
						streamError={streamError}
					/>
				)
			)}
		</div>
	)
}
