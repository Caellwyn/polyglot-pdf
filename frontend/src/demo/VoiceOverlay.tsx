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
import { SchemaFormStateManager } from '../schema-forms/state/schemaFormState'
import type { FormSchema } from '../schema-forms/types/schema'
import { computeNextField, formatNextFieldHint } from '../navigation'
import { useDemoVAD } from './useDemoVAD'
import { SPOKEN_LANGUAGES } from '../shared/languages'
import { DisclaimerModal, DISCLAIMER_TRANSLATIONS } from '../schema-forms/components/DisclaimerModal'
import { LanguageSelectionModal } from '../schema-forms/components/LanguageSelectionModal'
import { getBackendHttpUrl } from '../schema-forms/utils/pdfFiller'

interface VoiceOverlayProps {
	schema: FormSchema
	wsUrl?: string
	onClose?: () => void
	connectionManager?: ConnectionManager
	status?: string
	// FIX #1: Shared audio stream passed from parent (prevents race conditions)
	sharedStream?: MediaStream | null
	// FIX #4: Stream error from parent (for error visibility)
	streamError?: string | null
	/** Pre-selected language from onboarding (skips language selection modal) */
	initialLanguage?: string
}

export function VoiceOverlay({ schema, wsUrl, onClose, connectionManager: sharedConnectionManager, status: sharedStatus, sharedStream, streamError, initialLanguage }: VoiceOverlayProps) {
	const [connectionManager, setConnectionManager] = useState<ConnectionManager | null>(sharedConnectionManager || null)
	const connectionManagerRef = useRef<ConnectionManager | null>(sharedConnectionManager || null)
	const [status, setStatus] = useState<string>(sharedStatus || 'Ready')
	const [error, setError] = useState<string | null>(null)
	// FIX #2: Removed pendingVADStart state - consolidated VAD start logic into single useEffect
	const [currentSectionId, setCurrentSectionId] = useState<string>('')
	const [completedSections, setCompletedSections] = useState<Set<string>>(new Set())
	const [sectionFieldCount, setSectionFieldCount] = useState({ filled: 0, total: 12 })
	const [showSectionDropdown, setShowSectionDropdown] = useState(false)
	// PTT default is true (HALLUCINATION_REDUCTION, Oct 30 2025), BUT when this
	// overlay is remounted onto an ALREADY-LIVE session (a desktop<->mobile
	// breakpoint cross) restore the user's actual choice from the connection rather
	// than resetting to true (Codex review PR #119).
	const [pushToTalkMode, setPushToTalkMode] = useState(
		() => sharedConnectionManager?.getPushToTalkMode?.() ?? true
	)
	// bd polyglot-pdf-tlc: whether Gemini's own (native) VAD is driving turns. Set
	// by the backend at session_ready (mirror of DISABLE_GEMINI_VAD) and reported
	// via connectionManager.isNativeVad(). When true, Gemini's VAD streams
	// continuous audio and the manual PTT control does not apply -- the toggle is
	// disabled and the displayed mode reflects native VAD (not a stale "PTT").
	const [nativeVad, setNativeVad] = useState(false)
	const [isHoldingPushToTalk, setIsHoldingPushToTalk] = useState(false)
	const [isCollapsed, setIsCollapsed] = useState(false)
	// If initialLanguage is provided (from parent onboarding), use it and skip language modal
	const [selectedLanguage, setSelectedLanguage] = useState(initialLanguage || '')
	const [showLanguageModal, setShowLanguageModal] = useState(!initialLanguage)  // Skip if language pre-selected
	const [showDisclaimerModal, setShowDisclaimerModal] = useState(false)  // Track if disclaimer modal is showing
	const [pendingDisclaimerRead, setPendingDisclaimerRead] = useState(false)  // Track if we need to send disclaimer prompt when connected
	const panelRef = useRef<HTMLDivElement>(null)
	const isDraggingRef = useRef(false)
	const offsetRef = useRef({ x: 0, y: 0 })

	// Helper functions for section navigation
	const getCurrentSectionOrder = (): number => {
		if (!schema.sections || !currentSectionId) return 0
		const section = schema.sections.find(s => s.id === currentSectionId)
		return section?.order ?? 0
	}

	const getCurrentSectionLabel = (): string => {
		if (!schema.sections || !currentSectionId) return ''
		const section = schema.sections.find(s => s.id === currentSectionId)
		return section?.label ?? ''
	}

	const getSectionIdFromOrder = (order: number): string | undefined => {
		if (!schema.sections) return undefined
		const section = schema.sections.find(s => s.order === order)
		return section?.id
	}

	// FIX #1: Use shared stream from parent (created before React rendering)
	// No need to create our own stream - parent already did this to prevent race conditions
	const sharedStreamRef = useRef<MediaStream | null>(sharedStream || null)

	// Track speech duration to prevent short grunts/noises from interrupting Gemini
	const speechStartTimeRef = useRef<number | null>(null)
	const bargeInTriggeredRef = useRef<boolean>(false)  // Track if we triggered barge-in for this speech event
	const MIN_TURN_DURATION_MS = 450  // Minimum 450ms of speech before triggering barge-in

	// CRITICAL: Use ref for pushToTalkMode to avoid closure capture in VAD callbacks
	// Without this, old callbacks fire with stale pushToTalkMode=false value
	const pushToTalkModeRef = useRef<boolean>(pushToTalkMode)

	// CRITICAL: Use ref for status to avoid closure capture in keyboard handlers
	// This allows keyboard handlers to check current connection status without adding status to useEffect deps
	const statusRef = useRef<string>(status)

	// PTT release delay timer (allows final audio to be sent before muting)
	const pttReleaseTimeoutRef = useRef<number | null>(null)
	const isHoldingPushToTalkRef = useRef<boolean>(isHoldingPushToTalk)

	// FIX #1: Update stream ref when prop changes (parent manages lifecycle)
	useEffect(() => {
		sharedStreamRef.current = sharedStream || null
		console.log('[VoiceOverlay] 🔗 Using shared stream from parent:', !!sharedStream)
	}, [sharedStream])

	// If language is pre-selected from onboarding, auto-trigger disclaimer flow on mount
	useEffect(() => {
		if (initialLanguage && !showLanguageModal) {
			// Guard against a remount re-running connect+disclaimer on an ALREADY-LIVE
			// session (bd polyglot-pdf-6vo): a desktop<->mobile switch remounts this
			// overlay while connectionManager stays alive; reconnecting + re-showing
			// the disclaimer would restart the Gemini session and repeat the
			// disclaimer. Skip if already connected.
			const st = (connectionManager?.getStatus?.() || '').toLowerCase()
			// Include 'connecting' so a desktop<->mobile flip DURING the first connect
			// does not kick off a second concurrent connect (fresh-eyes PR #119).
			const alreadyLive = st === 'connected' || st.startsWith('connected ') ||
				st === 'connecting' || st === 'switching_section' || st.startsWith('reconnecting')
			if (alreadyLive) {
				// Skip the re-CONNECT but do NOT drop the disclaimer step (Codex review
				// PR #119): a flip during the initial connect loses the old overlay's
				// pending setShowDisclaimerModal(true). Surface it here if not yet
				// accepted, so the user still gets the agree step.
				const accepted = SchemaFormStateManager.load()?.disclaimerAccepted
				if (!accepted) {
					console.log('[VoiceOverlay] Live session, disclaimer not yet accepted - showing modal (no reconnect)')
					setPendingDisclaimerRead(true)
					setShowDisclaimerModal(true)
				} else {
					console.log('[VoiceOverlay] Mounted onto a live session (disclaimer accepted) - skipping connect/disclaimer')
				}
				// Re-arm mic capture: the old overlay's unmount stopped audio capture,
				// so the new (remounted) overlay must re-start it without reconnecting.
				// No-ops if already recording (double-arm guard inside rearmAudioCapture).
				// bd polyglot-pdf-nlfc.
				connectionManager?.rearmAudioCapture().catch((err) => {
					console.error('[VoiceOverlay] rearmAudioCapture failed -- mic may be dead after overlay swap:', err)
				})
				return
			}
			console.log('[VoiceOverlay] Language pre-selected from onboarding:', initialLanguage)
			// Trigger the same flow as handleInitialLanguageSelect
			const triggerDisclaimerFlow = async () => {
				try {
					setPendingDisclaimerRead(true)
					await handleConnect()
					setShowDisclaimerModal(true)
				} catch (err) {
					console.error('[VoiceOverlay] Failed to connect after pre-selected language:', err)
					setError(err instanceof Error ? err.message : 'Connection failed')
					setPendingDisclaimerRead(false)
				}
			}
			triggerDisclaimerFlow()
		}
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, []) // Only run on mount

	// Keep pushToTalkMode ref updated
	useEffect(() => {
		pushToTalkModeRef.current = pushToTalkMode
	}, [pushToTalkMode])

	// Ensure connection manager + audio pipeline reflect current PTT mode.
	// PTT is a client-side audio gate that works EVEN under native VAD (noisy-room
	// support): we always apply the mute/unmute so PTT gates which client bytes
	// reach Gemini. The worklet noise gate stays bypassed in native mode regardless
	// of PTT (audioManager.setPTTMode honors nativeVad), so toggling PTT off does
	// not re-arm the RMS gate and starve Gemini's VAD of its silence stream.
	useEffect(() => {
		if (!connectionManager) return

		connectionManager.setPushToTalkMode(pushToTalkMode)
		const audioManager = connectionManager.getAudioManager()

		// FIX (Nov 7, 2025): Notify audio worklet about PTT mode (bypasses noise gate)
		audioManager?.setPTTMode(pushToTalkMode)

		if (pushToTalkMode) {
			audioManager?.muteInput()
		} else {
			audioManager?.unmuteInput()
		}
	}, [connectionManager, pushToTalkMode])

	// bd polyglot-pdf-tlc: learn the backend's VAD mode once connected. The
	// session_ready handshake fires onNativeVadMode BEFORE flipping status to
	// "connected", so isNativeVad() is reliable on connect. In native-VAD mode
	// Gemini drives turns on a continuous stream -- NEITHER PTT nor client-side
	// Silero VAD applies -- so the Input-Mode toggle is disabled and the displayed
	// mode reads "Native" (see the JSX + the shouldRunVAD / PTT-button /
	// Listening-badge guards, all keyed on `nativeVad`). We deliberately do NOT
	// mutate pushToTalkMode: forcing it false would satisfy `!pushToTalkMode` and
	// start Silero VAD in native mode, whose callbacks would block Gemini's audio
	// (fresh-eyes on PR #110). Reset to false when not connected so a
	// disconnect/reconnect into manual mode shows the normal enabled toggle.
	useEffect(() => {
		if (!connectionManager) {
			setNativeVad(false)
			return
		}
		const isConnected = status.toLowerCase() === 'connected' ||
			status.toLowerCase().startsWith('connected ')
		setNativeVad(isConnected ? connectionManager.isNativeVad() : false)
	}, [connectionManager, status])

	// Keep status ref updated
	useEffect(() => {
		statusRef.current = status
	}, [status])

	// Keep isHoldingPushToTalk ref updated
	useEffect(() => {
		isHoldingPushToTalkRef.current = isHoldingPushToTalk
	}, [isHoldingPushToTalk])

	// Cleanup PTT release timeout on unmount
	useEffect(() => {
		return () => {
			if (pttReleaseTimeoutRef.current !== null) {
				clearTimeout(pttReleaseTimeoutRef.current)
				pttReleaseTimeoutRef.current = null
			}
		}
	}, [])

	// SAFETY NET: Force-release PTT if stuck on for any reason
	// This handles: tab switch, incoming calls, screen rotation, browser throttling, etc.
	const MAX_PTT_DURATION_MS = 30000 // 30 second max - prevents wasted Gemini API costs
	const pttSafetyTimeoutRef = useRef<number | null>(null)

	// Force release function that can be called from any safety mechanism
	const forceReleasePTT = () => {
		if (!isHoldingPushToTalkRef.current) return

		console.log('[PTT Safety] ⚠️ Force-releasing PTT due to safety trigger')
		setIsHoldingPushToTalk(false)

		// Clear any pending timeouts
		if (pttReleaseTimeoutRef.current !== null) {
			clearTimeout(pttReleaseTimeoutRef.current)
			pttReleaseTimeoutRef.current = null
		}
		if (pttSafetyTimeoutRef.current !== null) {
			clearTimeout(pttSafetyTimeoutRef.current)
			pttSafetyTimeoutRef.current = null
		}

		// Send activity end and mute
		connectionManager?.sendActivityEnd()
		const audioManager = connectionManager?.getAudioManager()
		audioManager?.muteInput()
		audioManager?.resumePlayback()
	}

	// Safety mechanism 1: Max duration timeout (prevents infinite recording)
	useEffect(() => {
		if (isHoldingPushToTalk) {
			console.log('[PTT Safety] Starting safety timeout (max 60s)')
			pttSafetyTimeoutRef.current = window.setTimeout(() => {
				console.log('[PTT Safety] ⚠️ Max duration reached - force releasing')
				forceReleasePTT()
			}, MAX_PTT_DURATION_MS)
		} else {
			// Clear safety timeout when released normally
			if (pttSafetyTimeoutRef.current !== null) {
				clearTimeout(pttSafetyTimeoutRef.current)
				pttSafetyTimeoutRef.current = null
			}
		}

		return () => {
			if (pttSafetyTimeoutRef.current !== null) {
				clearTimeout(pttSafetyTimeoutRef.current)
				pttSafetyTimeoutRef.current = null
			}
		}
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [isHoldingPushToTalk])

	// Safety mechanism 2: Visibility change (tab switch, app switch, screen lock)
	useEffect(() => {
		const handleVisibilityChange = () => {
			if (document.hidden && isHoldingPushToTalkRef.current) {
				console.log('[PTT Safety] ⚠️ Tab hidden while recording - force releasing')
				forceReleasePTT()
			}
		}

		document.addEventListener('visibilitychange', handleVisibilityChange)
		return () => document.removeEventListener('visibilitychange', handleVisibilityChange)
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [])

	// Safety mechanism 3: Window blur (user clicked outside browser, system dialogs)
	useEffect(() => {
		const handleWindowBlur = () => {
			if (isHoldingPushToTalkRef.current) {
				console.log('[PTT Safety] ⚠️ Window lost focus while recording - force releasing')
				forceReleasePTT()
			}
		}

		window.addEventListener('blur', handleWindowBlur)
		return () => window.removeEventListener('blur', handleWindowBlur)
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [])

	// Safety mechanism 4: Connection status change (disconnect while recording)
	useEffect(() => {
		const isConnected = status.toLowerCase() === 'connected' ||
			status.toLowerCase().startsWith('connected ')

		if (!isConnected && isHoldingPushToTalkRef.current) {
			console.log('[PTT Safety] ⚠️ Connection lost while recording - force releasing')
			forceReleasePTT()
		}
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [status])

	// Safety mechanism 5: Cleanup on unmount
	useEffect(() => {
		return () => {
			if (isHoldingPushToTalkRef.current) {
				console.log('[PTT Safety] ⚠️ Component unmounting while recording - force releasing')
				// Direct cleanup since we're unmounting
				connectionManager?.sendActivityEnd()
				connectionManager?.getAudioManager()?.muteInput()
			}
		}
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [])

	// Memoize VAD callbacks to prevent re-initialization on every render
	const vadCallbacks = useMemo(() => ({
		onSpeechStart: () => {
			// In push-to-talk mode, ignore VAD
			// CRITICAL: Use ref.current to get CURRENT value, not closure-captured value
			if (pushToTalkModeRef.current) return

			console.log('[VFF VAD] 🎤 User speech started - buffering audio...')

			// Record speech start time
			const speechDetectedTime = performance.now()
			speechStartTimeRef.current = Date.now()
			bargeInTriggeredRef.current = false  // Reset flag
			console.log(`[VFF VAD] 🎤 Speech detected at t=${speechDetectedTime.toFixed(2)}ms`)

			// INSTANT FEEDBACK: Pause audio immediately if Gemini is speaking
			// This gives instant barge-in feel while we wait to confirm speech duration
			const audioManager = connectionManager?.getAudioManager()
			if (audioManager && audioManager.isSpeaking()) {
				audioManager.pauseAudioContext()
				console.log(`[VFF VAD] 🔇 Tentative pause at t=${performance.now().toFixed(2)}ms - waiting to confirm speech duration`)
			}
			// Schedule delayed turn start - only send activity_start + audio if speech lasts ≥450ms
			// This prevents false positives (throat clears, grunts) from creating incomplete turns
			setTimeout(() => {
				const speechDuration = speechStartTimeRef.current
					? Date.now() - speechStartTimeRef.current
					: 0

				// Only start turn if speech is still active AND duration met
				if (speechStartTimeRef.current !== null && speechDuration >= MIN_TURN_DURATION_MS) {
					console.log(`[VFF VAD] ✅ Valid speech detected (${speechDuration}ms) - starting turn`)
					bargeInTriggeredRef.current = true

					// CRITICAL: Send activity_start BEFORE opening audio gate
					// This ensures Gemini receives the turn signal before any audio chunks
					// Pattern: activity_start → audio chunks → activity_end (Gemini Live API docs lines 419-435)
					if (connectionManager) {
						const startTime = performance.now()
						connectionManager.sendActivityStart()
						console.log(`[VFF VAD] 📤 Sent activity_start signal at t=${startTime.toFixed(2)}ms (user turn begins)`)
					}

					// Privacy Gate: Open audio flow (sends pre-buffer + live audio)
					// Must happen AFTER activity_start to ensure proper turn framing
					if (audioManager) {
						const gateOpenTime = performance.now()
						console.log(`[VFF VAD] 🚪 Opening audio gate at t=${gateOpenTime.toFixed(2)}ms`)
						audioManager.setVADActive(true) // Opens gate, flushes 600ms pre-buffer to backend
						console.log(`[VFF VAD] 🚪 Audio gate opened, pre-buffer flushed, live audio now flowing`)
					}

					// Trigger FULL barge-in (flushes audio queue if Gemini speaking)
					const geminiSpeaking = audioManager?.isSpeaking()
					if (geminiSpeaking && audioManager) {
						console.log('[VFF VAD] 🔇 Flushing Gemini audio queue (full barge-in)')
						audioManager.flushAudioQueue()
					}
				}
			}, MIN_TURN_DURATION_MS)
		},
		onSpeechEnd: (audio: Float32Array) => {
			// In push-to-talk mode, ignore VAD
			// CRITICAL: Use ref.current to get CURRENT value, not closure-captured value
			if (pushToTalkModeRef.current) return

			// Calculate speech duration
			const speechDuration = speechStartTimeRef.current
				? Date.now() - speechStartTimeRef.current
				: 0

			// Privacy Gate: Always close audio flow (only if it was opened)
			const audioManager = connectionManager?.getAudioManager()

			// Only close gate and send activity_end if we actually started a turn (≥450ms)
			if (bargeInTriggeredRef.current) {
				console.log(`[VFF VAD] ✅ Valid turn completed (${speechDuration}ms) - closing turn`)

				// Close audio gate
				if (audioManager) {
					audioManager.setVADActive(false) // Closes gate, stops audio flow
				}

				// Send activity_end to signal user is done speaking
				connectionManager?.onVADSpeechEnd()
			} else {
				console.log(`[VFF VAD] ⚠️ Speech too short (${speechDuration}ms < ${MIN_TURN_DURATION_MS}ms) - no turn started, false positive`)

				// FALSE POSITIVE: Resume audio playback (speech was too short to start a turn)
				// Gate was never opened, so nothing to close
				if (audioManager) {
					audioManager.resumeAudioContext()
					console.log('[VFF VAD] 🔊 Resuming audio - false positive')
				}
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
	}), [connectionManager])  // Removed pushToTalkMode - using ref now to avoid closure capture

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

		// Initialize with schema-based state
		const state = SchemaFormStateManager.init(schema)

		// FIX #1: Connection manager receives stream from parent (already created)
		const manager = createConnectionManager(
			state.schema,
			(newStatus) => {
				setStatus(newStatus)
				setError(null)
			},
			'English', // Default to English
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
	}, [schema, sharedConnectionManager]) // Recreate when schema changes
	// Sync status from shared prop
	useEffect(() => {
		if (sharedStatus !== undefined) {
			setStatus(sharedStatus)
		}
	}, [sharedStatus])

	// Check if user has already accepted disclaimer (returning user)
	useEffect(() => {
		const state = SchemaFormStateManager.load()
		if (state?.disclaimerAccepted && state?.selectedLanguage) {
			console.log('[VoiceOverlay] Returning user - skipping language/disclaimer modals')
			setShowLanguageModal(false)
			setShowDisclaimerModal(false)
			setSelectedLanguage(state.selectedLanguage)
		}
	}, [])

	// Send disclaimer read request when connection is ready and disclaimer read is pending
	useEffect(() => {
		const isConnected = status.toLowerCase() === 'connected' || status.toLowerCase().startsWith('connected ')

		if (isConnected && pendingDisclaimerRead && connectionManager && selectedLanguage) {
			console.log('[VoiceOverlay] ✅ Connection ready - requesting disclaimer read')

			// Clear the flag IMMEDIATELY to prevent double-firing
			setPendingDisclaimerRead(false)

			// Send read_disclaimer message to backend using the proven language change pattern
			const disclaimerText = DISCLAIMER_TRANSLATIONS[selectedLanguage]?.fullText || DISCLAIMER_TRANSLATIONS['English'].fullText
			connectionManager.readDisclaimer(selectedLanguage, disclaimerText)
		}
	}, [status, pendingDisclaimerRead, connectionManager, selectedLanguage])

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
		// bd polyglot-pdf-tlc: never run client Silero VAD in native mode -- Gemini's
		// own VAD drives turns there, and Silero's onSpeechStart/End would block
		// playback (flushAudioQueue) without a matching resume (onVADSpeechEnd
		// no-ops on nativeVad).
		const shouldRunVAD = isConnected && !pushToTalkMode && !nativeVad && !vad.loading && !vad.errored

		if (shouldRunVAD && !vad.userSpeaking) {
			console.log('[VoiceOverlay] 🎙️ Starting VAD (conditions met)')
			vad.start()
		} else if (!shouldRunVAD && vad.userSpeaking) {
			console.log('[VoiceOverlay] ⏸️ Pausing VAD (conditions not met)')
			vad.pause()
		}

		// FIX #4: Display VAD errors to user
		if (vad.errored) {
			setError(`Voice detection error: ${vad.errored}`)
		}
		// NOTE: vad.start and vad.pause intentionally excluded from deps
		// They are stable callbacks that shouldn't trigger re-renders
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [status, pushToTalkMode, nativeVad, vad.loading, vad.errored, vad.userSpeaking])

	// Handle connect button
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

			// Phase 3: Use regular connect() for initial connection
			// The WebFormConnection will use the section-based schema from state
			await connectionManager.connect()

			// FIX #3: Poll for connected status instead of hard-coded delay
			// On cloud deployments, WSS handshake can take 500-2000ms (not 100ms)
			const maxWaitMs = 5000
			const startTime = Date.now()

			while (Date.now() - startTime < maxWaitMs) {
				const currentStatus = connectionManager.getStatus()
				const isActive = currentStatus === 'connected' || currentStatus === 'switching_section'

				if (isActive) {
					console.log('[VoiceOverlay] ✅ WebSocket connected, setting up audio...')
					// Update status to indicate audio setup in progress
					setStatus('Setting up audio...')

					// Start recording (this completes the connection)
					await connectionManager.startRecording()

					// Now fully connected - update status
					setStatus('connected')
					console.log('[VoiceOverlay] ✅ Audio ready - fully connected')
					// FIX #2: VAD will auto-start via consolidated useEffect when status changes
					break
				}

				// Wait 50ms before checking again
				await new Promise(resolve => setTimeout(resolve, 50))
			}

			// Check final status
			const finalStatus = connectionManager.getStatus()
			if (finalStatus !== 'connected' && finalStatus !== 'switching_section') {
				console.error('[VoiceOverlay] ❌ Connection timeout, final status:', finalStatus)
				setError('Connection timed out - please try again')
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

	// FIX #2: Removed pendingVADStart useEffect - consolidated into single VAD control useEffect below

	// Handle push-to-talk mode toggle
	const handlePushToTalkToggle = async () => {
		// PTT is a CLIENT-SIDE AUDIO GATE layered on top of native VAD (user request,
		// noisy-room support): native Gemini VAD always runs on the backend, but PTT
		// can still gate which client audio bytes reach Gemini. So we run the full
		// mute/unmute + worklet reconfig regardless of native-VAD mode. (We still
		// never send manual activity_start/end in native mode -- those stay
		// suppressed in connection.ts; PTT only decides which bytes are sent.)
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
			// Switching to VAD mode
			// FIX #2: VAD will auto-start via consolidated useEffect (monitors pushToTalkMode)
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
	// TABLET FIX: Wrapper for touch events that prevents context menu
	const handlePushToTalkTouchStart = (e: React.TouchEvent) => {
		// CRITICAL: Prevent browser context menu on long-press (tablet issue)
		e.preventDefault()
		handlePushToTalkPress()
	}

	// TABLET FIX: Touch end handler with preventDefault
	const handlePushToTalkTouchEnd = (e: React.TouchEvent) => {
		e.preventDefault()
		handlePushToTalkRelease()
	}

	const handlePushToTalkPress = async () => {
		// Use statusRef for current status (avoids closure capture issues)
		const currentStatus = statusRef.current
		console.log('[PTT] Press handler called, pushToTalkMode:', pushToTalkMode, 'isHoldingPushToTalk:', isHoldingPushToTalk, 'status:', currentStatus)

		if (!pushToTalkMode) {
			console.log('[PTT] Ignoring press - not in PTT mode')
			return
		}

		// Clear any pending release timeout (user pressed again before release completed)
		if (pttReleaseTimeoutRef.current !== null) {
			console.log('[PTT] Clearing pending release timeout (re-press)')
			clearTimeout(pttReleaseTimeoutRef.current)
			pttReleaseTimeoutRef.current = null
		}

		const isCurrentlyConnected = currentStatus.toLowerCase() === 'connected' ||
			currentStatus.toLowerCase().startsWith('connected ') ||
			currentStatus.toLowerCase() === 'switching_section' ||
			currentStatus.toLowerCase().startsWith('reconnecting')
		if (!isCurrentlyConnected) {
			console.log('[PTT] Ignoring press - not connected, status:', currentStatus)
			return
		}

		console.log('[PTT] Processing press - flushing audio and opening Gemini turn')
		console.log('[PTT] connectionManager:', connectionManager, 'isNull:', connectionManager === null, 'isUndefined:', connectionManager === undefined)
		setIsHoldingPushToTalk(true)

		const audioManager = connectionManager?.getAudioManager()
		console.log('[PTT] audioManager:', audioManager, 'isNull:', audioManager === null, 'isUndefined:', audioManager === undefined)

		// BARGE-IN: Clear any pending Gemini audio before opening mic
		if (audioManager) {
			audioManager.flushAudioQueue()
		}

		// CRITICAL: Send activity_start to open Gemini turn for PTT mode
		// Without this, activity_end will close the turn before audio arrives
		console.log('[PTT] About to call sendActivityStart, connectionManager:', connectionManager)
		connectionManager?.sendActivityStart()
		console.log('[PTT] sendActivityStart call completed')

		// UNMUTE: Allow real audio through only after Gemini turn is open
		audioManager?.unmuteInput()
	}

	const handlePushToTalkRelease = () => {
		// Use refs for current values (avoids closure capture issues)
		const currentStatus = statusRef.current
		const currentPTTMode = pushToTalkModeRef.current
		const currentlyHolding = isHoldingPushToTalkRef.current
		console.log('[PTT] Release handler called, pushToTalkMode:', currentPTTMode, 'isHoldingPushToTalk:', currentlyHolding, 'status:', currentStatus)

		if (!currentPTTMode) {
			console.log('[PTT] Ignoring release - not in PTT mode')
			return
		}

		// CRITICAL: Prevent duplicate calls (onMouseUp + onMouseLeave both fire)
		if (!currentlyHolding) {
			console.log('[PTT] Ignoring release - already released (not holding)')
			return
		}

		const isCurrentlyConnected = currentStatus.toLowerCase() === 'connected' ||
			currentStatus.toLowerCase().startsWith('connected ') ||
			currentStatus.toLowerCase() === 'switching_section' ||
			currentStatus.toLowerCase().startsWith('reconnecting')
		if (!isCurrentlyConnected) {
			console.log('[PTT] Ignoring release - not connected, status:', currentStatus)
			return
		}

		console.log('[PTT] Processing release - will delay 500ms before ending activity')

		// Clear any existing timeout (in case of rapid press/release)
		if (pttReleaseTimeoutRef.current !== null) {
			clearTimeout(pttReleaseTimeoutRef.current)
			pttReleaseTimeoutRef.current = null
		}

		// Update UI immediately to show button is no longer held
		setIsHoldingPushToTalk(false)

		// CRITICAL: Delay 500ms before sending activity_end and muting
		// This allows final audio chunks to be recorded and sent to Gemini
		// without being cut off by immediate muting
		pttReleaseTimeoutRef.current = window.setTimeout(async () => {
			console.log('[PTT] 500ms delay complete - sending activity_end and muting')

			// Send audio_stream_end to flush Gemini's audio buffer
			// CRITICAL: Wait for all buffered audio to be sent before signaling end
			// (sendActivityEnd now waits for WebSocket buffer drain)
			await connectionManager?.sendActivityEnd()

			// MUTE: Stop streaming audio after signaling end of turn
			// All audio recorded during the 500ms delay has already been sent
			const audioManager = connectionManager?.getAudioManager()
			audioManager?.muteInput()

			// Allow Gemini's response to play now that the user released the mic
			audioManager?.resumePlayback()
			audioManager?.resumeAudioContext?.()

			pttReleaseTimeoutRef.current = null
		}, 500) // 500ms delay to capture final audio
	}

	// Handle push-to-talk with spacebar (keyboard)
	useEffect(() => {
		console.log('[PTT Keyboard] useEffect running, pushToTalkMode:', pushToTalkMode)

		if (!pushToTalkMode) {
			console.log('[PTT Keyboard] Not in PTT mode - not attaching listeners')
			return
		}

		console.log('[PTT Keyboard] Attaching keyboard listeners')

		const handleKeyDown = (e: KeyboardEvent) => {
			if (e.code === 'Space') {
				// Check connection status from ref (always current, doesn't cause re-renders)
				const currentStatus = statusRef.current
				const isConnected = currentStatus.toLowerCase() === 'connected' ||
					currentStatus.toLowerCase().startsWith('connected ') ||
					currentStatus.toLowerCase() === 'switching_section' ||
					currentStatus.toLowerCase().startsWith('reconnecting')

				// Only trigger if not typing in a form field
				const target = e.target as HTMLElement
				if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {
					return
				}

				// ALWAYS prevent default to stop page scrolling in PTT mode
				e.preventDefault()

				// Only trigger PTT if connected and not a repeat event (held-key
				// auto-repeat fires keydown continuously; ignore those).
				if (!e.repeat && isConnected) {
					handlePushToTalkPress()
				}
			}
		}

		const handleKeyUp = (e: KeyboardEvent) => {
			if (e.code === 'Space') {
				// Check connection status from ref (always current, doesn't cause re-renders)
				const currentStatus = statusRef.current
				const isConnected = currentStatus.toLowerCase() === 'connected' ||
					currentStatus.toLowerCase().startsWith('connected ') ||
					currentStatus.toLowerCase() === 'switching_section' ||
					currentStatus.toLowerCase().startsWith('reconnecting')

				const target = e.target as HTMLElement
				if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {
					return
				}

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
		console.log('[PTT Keyboard] ✅ Keyboard listeners attached')

		return () => {
			console.log('[PTT Keyboard] ❌ Removing keyboard listeners')
			window.removeEventListener('keydown', handleKeyDown)
			window.removeEventListener('keyup', handleKeyUp)
		}
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [pushToTalkMode])

	// Handle global mouse/touch release (catch PTT release even if mouse moves off button)
	useEffect(() => {
		if (!pushToTalkMode) return

		const handleGlobalMouseUp = (e: MouseEvent | TouchEvent) => {
			// Only handle if we're currently holding PTT
			if (isHoldingPushToTalkRef.current) {
				const currentStatus = statusRef.current
				const isConnected = currentStatus.toLowerCase() === 'connected' ||
					currentStatus.toLowerCase().startsWith('connected ') ||
					currentStatus.toLowerCase() === 'switching_section' ||
					currentStatus.toLowerCase().startsWith('reconnecting')

				if (isConnected) {
					console.log('[PTT Global] Mouse/touch released - calling handlePushToTalkRelease()')
					handlePushToTalkRelease()
				}
			}
		}

		document.addEventListener('mouseup', handleGlobalMouseUp)
		document.addEventListener('touchend', handleGlobalMouseUp)
		console.log('[PTT Global] ✅ Global mouse/touch release listeners attached')

		return () => {
			console.log('[PTT Global] ❌ Removing global mouse/touch release listeners')
			document.removeEventListener('mouseup', handleGlobalMouseUp)
			document.removeEventListener('touchend', handleGlobalMouseUp)
		}
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [pushToTalkMode])

	// Initialize schema-based state and update section UI (only once on mount)
	useEffect(() => {
		const state = SchemaFormStateManager.init(schema)
		setCurrentSectionId(state.currentSectionId || schema.sections?.[0]?.id || '')
		setCompletedSections(state.completedSections || new Set())

		// Update field counter
		const totalFields = schema.fields.length
		const filledFields = Object.keys(state.fieldValues).filter(fieldId => {
			const fieldValue = state.fieldValues[fieldId]
			const actualValue = fieldValue?.value
			return actualValue !== null && actualValue !== undefined && actualValue !== ""
		}).length
		setSectionFieldCount({ filled: filledFields, total: totalFields })
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, []) // Only run once on mount, not when schema changes

	// Poll field count AND section state (updates as AI switches sections)
	useEffect(() => {
		const interval = setInterval(() => {
			const state = SchemaFormStateManager.load()
			if (state) {
				const totalFields = schema.fields.length
				const filledFields = Object.keys(state.fieldValues).filter(fieldId => {
					const fieldValue = state.fieldValues[fieldId]
					const actualValue = fieldValue?.value
					return actualValue !== null && actualValue !== undefined && actualValue !== ""
				}).length
				setSectionFieldCount({ filled: filledFields, total: totalFields })

				// Update section if changed (AI completed section and moved forward)
				if (state.currentSectionId && state.currentSectionId !== currentSectionId) {
					setCurrentSectionId(state.currentSectionId)
				}

				// Update completed sections if changed
				if (state.completedSections) {
					const currentCompleted = new Set(Array.from(completedSections))
					const newCompleted = new Set(Array.from(state.completedSections))

					// Check if sets are different
					if (currentCompleted.size !== newCompleted.size ||
						![...currentCompleted].every(s => newCompleted.has(s))) {
						setCompletedSections(newCompleted)
					}
				}
			}
		}, 1000) // Update every second

		return () => clearInterval(interval)
	}, [currentSectionId, completedSections])

	// Handle initial language selection from modal (fallback when initialLanguage not provided)
	const handleInitialLanguageSelect = async (_formId: string, language: string) => {
		console.log('[VoiceOverlay] Initial language selected from modal:', language)
		setSelectedLanguage(language)
		setShowLanguageModal(false)

		// First time - connect to Gemini, THEN show disclaimer modal
		console.log('[VoiceOverlay] First language selection - connecting to Gemini...')
		try {
			// Set pending flag so disclaimer will be read when connection is ready
			setPendingDisclaimerRead(true)

			// Start connection
			await handleConnect()

			// Show disclaimer modal
			console.log('[VoiceOverlay] Connection initiated - showing disclaimer modal')
			setShowDisclaimerModal(true)

			// The useEffect watching status will send the disclaimer prompt when ready
		} catch (err) {
			console.error('[VoiceOverlay] Failed to connect after language selection:', err)
			setError(err instanceof Error ? err.message : 'Connection failed')
			setPendingDisclaimerRead(false) // Clear flag on error
		}
	}

	// Handle language selection change (from dropdown - for changing language later)
	const handleLanguageChange = async (event: React.ChangeEvent<HTMLSelectElement>) => {
		const newLanguage = event.target.value

		// If clearing selection, just update state
		if (!newLanguage) {
			setSelectedLanguage('')
			return
		}

		console.log('[VoiceOverlay] Language selected:', newLanguage)
		setSelectedLanguage(newLanguage)

		// Check if disclaimer already accepted (returning user)
		const state = SchemaFormStateManager.load()
		if (state?.disclaimerAccepted) {
			console.log('[VoiceOverlay] Disclaimer already accepted - proceeding to connection')
			// Already accepted, just change language if connected
			if (connectionManager && isConnected) {
				try {
					const nextField = computeNextField(state)
					const nextFieldHint = nextField
						? formatNextFieldHint(nextField)
						: 'all fields are complete'
					connectionManager.changeSpokenLanguage(newLanguage, nextFieldHint)
				} catch (err) {
					console.error('[VoiceOverlay] Failed to change spoken language:', err)
					setError(err instanceof Error ? err.message : 'Failed to change language')
				}
			}
			return
		}

		// First time - connect to Gemini, THEN show disclaimer modal
		console.log('[VoiceOverlay] First language selection - connecting to Gemini...')
		try {
			// Set pending flag so disclaimer will be read when connection is ready
			setPendingDisclaimerRead(true)

			// Start connection
			await handleConnect()

			// Show disclaimer modal
			console.log('[VoiceOverlay] Connection initiated - showing disclaimer modal')
			setShowDisclaimerModal(true)

			// The useEffect watching status will send the disclaimer prompt when ready
		} catch (err) {
			console.error('[VoiceOverlay] Failed to connect after language selection:', err)
			setError(err instanceof Error ? err.message : 'Connection failed')
			setPendingDisclaimerRead(false) // Clear flag on error
		}
	}

	// Handle "Listen Again" button in disclaimer modal
	const handleDisclaimerListenAgain = () => {
		if (!connectionManager || !selectedLanguage) return

		console.log('[VoiceOverlay] User requested disclaimer re-read')

		// Send read_disclaimer message using the same proven pattern
		const disclaimerText = DISCLAIMER_TRANSLATIONS[selectedLanguage]?.fullText || DISCLAIMER_TRANSLATIONS['English'].fullText
		connectionManager.readDisclaimer(selectedLanguage, disclaimerText)
	}

	// Handle "I Agree" button in disclaimer modal
	const handleDisclaimerAgree = async () => {
		console.log('[VoiceOverlay] User agreed to disclaimer')

		// Update state with disclaimer acceptance
		const state = SchemaFormStateManager.load()
		if (state) {
			state.disclaimerAccepted = true
			state.disclaimerAcceptedAt = Date.now()
			state.selectedLanguage = selectedLanguage
			SchemaFormStateManager.save(state)
		}

		// Hide modal
		setShowDisclaimerModal(false)

		// Step 1: Send activity_start FIRST to stop backend from sending more audio.
		// The user just agreed, so cut off any still-playing disclaimer read instead
		// of letting it finish (matches VoiceOverlayMobile; bd polyglot-pdf-zq9l).
		// No-op in native VAD (connection.ts suppresses activity_start there); in
		// manual VAD it opens the user turn that the sendActivityEnd below closes.
		console.log('[VoiceOverlay] Sending activity_start to interrupt Gemini')
		connectionManager?.sendActivityStart()

		// Step 2: THEN flush the local audio queue (the interrupt the user perceives).
		const agreeAudioManager = connectionManager?.getAudioManager()
		if (agreeAudioManager) {
			console.log('[VoiceOverlay] Clearing audio queue on disclaimer agreement')
			agreeAudioManager.flushAudioQueue()
		}

		// Log disclaimer acceptance to backend
		try {
			const timestamp = Date.now()
			const backendUrl = getBackendHttpUrl()
			const response = await fetch(`${backendUrl}/api/disclaimer-acceptance`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
				},
				body: JSON.stringify({
					form_session_id: state?.formSessionId || 'unknown',
					language: selectedLanguage,
					timestamp: timestamp,
					user_agent: navigator.userAgent,
				}),
			})

			if (response.ok) {
				const result = await response.json()
				console.log('[VoiceOverlay] ✅ Disclaimer acceptance logged to backend:', result)
			} else {
				console.warn('[VoiceOverlay] ⚠️ Backend logging returned non-OK status:', response.status)
			}
		} catch (err) {
			console.error('[VoiceOverlay] ❌ Failed to log disclaimer acceptance to backend:', err)
			// Don't block user - logging failure is non-fatal
		}

		// Check if connection is still active - the long disclaimer read may have caused
		// the connection to go stale (idle timeout or disconnected)
		const currentStatus = connectionManager?.getStatus()
		const isConnectionActive = currentStatus === 'connected' || currentStatus === 'switching_section'

		let reconnected = false
		if (!isConnectionActive) {
			console.log('[VoiceOverlay] 🔄 Connection stale after disclaimer - reconnecting...')
			console.log('[VoiceOverlay] Current status:', currentStatus)

			try {
				// Reconnect to backend
				await handleConnect()
				// handleConnect() does not throw on timeout -- it calls setError and returns
				// normally. Re-check status so a silent timeout does not fall through to
				// switchToFirstSection on a dead connection (bd polyglot-pdf-ppf1).
				const postReconnectStatus = connectionManager?.getStatus()
				if (postReconnectStatus !== 'connected' && postReconnectStatus !== 'switching_section') {
					console.error('[VoiceOverlay] ❌ Reconnect timed out, status:', postReconnectStatus)
					setError('Connection lost - please click Reconnect')
					return
				}
				reconnected = true
				console.log('[VoiceOverlay] ✅ Reconnected after disclaimer acceptance')
			} catch (err) {
				console.error('[VoiceOverlay] ❌ Reconnection failed:', err)
				setError('Connection lost - please click Reconnect')
				return
			}
		}

		// Now switch to section 1 to restart Gemini with form-filling context (clean session, no disclaimer leakage)
		console.log('[VoiceOverlay] ✅ Disclaimer accepted - switching to first section (restarts Gemini session)')

		if (connectionManager && selectedLanguage) {
			// Step 3: Resume audio playback FIRST so we don't miss any response chunks
			const am = connectionManager.getAudioManager()
			if (am) {
				console.log('[VoiceOverlay] 🔊 Resuming audio playback for Gemini response')
				am.resumePlayback()
			}

			// Step 4: Send activity_end to close the "user turn" so Gemini can respond.
			// SKIP on the reconnect path (bd polyglot-pdf-ala0): the sendActivityStart
			// above opened the turn on the OLD (stale) connection, so the new connection
			// has no matching open turn -- sending activity_end here would be an unmatched
			// signal (in native VAD the backend turns it into a spurious audio_stream_end
			// on a turn that never opened). On reconnect, switchToFirstSection below
			// restarts Gemini cleanly and drives the turn, so the end is unnecessary.
			if (!reconnected) {
				console.log('[VoiceOverlay] 🎤 Sending activity_end to signal user turn complete')
				await connectionManager.sendActivityEnd()
			}

			// Step 5: Switch to first section - this restarts Gemini with form-filling context
			// The section switch mechanism:
			// 1. Closes the current Gemini session (flushes disclaimer context)
			// 2. Starts a fresh Gemini session with form-filling system instruction
			// 3. Sends the initiating message for the first field
			await connectionManager.switchToFirstSection(selectedLanguage)
		}
	}

	// Handle clear form button
	const handleClearForm = () => {
		if (!confirm('⚠️ Clear all form data?\n\nThis will delete all fields and reload the page.\nThis action cannot be undone.')) {
			return
		}

		// Clear sessionStorage
		SchemaFormStateManager.clear()
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
	const requiredCount = schema.fields.filter(f => f.validation?.required).length

	// Debug logging removed - was causing 100+ logs per second in development mode

	return (
		<>
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
							{isConnected ? '🟢' : status === 'idle_timeout' ? '⏱️' : '⚪'}
						</span>
						<span className="vff-status-text">
							{status === 'idle_timeout' ? 'Disconnected due to inactivity' : status}
						</span>
						{/* VAD speech detection indicator */}
						{vad.userSpeaking && !pushToTalkMode && !nativeVad && (
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
								{getCurrentSectionLabel()}
							</span>
							<span className="vff-dropdown-arrow">{showSectionDropdown ? '▲' : '▼'}</span>
						</div>
						<div className="vff-field-counter">
							📊 {sectionFieldCount.filled} of {sectionFieldCount.total} fields completed
						</div>
						{showSectionDropdown && (
							<div className="vff-section-dropdown">
								{schema.sections?.map((section) => (
									<div
										key={section.id}
										className={`vff-section-item ${currentSectionId === section.id ? 'active' : ''}`}
										onClick={async () => {
											if (!connectionManager) return

											setShowSectionDropdown(false)

											// Don't switch if already on this section
											if (section.id === currentSectionId) {
												return
											}

											try {
												setError(null)

												// Update UI immediately for responsiveness
												setCurrentSectionId(section.id)
												setStatus('Reconnecting to section ' + section.order)

												// Update field count for new section (from state, before reconnect)
												const state = SchemaFormStateManager.load()
												if (state) {
													// Switch section in state first
													const updatedState = SchemaFormStateManager.switchToSection(state, section.id)
													const totalFields = schema.fields.length
													const filledFields = Object.keys(updatedState.fieldValues).filter(fieldId => {
														const fieldValue = updatedState.fieldValues[fieldId]
														const actualValue = fieldValue?.value
														return actualValue !== null && actualValue !== undefined && actualValue !== ""
													}).length
													setSectionFieldCount({ filled: filledFields, total: totalFields })
												}

												// Now do the actual connection switch (async, may take time)
												await connectionManager.switchToSection(section.id)
											} catch (err) {
												console.error('[VoiceOverlay] Section switch error:', err)
												setError(err instanceof Error ? err.message : 'Section switch failed')
											}
										}}
									>
										<span className="vff-section-status">
											{completedSections.has(section.id) ? '✓' :
												currentSectionId === section.id ? '→' : '○'}
										</span>
										<span className="vff-section-text">
											{section.label}
										</span>
									</div>
								))}
							</div>
						)}
					</div>
					{/* Input-mode toggle. PTT is a CLIENT-SIDE AUDIO GATE that works in
					    BOTH modes: native Gemini VAD always runs on the backend, and PTT
					    (when on) gates which client audio bytes reach Gemini -- useful in
					    noisy rooms so background noise doesn't trip Gemini's VAD. PTT on =
					    "PTT" (send only while held); PTT off = "Auto" (stream
					    continuously). The toggle is always enabled. */}
					<div className="vff-ptt-toggle-container">
						<label
							className="vff-ptt-toggle-label"
							title={pushToTalkMode
								? 'Push-to-talk: audio is sent only while you hold the button (good for noisy rooms).'
								: 'Continuous: your mic streams to Gemini and its voice detection decides when you are speaking.'}
						>
							<span className="vff-ptt-label-text">Input Mode:</span>
							<div className="vff-ptt-toggle-switch">
								<input
									type="checkbox"
									checked={pushToTalkMode}
									onChange={handlePushToTalkToggle}
									className="vff-ptt-toggle-input"
									onKeyDown={(e) => {
										if (e.code === 'Space') {
											e.preventDefault() // Prevent spacebar from toggling checkbox when focused
										}
									}}
								/>
								<span className="vff-ptt-toggle-slider">
									<span className="vff-ptt-toggle-icon vff-ptt-toggle-icon-auto">🎤</span>
									<span className="vff-ptt-toggle-icon vff-ptt-toggle-icon-ptt">⌨️</span>
								</span>
							</div>
							<span className="vff-ptt-mode-label">{pushToTalkMode ? 'PTT' : 'Auto'}</span>
						</label>
					</div>

					{/* Push-to-Talk button: visible whenever PTT gating is on (works in
					    native VAD too -- it gates the client audio bytes). */}
					{pushToTalkMode && isConnected && (
						<div className="vff-ptt-button-container">
							<button
								className={`vff-button vff-ptt-button ${isHoldingPushToTalk ? 'active' : ''}`}
								onMouseDown={handlePushToTalkPress}
								onTouchStart={handlePushToTalkPress}
							>
								{isHoldingPushToTalk ? '🔴 Recording...' : '⌨️ Hold to Talk (or Spacebar)'}
							</button>
						</div>
					)}

					{/* Controls */}
					<div className="vff-controls">
						{/* Connection is automatic after language selection - no connect button needed */}
						{status === 'idle_timeout' ? (
							<button
								className="vff-button vff-reconnect"
								onClick={handleConnect}
							>
								🔄 Reconnect
							</button>
						) : isPausedState ? (
							<button
								className="vff-button vff-resume"
								onClick={handleConnect}
							>
								▶️ Resume
							</button>
						) : isConnected ? (
							<button
								className="vff-button vff-pause"
								onClick={handleDisconnect}
							>
								⏸️ Pause
							</button>
						) : null}
						<button className="vff-button vff-clear-form" onClick={handleClearForm}>
							🗑️ Clear Form
						</button>
					</div>

					{/* Error Display */}
					{/* FIX #4: Show both connection errors and stream errors */}
					{(error || streamError) && (
						<div className="vff-error">
							{streamError && (
								<div><strong>🎤 Microphone Error:</strong> {streamError}</div>
							)}
							{error && <div>{error}</div>}
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

				.vff-language-selector {
					margin-bottom: 16px;
					padding: 12px;
					background: #f0f9ff;
					border-radius: 8px;
					border: 1px solid #bae6fd;
				}

				.vff-language-label {
					display: block;
					font-size: 13px;
					font-weight: 600;
					color: #0369a1;
					margin-bottom: 8px;
				}

				.vff-language-select {
					width: 100%;
					padding: 8px 12px;
					font-size: 14px;
					border: 1px solid #7dd3fc;
					border-radius: 6px;
					background: white;
					color: #0c4a6e;
					cursor: pointer;
					transition: all 0.2s;
				}

				.vff-language-select:hover {
					border-color: #0ea5e9;
					box-shadow: 0 0 0 2px rgba(14, 165, 233, 0.1);
				}

				.vff-language-select:focus {
					outline: none;
					border-color: #0284c7;
					box-shadow: 0 0 0 3px rgba(14, 165, 233, 0.2);
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

				/* PTT Toggle Container */
				.vff-ptt-toggle-container {
					padding: 12px;
					background: #f8f9ff;
					border-radius: 8px;
					border: 1px solid #d0dbff;
					margin-bottom: 12px;
				}

				.vff-ptt-toggle-label {
					display: flex;
					align-items: center;
					justify-content: space-between;
					gap: 10px;
					cursor: pointer;
				}

				.vff-ptt-label-text {
					font-size: 13px;
					font-weight: 600;
					color: #374151;
				}

				.vff-ptt-toggle-switch {
					position: relative;
					display: inline-block;
					width: 50px;
					height: 24px;
				}

				.vff-ptt-toggle-input {
					opacity: 0;
					width: 0;
					height: 0;
				}

				.vff-ptt-toggle-slider {
					position: absolute;
					cursor: pointer;
					top: 0;
					left: 0;
					right: 0;
					bottom: 0;
					background-color: #667eea;
					transition: 0.3s;
					border-radius: 24px;
					display: flex;
					align-items: center;
					justify-content: space-between;
					padding: 0 4px;
				}

				.vff-ptt-toggle-slider:before {
					content: "";
					position: absolute;
					height: 18px;
					width: 18px;
					left: 3px;
					bottom: 3px;
					background-color: white;
					transition: 0.3s;
					border-radius: 50%;
					box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
					z-index: 1;
				}

				.vff-ptt-toggle-input:checked + .vff-ptt-toggle-slider {
					background-color: #4c51bf;
				}

				.vff-ptt-toggle-input:checked + .vff-ptt-toggle-slider:before {
					transform: translateX(26px);
				}

				.vff-ptt-toggle-input:focus + .vff-ptt-toggle-slider {
					box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.3);
				}

				.vff-ptt-toggle-icon {
					font-size: 12px;
					opacity: 0.7;
					transition: opacity 0.3s;
				}

				.vff-ptt-toggle-icon-auto {
					order: 1;
				}

				.vff-ptt-toggle-icon-ptt {
					order: 2;
				}

				.vff-ptt-toggle-input:not(:checked) ~ .vff-ptt-toggle-slider .vff-ptt-toggle-icon-auto {
					opacity: 1;
				}

				.vff-ptt-toggle-input:checked ~ .vff-ptt-toggle-slider .vff-ptt-toggle-icon-ptt {
					opacity: 1;
				}

				.vff-ptt-mode-label {
					font-size: 13px;
					font-weight: 600;
					color: #6b7280;
					min-width: 40px;
					text-align: right;
				}

			.vff-ptt-button-container {
				margin-bottom: 12px;
			}

			.vff-ptt-button {
				width: 100%; /* Full width regardless of text content */
				background: linear-gradient(135deg, #4c51bf 0%, #667eea 100%);
				color: white;
				font-size: 15px;
				padding: 16px;
				user-select: none;
				-webkit-user-select: none;
				-webkit-touch-callout: none;
				text-align: center; /* Center text when width is fixed */
			}				.vff-ptt-button:active,
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

			{/* Language Selection Modal - fallback if initialLanguage not provided */}
			{showLanguageModal && (
				<LanguageSelectionModal
					onSelection={handleInitialLanguageSelect}
					preselectedFormId={schema.form_metadata.form_number || 'default'}
				/>
			)}

			{/* Disclaimer Modal - shown after language selection */}
			<DisclaimerModal
				isOpen={showDisclaimerModal}
				selectedLanguage={selectedLanguage}
				onListenAgain={handleDisclaimerListenAgain}
				onAgree={handleDisclaimerAgree}
			/>
		</>
	)
}
