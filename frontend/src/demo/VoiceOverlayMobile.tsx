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
import { SPOKEN_LANGUAGES } from '../shared/languages'

interface VoiceOverlayMobileProps {
	schema: FormSchema
	sectionIndex: SectionIndex
	wsUrl?: string
	connectionManager?: ConnectionManager
	status?: string
	// FIX #1: Shared audio stream passed from parent (prevents race conditions)
	sharedStream?: MediaStream | null
	// FIX #4: Stream error from parent (for error visibility)
	streamError?: string | null
}

export function VoiceOverlayMobile({ schema, sectionIndex, wsUrl, connectionManager: sharedConnectionManager, status: sharedStatus, sharedStream, streamError }: VoiceOverlayMobileProps) {
	const [connectionManager, setConnectionManager] = useState<ConnectionManager | null>(sharedConnectionManager || null)
	const connectionManagerRef = useRef<ConnectionManager | null>(sharedConnectionManager || null)
	const [status, setStatus] = useState<string>(sharedStatus || 'Ready')
	const [error, setError] = useState<string | null>(null)
	const [isExpanded, setIsExpanded] = useState(false)
	// FIX #2: Removed pendingVADStart state - consolidated VAD start logic into single useEffect
	const [currentSection, setCurrentSection] = useState(1)
	const [completedSections, setCompletedSections] = useState<Set<number>>(new Set())
	const [sectionFieldCount, setSectionFieldCount] = useState({ filled: 0, total: 12 })
	const [pushToTalkMode, setPushToTalkMode] = useState(false)
	const [isHoldingPushToTalk, setIsHoldingPushToTalk] = useState(false)
	const [showGreetingCarousel, setShowGreetingCarousel] = useState(false)
	const carouselDismissedRef = useRef(false)  // Track if user/system dismissed carousel
	const [selectedLanguage, setSelectedLanguage] = useState('English')  // Track selected spoken language

	// FIX #1: Use shared stream from parent (created before React rendering)
	// No need to create our own stream - parent already did this to prevent race conditions
	const sharedStreamRef = useRef<MediaStream | null>(sharedStream || null)

	// Track speech duration to prevent short grunts/noises from interrupting Gemini
	const speechStartTimeRef = useRef<number | null>(null)
	const bargeInTriggeredRef = useRef<boolean>(false)  // Track if we triggered barge-in for this speech event
	const MIN_TURN_DURATION_MS = 450  // Minimum 450ms of speech before triggering barge-in

	// FIX #1: Update stream ref when prop changes (parent manages lifecycle)
	useEffect(() => {
		sharedStreamRef.current = sharedStream || null
		console.log('[VoiceOverlayMobile] 🔗 Using shared stream from parent:', !!sharedStream)
	}, [sharedStream])

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

	// FIX #1: VAD options with shared stream (stream is already ready from parent)
	const vadOptions = useMemo(() => ({
		sharedStream: sharedStreamRef.current,
		callbacks: vadCallbacks
	}), [vadCallbacks, sharedStream])

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

		// FIX #1: Connection manager receives stream from parent (already created)
		const manager = createConnectionManager(
			state.schema,
			(newStatus) => {
				setStatus(newStatus)
				setError(null)
			},
			'English',
			sharedStream || undefined // Pass shared stream from parent
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
			console.log('[VoiceOverlayMobile] 🌍 Connected - showing greeting carousel')
			setShowGreetingCarousel(true)
		}
		
		// Reset dismissed flag when disconnected (allow carousel on reconnect)
		if (!isConnected && carouselDismissedRef.current) {
			carouselDismissedRef.current = false
		}
	}, [status, showGreetingCarousel])

	// FIX #2: SINGLE SOURCE OF TRUTH for VAD state management
	// This replaces 3 separate code paths with one consolidated control flow
	useEffect(() => {
		const isConnected = status.toLowerCase() === 'connected' ||
		                    status.toLowerCase().startsWith('connected ')

		// VAD should run when:
		// 1. Connected to backend
		// 2. NOT in push-to-talk mode
		// 3. VAD library finished loading
		// 4. No VAD errors occurred
		const shouldRunVAD = isConnected && !pushToTalkMode && !vad.loading && !vad.errored

		if (shouldRunVAD && !vad.userSpeaking) {
			console.log('[VoiceOverlayMobile] 🎙️ Starting VAD (conditions met)')
			vad.start()
		} else if (!shouldRunVAD && vad.userSpeaking) {
			console.log('[VoiceOverlayMobile] ⏸️ Pausing VAD (conditions not met)')
			vad.pause()
		}

		// FIX #4: Display VAD errors to user
		if (vad.errored) {
			setError(`Voice detection error: ${vad.errored}`)
		}
		// NOTE: vad.start and vad.pause intentionally excluded from deps
		// They are stable callbacks that shouldn't trigger re-renders
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [status, pushToTalkMode, vad.loading, vad.errored, vad.userSpeaking])

	// Hook up Gemini audio playback callbacks for greeting carousel dismissal
	useEffect(() => {
		// Set global callback when Gemini starts speaking
		window.vffOnAudioPlaybackStart = () => {
			// Hide greeting carousel when Gemini starts the conversation
			if (showGreetingCarousel) {
				console.log('[VoiceOverlayMobile] 🌍 Gemini speaking - hiding greeting carousel')
				setShowGreetingCarousel(false)
				carouselDismissedRef.current = true
			}
		}

		return () => {
			// Clean up on unmount
			delete window.vffOnAudioPlaybackStart
		}
	}, [showGreetingCarousel])

	// Handle language selection change
	const handleLanguageChange = async (event: React.ChangeEvent<HTMLSelectElement>) => {
		const newLanguage = event.target.value
		setSelectedLanguage(newLanguage)

		console.log('[VoiceOverlayMobile] Language changed to:', newLanguage)

		// Send initiating message if connected
		const isCurrentlyConnected = status.toLowerCase() === 'connected' || status.toLowerCase().startsWith('connected ')
		if (connectionManager && isCurrentlyConnected) {
			try {
				// Compute next field hint for the initiating message
				const state = WebFormStateManager.load()
				if (!state) {
					console.error('[VoiceOverlayMobile] No state found for next field hint')
					return
				}

				// Compute next unfilled field
				const nextField = computeNextField(state.schema, state.current_values)
				const nextFieldHint = nextField
					? formatNextFieldHint(nextField, state.schema)
					: 'all fields are complete'

				// Send spoken language change message via connection manager
				connectionManager.changeSpokenLanguage(newLanguage, nextFieldHint)
			} catch (err) {
				console.error('[VoiceOverlayMobile] Failed to change spoken language:', err)
				setError(err instanceof Error ? err.message : 'Failed to change language')
			}
		}
	}

	const handleConnect = async () => {
		if (!connectionManager) return
		try {
			setError(null)
			
			// If paused, just resume (which will restart recording)
			if (connectionManager.isPaused()) {
				await connectionManager.resume()
				// FIX #2: VAD will auto-start via consolidated useEffect when status changes
				return
			}
			
			// Otherwise, full connect
			await connectionManager.connect()

			// FIX #3: Poll for connected status instead of hard-coded delay
			// On cloud deployments, WSS handshake can take 500-2000ms (not 100ms)
			const maxWaitMs = 5000
			const startTime = Date.now()

			while (Date.now() - startTime < maxWaitMs) {
				const currentStatus = connectionManager.getStatus()
				const isActive = currentStatus === 'connected' || currentStatus === 'switching_section'

				if (isActive) {
					console.log('[VoiceOverlayMobile] ✅ WebSocket connected, setting up audio...')
					// Update status to indicate audio setup in progress
					setStatus('Setting up audio...')

					// Start recording (this completes the connection)
					await connectionManager.startRecording()

					// Now fully connected - update status
					setStatus('connected')
					console.log('[VoiceOverlayMobile] ✅ Audio ready - fully connected')
					// FIX #2: VAD will auto-start via consolidated useEffect when status changes
					break
				}

				// Wait 50ms before checking again
				await new Promise(resolve => setTimeout(resolve, 50))
			}

			// Check final status
			const finalStatus = connectionManager.getStatus()
			if (finalStatus !== 'connected' && finalStatus !== 'switching_section') {
				console.error('[VoiceOverlayMobile] ❌ Connection timeout, final status:', finalStatus)
				setError('Connection timed out - please try again')
			}
		} catch (err) {
			console.error('[VoiceOverlay] Connection error:', err)
			setError(err instanceof Error ? err.message : 'Connection failed')
		}
	}

	const handleDisconnect = () => {
		if (!connectionManager) return

		// Pause instead of disconnect (keeps connection warm)
		connectionManager.pause()
		
		// Pause VAD
		vad.pause()
	}

	// FIX #2: Removed pendingVADStart useEffect - consolidated into single VAD control useEffect below

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
			// Switching to VAD mode
			// FIX #2: VAD will auto-start via consolidated useEffect (monitors pushToTalkMode)
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

		// No need to send activity_start - Gemini's automatic VAD will detect
		// the incoming audio stream and start processing automatically
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

		// Send audio_stream_end to flush Gemini's audio buffer
		// (sendActivityEnd now sends audio_stream_end on backend)
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

						{/* Language Selection - Shows when connecting or connected */}
						{!isReady && status !== 'disconnected' && status !== 'paused' && (
							<div className="vff-language-selector-mobile">
								<label htmlFor="vff-language-select-mobile" className="vff-language-label-mobile">
									🌍 Spoken Language
								</label>
								<select
									id="vff-language-select-mobile"
									className="vff-language-select-mobile"
									value={selectedLanguage}
									onChange={handleLanguageChange}
								>
									{SPOKEN_LANGUAGES.map((lang) => (
										<option key={lang.name} value={lang.name}>
											{lang.nativeName}
										</option>
									))}
								</select>
							</div>
						)}

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
						{/* FIX #4: Show both connection errors and stream errors */}
						{(error || streamError) && (
							<div className="vff-error-compact">
								{streamError && (
									<div><strong>🎤 Mic Error:</strong> {streamError}</div>
								)}
								{error && <div>{error}</div>}
							</div>
						)}

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
					margin-bottom: 12px;
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

				.vff-language-selector-mobile {
					margin-bottom: 12px;
					padding: 10px;
					background: #f0f9ff;
					border-radius: 8px;
					border: 1px solid #bae6fd;
				}

				.vff-language-label-mobile {
					display: block;
					font-size: 12px;
					font-weight: 600;
					color: #0369a1;
					margin-bottom: 6px;
				}

				.vff-language-select-mobile {
					width: 100%;
					padding: 6px 10px;
					font-size: 13px;
					border: 1px solid #7dd3fc;
					border-radius: 6px;
					background: white;
					color: #0c4a6e;
					cursor: pointer;
					transition: all 0.2s;
				}

				.vff-language-select-mobile:hover {
					border-color: #0ea5e9;
					box-shadow: 0 0 0 2px rgba(14, 165, 233, 0.1);
				}

				.vff-language-select-mobile:focus {
					outline: none;
					border-color: #0284c7;
					box-shadow: 0 0 0 3px rgba(14, 165, 233, 0.2);
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
