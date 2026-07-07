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
import type { ConnectionManager } from '../shared/connection'
import { SchemaFormStateManager } from '../schema-forms/state/schemaFormState'
import type { FormSchema } from '../schema-forms/types/schema'
import { computeNextField, formatNextFieldHint } from '../navigation'
import { useDemoVAD } from './useDemoVAD'
import { SPOKEN_LANGUAGES } from '../shared/languages'
import { DisclaimerModal, DISCLAIMER_TRANSLATIONS } from '../schema-forms/components/DisclaimerModal'
import { ConnectionTimeoutModal } from '../schema-forms/components/ConnectionTimeoutModal'
import { LanguageSelectionModal } from '../schema-forms/components/LanguageSelectionModal'
import { getBackendHttpUrl } from '../schema-forms/utils/pdfFiller'

interface VoiceOverlayProps {
	schema: FormSchema
	wsUrl?: string
	onClose?: () => void
	// Required (bd polyglot-pdf-d0k): this overlay never creates its own
	// ConnectionManager (all connections must carry an auth token, and the parent
	// -- SchemaForm.tsx -- is the only production render site), so it always
	// receives the manager from the parent.
	connectionManager: ConnectionManager
	status?: string
	// Thinking indicator from the parent (bd polyglot-pdf-wpw.5): SchemaForm owns
	// the shared ConnectionManager and wires onThinkingChange, passing the value
	// down here (mirrors `status`).
	thinking?: boolean
	// FIX #1: Shared audio stream passed from parent (prevents race conditions)
	sharedStream?: MediaStream | null
	// FIX #4: Stream error from parent (for error visibility)
	streamError?: string | null
	/** Pre-selected language from onboarding (skips language selection modal) */
	initialLanguage?: string
}

