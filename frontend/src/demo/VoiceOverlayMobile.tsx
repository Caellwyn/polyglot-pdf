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
import { SchemaFormStateManager } from '../schema-forms/state/schemaFormState'
import type { FormSchema } from '../schema-forms/types/schema'
import { computeNextField, formatNextFieldHint } from '../navigation'
import { useDemoVAD } from './useDemoVAD'
import { DisclaimerModal, DISCLAIMER_TRANSLATIONS } from '../schema-forms/components/DisclaimerModal'
import { ConnectionTimeoutModal } from '../schema-forms/components/ConnectionTimeoutModal'
import { LanguageSelectionModal } from '../schema-forms/components/LanguageSelectionModal'
import { SPOKEN_LANGUAGES } from '../shared/languages'
import { getBackendHttpUrl } from '../schema-forms/utils/pdfFiller'

interface VoiceOverlayMobileProps {
	schema: FormSchema
	wsUrl?: string
	connectionManager?: ConnectionManager
	status?: string
	// FIX #1: Shared audio stream passed from parent (prevents race conditions)
	sharedStream?: MediaStream | null
	// FIX #4: Stream error from parent (for error visibility)
	streamError?: string | null
	/** Pre-selected language from onboarding (skips language selection modal) */
	initialLanguage?: string
}

