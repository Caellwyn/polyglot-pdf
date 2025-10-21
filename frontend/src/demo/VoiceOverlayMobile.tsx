/**
 * VoiceOverlayMobile - Compact circular FAB-style overlay for mobile
 * 
 * Design: Floating action button that expands into a compact control panel
 * - Minimizes screen real estate
 * - Fun circular design with radial buttons
 * - Clear visual feedback for connection status
 * IMPORTANT: if you change logic here, change it in VoiceOverlay.tsx too
 */

import React, { useEffect, useRef, useState, useMemo } from 'react'
import { createConnectionManager, type ConnectionManager } from '../shared/connection'
import { WebFormStateManager, type FormSchema, type SectionIndex } from '../webFormState'
import { computeNextField, formatNextFieldHint } from '../navigation'
import { useDemoVAD } from './useDemoVAD'
import { GreetingCarousel } from './GreetingCarousel'

interface VoiceOverlayMobileProps {
	schema: FormSchema
	sectionIndex: SectionIndex
	wsUrl?: string
	connectionManager?: ConnectionManager
	status?: string
}

export function VoiceOverlayMobile({ schema, sectionIndex, wsUrl, connectionManager: sharedConnectionManager, status: sharedStatus }: VoiceOverlayMobileProps) {
	const [connectionManager, setConnectionManager] = useState<ConnectionManager | null>(sharedConnectionManager || null)
	const connectionManagerRef = useRef<ConnectionManager | null>(sharedConnectionManager || null)
	const [status, setStatus] = useState<string>(sharedStatus || 'Ready')
	const [error, setError] = useState<string | null>(null)
	const [isExpanded, setIsExpanded] = useState(false)
	const [pendingVADStart, setPendingVADStart] = useState(false)
	const [currentSection, setCurrentSection] = useState(1)
	const [completedSections, setCompletedSections] = useState<Set<number>>(new Set())
	const [sectionFieldCount, setSectionFieldCount] = useState({ filled: 0, total: 12 })
	const [pushToTalkMode, setPushToTalkMode] = useState(false)
	const [isHoldingPushToTalk, setIsHoldingPushToTalk] = useState(false)
	const [showGreetingCarousel, setShowGreetingCarousel] = useState(false)
	const carouselDismissedRef = useRef(false)  // Track if user/system dismissed carousel

	// Create shared audio stream ONCE on mount (before VAD initialization)
	// This ensures both VAD and recording use the SAME stream with browser AEC
	const sharedStreamRef = useRef<MediaStream | null>(null)
	const [vadReady, setVadReady] = useState(false)

	// Track speech duration to prevent short grunts/noises from interrupting Gemini
	const speechStartTimeRef = useRef<number | null>(null)
	const bargeInTriggeredRef = useRef<boolean>(false)  // Track if we triggered barge-in for this speech event
	const MIN_TURN_DURATION_MS = 450  // Minimum 450ms of speech before triggering barge-in
	
	// VAD warmup period - prevents false positives during initial calibration
	// During warmup: VAD runs (calibrates), but we block barge-in signals and keep privacy gate closed
	const vadWarmupActiveRef = useRef<boolean>(false)
	
	// Activity watchdog - prevents conversational deadlock with progressive escalation
	const lastActivityTimeRef = useRef<number>(Date.now())
	const activityWatchdogRef = useRef<NodeJS.Timeout | null>(null)
	const escalationLevelRef = useRef<number>(0)  // Track escalation level (0-3)
	const waitingForFarewellRef = useRef<boolean>(false)  // Track if we're waiting for Level 3 farewell to complete
	const INACTIVITY_TIMEOUT_MS = 6000  // 6 seconds before each escalation
	const MAX_ESCALATION_LEVEL = 3  // 3 levels = disconnect (18 seconds total)
	
	// Create stream once on mount
	useEffect(() => {
		let mounted = true
		
		async function initSharedStream() {
			try {
				console.log('[VoiceOverlayMobile] 🎤 Creating shared audio stream...')
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
					console.log('[VoiceOverlayMobile] ✅ Shared stream ready (AEC enabled)')
				} else {
					// Component unmounted, clean up
					stream.getTracks().forEach(track => track.stop())
				}
			} catch (err) {
				console.error('[VoiceOverlayMobile] ❌ Failed to create shared stream:', err)
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
			
			// During warmup, ignore speech events (let VAD calibrate)
			if (vadWarmupActiveRef.current) {
				console.log('[VFF VAD] 🔇 Speech detected during warmup - ignoring (calibrating...)')
				return
			}
			
			console.log('[VFF VAD] 🎤 User speech started - buffering audio...')
			
			// Record speech start time
			speechStartTimeRef.current = Date.now()
			bargeInTriggeredRef.current = false  // Reset flag
			
			// Hide greeting carousel when user starts speaking
			if (showGreetingCarousel) {
				console.log('[VoiceOverlayMobile] 🌍 User speaking - hiding greeting carousel')
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
			
			// During warmup, ignore speech events
			if (vadWarmupActiveRef.current) {
				return
			}
			
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
				
				// User completed a valid turn - reset escalation to 0 and restart timer
				onUserTurnComplete()
			} else {
				console.log(`[VFF VAD] ⚠️ Turn too short (${speechDuration}ms < ${MIN_TURN_DURATION_MS}ms) - no barge-in triggered, discarding`)
				
				// Short noise - didn't interrupt Gemini, so nothing to clean up
				// Just restart timer but don't reset escalation (user not actively participating)
				restartActivityTimer()
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
			'English',
			sharedStreamRef.current || undefined // Pass shared stream if ready
		)
		
		connectionManagerRef.current = manager
		setConnectionManager(manager)

		return () => {
			// Stop activity watchdog on unmount
			stopActivityWatchdog()
			
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
			console.log('[VoiceOverlayMobile] 🌍 Connected - showing greeting carousel')
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

	// Hook up Gemini audio playback and turn completion callbacks for activity watchdog
	useEffect(() => {
		let debounceTimeout: NodeJS.Timeout | null = null
		let turnCompleteReceived = false  // Track if backend signaled turn_complete
		
		// Set global callback when backend signals turn is complete (all chunks sent)
		window.vffOnTurnComplete = () => {
			turnCompleteReceived = true
			console.log('[VFF Watchdog] ✅ Turn complete signal received from backend')
		}
		
		// Set global callback when Gemini STARTS speaking (STOP timer entirely)
		window.vffOnAudioPlaybackStart = () => {
			console.log('[VFF Watchdog] 🔊 Gemini started speaking - pausing timer')
			// Don't restart timer yet - wait for speech to end
			// Just update lastActivityTime so timer doesn't fire during speech
			lastActivityTimeRef.current = Date.now()
		}
		
		// Set global callback when Gemini STOPS speaking (START timer after audio queue empties)
		window.vffOnAudioPlaybackEnd = () => {
			// End VAD warmup after Gemini's first greeting completes
			if (vadWarmupActiveRef.current) {
				console.log('[VFF VAD] ✅ Warmup complete - VAD now active')
				vadWarmupActiveRef.current = false
			}
			
			// Hide greeting carousel when Gemini starts the conversation
			if (showGreetingCarousel) {
				console.log('[VoiceOverlayMobile] 🌍 Gemini speaking - hiding greeting carousel')
				setShowGreetingCarousel(false)
				carouselDismissedRef.current = true
			}
			
			if (debounceTimeout) {
				clearTimeout(debounceTimeout)
			}
			
			// Different behavior if waiting for farewell vs. normal conversation
			const silenceThreshold = waitingForFarewellRef.current ? 100 : 500
			
			debounceTimeout = setTimeout(() => {
				// Normal case: Gemini finished speaking, restart activity timer
				if (!waitingForFarewellRef.current) {
					console.log('[VFF Watchdog] 🔊 Gemini finished speaking - restarting timer')
					restartActivityTimer()
				} else {
					// Farewell case: Only disconnect if we've received turn_complete signal
					if (turnCompleteReceived) {
						console.log('[VFF Watchdog] 🚪 Farewell complete (turn_complete + 100ms silence) - ending Gemini session')
						waitingForFarewellRef.current = false
						turnCompleteReceived = false  // Reset for next time
						
						// Stop watchdog
						stopActivityWatchdog()
						
						// Pause VAD
						vad.pause()
						
						// Close Gemini session only (keeps WebSocket alive)
						if (connectionManager) {
							connectionManager.endGeminiSession()
						}
						
						// Update UI
						setStatus('Ready')
						console.log('[VFF Watchdog] ✅ Gemini session closed, ready to reconnect')
					} else {
						console.log('[VFF Watchdog] ⏳ Audio silence but no turn_complete yet - waiting...')
					}
				}
				
				debounceTimeout = null
			}, silenceThreshold)
		}
		
		return () => {
			// Clean up on unmount
			if (debounceTimeout) {
				clearTimeout(debounceTimeout)
			}
			delete window.vffOnAudioPlaybackEnd
			delete window.vffOnAudioPlaybackStart
			delete window.vffOnTurnComplete
		}
	}, [connectionManager, vad]) // Include deps for disconnect logic

	// Called when user speaks (resets escalation to 0, restarts timer)
	const onUserTurnComplete = () => {
		console.log('[VFF Watchdog] 🗣️ User turn complete - resetting escalation to 0')
		escalationLevelRef.current = 0
		lastActivityTimeRef.current = Date.now()
	}
	
	// Called when timer runs out (increments escalation, restarts timer)
	const onInactivityTimeout = () => {
		// Don't escalate past maximum
		if (escalationLevelRef.current >= MAX_ESCALATION_LEVEL) {
			console.log(`[VFF Watchdog] ⏸️ Already at max escalation level ${MAX_ESCALATION_LEVEL} - waiting for farewell to complete`)
			return
		}
		
		escalationLevelRef.current++
		console.log(`[VFF Watchdog] ⏱️ Inactivity timeout - escalation level ${escalationLevelRef.current}/${MAX_ESCALATION_LEVEL}`)
		lastActivityTimeRef.current = Date.now()
		
		// Handle escalation
		if (escalationLevelRef.current === 1) {
			handleEscalationLevel1()
		} else if (escalationLevelRef.current === 2) {
			handleEscalationLevel2()
		} else if (escalationLevelRef.current >= MAX_ESCALATION_LEVEL) {
			handleEscalationLevel3()
		}
	}

	// Start activity watchdog
	const startActivityWatchdog = () => {
		console.log('[VFF Watchdog] 🟢 Starting activity monitoring')
		// Clear any existing watchdog
		if (activityWatchdogRef.current) {
			clearInterval(activityWatchdogRef.current)
		}

		// Reset counters
		escalationLevelRef.current = 0
		lastActivityTimeRef.current = Date.now()

		// Start periodic check
		activityWatchdogRef.current = setInterval(() => {
			const timeSinceActivity = Date.now() - lastActivityTimeRef.current

			if (timeSinceActivity >= INACTIVITY_TIMEOUT_MS) {
				onInactivityTimeout()
			}
		}, 1000) // Check every second
	}

	// Stop activity watchdog
	const stopActivityWatchdog = () => {
		if (activityWatchdogRef.current) {
			clearInterval(activityWatchdogRef.current)
			activityWatchdogRef.current = null
		}
		escalationLevelRef.current = 0
	}
	
	// Restart timer (called when anyone speaks - stops timer during speech, restarts after)
	const restartActivityTimer = () => {
		lastActivityTimeRef.current = Date.now()
		// Note: Does NOT reset escalation level (only user turn does that)
	}

	// Escalation Level 1: Re-prompt for current field
	const handleEscalationLevel1 = () => {
		if (!connectionManager) return
		
		console.log('[VFF Watchdog] 📝 Level 1: Field re-prompt')
		
		// Get LAST field hint from sessionStorage (the field Gemini last asked for)
		// This ensures we re-prompt for the SAME field, not move to the next one
		const lastHint = sessionStorage.getItem('vff_last_field_hint')
		
		if (lastHint) {
			// Re-use the exact same field hint Gemini last used
			console.log('[VFF Watchdog] Re-prompting for last field:', lastHint)
			connectionManager.sendRecoveryPrompt(1, lastHint)
		} else {
			// Fallback: compute next unfilled field (should rarely happen)
			const stateJson = sessionStorage.getItem('vff_state')
			if (!stateJson) {
				connectionManager.sendRecoveryPrompt(1)
				return
			}

			const state = JSON.parse(stateJson)
			const nextField = computeNextField(state)
			
			if (nextField) {
				const hint = formatNextFieldHint(nextField)
				connectionManager.sendRecoveryPrompt(1, hint)
			} else {
				connectionManager.sendRecoveryPrompt(1)
			}
		}
	}

	// Escalation Level 2: "Are you still there?"
	const handleEscalationLevel2 = () => {
		if (!connectionManager) return
		
		console.log('[VFF Watchdog] � Level 2: Are you still there?')
		
		// Backend config has the actual prompt wording
		connectionManager.sendRecoveryPrompt(2)
	}
	
	// Escalation Level 3: Close session gracefully
	const handleEscalationLevel3 = () => {
		if (!connectionManager) return
		
		console.log('[VFF Watchdog] 🚪 Level 3: Closing session due to inactivity')
		
		// Set flag to indicate we're waiting for the farewell message to complete
		waitingForFarewellRef.current = true
		
		// Send goodbye via backend config prompt
		// Backend will send turn_complete message when Gemini finishes speaking
		connectionManager.sendRecoveryPrompt(3)
		
		// CRITICAL: Set timeout fallback in case audio silence detection fails
		// This prevents infinite waiting if Gemini gets stuck
		// Normal path: audio stops → 100ms silence → disconnect (fast and clean)
		// Fallback path: 15 second timeout → force disconnect (safety net)
		setTimeout(() => {
			if (waitingForFarewellRef.current) {
				console.log('[VFF Watchdog] ⏱️ Farewell timeout - forcing disconnect after 15s (audio silence detection failed)')
				waitingForFarewellRef.current = false
				
				// Stop watchdog
				stopActivityWatchdog()
				
				// Pause VAD
				vad.pause()
				
				// Full disconnect
				if (connectionManager) {
					connectionManager.disconnect()
				}
				
				// Update UI
				setStatus('Ready')
				console.log('[VFF Watchdog] ✅ Session closed (timeout fallback) and ready to reconnect')
			}
		}, 15000) // 15 second fallback timeout
	}

	const handleConnect = async () => {
		if (!connectionManager) return
		try {
			setError(null)
			
			// If paused, just resume (which will restart recording)
			if (connectionManager.isPaused()) {
				await connectionManager.resume()
				setPendingVADStart(true)
				return
			}
			
			// Otherwise, full connect
			await connectionManager.connect()
			
			// Wait a moment for connection to fully establish
			await new Promise(resolve => setTimeout(resolve, 100))
			
			// Start recording after successful connection
			const currentStatus = connectionManager.getStatus()
			const isActive = currentStatus === 'connected' || currentStatus === 'switching_section'
			
			if (isActive) {
				await connectionManager.startRecording()
				
				// Enable VAD warmup mode - will auto-disable after Gemini's first greeting
				vadWarmupActiveRef.current = true
				console.log('[VFF VAD] 🔇 Warmup mode enabled - ignoring speech events until Gemini finishes greeting')
				
				// Start activity watchdog
				startActivityWatchdog()
				
				// Start VAD only if NOT in push-to-talk mode
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
			stopActivityWatchdog()  // Stop watchdog on error
		}
	}

	const handleDisconnect = () => {
		if (!connectionManager) return
		
		// Stop activity watchdog
		stopActivityWatchdog()
		
		// Pause instead of disconnect (keeps connection warm)
		connectionManager.pause()
		
		// Pause VAD
		vad.pause()
	}

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
			// Switching to PTT: pause VAD
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
	}

	// Handle push-to-talk button press (touch)
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

	// Phase 3: Initialize section-based state and update section UI
	useEffect(() => {
		const state = WebFormStateManager.initWithSections(schema, sectionIndex)
		setCurrentSection(state.current_section || 1)
		setCompletedSections(state.completed_sections || new Set())
		
		// Update field counter
		const fieldCount = WebFormStateManager.getSectionFieldCount(state)
		setSectionFieldCount(fieldCount)
	}, [schema, sectionIndex])

	// Phase 3: Poll field count (updates as user fills fields)
	useEffect(() => {
		const interval = setInterval(() => {
			const state = WebFormStateManager.load()
			if (state) {
				const fieldCount = WebFormStateManager.getSectionFieldCount(state)
				setSectionFieldCount(fieldCount)
			}
		}, 1000) // Update every second
		
		return () => clearInterval(interval)
	}, [])

	const isConnected = status.toLowerCase() === 'connected' || status.toLowerCase().startsWith('connected ')
	const isPausedState = status.toLowerCase() === 'paused'
	const isWarming = status.toLowerCase().includes('warming')
	const isReady = status.toLowerCase() === 'ready'
	const fieldCount = schema.fields.length
	const requiredCount = schema.fields.filter(f => f.required).length

	// Status color
	const statusColor = isConnected ? '#10b981' : isPausedState ? '#f59e0b' : isWarming ? '#f59e0b' : isReady ? '#3b82f6' : '#6b7280'

	return (
		<>
			{/* Greeting Carousel - Show when connected */}
			{showGreetingCarousel && (
				<GreetingCarousel 
					intervalMs={3000}
					onDismiss={() => {
						console.log('[VoiceOverlayMobile] 🌍 User dismissed greeting carousel')
						setShowGreetingCarousel(false)
						carouselDismissedRef.current = true
					}}
				/>
			)}
			
			{/* Main FAB */}
			<div className="vff-fab" onClick={() => setIsExpanded(!isExpanded)}>
				<div className="vff-fab-pulse" style={{ borderColor: statusColor }}></div>
				{/* VAD speech detection indicator - small green dot badge */}
				{vad.userSpeaking && !pushToTalkMode && (
					<div className="vff-fab-vad-badge">
						<div className="vff-fab-vad-dot"></div>
					</div>
				)}
				<div className="vff-fab-icon" style={{ background: statusColor }}>
					🎤
				</div>
			</div>

			{/* Expanded Panel */}
			{isExpanded && (
				<div className="vff-panel-mobile">
					<div className="vff-panel-header">
						<span className="vff-title">Voice Form Filler</span>
						<button className="vff-close" onClick={() => setIsExpanded(false)}>×</button>
					</div>

					<div className="vff-panel-body">
						{/* Status */}
						<div className="vff-status-compact">
							<div className="vff-status-dot" style={{ background: statusColor }}></div>
							<span className="vff-status-text">{status}</span>
						</div>

						{/* Push-to-Talk Toggle */}
						{(isConnected || isPausedState) && (
							<div className="vff-ptt-toggle-mobile">
								<div className="vff-toggle-label-row">
									<span className="vff-toggle-mode-label">🎤 Auto</span>
									<label className="vff-toggle-switch">
										<input
											type="checkbox"
											checked={pushToTalkMode}
											onChange={handlePushToTalkToggle}
											onKeyDown={(e) => {
												// Prevent spacebar from toggling checkbox
												if (e.code === 'Space') {
													e.preventDefault()
												}
											}}
										/>
										<span className="vff-toggle-slider"></span>
									</label>
									<span className="vff-toggle-mode-label">⌨️ PTT</span>
								</div>
							</div>
						)}						{/* Push-to-Talk Button (only in PTT mode when connected) */}
						{pushToTalkMode && isConnected && (
							<button
								className={`vff-action-btn vff-ptt-btn ${isHoldingPushToTalk ? 'active' : ''}`}
								onTouchStart={handlePushToTalkPress}
								onTouchEnd={handlePushToTalkRelease}
								onMouseDown={handlePushToTalkPress}
								onMouseUp={handlePushToTalkRelease}
								onMouseLeave={handlePushToTalkRelease}
							>
								{isHoldingPushToTalk ? '🔴 Speaking...' : '⚫ Hold to Speak'}
							</button>
						)}

						{/* Action Button */}
						{!isConnected && !isPausedState ? (
							<button className="vff-action-btn vff-connect-btn" onClick={handleConnect}>
								🎙️ Connect
							</button>
						) : isPausedState ? (
							<button className="vff-action-btn vff-resume-btn" onClick={handleConnect}>
								▶️ Resume
							</button>
						) : (
							<button className="vff-action-btn vff-pause-btn" onClick={handleDisconnect}>
								⏸️ Pause
							</button>
						)}

						{/* Error */}
						{error && <div className="vff-error-compact">{error}</div>}

						{/* Info */}
						<div className="vff-info-compact">
							{fieldCount} fields · {requiredCount} required
						</div>
					</div>
				</div>
			)}

			<style>{`
				/* Floating Action Button */
				.vff-fab {
					position: fixed;
					bottom: 20px;
					right: 20px;
					width: 56px;
					height: 56px;
					cursor: pointer;
					z-index: 9999;
					filter: drop-shadow(0 4px 12px rgba(0, 0, 0, 0.15));
				}

				.vff-fab-pulse {
					position: absolute;
					width: 100%;
					height: 100%;
					border-radius: 50%;
					border: 3px solid;
					animation: vff-pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
				}

				@keyframes vff-pulse {
					0%, 100% {
						opacity: 1;
						transform: scale(1);
					}
					50% {
						opacity: 0.3;
						transform: scale(1.1);
					}
				}

				.vff-fab-icon {
					position: absolute;
					width: 100%;
					height: 100%;
					border-radius: 50%;
					display: flex;
					align-items: center;
					justify-content: center;
					font-size: 24px;
					transition: transform 0.2s;
				}

				.vff-fab:active .vff-fab-icon {
					transform: scale(0.9);
				}

				/* VAD Speech Detection Badge - Small green dot in top-right */
				.vff-fab-vad-badge {
					position: absolute;
					top: -4px;
					right: -4px;
					width: 20px;
					height: 20px;
					background: white;
					border-radius: 50%;
					display: flex;
					align-items: center;
					justify-content: center;
					z-index: 10;
					box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
				}

				.vff-fab-vad-dot {
					width: 12px;
					height: 12px;
					border-radius: 50%;
					background: #10b981;
					animation: vff-vad-pulse 1s ease-in-out infinite;
				}

				@keyframes vff-vad-pulse {
					0%, 100% {
						opacity: 1;
						transform: scale(1);
						box-shadow: 0 0 4px #10b981;
					}
					50% {
						opacity: 0.6;
						transform: scale(1.2);
						box-shadow: 0 0 8px #10b981;
					}
				}

				/* Compact Panel */
				.vff-panel-mobile {
					position: fixed;
					bottom: 90px;
					right: 20px;
					width: 240px;
					background: white;
					border-radius: 16px;
					box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
					z-index: 9998;
					font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
					animation: vff-slide-up 0.2s ease-out;
				}

				@keyframes vff-slide-up {
					from {
						opacity: 0;
						transform: translateY(10px);
					}
					to {
						opacity: 1;
						transform: translateY(0);
					}
				}

				.vff-panel-header {
					display: flex;
					justify-content: space-between;
					align-items: center;
					padding: 12px 16px;
					border-bottom: 1px solid #e5e7eb;
				}

				.vff-title {
					font-weight: 600;
					font-size: 14px;
					color: #111827;
				}

				.vff-close {
					background: none;
					border: none;
					font-size: 24px;
					color: #6b7280;
					cursor: pointer;
					padding: 0;
					width: 24px;
					height: 24px;
					line-height: 1;
				}

				.vff-panel-body {
					padding: 16px;
					display: flex;
					flex-direction: column;
					gap: 12px;
				}

				.vff-status-compact {
					display: flex;
					align-items: center;
					gap: 8px;
					padding: 8px 12px;
					background: #f9fafb;
					border-radius: 8px;
				}

				.vff-status-dot {
					width: 8px;
					height: 8px;
					border-radius: 50%;
				}

				.vff-status-text {
					font-size: 12px;
					font-weight: 500;
					color: #374151;
				}

				.vff-ptt-toggle-mobile {
					padding: 10px 12px;
					background: #f8f9ff;
					border-radius: 8px;
					border: 1px solid #d0dbff;
				}

				.vff-toggle-label-row {
					display: flex;
					align-items: center;
					justify-content: center;
					gap: 10px;
				}

				.vff-toggle-mode-label {
					font-size: 12px;
					font-weight: 600;
					color: #6b7280;
					min-width: 50px;
					text-align: center;
				}

				.vff-toggle-switch {
					position: relative;
					display: inline-block;
					width: 44px;
					height: 22px;
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
					border-radius: 22px;
				}

				.vff-toggle-slider:before {
					position: absolute;
					content: "";
					height: 16px;
					width: 16px;
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
					transform: translateX(22px);
				}

				.vff-toggle-switch input:focus + .vff-toggle-slider {
					box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.3);
				}

				.vff-action-btn {
					width: 100%;
					padding: 12px;
					border: none;
					border-radius: 8px;
					font-size: 14px;
					font-weight: 600;
					cursor: pointer;
					transition: all 0.2s;
					user-select: none;
					-webkit-user-select: none;
					-webkit-touch-callout: none;
				}

				.vff-ptt-btn {
					background: linear-gradient(135deg, #4c51bf 0%, #667eea 100%);
					color: white;
					font-size: 14px;
					padding: 14px;
				}

				.vff-ptt-btn:active,
				.vff-ptt-btn.active {
					background: linear-gradient(135deg, #dc2626 0%, #ef4444 100%);
					transform: scale(0.95);
				}

				.vff-connect-btn {
					background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
					color: white;
				}

				.vff-connect-btn:active {
					transform: scale(0.98);
				}

				.vff-pause-btn {
					background: #f59e0b;
					color: white;
				}

				.vff-pause-btn:active {
					transform: scale(0.98);
				}

				.vff-resume-btn {
					background: #10b981;
					color: white;
				}

				.vff-resume-btn:active {
					transform: scale(0.98);
				}

				.vff-disconnect-btn {
					background: #ef4444;
					color: white;
				}

				.vff-disconnect-btn:active {
					transform: scale(0.98);
				}

				.vff-error-compact {
					padding: 8px 12px;
					background: #fef2f2;
					border: 1px solid #fecaca;
					border-radius: 8px;
					color: #991b1b;
					font-size: 12px;
				}

				.vff-info-compact {
					text-align: center;
					font-size: 11px;
					color: #6b7280;
				}

				/* Mobile Adjustments */
				@media (max-width: 480px) {
					.vff-panel-mobile {
						right: 10px;
						width: calc(100vw - 20px);
						max-width: 280px;
					}

					.vff-fab {
						bottom: 16px;
						right: 16px;
					}
				}
			`}</style>
		</>
	)
}