export function VoiceOverlay({ schema, wsUrl, onClose, connectionManager: sharedConnectionManager, status: sharedStatus, thinking: sharedThinking, sharedStream, streamError, initialLanguage }: VoiceOverlayProps) {
	const [connectionManager, setConnectionManager] = useState<ConnectionManager>(sharedConnectionManager)
	const connectionManagerRef = useRef<ConnectionManager>(sharedConnectionManager)
	const [status, setStatus] = useState<string>(sharedStatus || 'Ready')
	const [error, setError] = useState<string | null>(null)
	// Thinking indicator (bd polyglot-pdf-wpw.5): true while the agent is processing
	// a turn (user-turn-end -> first response audio), driven by the backend
	// agent_processing signal. Shows a calm animated indicator so the app never looks
	// frozen during a slow turn / secretary lookup.
	const [thinking, setThinking] = useState<boolean>(false)
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
	// Continuous-session mode (bd polyglot-pdf-x8rt): when on, the form is one
	// session with no sections to navigate -- the section-picker dropdown is hidden
	// so a user cannot trigger a manual section switch (which would reset the
	// session we deliberately keep open). Read from the persisted form state, which
	// handleSessionReady sets from the backend flag.
	const [continuousSession, setContinuousSession] = useState(false)
	const [isHoldingPushToTalk, setIsHoldingPushToTalk] = useState(false)
	const [isCollapsed, setIsCollapsed] = useState(false)
	// Live mic-energy meter (bd polyglot-pdf-s3zv). `micEnergy` is the worklet's
	// smoothed RMS (0-100); `micSending` is whether the most recent frame actually
	// passed the send gate (so the meter shows "sending" vs "mic alive but gated").
	// The worklet posts ~50x/sec; we stash the latest in a ref and flush to state on
	// an rAF loop so React re-renders at most once per frame, not 50x.
	const [micEnergy, setMicEnergy] = useState(0)
	const [micSending, setMicSending] = useState(false)
	const energyRef = useRef({ energy: 0, sending: false, lastFrameAt: 0 })
	// If initialLanguage is provided (from parent onboarding), use it and skip language modal
	const [selectedLanguage, setSelectedLanguage] = useState(initialLanguage || '')
	const [showLanguageModal, setShowLanguageModal] = useState(!initialLanguage)  // Skip if language pre-selected
	const [showDisclaimerModal, setShowDisclaimerModal] = useState(false)  // Track if disclaimer modal is showing
	// User dismissed the connection-timeout modal without reconnecting (bd
	// polyglot-pdf-jf6w.2). Reset whenever status leaves reconnect_failed so a
	// later terminal drop re-shows the modal.
	const [reconnectModalDismissed, setReconnectModalDismissed] = useState(false)
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
		console.log('[VoiceOverlay] [link] Using shared stream from parent:', !!sharedStream)
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

	// Live mic-energy meter subscription (bd polyglot-pdf-s3zv). Tap the worklet's
	// existing RMS stream via the audio manager; stash each frame in a ref (the
	// worklet fires ~50x/sec) and flush to React state on a rAF loop so the meter
	// animates without 50 re-renders/sec. If no frame has arrived for ~250ms the
	// mic is idle/gone, so we decay the bar to 0 -- a flat meter then reads as
	// "no audio reaching the backend", the diagnostic this feature is for.
	//
	// Only runs while CONNECTED (the meter is only rendered then): no point waking
	// every frame through the pre-connect language/disclaimer flow, paused/idle, or a
	// terminal reconnect-failure (Codex PR #203). The effect re-runs on `status`, so
	// it tears down the rAF + unsubscribes the moment we leave `connected`.
	useEffect(() => {
		// MUST match the listening-indicator gate (`isListening` below): the meter is
		// nested inside that badge, so it is only rendered while `connected*`. Waking
		// the rAF loop / holding the energy callback for `switching_section` or
		// `reconnecting` -- where the badge is hidden -- is per-frame work for an
		// element that cannot render (Codex PR #278 round 3).
		const s = status.toLowerCase()
		const meterVisible = s === 'connected' || s.startsWith('connected ')
		if (!meterVisible) return
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
			// `sending` from the worklet means the frame passed the audio-routing gate
			// (mode/PTT/VAD). But the chunk ALSO has to clear the CONNECTION send gate
			// before any bytes reach the backend. Ask the manager for the REAL gate
			// decision (shouldSendMicChunk over live status + socket state) rather than
			// re-deriving a partial copy from status -- that correctly counts the valid
			// `switching_section` + open-socket case as sending and excludes
			// `reconnecting` (Codex PR #203).
			const connectionSends = connectionManager?.isSendingMicAudio?.() ?? false
			const displaySending = stale ? false : (sending && connectionSends)
			// Functional updates + a small threshold so we don't thrash state when
			// the value is effectively unchanged.
			setMicEnergy(prev => (Math.abs(prev - displayEnergy) > 0.5 ? displayEnergy : prev))
			setMicSending(prev => (prev !== displaySending ? displaySending : prev))
			rafId = requestAnimationFrame(tick)
		}
		rafId = requestAnimationFrame(tick)

		return () => {
			cancelAnimationFrame(rafId)
			audioManager.setEnergyCallback?.(null)
		}
	}, [connectionManager, status])

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
		// Continuous-session mode is set on the persisted state by handleSessionReady.
		try {
			setContinuousSession(SchemaFormStateManager.load()?.continuousSessionEnabled === true)
		} catch {
			setContinuousSession(false)
		}
	}, [connectionManager, status])

	// Keep status ref updated
	useEffect(() => {
		statusRef.current = status
	}, [status])

	// Clear the connection-timeout-modal dismissal once the connection leaves the
	// terminal reconnect_failed state, so a later give-up re-shows the modal (bd
	// polyglot-pdf-jf6w.2).
	useEffect(() => {
		if (status.toLowerCase() !== 'reconnect_failed' && reconnectModalDismissed) {
			setReconnectModalDismissed(false)
		}
	}, [status, reconnectModalDismissed])

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

		console.log('[PTT Safety] [warn] Force-releasing PTT due to safety trigger')
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
		// Keep the ConnectionManager hold flag consistent with the mute we apply
		// here (bd polyglot-pdf-qt7w) -- a force-release ends the unmuted window.
		connectionManager?.setPushToTalkHeld(false)
		audioManager?.muteInput()
		audioManager?.resumePlayback()
	}

	// Safety mechanism 1: Max duration timeout (prevents infinite recording)
	useEffect(() => {
		if (isHoldingPushToTalk) {
			console.log('[PTT Safety] Starting safety timeout (max 60s)')
			pttSafetyTimeoutRef.current = window.setTimeout(() => {
				console.log('[PTT Safety] [warn] Max duration reached - force releasing')
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
				console.log('[PTT Safety] [warn] Tab hidden while recording - force releasing')
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
				console.log('[PTT Safety] [warn] Window lost focus while recording - force releasing')
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
			console.log('[PTT Safety] [warn] Connection lost while recording - force releasing')
			forceReleasePTT()
		}
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [status])

	// Safety mechanism 5: Cleanup on unmount
	useEffect(() => {
		return () => {
			if (isHoldingPushToTalkRef.current) {
				console.log('[PTT Safety] [warn] Component unmounting while recording - force releasing')
				// Direct cleanup since we're unmounting
				connectionManager?.sendActivityEnd()
				connectionManager?.setPushToTalkHeld(false)
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
			const speechDetectedTime = performance.now()
			speechStartTimeRef.current = Date.now()
			bargeInTriggeredRef.current = false  // Reset flag
			console.log(`[VFF VAD] [mic] Speech detected at t=${speechDetectedTime.toFixed(2)}ms`)

			// INSTANT FEEDBACK: Pause audio immediately if Gemini is speaking
			// This gives instant barge-in feel while we wait to confirm speech duration
			const audioManager = connectionManager?.getAudioManager()
			if (audioManager && audioManager.isSpeaking()) {
				audioManager.pauseAudioContext()
				console.log(`[VFF VAD] [mute] Tentative pause at t=${performance.now().toFixed(2)}ms - waiting to confirm speech duration`)
			}
			// Schedule delayed turn start - only send activity_start + audio if speech lasts >=450ms
			// This prevents false positives (throat clears, grunts) from creating incomplete turns
			setTimeout(() => {
				const speechDuration = speechStartTimeRef.current
					? Date.now() - speechStartTimeRef.current
					: 0

				// Only start turn if speech is still active AND duration met
				if (speechStartTimeRef.current !== null && speechDuration >= MIN_TURN_DURATION_MS) {
					console.log(`[VFF VAD] [OK] Valid speech detected (${speechDuration}ms) - starting turn`)
					bargeInTriggeredRef.current = true

					// CRITICAL: Send activity_start BEFORE opening audio gate
					// This ensures Gemini receives the turn signal before any audio chunks
					// Pattern: activity_start -> audio chunks -> activity_end (Gemini Live API docs lines 419-435)
					if (connectionManager) {
						const startTime = performance.now()
						connectionManager.sendActivityStart()
						console.log(`[VFF VAD] [send] Sent activity_start signal at t=${startTime.toFixed(2)}ms (user turn begins)`)
					}

					// Privacy Gate: Open audio flow (sends pre-buffer + live audio)
					// Must happen AFTER activity_start to ensure proper turn framing
					if (audioManager) {
						const gateOpenTime = performance.now()
						console.log(`[VFF VAD] [door] Opening audio gate at t=${gateOpenTime.toFixed(2)}ms`)
						audioManager.setVADActive(true) // Opens gate, flushes 600ms pre-buffer to backend
						console.log(`[VFF VAD] [door] Audio gate opened, pre-buffer flushed, live audio now flowing`)
					}

					// Trigger FULL barge-in (flushes audio queue if Gemini speaking)
					const geminiSpeaking = audioManager?.isSpeaking()
					if (geminiSpeaking && audioManager) {
						console.log('[VFF VAD] [mute] Flushing Gemini audio queue (full barge-in)')
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
				console.log(`[VFF VAD] [OK] Valid turn completed (${speechDuration}ms) - closing turn`)

				// Close audio gate
				if (audioManager) {
					audioManager.setVADActive(false) // Closes gate, stops audio flow
				}

				// Send activity_end to signal user is done speaking
				connectionManager?.onVADSpeechEnd()
			} else {
				console.log(`[VFF VAD] [warn] Speech too short (${speechDuration}ms < ${MIN_TURN_DURATION_MS}ms) - no turn started, false positive`)

				// FALSE POSITIVE: Resume audio playback (speech was too short to start a turn)
				// Gate was never opened, so nothing to close
				if (audioManager) {
					audioManager.resumeAudioContext()
					console.log('[VFF VAD] [sound] Resuming audio - false positive')
				}
			}
			// Clear state
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

	// Adopt the shared connection manager on mount (bd polyglot-pdf-d0k). This
	// overlay never creates its own ConnectionManager: all connections must carry
	// an auth token (Google retired the tokenless Live API path), and the parent
	// (SchemaForm.tsx) is the only production render site, always supplying one.
	useEffect(() => {
		connectionManagerRef.current = sharedConnectionManager
		setConnectionManager(sharedConnectionManager)
	}, [sharedConnectionManager])
	// Sync status from shared prop
	useEffect(() => {
		if (sharedStatus !== undefined) {
			setStatus(sharedStatus)
		}
	}, [sharedStatus])
	// Sync thinking from shared prop (bd polyglot-pdf-wpw.5): when the parent owns the
	// ConnectionManager it drives the indicator; mirror it into local state.
	useEffect(() => {
		if (sharedThinking !== undefined) {
			setThinking(sharedThinking)
		}
	}, [sharedThinking])

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
			console.log('[VoiceOverlay] [OK] Connection ready - requesting disclaimer read')

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
			console.log('[VoiceOverlay] [mic] Starting VAD (conditions met)')
			vad.start()
		} else if (!shouldRunVAD && vad.userSpeaking) {
			console.log('[VoiceOverlay] [pause] Pausing VAD (conditions not met)')
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
					console.log('[VoiceOverlay] [OK] WebSocket connected, setting up audio...')
					// Update status to indicate audio setup in progress
					setStatus('Setting up audio...')

					// Start recording (this completes the connection)
					await connectionManager.startRecording()

					// Now fully connected - update status
					setStatus('connected')
					console.log('[VoiceOverlay] [OK] Audio ready - fully connected')
					// FIX #2: VAD will auto-start via consolidated useEffect when status changes
					break
				}

				// Wait 50ms before checking again
				await new Promise(resolve => setTimeout(resolve, 50))
			}

			// Check final status
			const finalStatus = connectionManager.getStatus()
			if (finalStatus !== 'connected' && finalStatus !== 'switching_section') {
				console.error('[VoiceOverlay] [X] Connection timeout, final status:', finalStatus)
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
		// A mode toggle ends any notion of an active hold; clear the hold flag so it
		// can never go stale-true across the mode change (bd polyglot-pdf-qt7w). Both
		// branches below re-apply the correct mute/unmute for the new mode.
		connectionManager?.setPushToTalkHeld(false)

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
		// Record the hold in the ConnectionManager (bd polyglot-pdf-qt7w) so a
		// reconnect that arms a FRESH mic mid-hold does not re-mute the user. Cleared
		// in the release timeout, right before the actual muteInput() below.
		connectionManager?.setPushToTalkHeld(true)
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
		// Clear the hold flag SYNCHRONOUSLY at release, not inside the deferred
		// timeout below (bd polyglot-pdf-qt7w). The flag drives whether a fresh-arm
		// reconnect leaves the mic unmuted; once the user has RELEASED, a reconnect
		// should apply the resting mute even mid-grace-window. Clearing it here (vs in
		// the timeout) also means an unmount during the 500ms window -- which CANCELS
		// that timeout, e.g. the desktop<->mobile resize flip -- cannot leave the flag
		// stale-true on the shared ConnectionManager.
		connectionManager?.setPushToTalkHeld(false)

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
			// (Hold flag was already cleared synchronously at release above -- bd
			// polyglot-pdf-qt7w; this timeout only handles the deferred mute.)
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
		console.log('[PTT Keyboard] [OK] Keyboard listeners attached')

		return () => {
			console.log('[PTT Keyboard] [X] Removing keyboard listeners')
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
		console.log('[PTT Global] [OK] Global mouse/touch release listeners attached')

		return () => {
			console.log('[PTT Global] [X] Removing global mouse/touch release listeners')
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
				console.log('[VoiceOverlay] [OK] Disclaimer acceptance logged to backend:', result)
			} else {
				console.warn('[VoiceOverlay] [warn] Backend logging returned non-OK status:', response.status)
			}
		} catch (err) {
			console.error('[VoiceOverlay] [X] Failed to log disclaimer acceptance to backend:', err)
			// Don't block user - logging failure is non-fatal
		}

		// Check if connection is still active - the long disclaimer read may have caused
		// the connection to go stale (idle timeout or disconnected)
		const currentStatus = connectionManager?.getStatus()
		const isConnectionActive = currentStatus === 'connected' || currentStatus === 'switching_section'

		let reconnected = false
		if (!isConnectionActive) {
			console.log('[VoiceOverlay] [reconnect] Connection stale after disclaimer - reconnecting...')
			console.log('[VoiceOverlay] Current status:', currentStatus)

			try {
				// Reconnect to backend
				await handleConnect()
				// handleConnect() does not throw on timeout -- it calls setError and returns
				// normally. Re-check status so a silent timeout does not fall through to
				// switchToFirstSection on a dead connection (bd polyglot-pdf-ppf1).
				const postReconnectStatus = connectionManager?.getStatus()
				if (postReconnectStatus !== 'connected' && postReconnectStatus !== 'switching_section') {
					console.error('[VoiceOverlay] [X] Reconnect timed out, status:', postReconnectStatus)
					setError('Connection lost - please click Reconnect')
					return
				}
				reconnected = true
				console.log('[VoiceOverlay] [OK] Reconnected after disclaimer acceptance')
			} catch (err) {
				console.error('[VoiceOverlay] [X] Reconnection failed:', err)
				setError('Connection lost - please click Reconnect')
				return
			}
		}

		// Now switch to section 1 to restart Gemini with form-filling context (clean session, no disclaimer leakage)
		console.log('[VoiceOverlay] [OK] Disclaimer accepted - switching to first section (restarts Gemini session)')

		if (connectionManager && selectedLanguage) {
			// Step 3: Resume audio playback FIRST so we don't miss any response chunks
			const am = connectionManager.getAudioManager()
			if (am) {
				console.log('[VoiceOverlay] [sound] Resuming audio playback for Gemini response')
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
				console.log('[VoiceOverlay] [mic] Sending activity_end to signal user turn complete')
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
	// Listening indicator (bd polyglot-pdf-1dvp): show ONLY when mic audio is
	// actually reaching the backend -- i.e. a steady `connected` session. We
	// deliberately do NOT include the transient turn-taking states:
	//   - `reconnecting`: `isConnected` stays true for the status dot, but the mic
	//     gate (shouldSendMicChunk) drops all audio, so a "listening" cue there is
	//     misleading (Codex PR #278);
	//   - `switching_section`: the AI-initiated swap keeps the socket up, but the
	//     reconnecting `startSection()` path sets `switching_section` BEFORE it
	//     closes + reopens the socket, so audio can be dropped in that sub-second
	//     window; rather than a fragile per-render socket probe, we just hide the
	//     cue during the switch (briefly not showing "listening" mid-switch is
	//     harmless and honest -- Codex PR #278 round 3).
	// This keeps the gate a pure, reactive function of `status` and lets the
	// mic-energy meter effect below share the exact same visibility condition.
	const isListening = status.toLowerCase() === 'connected' || status.toLowerCase().startsWith('connected ')
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
						{/* Thinking indicator (bd polyglot-pdf-wpw.5): calm animated dots
						    while the agent processes a turn, so the app never looks frozen
						    during a slow turn / secretary lookup. Language-neutral (no word
						    to translate across the 18 spoken languages). */}
						{thinking && isConnected && (
							<span className="vff-thinking-indicator" title="Working..." aria-label="Working" role="status">
								<span className="vff-thinking-dot"></span>
								<span className="vff-thinking-dot"></span>
								<span className="vff-thinking-dot"></span>
							</span>
						)}
						{/* Listening indicator (bd polyglot-pdf-1dvp): an ear glyph paired
						    with the live mic-energy meter. Shown ONLY while connected (i.e.
						    actually listening) -- hidden when paused/disconnected, which
						    fixes the old reversed badge that lit "Listening" precisely when
						    it was NOT. Language-neutral: the ear glyph replaces the English
						    word so it reads the same across all 18 spoken languages. The
						    meter still distinguishes mic-alive-but-gated (grey bar) from
						    audio-reaching-the-backend (green, --sending). Gated on
						    `isListening` (send-capable states) not `isConnected`, so it
						    stays hidden while reconnecting. */}
						{isListening && (
							<span
								className={`vff-listening${micSending ? ' vff-listening--sending' : ''}`}
								title={micSending
									? `Listening -- sending audio (energy ${micEnergy.toFixed(0)})`
									: `Listening -- mic active, not sending (energy ${micEnergy.toFixed(0)})`}
								aria-label="Listening"
								role="status"
							>
								{/* Ear glyph via an ASCII-safe Unicode escape (U+1F442) so the
								    .tsx source stays ASCII per AGENTS.md; it still renders the ear
								    emoji at runtime. Language-neutral -- no word to translate. */}
								<span className="vff-listening-ear" aria-hidden="true">{'\u{1F442}'}</span>
								<span className="vff-mic-meter">
									<span
										className="vff-mic-meter-bar"
										style={{ width: `${Math.min(100, micEnergy)}%` }}
									></span>
								</span>
							</span>
						)}
					</div>


					{/* Section Navigation. In continuous-session mode (bd polyglot-pdf-x8rt)
					    there are no sections to navigate -- render the label + field
					    counter but NOT the clickable dropdown, so a manual section switch
					    (which would reset the one continuous session) is unreachable. */}
					<div className="vff-section-nav">
						<div
							className="vff-section-display"
							onClick={continuousSession ? undefined : () => setShowSectionDropdown(!showSectionDropdown)}
							style={continuousSession ? { cursor: 'default' } : undefined}
						>
							<span className="vff-section-label">
								{getCurrentSectionLabel()}
							</span>
							{!continuousSession && (
								<span className="vff-dropdown-arrow">{showSectionDropdown ? '▲' : '▼'}</span>
							)}
						</div>
						<div className="vff-field-counter">
							📊 {sectionFieldCount.filled} of {sectionFieldCount.total} fields completed
						</div>
						{!continuousSession && showSectionDropdown && (
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
						{/* Connection is automatic after language selection - no connect button needed.
						    The Reconnect button covers both the idle timeout AND a generic
						    "disconnected" drop: the latter sets the "please click Reconnect"
						    error, so it must offer a button to click (bd polyglot-pdf-b2yj). */}
						{status === 'idle_timeout' || status === 'disconnected' ? (
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
				/* Listening indicator (bd polyglot-pdf-1dvp): ear glyph + live
				   mic-energy meter, shown only while connected. Language-neutral. */
				.vff-listening {
					display: inline-flex;
					align-items: center;
					gap: 6px;
					padding: 4px 10px;
					background: #f3f4f6;
					border-radius: 12px;
					border: 1px solid #d1d5db;
					transition: background 120ms ease, border-color 120ms ease;
				}

				.vff-listening--sending {
					background: #d1fae5;
					border-color: #10b981;
				}

				.vff-listening-ear {
					font-size: 14px;
					line-height: 1;
				}

				/* Thinking indicator (bd polyglot-pdf-wpw.5): three calm pulsing dots
				   shown while the agent processes a turn. Deliberately neutral/quiet
				   (slate, slow pulse) -- it shows on every turn, so it must not alarm. */
				.vff-thinking-indicator {
					display: inline-flex;
					align-items: center;
					gap: 4px;
					padding: 4px 10px;
				}

				.vff-thinking-dot {
					display: inline-block;
					width: 6px;
					height: 6px;
					border-radius: 50%;
					background: #94a3b8;
					animation: vff-thinking-pulse 1.4s ease-in-out infinite;
				}

				.vff-thinking-dot:nth-child(2) { animation-delay: 0.2s; }
				.vff-thinking-dot:nth-child(3) { animation-delay: 0.4s; }

				@keyframes vff-thinking-pulse {
					0%, 80%, 100% { opacity: 0.3; transform: scale(0.85); }
					40% { opacity: 1; transform: scale(1); }
				}

				/* Live mic-energy meter (bd polyglot-pdf-s3zv) */
				.vff-mic-meter {
					display: inline-block;
					width: 48px;
					height: 8px;
					border-radius: 4px;
					background: #e5e7eb;
					overflow: hidden;
					flex-shrink: 0;
				}

				.vff-mic-meter-bar {
					display: block;
					height: 100%;
					width: 0%;
					border-radius: 4px;
					/* Grey when the mic is alive but the frame is gated (muted PTT /
					   idle VAD / silence) -- a moving grey bar still proves the mic
					   works; green only when frames actually reach the backend. */
					background: #9ca3af;
					transition: width 80ms linear, background 120ms ease;
				}

				.vff-listening--sending .vff-mic-meter-bar {
					background: #10b981;
					box-shadow: 0 0 6px rgba(16, 185, 129, 0.6);
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

			{/* Connection-timeout modal - shown on terminal reconnect failure (bd
			    polyglot-pdf-jf6w.2). The reconnect button re-runs the existing
			    connect/restore path; vmxx silent-resume picks up the current field. */}
			<ConnectionTimeoutModal
				isOpen={status.toLowerCase() === 'reconnect_failed' && !reconnectModalDismissed}
				selectedLanguage={selectedLanguage}
				onReconnect={() => { setReconnectModalDismissed(false); handleConnect() }}
				onCancel={() => setReconnectModalDismissed(true)}
			/>
		</>
	)
}