export function VoiceOverlayMobile({ schema, wsUrl, connectionManager: sharedConnectionManager, status: sharedStatus, sharedStream, streamError, initialLanguage }: VoiceOverlayMobileProps) {
	const [connectionManager, setConnectionManager] = useState<ConnectionManager | null>(sharedConnectionManager || null)
	const connectionManagerRef = useRef<ConnectionManager | null>(sharedConnectionManager || null)
	const [status, setStatus] = useState<string>(sharedStatus || 'Ready')
	const [error, setError] = useState<string | null>(null)
	const [isExpanded, setIsExpanded] = useState(false)
	// FIX #2: Removed pendingVADStart state - consolidated VAD start logic into single useEffect
	const [currentSectionId, setCurrentSectionId] = useState<string>('')
	const [completedSections, setCompletedSections] = useState<Set<string>>(new Set())
	const [sectionFieldCount, setSectionFieldCount] = useState({ filled: 0, total: 12 })
	// PTT default is true (HALLUCINATION_REDUCTION, Oct 30 2025), BUT when this
	// overlay is remounted onto an ALREADY-LIVE session (a desktop<->mobile
	// breakpoint cross) restore the user's actual choice from the connection rather
	// than resetting to true (Codex review PR #119) -- otherwise a flip silently
	// reverts Auto back to PTT and stops streaming.
	const [pushToTalkMode, setPushToTalkMode] = useState(
		() => sharedConnectionManager?.getPushToTalkMode?.() ?? true
	)
	// bd polyglot-pdf-tlc: whether Gemini's own (native) VAD drives turns. Set by
	// the backend at session_ready (mirror of DISABLE_GEMINI_VAD). When true the
	// manual PTT toggle does not apply, so it is disabled and the displayed mode
	// reflects native VAD instead of a stale "PTT".
	const [nativeVad, setNativeVad] = useState(false)
	const [isHoldingPushToTalk, setIsHoldingPushToTalk] = useState(false)
	// Live mic-energy meter (bd polyglot-pdf-s3zv): mirrors the desktop overlay.
	// `micEnergy` is the worklet's smoothed RMS (0-100); `micSending` is whether the
	// latest frame passed the send gate. The worklet fires ~50x/sec, so we stash the
	// latest in a ref and flush to state on an rAF loop (one re-render per frame).
	const [micEnergy, setMicEnergy] = useState(0)
	const [micSending, setMicSending] = useState(false)
	const energyRef = useRef({ energy: 0, sending: false, lastFrameAt: 0 })
	const [showDisclaimerModal, setShowDisclaimerModal] = useState(false)
	// User dismissed the connection-timeout modal without reconnecting (bd
	// polyglot-pdf-jf6w.2); reset when status leaves reconnect_failed.
	const [reconnectModalDismissed, setReconnectModalDismissed] = useState(false)
	// If initialLanguage is provided (from parent onboarding), use it and skip language modal
	const [showLanguageModal, setShowLanguageModal] = useState(!initialLanguage)  // Skip if language pre-selected
	const [selectedLanguage, setSelectedLanguage] = useState(initialLanguage || '')  // Track selected spoken language
	const [pendingDisclaimerRead, setPendingDisclaimerRead] = useState(false)  // Track if we need to send disclaimer prompt when connected

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

	// CRITICAL: Use ref for status to avoid closure capture in global handlers
	// This allows handlers to check current connection status without adding status to useEffect deps
	const statusRef = useRef<string>(status)

	// PTT release delay timer (allows final audio to be sent before muting)
	const pttReleaseTimeoutRef = useRef<number | null>(null)
	const isHoldingPushToTalkRef = useRef<boolean>(isHoldingPushToTalk)

	// Helper functions for section-based navigation (parts use string IDs, not numbers)
	const getCurrentSectionOrder = (): number => {
		const section = schema.sections?.find(p => p.id === currentSectionId)
		return section?.order ?? 1
	}

	const getCurrentSectionLabel = (): string => {
		const section = schema.sections?.find(p => p.id === currentSectionId)
		return section?.label ?? 'Unknown Part'
	}

	const getSectionIdFromOrder = (order: number): string => {
		const section = schema.sections?.find(p => p.order === order)
		return section?.id ?? ''
	}

	// FIX #1: Update stream ref when prop changes (parent manages lifecycle)
	useEffect(() => {
		sharedStreamRef.current = sharedStream || null
		console.log('[VoiceOverlayMobile] [link] Using shared stream from parent:', !!sharedStream)
	}, [sharedStream])

	// If language is pre-selected from onboarding, auto-trigger disclaimer flow on mount
	useEffect(() => {
		if (initialLanguage && !showLanguageModal) {
			// Guard against a remount re-running the connect+disclaimer flow on an
			// ALREADY-LIVE session (bd polyglot-pdf-6vo): this overlay can remount
			// (e.g. a desktop<->mobile switch) while connectionManager stays alive. If
			// it is already connected, re-connecting + re-showing the disclaimer would
			// restart the Gemini session and repeat the disclaimer. Skip in that case.
			const st = (connectionManager?.getStatus?.() || '').toLowerCase()
			// Include 'connecting' so a desktop<->mobile flip DURING the first connect
			// does not kick off a second concurrent connect (fresh-eyes PR #119).
			const alreadyLive = st === 'connected' || st.startsWith('connected ') ||
				st === 'connecting' || st === 'switching_section' || st.startsWith('reconnecting')
			if (alreadyLive) {
				// Skip the re-CONNECT, but do NOT drop the disclaimer step (Codex review
				// PR #119): a flip during the initial connect unmounts the old overlay
				// mid-flow, so its pending setShowDisclaimerModal(true) is lost. If the
				// user has not yet accepted, surface the modal here so they still get the
				// agree step instead of ending up connected but never prompted. (A
				// returning user with disclaimerAccepted is handled by the effect below.)
				const accepted = SchemaFormStateManager.load()?.disclaimerAccepted
				if (!accepted) {
					console.log('[VoiceOverlayMobile] Live session, disclaimer not yet accepted - showing modal (no reconnect)')
					setPendingDisclaimerRead(true)
					setShowDisclaimerModal(true)
				} else {
					console.log('[VoiceOverlayMobile] Mounted onto a live session (disclaimer accepted) - skipping connect/disclaimer')
				}
				// Re-arm mic capture: the old overlay's unmount stopped audio capture,
				// so the new (remounted) overlay must re-start it without reconnecting.
				// No-ops if already recording (double-arm guard inside rearmAudioCapture).
				// bd polyglot-pdf-nlfc.
				connectionManager?.rearmAudioCapture().catch((err) => {
					console.error('[VoiceOverlayMobile] rearmAudioCapture failed -- mic may be dead after overlay swap:', err)
				})
				return
			}
			console.log('[VoiceOverlayMobile] Language pre-selected from onboarding:', initialLanguage)
			// Trigger the same flow as handleInitialLanguageSelect
			const triggerDisclaimerFlow = async () => {
				try {
					setPendingDisclaimerRead(true)
					await handleConnect()
					setShowDisclaimerModal(true)
				} catch (err) {
					console.error('[VoiceOverlayMobile] Failed to connect after pre-selected language:', err)
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

	// Sync the audio pipeline to the current PTT mode (Codex review PR #119).
	// The desktop overlay has this; mobile previously synced only inside the toggle
	// HANDLER, so with the default pushToTalkMode=true the PTT bar showed but the
	// audio layer kept pttModeEnabled=false / inputMuted=false -> under native VAD
	// shouldSendAudioChunk streamed continuously while the UI claimed press-to-talk.
	// Run the same mute/unmute + worklet config on connect and on every mode change.
	// (setPTTMode keeps the worklet RMS gate bypassed under native VAD, so toggling
	// PTT off does not re-arm it.)
	useEffect(() => {
		if (!connectionManager) return
		connectionManager.setPushToTalkMode(pushToTalkMode)
		const audioManager = connectionManager.getAudioManager()
		audioManager?.setPTTMode(pushToTalkMode)
		if (pushToTalkMode) {
			audioManager?.muteInput()
		} else {
			audioManager?.unmuteInput()
		}
	}, [connectionManager, pushToTalkMode])

	// Live mic-energy meter subscription (bd polyglot-pdf-s3zv); mirrors the desktop
	// overlay. Tap the worklet RMS stream via the audio manager, stash each frame in
	// a ref, and flush to state on a rAF loop. Decay to 0 after ~250ms of no frames
	// so a flat meter reads as "no audio reaching the backend".
	useEffect(() => {
		const audioManager = connectionManager?.getAudioManager()
		if (!audioManager?.setEnergyCallback) return

		audioManager.setEnergyCallback((energy, sending) => {
			energyRef.current = { energy, sending, lastFrameAt: performance.now() }
		})

		let rafId = 0
		const tick = () => {
			const { energy, sending, lastFrameAt } = energyRef.current
			const stale = performance.now() - lastFrameAt > 250
			const displayEnergy = stale ? 0 : energy
			const displaySending = stale ? false : sending
			setMicEnergy(prev => (Math.abs(prev - displayEnergy) > 0.5 ? displayEnergy : prev))
			setMicSending(prev => (prev !== displaySending ? displaySending : prev))
			rafId = requestAnimationFrame(tick)
		}
		rafId = requestAnimationFrame(tick)

		return () => {
			cancelAnimationFrame(rafId)
			audioManager.setEnergyCallback?.(null)
		}
	}, [connectionManager])

	// Keep status ref updated
	useEffect(() => {
		statusRef.current = status
	}, [status])

	// Clear the connection-timeout-modal dismissal once the connection leaves the
	// terminal reconnect_failed state (bd polyglot-pdf-jf6w.2).
	useEffect(() => {
		if (status.toLowerCase() !== 'reconnect_failed' && reconnectModalDismissed) {
			setReconnectModalDismissed(false)
		}
	}, [status, reconnectModalDismissed])

	// bd polyglot-pdf-tlc: learn the backend's VAD mode once connected (mirror of
	// the desktop overlay). onNativeVadMode fires before status flips to
	// "connected", so isNativeVad() is reliable on connect. In native-VAD mode
	// neither PTT nor client Silero VAD applies, so the toggle is disabled and the
	// shouldRunVAD / PTT-button / Listening-badge guards key on `nativeVad`. We do
	// NOT force pushToTalkMode false -- that would start Silero in native mode and
	// block Gemini audio (fresh-eyes on PR #110). Reset on disconnect.
	useEffect(() => {
		if (!connectionManager) {
			setNativeVad(false)
			return
		}
		const isConn = status.toLowerCase() === 'connected' ||
			status.toLowerCase().startsWith('connected ')
		setNativeVad(isConn ? connectionManager.isNativeVad() : false)
	}, [connectionManager, status])

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

		console.log('[PTT Safety Mobile] [warn] Force-releasing PTT due to safety trigger')
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
			console.log('[PTT Safety Mobile] Starting safety timeout (max 60s)')
			pttSafetyTimeoutRef.current = window.setTimeout(() => {
				console.log('[PTT Safety Mobile] [warn] Max duration reached - force releasing')
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
				console.log('[PTT Safety Mobile] [warn] Tab hidden while recording - force releasing')
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
				console.log('[PTT Safety Mobile] [warn] Window lost focus while recording - force releasing')
				forceReleasePTT()
			}
		}

		window.addEventListener('blur', handleWindowBlur)
		return () => window.removeEventListener('blur', handleWindowBlur)
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [])

	// Safety mechanism 4: Connection status change (disconnect while recording)
	useEffect(() => {
		const isCurrentlyConnected = status.toLowerCase() === 'connected' ||
			status.toLowerCase().startsWith('connected ')

		if (!isCurrentlyConnected && isHoldingPushToTalkRef.current) {
			console.log('[PTT Safety Mobile] [warn] Connection lost while recording - force releasing')
			forceReleasePTT()
		}
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [status])

	// Safety mechanism 5: Cleanup on unmount
	useEffect(() => {
		return () => {
			if (isHoldingPushToTalkRef.current) {
				console.log('[PTT Safety Mobile] [warn] Component unmounting while recording - force releasing')
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

			console.log('[VFF VAD] [mic] User speech started - buffering audio...')

			// Record speech start time
			speechStartTimeRef.current = Date.now()
			bargeInTriggeredRef.current = false  // Reset flag


		// INSTANT FEEDBACK: Pause audio immediately if Gemini is speaking
		// This gives instant barge-in feel while we wait to confirm speech duration
		const audioManager = connectionManager?.getAudioManager()
		if (audioManager && audioManager.isSpeaking()) {
			audioManager.pauseAudioContext()
			console.log('[VFF VAD Mobile] [mute] Tentative pause - waiting to confirm speech duration')
		}

		// Schedule delayed turn start - only send activity_start + audio if speech lasts >=450ms
		// This prevents false positives (throat clears, grunts) from creating incomplete turns
		setTimeout(() => {
			const speechDuration = speechStartTimeRef.current
				? Date.now() - speechStartTimeRef.current
				: 0

			// Only start turn if speech is still active AND duration met
			if (speechStartTimeRef.current !== null && speechDuration >= MIN_TURN_DURATION_MS) {
				console.log(`[VFF VAD Mobile] [OK] Valid speech detected (${speechDuration}ms) - starting turn`)
				bargeInTriggeredRef.current = true

				// CRITICAL: Send activity_start BEFORE opening audio gate
				// This ensures Gemini receives the turn signal before any audio chunks
				// Pattern: activity_start -> audio chunks -> activity_end (Gemini Live API docs lines 419-435)
				if (connectionManager) {
					connectionManager.sendActivityStart()
					console.log('[VFF VAD Mobile] [send] Sent activity_start signal (user turn begins)')
				}

				// Privacy Gate: Open audio flow (sends pre-buffer + live audio)
				// Must happen AFTER activity_start to ensure proper turn framing
				if (audioManager) {
					audioManager.setVADActive(true) // Opens gate, flushes 600ms pre-buffer to backend
				}

				// Trigger FULL barge-in (flushes audio queue if Gemini speaking)
				const geminiSpeaking = audioManager?.isSpeaking()
				if (geminiSpeaking && audioManager) {
					console.log('[VFF VAD Mobile] [mute] Flushing Gemini audio queue (full barge-in)')
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
		
		// Only close gate and send activity_end if we actually started a turn (>=450ms)
		if (bargeInTriggeredRef.current) {
			console.log(`[VFF VAD Mobile] [OK] Valid turn completed (${speechDuration}ms) - closing turn`)

			// Close audio gate
			if (audioManager) {
				audioManager.setVADActive(false) // Closes gate, stops audio flow
			}

			// Send activity_end to signal user is done speaking
			connectionManager?.onVADSpeechEnd()
		} else {
			console.log(`[VFF VAD Mobile] [warn] Speech too short (${speechDuration}ms < ${MIN_TURN_DURATION_MS}ms) - no turn started, false positive`)

			// FALSE POSITIVE: Resume audio playback (speech was too short to start a turn)
			// Gate was never opened, so nothing to close
			if (audioManager) {
				audioManager.resumeAudioContext()
				console.log('[VFF VAD Mobile] [sound] Resuming audio - false positive')
			}
		}			// Clear state
			speechStartTimeRef.current = null
			bargeInTriggeredRef.current = false
		},
		onVADMisfire: () => {
			console.log('[VFF VAD] [warn] VAD misfire detected')
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
}, [schema, sharedConnectionManager]) // Recreate when schema changes	// Sync status from shared prop
	useEffect(() => {
		if (sharedStatus !== undefined) {
			setStatus(sharedStatus)
		}
	}, [sharedStatus])

	// Check for returning users (on mount)
	useEffect(() => {
		const state = SchemaFormStateManager.load()
		if (state?.disclaimerAccepted && state?.selectedLanguage) {
			console.log('[VoiceOverlayMobile] Returning user - skipping language/disclaimer modals')
			setShowLanguageModal(false)
			setShowDisclaimerModal(false)
			setSelectedLanguage(state.selectedLanguage)
		}
	}, [])

	// Send disclaimer read request when connection is ready and disclaimer read is pending
	useEffect(() => {
		const isConnected = status.toLowerCase() === 'connected' || status.toLowerCase().startsWith('connected ')

		if (isConnected && pendingDisclaimerRead && connectionManager && selectedLanguage) {
			console.log('[VoiceOverlayMobile] [OK] Connection ready - requesting disclaimer read')

			// Clear the flag IMMEDIATELY to prevent double-firing
			setPendingDisclaimerRead(false)

			// Send read_disclaimer message to backend using the proven language change pattern.
			// Pass the full translated disclaimer text (mirrors desktop VoiceOverlay.tsx):
			// omitting it makes the backend log missing_disclaimer_text and read a generic
			// fallback instead of the verbatim legal disclaimer (bd polyglot-pdf-cd0).
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
		// bd polyglot-pdf-tlc: never run client Silero VAD in native mode (Gemini's
		// VAD drives turns; Silero would block playback without a matching resume).
		const shouldRunVAD = isConnected && !pushToTalkMode && !nativeVad && !vad.loading && !vad.errored

		if (shouldRunVAD && !vad.userSpeaking) {
			console.log('[VoiceOverlayMobile] [mic] Starting VAD (conditions met)')
			vad.start()
		} else if (!shouldRunVAD && vad.userSpeaking) {
			console.log('[VoiceOverlayMobile] [pause] Pausing VAD (conditions not met)')
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


	// Handle initial language selection from modal (fallback when initialLanguage not provided)
	const handleInitialLanguageSelect = async (_formId: string, language: string) => {
		console.log('[VoiceOverlayMobile] Initial language selected from modal:', language)
		setSelectedLanguage(language)
		setShowLanguageModal(false)

		// Set pending flag so disclaimer will be read when connection is ready
		setPendingDisclaimerRead(true)

		// Start connection
		try {
			await handleConnect()

			// Show disclaimer modal after connection starts
			console.log('[VoiceOverlayMobile] Connection initiated - showing disclaimer modal')
			setShowDisclaimerModal(true)

			// The useEffect watching status will send the disclaimer prompt when ready
		} catch (err) {
			console.error('[VoiceOverlayMobile] Failed to connect after language selection:', err)
			setError(err instanceof Error ? err.message : 'Connection failed')
			setPendingDisclaimerRead(false) // Clear flag on error
		}
	}

	// Handle language selection change
	const handleLanguageChange = async (event: React.ChangeEvent<HTMLSelectElement>) => {
		const newLanguage = event.target.value

		if (!newLanguage) {
			setSelectedLanguage('')
			return
		}

		console.log('[VoiceOverlayMobile] Language selected:', newLanguage)
		setSelectedLanguage(newLanguage)

		// Check if disclaimer already accepted (returning user)
		const state = SchemaFormStateManager.load()
		if (state?.disclaimerAccepted) {
			console.log('[VoiceOverlayMobile] Disclaimer already accepted - proceeding to connection')
			// Already accepted, just change language if connected
			if (connectionManager && isConnected) {
				try {
					const nextField = computeNextField(state)
					const nextFieldHint = nextField ? formatNextFieldHint(nextField) : 'all fields are complete'
					connectionManager.changeSpokenLanguage(newLanguage, nextFieldHint)
				} catch (err) {
					console.error('[VoiceOverlayMobile] Failed to change spoken language:', err)
					setError(err instanceof Error ? err.message : 'Failed to change language')
				}
			}
			return
		}

		// First time - connect to Gemini, THEN show disclaimer modal
		console.log('[VoiceOverlayMobile] First language selection - connecting to Gemini...')
		try {
			// Set pending flag so disclaimer will be read when connection is ready
			setPendingDisclaimerRead(true)

			// Start connection
			await handleConnect()

			// Show disclaimer modal
			console.log('[VoiceOverlayMobile] Connection initiated - showing disclaimer modal')
			setShowDisclaimerModal(true)

			// The useEffect watching status will send the disclaimer prompt when ready
		} catch (err) {
			console.error('[VoiceOverlayMobile] Failed to connect after language selection:', err)
			setError(err instanceof Error ? err.message : 'Connection failed')
			setPendingDisclaimerRead(false) // Clear flag on error
		}
	}

	const handleDisclaimerListenAgain = () => {
		console.log('[VoiceOverlayMobile] User requested to listen again')

		if (connectionManager && selectedLanguage) {
			// Send read_disclaimer message using the same proven pattern. Pass the
			// full translated text so the backend reads the verbatim disclaimer, not
			// the generic missing_disclaimer_text fallback (bd polyglot-pdf-cd0).
			const disclaimerText = DISCLAIMER_TRANSLATIONS[selectedLanguage]?.fullText || DISCLAIMER_TRANSLATIONS['English'].fullText
			connectionManager.readDisclaimer(selectedLanguage, disclaimerText)
		}
	}

	const handleDisclaimerAgree = async () => {
		console.log('[VoiceOverlayMobile] User agreed to disclaimer')

		// Update state with disclaimer acceptance
		const state = SchemaFormStateManager.load()
		if (state) {
			state.disclaimerAccepted = true
			state.disclaimerAcceptedAt = Date.now()
			state.selectedLanguage = selectedLanguage
			SchemaFormStateManager.save(state)
		}

		setShowDisclaimerModal(false)

		// Step 1: Send activity_start FIRST to stop backend from sending more audio
		console.log('[VoiceOverlayMobile] [mic] Sending activity_start to interrupt Gemini')
		connectionManager?.sendActivityStart()

		// Step 2: THEN flush the local audio queue
		const audioManager = connectionManager?.getAudioManager()
		if (audioManager) {
			console.log('[VoiceOverlayMobile] [mute] Clearing audio queue on disclaimer agreement')
			audioManager.flushAudioQueue()
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
				console.log('[VoiceOverlayMobile] [OK] Disclaimer acceptance logged to backend:', result)
			} else {
				console.warn('[VoiceOverlayMobile] [warn] Backend logging returned non-OK status:', response.status)
			}
		} catch (err) {
			console.error('[VoiceOverlayMobile] [X] Failed to log disclaimer acceptance to backend:', err)
			// Don't block user - logging failure is non-fatal
		}

		// Check if connection is still active - the long disclaimer read may have caused
		// the connection to go stale (idle timeout or disconnected)
		const currentStatus = connectionManager?.getStatus()
		const isConnectionActive = currentStatus === 'connected' || currentStatus === 'switching_section'

		let reconnected = false
		if (!isConnectionActive) {
			console.log('[VoiceOverlayMobile] [reconnect] Connection stale after disclaimer - reconnecting...')
			console.log('[VoiceOverlayMobile] Current status:', currentStatus)

			try {
				// Reconnect to backend
				await handleConnect()
				// handleConnect() does not throw on timeout -- it calls setError and returns
				// normally. Re-check status so a silent timeout does not fall through to
				// switchToFirstSection on a dead connection (bd polyglot-pdf-ppf1).
				const postReconnectStatus = connectionManager?.getStatus()
				if (postReconnectStatus !== 'connected' && postReconnectStatus !== 'switching_section') {
					console.error('[VoiceOverlayMobile] [X] Reconnect timed out, status:', postReconnectStatus)
					setError('Connection lost - please click Reconnect')
					return
				}
				reconnected = true
				console.log('[VoiceOverlayMobile] [OK] Reconnected after disclaimer acceptance')
			} catch (err) {
				console.error('[VoiceOverlayMobile] [X] Reconnection failed:', err)
				setError('Connection lost - please click Reconnect')
				return
			}
		}

		// Now switch to section 1 to restart Gemini with form-filling context (clean session, no disclaimer leakage)
		console.log('[VoiceOverlayMobile] [OK] Disclaimer accepted - switching to first section (restarts Gemini session)')

		if (connectionManager && selectedLanguage) {
			// Step 3: Resume audio playback FIRST so we don't miss any response chunks
			const am = connectionManager.getAudioManager()
			if (am) {
				console.log('[VoiceOverlayMobile] [sound] Resuming audio playback for Gemini response')
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
				console.log('[VoiceOverlayMobile] [mic] Sending activity_end to signal user turn complete')
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
					console.log('[VoiceOverlayMobile] [OK] WebSocket connected, setting up audio...')
					// Update status to indicate audio setup in progress
					setStatus('Setting up audio...')

					// Start recording (this completes the connection)
					await connectionManager.startRecording()

					// Now fully connected - update status
					setStatus('connected')
					console.log('[VoiceOverlayMobile] [OK] Audio ready - fully connected')
					// FIX #2: VAD will auto-start via consolidated useEffect when status changes
					break
				}

				// Wait 50ms before checking again
				await new Promise(resolve => setTimeout(resolve, 50))
			}

			// Check final status
			const finalStatus = connectionManager.getStatus()
			if (finalStatus !== 'connected' && finalStatus !== 'switching_section') {
				console.error('[VoiceOverlayMobile] [X] Connection timeout, final status:', finalStatus)
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

	const handleClearForm = () => {
		// Confirm before clearing
		if (!confirm('Are you sure you want to clear all form data? This cannot be undone.')) {
			return
		}

		// Clear the form state
		SchemaFormStateManager.clear()

		// Reload the page to reset everything
		window.location.reload()
	}

	// FIX #2: Removed pendingVADStart useEffect - consolidated into single VAD control useEffect below

	// Handle push-to-talk mode toggle.
	// PTT is a CLIENT-SIDE AUDIO GATE layered on top of native VAD (noisy-room
	// support): native Gemini VAD always runs on the backend, but PTT (when on)
	// gates which client audio bytes reach Gemini. We run the full mute/unmute +
	// worklet reconfig regardless of native VAD -- audioManager.setPTTMode keeps the
	// worklet noise gate bypassed under native VAD, so toggling PTT off does not
	// re-arm the RMS gate. Manual activity_start/end stay suppressed in native mode
	// (connection.ts); PTT only decides which bytes are sent.
	const handlePushToTalkToggle = async () => {
		const newMode = !pushToTalkMode
		setPushToTalkMode(newMode)

		// Update connection manager PTT mode (disables energy-based barge-in)
		connectionManager?.setPushToTalkMode(newMode)
		
		const isCurrentlyConnected = status.toLowerCase() === 'connected' || 
		                            status.toLowerCase().startsWith('connected ') || 
		                            status.toLowerCase() === 'switching_section' || 
		                            status.toLowerCase().startsWith('reconnecting')
		
		const audioManager = connectionManager?.getAudioManager()
		
		// FIX (Nov 7, 2025): Notify audio worklet about PTT mode (bypasses noise gate)
		audioManager?.setPTTMode(newMode)
		
		if (newMode) {
			// Switching to PTT: pause VAD
			vad.pause()
			// Mute input so only silence is sent until button is pressed
			audioManager?.muteInput()
		} else {
			// Switching to VAD mode
			// FIX #2: VAD will auto-start via consolidated useEffect (monitors pushToTalkMode)
			// Unmute input for normal VAD operation
			audioManager?.unmuteInput()
		}
	}

	// Handle push-to-talk button press (touch)
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
		if (!pushToTalkMode) return
		
		// Clear any pending release timeout (user pressed again before release completed)
		if (pttReleaseTimeoutRef.current !== null) {
			clearTimeout(pttReleaseTimeoutRef.current)
			pttReleaseTimeoutRef.current = null
		}
		
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

		// CRITICAL: Send activity_start to open Gemini turn for PTT mode
		// Without this, activity_end will close the turn before audio arrives
		connectionManager?.sendActivityStart()
	}

	const handlePushToTalkRelease = () => {
		// Use refs for current values (avoids closure capture issues)
		const currentPTTMode = pushToTalkModeRef.current
		const currentlyHolding = isHoldingPushToTalkRef.current
		const currentStatus = statusRef.current

		if (!currentPTTMode) return
		// CRITICAL: Prevent duplicate calls (onTouchEnd + touchcancel/touchleave might both fire)
		if (!currentlyHolding) return

		const isCurrentlyConnected = currentStatus.toLowerCase() === 'connected' ||
		                            currentStatus.toLowerCase().startsWith('connected ') ||
		                            currentStatus.toLowerCase() === 'switching_section' ||
		                            currentStatus.toLowerCase().startsWith('reconnecting')
		if (!isCurrentlyConnected) return

		console.log('[PTT Mobile] Processing release - will delay 500ms before ending activity')
		
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
			console.log('[PTT Mobile] 500ms delay complete - sending activity_end and muting')

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

// Handle global touch/mouse release (catch PTT release even if finger/mouse moves off button)
useEffect(() => {
	if (!pushToTalkMode) return

	const handleGlobalRelease = (e: MouseEvent | TouchEvent) => {
		// Only handle if we're currently holding PTT
		if (isHoldingPushToTalkRef.current) {
			const currentStatus = statusRef.current
			const isConnected = currentStatus.toLowerCase() === 'connected' ||
			                   currentStatus.toLowerCase().startsWith('connected ') ||
			                   currentStatus.toLowerCase() === 'switching_section' ||
			                   currentStatus.toLowerCase().startsWith('reconnecting')

			if (isConnected) {
				console.log('[PTT Mobile Global] Touch/mouse released - calling handlePushToTalkRelease()')
				handlePushToTalkRelease()
			}
		}
	}

	document.addEventListener('mouseup', handleGlobalRelease)
	document.addEventListener('touchend', handleGlobalRelease)
	console.log('[PTT Mobile Global] [OK] Global touch/mouse release listeners attached')

	return () => {
		console.log('[PTT Mobile Global] [X] Removing global touch/mouse release listeners')
		document.removeEventListener('mouseup', handleGlobalRelease)
		document.removeEventListener('touchend', handleGlobalRelease)
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

// Poll field count AND section state (updates as AI switches parts)
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
			
			// Update completed parts if changed
			if (state.completedSections) {
				const currentCompleted = new Set(Array.from(completedSections))
				const newCompleted = new Set(Array.from(state.completedSections))
				
				// Check if sets are different
				if (currentCompleted.size !== newCompleted.size || 
				    ![...currentCompleted].every(p => newCompleted.has(p))) {
					setCompletedSections(newCompleted)
				}
			}
		}
	}, 1000) // Update every second
	
	return () => clearInterval(interval)
}, [currentSectionId, completedSections])

const isConnected = status.toLowerCase() === 'connected' || status.toLowerCase().startsWith('connected ')
const isPausedState = status.toLowerCase() === 'paused'
const isWarming = status.toLowerCase().includes('warming')
const isReady = status.toLowerCase() === 'ready'
const fieldCount = schema.fields.length
const requiredCount = schema.fields.filter(f => f.validation?.required).length	// Status color
	const statusColor = isConnected ? '#10b981' : isPausedState ? '#f59e0b' : isWarming ? '#f59e0b' : isReady ? '#3b82f6' : '#6b7280'

	return (
		<>
			{/* Language Selection Modal - fallback if initialLanguage not provided */}
			{showLanguageModal && (
				<LanguageSelectionModal
					onSelection={handleInitialLanguageSelect}
					preselectedFormId={schema.form_metadata.form_number || 'default'}
				/>
			)}

			{/* Disclaimer Modal - Show on first language selection */}
			<DisclaimerModal
				isOpen={showDisclaimerModal}
				selectedLanguage={selectedLanguage}
				onListenAgain={handleDisclaimerListenAgain}
				onAgree={handleDisclaimerAgree}
			/>
			{/* Connection-timeout modal on terminal reconnect failure (bd
			    polyglot-pdf-jf6w.2). */}
			<ConnectionTimeoutModal
				isOpen={status.toLowerCase() === 'reconnect_failed' && !reconnectModalDismissed}
				selectedLanguage={selectedLanguage}
				onReconnect={() => { setReconnectModalDismissed(false); handleConnect() }}
				onCancel={() => setReconnectModalDismissed(true)}
			/>
			{/* Main FAB */}
			<div className="vff-fab" onClick={() => setIsExpanded(!isExpanded)}>
				<div className="vff-fab-pulse" style={{ borderColor: statusColor }}></div>
				{/* VAD speech detection indicator - small green dot badge */}
				{vad.userSpeaking && !pushToTalkMode && !nativeVad && (
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
							<div className="vff-status-dot" style={{
								background: status === 'idle_timeout' ? '#6b7280' : statusColor
							}}></div>
							<span className="vff-status-text">
								{status === 'idle_timeout' ? 'Idle timeout' : status}
							</span>
							{/* Live mic-energy meter (bd polyglot-pdf-s3zv) */}
							{isConnected && (
								<span
									className={`vff-mic-meter${micSending ? ' vff-mic-meter--sending' : ''}`}
									title={micSending
										? `Sending audio (energy ${micEnergy.toFixed(0)})`
										: `Mic active, not sending (energy ${micEnergy.toFixed(0)})`}
								>
									<span
										className="vff-mic-meter-bar"
										style={{ width: `${Math.min(100, micEnergy)}%` }}
									></span>
								</span>
							)}
						</div>


					{/* Input-mode toggle. PTT is a client-side audio gate that works in
					    BOTH modes: native Gemini VAD always runs on the backend; PTT (on)
					    sends audio only while held (noisy-room support), PTT (off) streams
					    continuously. Always enabled. Left icon = continuous, right = PTT. */}
					<div className="vff-ptt-toggle-container-mobile">
						<label
							className="vff-ptt-toggle-label-mobile"
							title={pushToTalkMode
								? 'Push-to-talk: audio is sent only while you hold the button (good for noisy rooms).'
								: 'Continuous: your mic streams to Gemini and its voice detection decides when you are speaking.'}
						>
							<span className="vff-ptt-icon-left">🎤</span>
							<div className="vff-ptt-toggle-switch-mobile">
								<input
									type="checkbox"
									checked={pushToTalkMode}
									onChange={handlePushToTalkToggle}
									className="vff-ptt-toggle-input-mobile"
								/>
								<span className="vff-ptt-toggle-slider-mobile"></span>
							</div>
							<span className="vff-ptt-icon-right">⌨️</span>
						</label>
					</div>

					{/* Push-to-Talk bar: visible whenever PTT gating is on (works in
					    native VAD too -- it gates the client audio bytes). */}
					{pushToTalkMode && isConnected && (
						<div className="vff-ptt-bar-container">
							<button
								className={`vff-ptt-bar-button ${isHoldingPushToTalk ? 'active' : ''}`}
								onMouseDown={handlePushToTalkPress}
								onMouseUp={handlePushToTalkRelease}
								onTouchStart={handlePushToTalkTouchStart}
								onTouchEnd={handlePushToTalkTouchEnd}
								onTouchCancel={handlePushToTalkTouchEnd}
								onContextMenu={(e) => e.preventDefault()}
							>
								{isHoldingPushToTalk ? '🔴 Recording...' : '⌨️ Tap & Hold to Talk'}
							</button>
						</div>
					)}

					{/* Action Buttons - Resume/Pause/Reconnect */}
					{status === 'idle_timeout' ? (
						<button className="vff-action-btn vff-reconnect-btn" onClick={handleConnect}>
							🔄 Reconnect
						</button>
					) : isPausedState ? (
						<button className="vff-action-btn vff-resume-btn" onClick={handleConnect}>
							▶️ Resume
						</button>
					) : isConnected ? (
						<button className="vff-action-btn vff-pause-btn" onClick={handleDisconnect}>
							⏸️ Pause
						</button>
					) : null}

					{/* Clear Form Button */}
					<button className="vff-action-btn vff-clear-btn" onClick={handleClearForm}>
						🗑️ Clear Form
					</button>

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

				/* Horizontal Panel - Bottom 1/3 of screen */
				.vff-panel-mobile {
					position: fixed;
					bottom: 0;
					left: 0;
					right: 0;
					height: auto;
					max-height: 33vh;
					background: white;
					border-radius: 16px 16px 0 0;
					box-shadow: 0 -4px 24px rgba(0, 0, 0, 0.15);
					z-index: 9998;
					font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
					animation: vff-slide-up 0.3s ease-out;
					display: flex;
					flex-direction: column;
					overflow: hidden;
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
					padding: 8px 12px;
					border-bottom: 1px solid #e5e7eb;
				}

				.vff-title {
					font-weight: 600;
					font-size: 13px;
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
					padding: 10px;
					display: grid;
					grid-template-columns: repeat(6, 1fr);
					grid-template-rows: auto auto auto auto;
					gap: 8px;
					flex: 1;
					align-items: start;
				}

				.vff-status-compact {
					grid-column: 1 / 3;
					grid-row: 1;
					display: flex;
					align-items: center;
					gap: 6px;
					padding: 6px 10px;
					background: #f9fafb;
					border-radius: 6px;
					white-space: nowrap;
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
					flex: 1;
				}

				/* Live mic-energy meter (bd polyglot-pdf-s3zv) */
				.vff-mic-meter {
					display: inline-block;
					width: 40px;
					height: 6px;
					border-radius: 3px;
					background: #e5e7eb;
					overflow: hidden;
					flex-shrink: 0;
				}

				.vff-mic-meter-bar {
					display: block;
					height: 100%;
					width: 0%;
					border-radius: 3px;
					background: #9ca3af;
					transition: width 80ms linear, background 120ms ease;
				}

				.vff-mic-meter--sending .vff-mic-meter-bar {
					background: #10b981;
					box-shadow: 0 0 5px rgba(16, 185, 129, 0.6);
				}

				.vff-language-selector-mobile {
					grid-column: 1 / 4;
					grid-row: 2;
					padding: 6px 10px;
					background: #f0f9ff;
					border-radius: 6px;
					border: 1px solid #bae6fd;
				}

				.vff-language-label-mobile {
					display: block;
					font-size: 11px;
					font-weight: 600;
					color: #0369a1;
					margin-bottom: 4px;
				}

				.vff-language-select-mobile {
					width: 100%;
					padding: 4px 8px;
					font-size: 12px;
					border: 1px solid #7dd3fc;
					border-radius: 4px;
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
					padding: 10px;
					border: none;
					border-radius: 6px;
					font-size: 13px;
					font-weight: 600;
					cursor: pointer;
					transition: all 0.2s;
					user-select: none;
					-webkit-user-select: none;
					-webkit-touch-callout: none;
				}

				/* Connect/Pause/Resume/Reconnect button - row 2, columns 4-6 (50% width), 50% taller */
				.vff-connect-btn,
				.vff-pause-btn,
				.vff-resume-btn,
				.vff-reconnect-btn {
					grid-column: 4 / 7;
					grid-row: 2;
					padding: 15px;
					min-height: 60px;
					display: flex;
					align-items: center;
					justify-content: center;
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

				.vff-reconnect-btn {
					background: #3b82f6;
					color: white;
				}

				.vff-reconnect-btn:active {
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
					grid-column: 1 / -1;
					grid-row: 4;
					padding: 6px 10px;
					background: #fef2f2;
					border: 1px solid #fecaca;
					border-radius: 6px;
					color: #991b1b;
					font-size: 11px;
				}

				.vff-info-compact {
					grid-column: 1 / -1;
					grid-row: 4;
					text-align: center;
					font-size: 10px;
					color: #6b7280;
					padding: 4px 0;
					margin-top: 4px;
				}

				/* Clear form button - row 1, columns 5-6 */
				.vff-clear-btn {
					grid-column: 5 / 7;
					grid-row: 1;
					background: #ef4444;
					color: white;
				}

				.vff-clear-btn:active {
					transform: scale(0.98);
					background: #dc2626;
				}

				/* Mobile Adjustments */
				/* Mobile PTT Toggle Styles - Row 1, columns 3-4 */
			.vff-ptt-toggle-container-mobile {
				grid-column: 3 / 5;
				grid-row: 1;
				padding: 8px;
				background: #f8f9ff;
				border-radius: 6px;
				border: 1px solid #d0dbff;
				display: flex;
				justify-content: center;
			}

			.vff-ptt-toggle-label-mobile {
				display: flex;
				align-items: center;
				justify-content: center;
				gap: 6px;
				cursor: pointer;
			}

			.vff-ptt-label-text-mobile {
				display: none;
			}

			.vff-ptt-icon-left,
			.vff-ptt-icon-right {
				font-size: 16px;
			}

			.vff-ptt-toggle-switch-mobile {
				position: relative;
				display: inline-block;
				width: 50px;
				height: 24px;
			}

			.vff-ptt-toggle-input-mobile {
				opacity: 0;
				width: 0;
				height: 0;
			}

			.vff-ptt-toggle-slider-mobile {
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

			.vff-ptt-toggle-slider-mobile:before {
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
			}

			.vff-ptt-toggle-input-mobile:checked + .vff-ptt-toggle-slider-mobile {
				background-color: #4c51bf;
			}

			.vff-ptt-toggle-input-mobile:checked + .vff-ptt-toggle-slider-mobile:before {
				transform: translateX(26px);
			}

			.vff-ptt-toggle-input-mobile:focus + .vff-ptt-toggle-slider-mobile {
				box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.3);
			}

			/* Mobile PTT Bar Button - Row 3, full width, maximum accessibility */
			.vff-ptt-bar-container {
				grid-column: 1 / -1;
				grid-row: 3;
			}

			.vff-ptt-bar-button {
				width: 100%;
				padding: 24px;
				font-size: 18px;
				font-weight: 700;
				background: linear-gradient(135deg, #4c51bf 0%, #667eea 100%);
				color: white;
				border: none;
				border-radius: 10px;
				cursor: pointer;
				user-select: none;
				-webkit-user-select: none;
				-webkit-touch-callout: none;
				transition: all 0.2s;
				box-shadow: 0 4px 16px rgba(76, 81, 191, 0.4);
				min-height: 80px;
				display: flex;
				align-items: center;
				justify-content: center;
			}

			.vff-ptt-bar-button:active,
			.vff-ptt-bar-button.active {
				background: linear-gradient(135deg, #dc2626 0%, #ef4444 100%);
				box-shadow: 0 6px 20px rgba(220, 38, 38, 0.5);
				transform: scale(0.98);
			}

			.vff-ptt-bar-button:hover:not(:active) {
				box-shadow: 0 6px 20px rgba(76, 81, 191, 0.5);
			}

			@media (max-width: 480px) {
					.vff-panel-mobile {
						max-height: 350px;
					}

					.vff-fab {
						bottom: 16px;
						right: 16px;
					}

					.vff-ptt-bar-button {
						min-height: 70px;
						font-size: 16px;
					}
				}
			`}</style>
		</>
	)
}
