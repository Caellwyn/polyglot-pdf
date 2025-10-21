/**
 * VoiceOverlay - Production-style voice form filling overlay
 * 
 * This component loads a pre-defined schema from JSON and integrates
 * voice functionality directly into the page. This is how production
 * installations work - no DOM parsing, just a curated schema.
 * * IMPORTANT: if you change logic here, change it in VoiceOverlayMobile.tsx too
 */

// Extend Window interface for global callbacks
declare global {
	interface Window {
		vffOnAudioPlaybackStart?: () => void
		vffOnAudioPlaybackEnd?: () => void
		vffOnTurnComplete?: () => void
	}
}

import React, { useEffect, useRef, useState, useMemo } from 'react'
import { createConnectionManager, type ConnectionManager } from '../shared/connection'
import { WebFormStateManager, type FormSchema, type SectionIndex } from '../webFormState'
import { computeNextField, formatNextFieldHint } from '../navigation'
import { useDemoVAD } from './useDemoVAD'
import { GreetingCarousel } from './GreetingCarousel'

interface VoiceOverlayProps {
	schema: FormSchema
	sectionIndex: SectionIndex
	wsUrl?: string
	onClose?: () => void
	connectionManager?: ConnectionManager
	status?: string
}

export function VoiceOverlay({ schema, sectionIndex, wsUrl, onClose, connectionManager: sharedConnectionManager, status: sharedStatus }: VoiceOverlayProps) {
	const [connectionManager, setConnectionManager] = useState<ConnectionManager | null>(sharedConnectionManager || null)
	const connectionManagerRef = useRef<ConnectionManager | null>(sharedConnectionManager || null)
	const [status, setStatus] = useState<string>(sharedStatus || 'Ready')
	const [error, setError] = useState<string | null>(null)
	const [pendingVADStart, setPendingVADStart] = useState(false)
	const [currentSection, setCurrentSection] = useState(1)
	const [completedSections, setCompletedSections] = useState<Set<number>>(new Set())
	const [sectionFieldCount, setSectionFieldCount] = useState({ filled: 0, total: 12 })
	const [showSectionDropdown, setShowSectionDropdown] = useState(false)
	const [pushToTalkMode, setPushToTalkMode] = useState(false)
	const [isHoldingPushToTalk, setIsHoldingPushToTalk] = useState(false)
	const [showGreetingCarousel, setShowGreetingCarousel] = useState(false)
	const [isCollapsed, setIsCollapsed] = useState(false)
	const carouselDismissedRef = useRef(false)  // Track if user/system dismissed carousel
	const panelRef = useRef<HTMLDivElement>(null)
	const isDraggingRef = useRef(false)
	const offsetRef = useRef({ x: 0, y: 0 })
	
	// Create shared audio stream ONCE on mount (before VAD initialization)
	// This ensures both VAD and recording use the SAME stream with browser AEC
	const sharedStreamRef = useRef<MediaStream | null>(null)
	const [vadReady, setVadReady] = useState(false)
	
	// Track speech duration to prevent short grunts/noises from interrupting Gemini
	const speechStartTimeRef = useRef<number | null>(null)
	const bargeInTriggeredRef = useRef<boolean>(false)  // Track if we triggered barge-in for this speech event
	const MIN_TURN_DURATION_MS = 450  // Minimum 450ms of speech before triggering barge-in

	// Create stream once on mount
	useEffect(() => {
		let mounted = true
		
		async function initSharedStream() {
			try {
				console.log('[VoiceOverlay] 🎤 Creating shared audio stream...')
				const stream = await navigator.mediaDevices.getUserMedia({
					audio: {
						echoCancellation: true,      // Browser AEC (critical!)
						noiseSuppression: true,       // Reduces background noise
						autoGainControl: true,        // Normalizes microphone volume
						channelCount: 1,              // Mono audio
						sampleRate: 16000,            // Match recording sample rate
					},
				})
				
				if (mounted) {
					sharedStreamRef.current = stream
					setVadReady(true)
					console.log('[VoiceOverlay] ✅ Shared stream ready (AEC enabled)')
				} else {
					// Component unmounted, clean up
					stream.getTracks().forEach(track => track.stop())
				}
			} catch (err) {
				console.error('[VoiceOverlay] ❌ Failed to create shared stream:', err)
			}
		}
		
		initSharedStream()
		
		return () => {
			mounted = false
			// Clean up stream on unmount
			if (sharedStreamRef.current) {
				sharedStreamRef.current.getTracks().forEach(track => track.stop())
				sharedStreamRef.current = null
			}
		}
	}, [])

	// Memoize VAD callbacks to prevent re-initialization on every render
	const vadCallbacks = useMemo(() => ({
		onSpeechStart: () => {
			// In push-to-talk mode, ignore VAD
			if (pushToTalkMode) return

			console.log('[VFF VAD] 🎤 User speech started - buffering audio...')
			
			// Record speech start time
			speechStartTimeRef.current = Date.now()
			bargeInTriggeredRef.current = false  // Reset flag
			
			// Hide greeting carousel when user starts speaking
			if (showGreetingCarousel) {
				console.log('[VoiceOverlay] 🌍 User speaking - hiding greeting carousel')
				setShowGreetingCarousel(false)
				carouselDismissedRef.current = true
			}
			
			// Privacy Gate: Open audio flow (sends pre-buffer + live audio)
			const audioManager = connectionManager?.getAudioManager()
			if (audioManager) {
				audioManager.setVADActive(true) // Opens gate, flushes 400ms pre-buffer
			}
			
			// Schedule delayed barge-in - only trigger if speech lasts ≥450ms
			// This prevents throat clears/grunts from interrupting Gemini
			setTimeout(() => {
				const speechDuration = speechStartTimeRef.current 
					? Date.now() - speechStartTimeRef.current 
					: 0
				
				// Only trigger barge-in if speech is still active AND duration met
				if (speechStartTimeRef.current !== null && speechDuration >= MIN_TURN_DURATION_MS) {
					console.log(`[VFF VAD] ✅ Valid speech detected (${speechDuration}ms) - triggering barge-in`)
					bargeInTriggeredRef.current = true
					
					// Trigger VAD-based barge-in (interrupts Gemini if speaking)
					connectionManager?.onVADSpeechStart()
				}
			}, MIN_TURN_DURATION_MS)
		},
		onSpeechEnd: (audio: Float32Array) => {
			// In push-to-talk mode, ignore VAD
			if (pushToTalkMode) return

			// Calculate speech duration
			const speechDuration = speechStartTimeRef.current 
				? Date.now() - speechStartTimeRef.current 
				: 0
			
			// Privacy Gate: Always close audio flow (send silence for privacy)
			const audioManager = connectionManager?.getAudioManager()
			if (audioManager) {
				audioManager.setVADActive(false) // Closes gate, switches to silence
			}
			
			// Only send activity_end if we actually triggered barge-in
			// This prevents sending incomplete turns to Gemini
			if (bargeInTriggeredRef.current) {
				console.log(`[VFF VAD] ✅ Valid turn detected (${speechDuration}ms) - completing turn`)

				// Send activity_end to signal user is done speaking
				connectionManager?.onVADSpeechEnd()
			} else {
				console.log(`[VFF VAD] ⚠️ Turn too short (${speechDuration}ms < ${MIN_TURN_DURATION_MS}ms) - no barge-in triggered, discarding`)
			}
			
			// Clear state
			speechStartTimeRef.current = null
			bargeInTriggeredRef.current = false
		},
		onVADMisfire: () => {
			console.log('[VFF VAD] ⚠️ VAD misfire detected')
			// VAD false positive - clear start time
			speechStartTimeRef.current = null
		},
	}), [pushToTalkMode, connectionManager])

	// Memoize VAD options to prevent re-initialization when stream becomes ready
	const vadOptions = useMemo(() => ({
		sharedStream: vadReady ? sharedStreamRef.current : null,
		callbacks: vadCallbacks
	}), [vadReady, vadCallbacks])

	// Integrate professional VAD library with shared stream
	// Only initialize after stream is ready
	const vad = useDemoVAD(vadOptions)

	// Initialize connection manager on mount
	useEffect(() => {
		// If shared manager provided, use it
		if (sharedConnectionManager) {
			connectionManagerRef.current = sharedConnectionManager
			setConnectionManager(sharedConnectionManager)
			return
		}

		// Otherwise create our own (standalone mode)
		if (connectionManagerRef.current) {
			return
		}

		// Phase 3: Initialize with section-based state
		const state = WebFormStateManager.initWithSections(schema, sectionIndex)
		
		// Use the section schema (already sliced to section 1)
		// Pass shared stream for VAD coordination (prevents duplicate getUserMedia)
		const manager = createConnectionManager(
			state.schema, 
			(newStatus) => {
				setStatus(newStatus)
				setError(null)
			}, 
			'English', // Default to English
			sharedStreamRef.current || undefined // Pass shared stream if ready
		)
		
		connectionManagerRef.current = manager
		setConnectionManager(manager)

		return () => {
			// Only cleanup if we created the manager (not shared)
			if (!sharedConnectionManager) {
				if (connectionManagerRef.current) {
					connectionManagerRef.current.disconnect()
					connectionManagerRef.current = null
				}
				setConnectionManager(null)
			}
		}
	}, [schema, sectionIndex, sharedConnectionManager]) // Recreate when schema or index changes

	// Sync status from shared prop
	useEffect(() => {
		if (sharedStatus !== undefined) {
			setStatus(sharedStatus)
		}
	}, [sharedStatus])

	// Show greeting carousel when connection is established (only once per session)
	useEffect(() => {
		const isConnected = status.toLowerCase() === 'connected' || status.toLowerCase().startsWith('connected ')
		
		// Only show if connected AND not already dismissed AND not currently showing
		if (isConnected && !carouselDismissedRef.current && !showGreetingCarousel) {
			console.log('[VoiceOverlay] 🌍 Connection established - showing greeting carousel')
			setShowGreetingCarousel(true)
		}
		
		// Reset dismissed flag when disconnected (allow carousel on reconnect)
		if (!isConnected && carouselDismissedRef.current) {
			carouselDismissedRef.current = false
		}
	}, [status, showGreetingCarousel])

	// Auto-start VAD when connection becomes active (for shared manager mode)
	useEffect(() => {
		const isConnected = status.toLowerCase() === 'connected' || status.toLowerCase().startsWith('connected ')
		
		if (isConnected && !pushToTalkMode && !vad.loading && !vad.errored) {
			vad.start()
		} else if (!isConnected && !vad.loading) {
			vad.pause()
		}
	}, [status, pushToTalkMode, vad.loading, vad.errored, vad.start, vad.pause])

	// Hook up Gemini audio playback callbacks for greeting carousel dismissal
	useEffect(() => {
		// Set global callback when Gemini starts speaking
		window.vffOnAudioPlaybackStart = () => {
			// Hide greeting carousel when Gemini starts the conversation
			if (showGreetingCarousel) {
				console.log('[VoiceOverlay] 🌍 Gemini speaking - hiding greeting carousel')
				setShowGreetingCarousel(false)
				carouselDismissedRef.current = true
			}
		}

		return () => {
			// Clean up on unmount
			delete window.vffOnAudioPlaybackStart
		}
	}, [showGreetingCarousel])

	// Handle connect button
	const handleConnect = async () => {
		if (!connectionManager) return

		try {
			setError(null)
			
			// If paused, just resume (which will restart recording)
			if (connectionManager.isPaused()) {
				await connectionManager.resume()
				
				// Resume VAD
				setPendingVADStart(true)
				return
			}
			
			// Phase 3: Use regular connect() for initial connection
			// The WebFormConnection will use the section-based schema from state
			await connectionManager.connect()
			
			// Wait a moment for connection to fully establish
			await new Promise(resolve => setTimeout(resolve, 100))
			
			// Start recording after successful connection
			const currentStatus = connectionManager.getStatus()
			const isActive = currentStatus === 'connected' || currentStatus === 'switching_section'
			
			if (isActive) {
				await connectionManager.startRecording()

				// Start VAD detection only if NOT in push-to-talk mode
				if (!pushToTalkMode && !vad.loading && !vad.errored) {
					vad.start()
				} else if (vad.loading) {
					setPendingVADStart(true)
				}
			} else {
				console.error('[VoiceOverlay] Connection status not active, status is:', currentStatus)
			}
		} catch (err) {
			console.error('[VoiceOverlay] Connection error:', err)
			setError(err instanceof Error ? err.message : 'Connection failed')
			setStatus('Connection failed')
		}
	}

	// Handle disconnect button (now "pause")
	const handleDisconnect = () => {
		if (!connectionManager) return

		// Pause instead of disconnect (keeps connection warm)
		connectionManager.pause()
		
		// Pause VAD
		vad.pause()
	}

	// Start VAD as soon as the hook finishes loading after we request start
	useEffect(() => {
		if (!pendingVADStart) return
		if (vad.loading) return
		if (vad.errored) {
			setPendingVADStart(false)
			return
		}
		vad.start()
		setPendingVADStart(false)
	}, [pendingVADStart, vad.loading, vad.errored, vad.start])

	// Handle push-to-talk mode toggle
	const handlePushToTalkToggle = async () => {
		const newMode = !pushToTalkMode
		setPushToTalkMode(newMode)
		
		// Update connection manager PTT mode (disables energy-based barge-in)
		connectionManager?.setPushToTalkMode(newMode)
		
		const isCurrentlyConnected = status.toLowerCase() === 'connected' || 
		                            status.toLowerCase().startsWith('connected ') || 
		                            status.toLowerCase() === 'switching_section' || 
		                            status.toLowerCase().startsWith('reconnecting')
		
		if (newMode) {
			// Switching to push-to-talk: pause VAD (but keep mic recording for heartbeat)
			vad.pause()
			// Mute input so only silence is sent until button is pressed
			const audioManager = connectionManager?.getAudioManager()
			audioManager?.muteInput()
		} else {
			// Switching to VAD: start VAD
			if (isCurrentlyConnected && !vad.loading) {
				vad.start()
			}
			// Unmute input for normal VAD operation
			const audioManager = connectionManager?.getAudioManager()
			audioManager?.unmuteInput()
		}
		
		// Blur the checkbox so spacebar doesn't toggle it again
		setTimeout(() => {
			const checkbox = document.activeElement as HTMLElement
			if (checkbox && checkbox.tagName === 'INPUT') {
				checkbox.blur()
			}
		}, 0)
	}

	// Handle push-to-talk button press (mouse/touch)
	const handlePushToTalkPress = async () => {
		if (!pushToTalkMode) return
		const isCurrentlyConnected = status.toLowerCase() === 'connected' || 
		                            status.toLowerCase().startsWith('connected ') || 
		                            status.toLowerCase() === 'switching_section' || 
		                            status.toLowerCase().startsWith('reconnecting')
		if (!isCurrentlyConnected) return
		
		setIsHoldingPushToTalk(true)
		
		// UNMUTE: Allow real audio through
		const audioManager = connectionManager?.getAudioManager()
		audioManager?.unmuteInput()
		
		// BARGE-IN: Stop Gemini's audio if she's talking
		if (audioManager?.isSpeaking()) {
			audioManager.flushAudioQueue()
		}
		
		// Notify Gemini user is speaking
		connectionManager?.sendActivityStart()
	}

	const handlePushToTalkRelease = () => {
		if (!pushToTalkMode) return
		const isCurrentlyConnected = status.toLowerCase() === 'connected' || 
		                            status.toLowerCase().startsWith('connected ') || 
		                            status.toLowerCase() === 'switching_section' || 
		                            status.toLowerCase().startsWith('reconnecting')
		if (!isCurrentlyConnected) return
		
		setIsHoldingPushToTalk(false)
		
		// MUTE: Send silence instead of real audio
		const audioManager = connectionManager?.getAudioManager()
		audioManager?.muteInput()
		
		// Notify Gemini user stopped speaking
		connectionManager?.sendActivityEnd()
	}

	// Handle push-to-talk with spacebar (keyboard)
	useEffect(() => {
		if (!pushToTalkMode) return
		
		const isConnected = status.toLowerCase() === 'connected' || 
		                   status.toLowerCase().startsWith('connected ') || 
		                   status.toLowerCase() === 'switching_section' || 
		                   status.toLowerCase().startsWith('reconnecting')

		const handleKeyDown = (e: KeyboardEvent) => {
			if (e.code === 'Space') {
				// Only trigger if not typing in a form field
				const target = e.target as HTMLElement
				if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') return
				
				// ALWAYS prevent default to stop page scrolling in PTT mode
				e.preventDefault()
				
				// Only trigger PTT if connected and not a repeat event
				if (!e.repeat && isConnected) {
					handlePushToTalkPress()
				}
			}
		}

		const handleKeyUp = (e: KeyboardEvent) => {
			if (e.code === 'Space') {
				const target = e.target as HTMLElement
				if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') return
				
				// ALWAYS prevent default to stop page scrolling in PTT mode
				e.preventDefault()
				
				// Only trigger PTT if connected
				if (isConnected) {
					handlePushToTalkRelease()
				}
			}
		}

		window.addEventListener('keydown', handleKeyDown)
		window.addEventListener('keyup', handleKeyUp)

		return () => {
			window.removeEventListener('keydown', handleKeyDown)
			window.removeEventListener('keyup', handleKeyUp)
		}
	}, [pushToTalkMode, status])

	// Phase 3: Initialize section-based state and update section UI
	useEffect(() => {
		const state = WebFormStateManager.initWithSections(schema, sectionIndex)
		setCurrentSection(state.current_section || 1)
		setCompletedSections(state.completed_sections || new Set())
		
		// Update field counter
		const fieldCount = WebFormStateManager.getSectionFieldCount(state)
		setSectionFieldCount(fieldCount)
	}, [schema, sectionIndex])

	// Phase 3: Poll field count AND section state (updates as AI switches sections)
	useEffect(() => {
		const interval = setInterval(() => {
			const state = WebFormStateManager.load()
			if (state) {
				const fieldCount = WebFormStateManager.getSectionFieldCount(state)
				setSectionFieldCount(fieldCount)
				
				// Update section if changed (AI completed section and moved forward)
				if (state.current_section && state.current_section !== currentSection) {
					setCurrentSection(state.current_section)
				}
				
				// Update completed sections if changed
				if (state.completed_sections) {
					const currentCompleted = new Set(Array.from(completedSections))
					const newCompleted = new Set(Array.from(state.completed_sections))
					
					// Check if sets are different
					if (currentCompleted.size !== newCompleted.size || 
					    ![...currentCompleted].every(s => newCompleted.has(s))) {
						setCompletedSections(newCompleted)
					}
				}
			}
		}, 1000) // Update every second
		
		return () => clearInterval(interval)
	}, [currentSection, completedSections])

	// Handle clear form button  
	const handleClearForm = () => {
		if (!confirm('⚠️ Clear all form data?\n\nThis will delete all fields and reload the page.\nThis action cannot be undone.')) {
			return
		}

		// Clear sessionStorage
		WebFormStateManager.clear()
		
		// Clear all DOM fields
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
		
		// Remove checkmark badges
		document.querySelectorAll('.vff-field-badge').forEach(badge => badge.remove())
		
		// Reload page to reset all state
		window.location.reload()
	}

	// Make panel draggable
	useEffect(() => {
		const panel = panelRef.current
		if (!panel) return

		const handleMouseDown = (e: MouseEvent) => {
			const target = e.target as HTMLElement
			if (!target.closest('.vff-panel-header')) return

			isDraggingRef.current = true
			const rect = panel.getBoundingClientRect()
			offsetRef.current = {
				x: e.clientX - rect.left,
				y: e.clientY - rect.top,
			}
			e.preventDefault()
		}

		const handleMouseMove = (e: MouseEvent) => {
			if (!isDraggingRef.current) return

			const x = e.clientX - offsetRef.current.x
			const y = e.clientY - offsetRef.current.y

			panel.style.left = `${x}px`
			panel.style.top = `${y}px`
			panel.style.right = 'auto'
		}

		const handleMouseUp = () => {
			isDraggingRef.current = false
		}

		panel.addEventListener('mousedown', handleMouseDown)
		document.addEventListener('mousemove', handleMouseMove)
		document.addEventListener('mouseup', handleMouseUp)

		return () => {
			panel.removeEventListener('mousedown', handleMouseDown)
			document.removeEventListener('mousemove', handleMouseMove)
			document.removeEventListener('mouseup', handleMouseUp)
		}
	}, [])

	const isConnected = status.toLowerCase() === 'connected' || status.toLowerCase().startsWith('connected ') || status.toLowerCase() === 'switching_section' || status.toLowerCase().startsWith('reconnecting')
	const isPausedState = status.toLowerCase() === 'paused'
	const isWarming = status.toLowerCase().includes('warming')
	const isReady = status.toLowerCase() === 'ready'
	const fieldCount = schema.fields.length
	const requiredCount = schema.fields.filter(f => f.required).length

	// Debug logging removed - was causing 100+ logs per second in development mode

	return (
		<>
			{/* Greeting Carousel - Shows after connection established */}
			{showGreetingCarousel && (
				<GreetingCarousel 
					intervalMs={3000}
					onDismiss={() => {
						console.log('[VoiceOverlay] 🌍 User dismissed greeting carousel')
						setShowGreetingCarousel(false)
						carouselDismissedRef.current = true
					}}
				/>
			)}
			
			<div ref={panelRef} className={`vff-panel ${isCollapsed ? 'collapsed' : ''}`}>
			<div className="vff-panel-header">
				<span className="vff-title">🎤 Voice Form Filler</span>
				<div style={{ display: 'flex', gap: '8px' }}>
					<button className="vff-collapse" onClick={() => setIsCollapsed(!isCollapsed)} aria-label={isCollapsed ? "Expand" : "Collapse"}>
						{isCollapsed ? '▼' : '▲'}
					</button>
					{onClose && (
						<button className="vff-close" onClick={onClose} aria-label="Close">
							×
						</button>
					)}
				</div>
			</div>

			<div className="vff-panel-body">
				{/* Status */}
				<div className="vff-status">
					<span className="vff-status-icon">
						{isConnected ? '🟢' : '⚪'}
					</span>
					<span className="vff-status-text">{status}</span>
					{/* VAD speech detection indicator */}
					{vad.userSpeaking && !pushToTalkMode && (
						<span className="vff-vad-indicator" title="Voice detected">
							<span className="vff-vad-light"></span>
							<span className="vff-vad-label">Listening</span>
						</span>
					)}
				</div>

				{/* Section Navigation */}
				<div className="vff-section-nav">
					<div 
						className="vff-section-display"
						onClick={() => setShowSectionDropdown(!showSectionDropdown)}
					>
						<span className="vff-section-label">
							Section {currentSection} of {sectionIndex.total_sections}: {sectionIndex.sections[currentSection - 1]?.section_label}
						</span>
						<span className="vff-dropdown-arrow">{showSectionDropdown ? '▲' : '▼'}</span>
					</div>
					<div className="vff-field-counter">
						📊 {sectionFieldCount.filled} of {sectionFieldCount.total} fields completed
					</div>
					{showSectionDropdown && (
						<div className="vff-section-dropdown">
							{sectionIndex.sections.map((section) => (
								<div
									key={section.section_number}
									className={`vff-section-item ${currentSection === section.section_number ? 'active' : ''}`}
									onClick={async () => {
										if (!connectionManager) return
										
										setShowSectionDropdown(false)
										
										// Don't switch if already on this section
										if (section.section_number === currentSection) {
											return
										}
										
										try {
											setError(null)
											
											// Update UI immediately for responsiveness
											setCurrentSection(section.section_number)
											setStatus('Reconnecting to section ' + section.section_number)
											
											// Update field count for new section (from state, before reconnect)
											const state = WebFormStateManager.load()
											if (state) {
												// Switch section in state first
												const updatedState = WebFormStateManager.switchSection(state, section.section_number)
												const fieldCount = WebFormStateManager.getSectionFieldCount(updatedState)
												setSectionFieldCount(fieldCount)
											}
											
											// Now do the actual connection switch (async, may take time)
											await connectionManager.switchSection(section.section_number)
										} catch (err) {
											console.error('[VoiceOverlay] Section switch error:', err)
											setError(err instanceof Error ? err.message : 'Section switch failed')
										}
									}}
								>
									<span className="vff-section-status">
										{completedSections.has(section.section_number) ? '✓' : 
										 currentSection === section.section_number ? '→' : '○'}
									</span>
									<span className="vff-section-text">
										{section.section_number}. {section.section_label}
									</span>
								</div>
							))}
						</div>
					)}
				</div>

				{/* Controls */}
				<div className="vff-controls">
					{!isConnected && !isPausedState ? (
						<button 
							className="vff-button vff-connect" 
							onClick={handleConnect}
						>
							Connect to Voice
						</button>
					) : isPausedState ? (
						<button 
							className="vff-button vff-resume" 
							onClick={handleConnect}
						>
							▶️ Resume
						</button>
					) : (
						<button 
							className="vff-button vff-pause" 
							onClick={handleDisconnect}
						>
							⏸️ Pause
						</button>
					)}
					<button className="vff-button vff-clear-form" onClick={handleClearForm}>
						🗑️ Clear Form
					</button>
				</div>

				{/* Error Display */}
				{error && (
					<div className="vff-error">
						{error}
					</div>
				)}
			</div>

			{/* Styles */}
			<style>{`
				.vff-panel {
					position: fixed;
					top: 20px;
					right: 20px;
					width: 320px;
					background: white;
					border-radius: 12px;
					box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
					font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
					z-index: 10000;
					transition: height 0.3s ease;
				}

				.vff-panel.collapsed .vff-panel-body {
					display: none;
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

				.vff-collapse,
				.vff-close {
					background: none;
					border: none;
					color: white;
					font-size: 20px;
					cursor: pointer;
					padding: 0;
					width: 24px;
					height: 24px;
					line-height: 1;
					opacity: 0.8;
					transition: opacity 0.2s;
				}

				.vff-collapse:hover,
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
					flex: 1;
				}

				/* VAD Speech Detection Indicator */
				.vff-vad-indicator {
					display: flex;
					align-items: center;
					gap: 6px;
					padding: 4px 12px;
					background: #d1fae5;
					border-radius: 12px;
					border: 1px solid #10b981;
				}

				.vff-vad-label {
					font-size: 12px;
					color: #059669;
					font-weight: 600;
					text-transform: uppercase;
					letter-spacing: 0.5px;
				}

				.vff-vad-light {
					display: inline-block;
					width: 10px;
					height: 10px;
					border-radius: 50%;
					background: #10b981;
					animation: vff-vad-pulse 1s ease-in-out infinite;
					box-shadow: 0 0 4px #10b981;
				}

				@keyframes vff-vad-pulse {
					0%, 100% {
						opacity: 1;
						box-shadow: 0 0 4px #10b981;
					}
					50% {
						opacity: 0.6;
						box-shadow: 0 0 12px #10b981, 0 0 20px rgba(16, 185, 129, 0.4);
					}
				}

				.vff-section-nav {
					position: relative;
					margin-bottom: 16px;
					padding: 12px;
					background: #f0f4ff;
					border-radius: 8px;
					border: 1px solid #d0dbff;
				}

				.vff-section-display {
					display: flex;
					justify-content: space-between;
					align-items: center;
					cursor: pointer;
					padding: 4px;
					border-radius: 4px;
					transition: background 0.2s;
				}

				.vff-section-display:hover {
					background: rgba(102, 126, 234, 0.1);
				}

				.vff-section-label {
					font-size: 13px;
					font-weight: 600;
					color: #4c51bf;
					flex: 1;
				}

				.vff-dropdown-arrow {
					font-size: 10px;
					color: #667eea;
					margin-left: 8px;
				}

				.vff-field-counter {
					font-size: 12px;
					color: #666;
					margin-top: 8px;
					font-weight: 500;
				}

				.vff-section-dropdown {
					position: absolute;
					top: 100%;
					left: 0;
					right: 0;
					background: white;
					border: 1px solid #d0dbff;
					border-radius: 8px;
					margin-top: 4px;
					max-height: 300px;
					overflow-y: auto;
					box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
					z-index: 1000;
				}

				.vff-section-item {
					display: flex;
					align-items: center;
					gap: 8px;
					padding: 10px 12px;
					cursor: pointer;
					transition: background 0.2s;
					border-bottom: 1px solid #f0f0f0;
				}

				.vff-section-item:last-child {
					border-bottom: none;
				}

				.vff-section-item:hover {
					background: #f8f9ff;
				}

				.vff-section-item.active {
					background: #e0e7ff;
					font-weight: 600;
				}

				.vff-section-status {
					font-size: 14px;
					width: 20px;
					text-align: center;
				}

				.vff-section-text {
					font-size: 13px;
					flex: 1;
				}

				.vff-controls {
					display: flex;
					flex-direction: column;
					gap: 8px;
					margin-bottom: 16px;
				}

				.vff-ptt-toggle {
					padding: 12px;
					background: #f8f9ff;
					border-radius: 8px;
					border: 1px solid #d0dbff;
				}

				.vff-toggle-label-row {
					display: flex;
					align-items: center;
					justify-content: center;
					gap: 12px;
				}

				.vff-toggle-mode-label {
					font-size: 13px;
					font-weight: 600;
					color: #6b7280;
					min-width: 60px;
					text-align: center;
				}

				.vff-toggle-switch {
					position: relative;
					display: inline-block;
					width: 50px;
					height: 24px;
				}

				.vff-toggle-switch input {
					opacity: 0;
					width: 0;
					height: 0;
				}

				.vff-toggle-slider {
					position: absolute;
					cursor: pointer;
					top: 0;
					left: 0;
					right: 0;
					bottom: 0;
					background-color: #667eea;
					transition: 0.3s;
					border-radius: 24px;
				}

				.vff-toggle-slider:before {
					position: absolute;
					content: "";
					height: 18px;
					width: 18px;
					left: 3px;
					bottom: 3px;
					background-color: white;
					transition: 0.3s;
					border-radius: 50%;
					box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
				}

				.vff-toggle-switch input:checked + .vff-toggle-slider {
					background-color: #4c51bf;
				}

				.vff-toggle-switch input:checked + .vff-toggle-slider:before {
					transform: translateX(26px);
				}

				.vff-toggle-switch input:focus + .vff-toggle-slider {
					box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.3);
				}

				.vff-ptt-hint {
					display: block;
					margin-top: 6px;
					font-size: 11px;
					color: #666;
					font-style: italic;
					text-align: center;
				}

				.vff-ptt-button {
					background: linear-gradient(135deg, #4c51bf 0%, #667eea 100%);
					color: white;
					font-size: 15px;
					padding: 16px;
					user-select: none;
					-webkit-user-select: none;
					-webkit-touch-callout: none;
				}

				.vff-ptt-button:active,
				.vff-ptt-button.active {
					background: linear-gradient(135deg, #dc2626 0%, #ef4444 100%);
					transform: scale(0.98);
				}

				.vff-ptt-button:hover:not(:active) {
					background: linear-gradient(135deg, #5a67d8 0%, #7c3aed 100%);
					transform: translateY(-1px);
				}

				.vff-button {
					padding: 12px 16px;
					border: none;
					border-radius: 8px;
					font-size: 14px;
					font-weight: 600;
					cursor: pointer;
					transition: all 0.2s;
					font-family: inherit;
				}

				.vff-connect {
					background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
					color: white;
				}

				.vff-connect:hover {
					transform: translateY(-1px);
					box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
				}

				.vff-pause {
					background: #f59e0b;
					color: white;
				}

				.vff-pause:hover {
					background: #d97706;
					transform: translateY(-1px);
				}

				.vff-resume {
					background: #10b981;
					color: white;
				}

				.vff-resume:hover {
					background: #059669;
					transform: translateY(-1px);
				}

				.vff-disconnect {
					background: #dc3545;
					color: white;
				}

				.vff-disconnect:hover {
					background: #c82333;
					transform: translateY(-1px);
				}

				.vff-clear-form {
					background: #6c757d;
					color: white;
				}

				.vff-clear-form:hover {
					background: #5a6268;
				}

				.vff-error {
					padding: 12px;
					background: #f8d7da;
					border: 1px solid #f5c6cb;
					border-radius: 8px;
					color: #721c24;
					font-size: 13px;
					margin-bottom: 16px;
				}

				.vff-info {
					text-align: center;
					opacity: 0.6;
				}

				.vff-info small {
					font-size: 12px;
					line-height: 1.4;
				}

				/* Mobile responsiveness */
				@media (max-width: 768px) {
					.vff-panel {
						width: calc(100% - 32px);
						max-width: 320px;
						right: 16px;
						top: 16px;
					}
				}
			`}</style>
		</div>
		</>
	)
}
