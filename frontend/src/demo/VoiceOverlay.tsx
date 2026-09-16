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

import React, { useCallback, useEffect, useRef, useState, useMemo } from 'react'
import type { ConnectionManager, VoiceMode } from '../shared/connection'
import { SchemaFormStateManager } from '../schema-forms/state/schemaFormState'
import type { FormSchema } from '../schema-forms/types/schema'
import { useDemoVAD } from './useDemoVAD'
import { SPOKEN_LANGUAGES } from '../shared/languages'
import { DisclaimerModal, DISCLAIMER_TRANSLATIONS } from '../schema-forms/components/DisclaimerModal'
import { getOverlayStrings, formatFieldsCompleted } from './overlayTranslations'
import { ConnectionTimeoutModal } from '../schema-forms/components/ConnectionTimeoutModal'
import { LanguageSelectionModal } from '../schema-forms/components/LanguageSelectionModal'
import { getBackendHttpUrl } from '../schema-forms/utils/pdfFiller'
import { SaveNudge } from '../schema-forms/components/SaveNudge'
import { ResumeUpload } from '../schema-forms/components/ResumeUpload'
import type { ResumeResult } from '../schema-forms/components/ResumeUpload'
import { applyResume } from '../schema-forms/applyResume'
import { loadOnboardingState } from '../schema-forms/onboardingStorage'
import { useSaveNudge } from '../schema-forms/useSaveNudge'
import {
	createNoticeSpeaker,
	NOTICE_SAVE_EARLY,
	NOTICE_VOICE_ENDING,
} from '../schema-forms/utils/noticeSpeech'
import { hasClientLinkToken } from '../shared/sessionCredential'
import { Sol, SOL_CSS, SOL_PLACEMENT_CSS } from '../shared/Sol'
import { deriveSolState } from '../shared/solState'
import { useGeminiSpeaking, useClipPlaying } from '../shared/useGeminiSpeaking'
import { isIntroClipEnabled } from '../shared/config'
import { createIntroPlayer, type IntroPlayer } from '../shared/introPlayer'
import { renderIntroParagraphs } from '../shared/introScript'
import { BUTTON_TRANSLATIONS } from '../schema-forms/components/DisclaimerModal'

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
	/**
	 * Auth token accessor for Sol's intro clip (bd polyglot-pdf-s1iex.5). The
	 * clip is fetched BEFORE any WebSocket exists, so it cannot borrow the
	 * connection's token plumbing; SchemaForm already builds this from the
	 * Firebase user for the manager, and passes the same function down here
	 * rather than a second auth path being invented in the overlay.
	 */
	getToken?: () => Promise<string | undefined>
}

export function VoiceOverlay({ schema, wsUrl, onClose, connectionManager: sharedConnectionManager, status: sharedStatus, thinking: sharedThinking, sharedStream, streamError, initialLanguage, getToken }: VoiceOverlayProps) {
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
	// PTT is the ONLY input mode (bd polyglot-pdf-v1m8g), so this is a constant,
	// not a restored user choice -- the mode toggle that used to set it is gone.
	// Kept as state rather than inlined `true` because the PTT press/release
	// handlers and the audio gate still read it as the "is PTT active" predicate.
	const [pushToTalkMode] = useState(true)
	// Manual/voice mode (bd polyglot-pdf-wurj8) -- the sticky half of the two-control
	// voice UI. Seeded from the connection manager so a remount (e.g. a
	// desktop<->mobile breakpoint flip onto a LIVE session) restores the user's real
	// choice instead of silently putting them back into voice mode. Feature-detected:
	// tests and older mocks supply a partial manager.
	const [voiceMode, setVoiceModeState] = useState<VoiceMode>(() =>
		typeof connectionManager?.getVoiceMode === 'function' ? connectionManager.getVoiceMode() : 'voice'
	)
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

	// --- Sol's scripted intro clip (bd polyglot-pdf-s1iex.5) -----------------
	// Flag-gated and read ONCE per mount: a flag that flipped mid-session would
	// otherwise strand the modal between two text sources.
	const introEnabled = useMemo(() => isIntroClipEnabled(), [])
	const [introClipState, setIntroClipState] =
		useState<'idle' | 'loading' | 'playing' | 'blocked'>('idle')
	// The player owns a blob cache, so it must outlive re-renders. It lives HERE
	// rather than in the ConnectionManager because the clip plays before any
	// connection exists.
	const introPlayerRef = useRef<IntroPlayer | null>(null)
	if (introEnabled && !introPlayerRef.current) {
		introPlayerRef.current = createIntroPlayer({
			getAudioManager: () => sharedConnectionManager?.getAudioManager?.() ?? null,
			getHttpBase: getBackendHttpUrl,
			getToken,
			onFetchStart: () => setIntroClipState('loading'),
		})
	}
	// The bounded form KEY the intro route validates against its own table --
	// never caller text (the keyed-route contract, bd s1iex.3).
	const introFormNumber = schema.form_metadata?.form_number || ''

	const playIntroClip = React.useCallback(async () => {
		const player = introPlayerRef.current
		if (!player || !selectedLanguage || !introFormNumber) return
		// A cache hit starts instantly; a cold fetch shows 'loading' until
		// onFetchStart -> playback flips it. Either way the state is honest
		// about whether audio is audible YET.
		setIntroClipState(player.isCached(selectedLanguage, introFormNumber)
			? 'playing' : 'loading')
		const started = player.play(selectedLanguage, introFormNumber)
		// Once the fetch resolves and play() is called, the player reports
		// isPlaying(); reflect that so the button leaves its disabled state.
		const flip = setInterval(() => {
			if (player.isPlaying()) {
				setIntroClipState('playing')
				clearInterval(flip)
			}
		}, 200)
		const result = await started
		clearInterval(flip)
		if (result.status === 'blocked') {
			// Autoplay refused -- the modal offers the button as tap-to-play.
			setIntroClipState('blocked')
		} else if (result.status !== 'stopped') {
			setIntroClipState('idle')
		}
		// 'stopped' means Agree/teardown took over; that path owns the state.
	}, [selectedLanguage, introFormNumber])

	// Release cached blobs on unmount.
	useEffect(() => () => { introPlayerRef.current?.dispose() }, [])

	// Panel UI copy in the session language (bd polyglot-pdf-ibxz); English fallback.
	// SAVE NUDGE WIRING (bd polyglot-pdf-dft1).
	//
	// CLIENT SESSIONS ONLY. Staff work on their own machines with their own
	// workflow; the nudge exists because a CLIENT's only copy is the file they
	// save, and browser form state is discarded after 60 minutes.
	const isClientSession = hasClientLinkToken()
	const formState = SchemaFormStateManager.load()
	const saveNudge = useSaveNudge({
		formSessionId: formState?.formSessionId,
		completedSectionCount: completedSections.size,
		// The nudge fires when voice is ENDING for any reason -- the spend
		// ceiling, an idle timeout, or the form finishing. All three are the last
		// moment before a client might close the tab.
		// budget_exhausted is listed EXPLICITLY (bd polyglot-pdf-cke6v). A spend
		// close used to land on reconnect_failed, so this fired; giving it its
		// own terminal status silently dropped the one case this comment names
		// first -- and a client link is exactly who needs the nudge, since the
		// file they save is their only copy.
		voiceEnding: status.toLowerCase() === 'idle_timeout'
			|| status.toLowerCase() === 'reconnect_failed'
			|| status.toLowerCase() === 'budget_exhausted',
		enabled: isClientSession,
	})

	// The notice speech route is FREE (require_auth, not the paid dependency),
	// so a budget-exhausted client still HEARS how to keep their work.
	const speakNotice = useMemo(() => {
		// getToken for the same reason: /api/tts/notice is auth-gated, so a
		// tokenless call is silent in every deployed environment.
		const speaker = createNoticeSpeaker({
			backendUrl: getBackendHttpUrl(),
			getToken,
		})
		return (text: string, language?: string) => speaker(
			text,
			language,
			saveNudge.variant === 'ending' ? NOTICE_VOICE_ENDING : NOTICE_SAVE_EARLY,
		)
	}, [saveNudge.variant, getToken])

	// EVERY connection-path error goes through here (bd polyglot-pdf-wwwa5,
	// widened after the Opus cross-surface review found my first fix covered 2
	// of 6 sites). On a spent link the translated spend-ceiling modal is
	// already on screen saying voice has finished; an English "please try
	// again" / "please click Reconnect" behind it contradicts that AND names a
	// button bd cke6v deliberately removed. Suppressing CENTRALLY means a
	// connection error added later inherits the behavior instead of becoming
	// the seventh site -- pin the set, not the instances.
	const setConnectionError = useCallback((message: string) => {
		// Feature-detect getStatus, do not just null-check the manager: `?.`
		// guards against null/undefined but NOT against an object that lacks
		// the method, and several tests pass a partial ConnectionManager mock.
		// CI caught this as a TypeError while my local run stayed green (a
		// separate flake had shuffled the file ordering). Suppression is a
		// nice-to-have; THROWING here would break the error path itself, which
		// is strictly worse than showing one redundant message.
		if (typeof connectionManager?.getStatus === 'function'
			&& connectionManager.getStatus() === 'budget_exhausted') {
			console.log('[VoiceOverlay] Suppressing connection error on a spent link:', message)
			return
		}
		setError(message)
	}, [connectionManager])

	const handleNudgeSave = useCallback(() => {
		saveNudge.markSaved()
		// Hand off to the form's own download, which is what stamps the resume
		// identity into the PDF. Dispatching rather than reaching across
		// components: the overlay does not own the fill/download path.
		window.dispatchEvent(new CustomEvent('polyglot:save-form'))
	}, [saveNudge])

	// RESUME CHOICE (bd polyglot-pdf-dft1). Offered BEFORE the disclaimer: a
	// client resuming should pick "continue my saved form" first and THEN agree,
	// so the acceptance record belongs to the session they are actually about to
	// work in.
	//
	// Client sessions only, and only when they have not already started -- a
	// client mid-form does not need a start-over prompt in their way.
	const [resumeDismissed, setResumeDismissed] = useState(false)
	const showResumeChoice = isClientSession
		&& !resumeDismissed
		&& !formState?.disclaimerAccepted
		&& Object.keys(formState?.fieldValues ?? {}).length === 0

	const handleResumed = useCallback((result: ResumeResult) => {
		const current = SchemaFormStateManager.load()
		if (current) {
			// applyResume clears disclaimerAccepted on purpose, so the modal below
			// opens next and the client agrees for THIS session.
			SchemaFormStateManager.save(applyResume(current, result))
		}
		setResumeDismissed(true)
	}, [])

	const overlayText = getOverlayStrings(selectedLanguage)
	const [showLanguageModal, setShowLanguageModal] = useState(!initialLanguage)  // Skip if language pre-selected
	const [showDisclaimerModal, setShowDisclaimerModal] = useState(false)
	// Start the clip when the modal becomes visible -- ONE trigger for all
	// three sites that open it (first language pick, a desktop<->mobile flip
	// onto a live session, and a soft-refresh resume), so a new open site
	// cannot forget to start the audio. The ref guard fires it once per
	// opening rather than on every re-render.
	const introStartedRef = useRef(false)
	useEffect(() => {
		if (!introEnabled) return
		if (!showDisclaimerModal) {
			introStartedRef.current = false
			return
		}
		if (introStartedRef.current) return
		if (!selectedLanguage || !introFormNumber) return
		introStartedRef.current = true
		void playIntroClip()
	}, [introEnabled, showDisclaimerModal, selectedLanguage, introFormNumber, playIntroClip])  // Track if disclaimer modal is showing
	// User dismissed the connection-timeout modal without reconnecting (bd
	// polyglot-pdf-jf6w.2). Reset whenever status leaves reconnect_failed so a
	// later terminal drop re-shows the modal.
	const [reconnectModalDismissed, setReconnectModalDismissed] = useState(false)
	// The spend-ceiling notice is TERMINAL, so unlike reconnectModalDismissed
	// this is never reset -- no later state should bring it back (bd
	// polyglot-pdf-cke6v). It exists so the client can get past a full-viewport
	// overlay to the typing and printing its own message promises they can do.
	const [budgetModalDismissed, setBudgetModalDismissed] = useState(false)
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
		// Continuous mode fills the WHOLE form as one session; currentSectionId is
		// pinned to the first section (bd polyglot-pdf-944q), so a section label
		// would misleadingly show only section 1. Show the form title instead.
		if (continuousSession) {
			return schema.form_metadata?.title || 'Full Form'
		}
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
			// On a SOFT PAGE REFRESH mid-session the disclaimer may ALREADY have
			// been accepted (it is persisted in schema_form_state). Re-showing it
			// while the resumed voice session is already speaking mid-section is
			// the "disclaimer re-shows while Gemini talks" desync
			// (bd polyglot-pdf-fn1m). So gate the disclaimer step on
			// disclaimerAccepted here, mirroring the alreadyLive branch above and
			// the initial language-selection handler: reconnect either way (to resume the session),
			// but only surface the agree step when it has NOT been accepted.
			const alreadyAccepted = SchemaFormStateManager.load()?.disclaimerAccepted

			// INTRO PATH (bd polyglot-pdf-s1iex.6): with the clip flag ON and the
			// disclaimer NOT yet accepted, do NOT connect here. Sol's clip needs no
			// Live session, and Agree becomes the first and ONLY handshake -- which
			// is what deletes the teardown/re-handshake seam.
			//
			// The `alreadyAccepted` branch STILL connects at mount, deliberately: a
			// reload user never sees Agree, so removing the mount connect wholesale
			// would leave them with no session at all (the plan calls this out
			// explicitly).
			if (introEnabled && !alreadyAccepted) {
				console.log('[VoiceOverlay] Intro clip enabled - deferring connect to Agree')
				setShowDisclaimerModal(true)
				return
			}

			// Trigger the same flow as handleInitialLanguageSelect
			const triggerDisclaimerFlow = async () => {
				try {
					if (!alreadyAccepted) {
						setPendingDisclaimerRead(true)
					}
					await handleConnect()
					if (!alreadyAccepted) {
						setShowDisclaimerModal(true)
					} else {
						console.log('[VoiceOverlay] Soft-refresh resume (disclaimer already accepted) - reconnecting without re-showing the agree step')
					}
				} catch (err) {
					console.error('[VoiceOverlay] Failed to connect after pre-selected language:', err)
					setConnectionError(err instanceof Error ? err.message : 'Connection failed')
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
	// PTT is the only input mode (bd polyglot-pdf-v1m8g): the mute/unmute here is
	// what decides which client bytes reach Gemini, and holding the button is the
	// turn signal itself.
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

	// Read the connected-session flags the UI keys on. (This used to also learn
	// the backend's VAD mode; that mode is gone -- bd polyglot-pdf-v1m8g -- so
	// push-to-talk is unconditional and there is nothing to learn.)
	useEffect(() => {
		if (!connectionManager) {
			return
		}
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
			// DELIBERATELY isSpeaking(), NOT isModelSpeaking (bd polyglot-pdf-uxc6s):
			// this is the SUSPEND half of the deadlock pair. A clip now lives INSIDE
			// the playback context, so suspending while one plays would cut it
			// mid-word and onVADSpeechEnd would never resume it. Clip-suppression
			// is the correct behavior here.
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

					// Trigger FULL barge-in (flushes audio queue if Gemini speaking).
					// isModelSpeaking, not isSpeaking (bd polyglot-pdf-uxc6s): during a
					// model-PCM + clip OVERLAP isSpeaking() reads false, so this flush
					// was skipped while the model talked over the user.
					const geminiSpeaking = audioManager?.isModelSpeaking()
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
		// INTRO PATH (bd polyglot-pdf-s1iex.5): Sol's scripted clip IS the
		// disclaimer read, so the legacy model-read must not also fire -- two
		// voices reading two different texts over each other. Guarded HERE, at
		// the single choke point every pendingDisclaimerRead path flows
		// through, rather than at each setPendingDisclaimerRead(true) site
		// (there are three per overlay; guarding the sites is the miss the
		// cross-surface review caught). Clear the flag so it cannot fire later.
		if (introEnabled) {
			if (pendingDisclaimerRead) setPendingDisclaimerRead(false)
			return
		}

		const isConnected = status.toLowerCase() === 'connected' || status.toLowerCase().startsWith('connected ')

		if (isConnected && pendingDisclaimerRead && connectionManager && selectedLanguage) {
			console.log('[VoiceOverlay] [OK] Connection ready - requesting disclaimer read')

			// Clear the flag IMMEDIATELY to prevent double-firing
			setPendingDisclaimerRead(false)

			// Send read_disclaimer message to backend using the proven language change pattern
			// ONE SOURCE (bd polyglot-pdf-nsb4y): the model reads the SAME
			// paragraphs the modal renders, joined. It used to read
			// DISCLAIMER_TRANSLATIONS.fullText, which carries only "we strongly
			// advise" -- while the modal (and Sol's clip) carry "you agree to
			// review". Same Agree button, two legal registers, decided by
			// whether the user listened or read. The heading is NOT script.
			const disclaimerText = renderIntroParagraphs(
				selectedLanguage,
				introFormNumber,
				(BUTTON_TRANSLATIONS[selectedLanguage] || BUTTON_TRANSLATIONS['English']).agree,
			).join(' ')
			connectionManager.readDisclaimer(selectedLanguage, disclaimerText)
		}
	}, [introEnabled, status, pendingDisclaimerRead, connectionManager, selectedLanguage])

	// FIX #2: SINGLE SOURCE OF TRUTH for VAD state management
	// This replaces 3 separate code paths with one consolidated control flow
	useEffect(() => {
		const isConnected = status.toLowerCase() === 'connected' ||
			status.toLowerCase().startsWith('connected ')

		// Client Silero VAD runs only when PTT is off -- which, since PTT is now the
		// ONLY input mode (bd polyglot-pdf-v1m8g), means never in practice. The
		// condition is kept rather than hardcoded false so the pause() branch below
		// still fires if a VAD session were somehow live across the cutover; the
		// hook itself is retired separately (bd polyglot-pdf-ggdpn).
		const shouldRunVAD = isConnected && !pushToTalkMode && !vad.loading && !vad.errored

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
	}, [status, pushToTalkMode, vad.loading, vad.errored, vad.userSpeaking])

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

				// A TERMINAL status will never become 'connected', so stop waiting
				// (bd polyglot-pdf-wwwa5). The backend ACCEPTS the socket before
				// closing it on a spent link, so connect() resolves and this loop
				// would otherwise burn its full 5s against an already-decided
				// outcome.
				if (currentStatus === 'budget_exhausted') {
					console.log('[VoiceOverlay] Link spend ceiling reached -- not waiting for connect')
					break
				}

				// Wait 50ms before checking again
				await new Promise(resolve => setTimeout(resolve, 50))
			}

			// Check final status
			const finalStatus = connectionManager.getStatus()
			if (finalStatus !== 'connected' && finalStatus !== 'switching_section') {
				console.error('[VoiceOverlay] [X] Connection timeout, final status:', finalStatus)
				setConnectionError('Connection timed out - please try again')
			}
		} catch (err) {
			console.error('[VoiceOverlay] Connection error:', err)
			setConnectionError(err instanceof Error ? err.message : 'Connection failed')
			// Set the union status 'error', NOT a freeform 'Connection failed'
			// string (bd polyglot-pdf-m77y): the freeform value matches no arm of
			// the controls ternary, so a RE-failed Reconnect (both backends still
			// down) would fall back to no button -- the same dead end this bead
			// fixes -- and only recover via the parent prop-sync effect winning a
			// render race. 'error' is a real ConnectionStatus, so the Reconnect
			// button renders deterministically. The failure message reaches the
			// user via setConnectionError above -- except on a spent link, where
			// the spend-ceiling modal is the single explanation. (The mobile
			// overlay's catch never set a status here, so it was already immune;
			// this aligns desktop with it.)
			//
			// NOT ON A SPENT LINK (bd polyglot-pdf-wwwa5). budget_exhausted is
			// TERMINAL, and FOUR surfaces key off it: the spend-ceiling modal,
			// the save nudge's voiceEnding gate (level-triggered, so an
			// already-showing nudge would vanish), and the controls ternary,
			// which renders Reconnect for 'error' -- plus solState.isOffline, which makes Sol LEAVE rather than dim. Overwriting the status here
			// retracts the correct UI and restores the dead button this work
			// removed -- and the parent cannot repair it, because its sync effect
			// keys on [sharedStatus], which never changes. Suppressing the error
			// TEXT while still writing this status was the incomplete half.
			// Feature-detect (see setConnectionError): `?.` does not protect
			// against a partial mock that lacks getStatus, and a throw here would
			// break the error path itself. Unknown status -> set 'error', the
			// pre-bead behavior, which is the safe fallback.
			const statusNow = typeof connectionManager?.getStatus === 'function'
				? connectionManager.getStatus()
				: undefined
			if (statusNow !== 'budget_exhausted') {
				setStatus('error')
			}
		}
	}


	// Keep the toggle honest (bd polyglot-pdf-wurj8). The mode changes WITHOUT a
	// click: a PTT press auto-leaves manual mode. Without this the button would go
	// on showing "quiet" while the assistant is live and about to speak -- the
	// control's one job is telling the user at a glance whether they will be
	// spoken to, and a stale label defeats exactly that.
	//
	// Re-reads on subscribe as well, to close the window between the mount-time
	// initializer and this effect running.
	useEffect(() => {
		if (!connectionManager) return
		if (typeof connectionManager.getVoiceMode === 'function') {
			setVoiceModeState(connectionManager.getVoiceMode())
		}
		if (typeof connectionManager.onVoiceModeChange !== 'function') return
		return connectionManager.onVoiceModeChange(setVoiceModeState)
	}, [connectionManager])

	// Manual/voice mode toggle (bd polyglot-pdf-wurj8). REPLACES the old Pause
	// button. The crucial difference: pause() suspended the session -- it tore the
	// mic down (user went mute, not merely deaf), discarded Gemini's in-flight
	// question client-side, and made coming back cost a paid re-ask. Manual mode
	// leaves the session live and the mic usable, and suppresses the model's
	// proactive speech AT THE BACKEND, so nothing is billed for speech nobody hears
	// and nothing has to be re-asked on the way back.
	//
	// The manager owns the authoritative mode (it survives a remount and is
	// re-asserted on every reconnect); this component mirrors it for rendering.
	const handleToggleVoiceMode = () => {
		if (!connectionManager) return
		const next: VoiceMode = voiceMode === 'voice' ? 'manual' : 'voice'
		// Feature-detect: a partial mock lacking the setter must not throw out of a
		// click handler and blank the overlay.
		if (typeof connectionManager.setVoiceMode === 'function') {
			connectionManager.setVoiceMode(next)
		}
		// Usually redundant -- the manager notifies its subscribers synchronously,
		// so the effect above has already set this to the same value. KEPT because
		// it is the only path that works for a manager without onVoiceModeChange
		// (an older or partial one), where nothing else would ever move the label.
		// Setting state to the value it already holds does not re-render.
		setVoiceModeState(next)
	}

	// FIX #2: Removed pendingVADStart useEffect - consolidated into single VAD control useEffect below

	// Handle push-to-talk mode toggle
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
		// synchronously in handlePushToTalkRelease (and force-release / unmount /
		// mode-toggle), never in a cancellable timeout.
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

		// Update field counter -- visible-field-aware (bd polyglot-pdf-kbkd): the
		// old raw schema.fields.length denominator counted statically-hidden and
		// unmet-show_if fields the user can never fill, capping the displayed
		// percentage below 100% on any kit with such fields; the old raw
		// fieldValues key scan independently counted stale values left on
		// fields that are no longer visible. getProgressCounts shares the SAME
		// visible-field filter the progress bar itself uses.
		setSectionFieldCount(SchemaFormStateManager.getProgressCounts(state))
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, []) // Only run once on mount, not when schema changes

	// Poll field count AND section state (updates as AI switches sections)
	useEffect(() => {
		const interval = setInterval(() => {
			const state = SchemaFormStateManager.load()
			if (state) {
				// Visible-field-aware (bd polyglot-pdf-kbkd) -- see the mount effect
				// above for why raw schema.fields.length / raw fieldValues scans
				// undercounted the denominator and could inflate the numerator.
				setSectionFieldCount(SchemaFormStateManager.getProgressCounts(state))

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

		// INTRO PATH (bd polyglot-pdf-s1iex.6): show the modal WITHOUT connecting.
		// Sol's clip plays against no Live session, and Agree makes the first and
		// only handshake. This is the second of the two connect-before-Agree sites
		// (the other is the mount effect); both must defer or the seam survives.
		if (introEnabled) {
			console.log('[VoiceOverlay] Intro clip enabled - showing modal without connecting')
			setShowDisclaimerModal(true)
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
			setConnectionError(err instanceof Error ? err.message : 'Connection failed')
			setPendingDisclaimerRead(false) // Clear flag on error
		}
	}

	// NOTE: there is deliberately NO mid-session language change here.
	// The spoken language is PINNED for the whole form -- chosen once in
	// LanguageSelectionModal (handleInitialLanguageSelect above), carried into the
	// Gemini config + system instruction at session start, and held for every turn.
	// The only way to change it is a NEW session: 'clear form', then pick again in
	// the modal. A handleLanguageChange() that swapped the language on a live
	// session used to sit here, wired to nothing; it was removed rather than left
	// as a trap, because its presence implied a supported flow that does not exist
	// (bd polyglot-pdf-87a9). See docs/standards/voice-and-vad.md.

	// Handle "Listen Again" button in disclaimer modal
	const handleDisclaimerListenAgain = () => {
		// INTRO PATH (bd polyglot-pdf-s1iex.5): replay the CACHED blob --
		// instant, no network round trip, and provably the same audio the user
		// just heard. This is also the tap-to-play control when autoplay was
		// refused, so it must work from a plain click with no session.
		if (introEnabled) {
			console.log('[VoiceOverlay] Replaying intro clip')
			void playIntroClip()
			return
		}

		if (!connectionManager || !selectedLanguage) return

		console.log('[VoiceOverlay] User requested disclaimer re-read')

		// Send read_disclaimer message using the same proven pattern
		// ONE SOURCE (bd polyglot-pdf-nsb4y): the model reads the SAME
		// paragraphs the modal renders, joined. It used to read
		// DISCLAIMER_TRANSLATIONS.fullText, which carries only "we strongly
		// advise" -- while the modal (and Sol's clip) carry "you agree to
		// review". Same Agree button, two legal registers, decided by
		// whether the user listened or read. The heading is NOT script.
		const disclaimerText = renderIntroParagraphs(
			selectedLanguage,
			introFormNumber,
			(BUTTON_TRANSLATIONS[selectedLanguage] || BUTTON_TRANSLATIONS['English']).agree,
		).join(' ')
		connectionManager.readDisclaimer(selectedLanguage, disclaimerText)
	}

	// Handle "I Agree" button in disclaimer modal
	// The disclaimer-acceptance record (the legal trail). Extracted so the intro
	// path and the legacy path log IDENTICALLY -- a second inline copy is how the
	// two drift (bd polyglot-pdf-s1iex.6). Fire-and-forget by design: a logging
	// failure must never block the user, and on the intro path it must not delay
	// the connect they are waiting on.
	const logDisclaimerAcceptance = (
		state: ReturnType<typeof SchemaFormStateManager.load>,
		language: string,
	) => {
		const backendUrl = getBackendHttpUrl()
		fetch(`${backendUrl}/api/disclaimer-acceptance`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				form_session_id: state?.formSessionId || 'unknown',
				language,
				timestamp: Date.now(),
				user_agent: navigator.userAgent,
				// WHICH text they agreed to (bd polyglot-pdf-s1iex.7). Echoed from
				// the intro route's X-Intro-Script-Version header, so the backend
				// stays the single source of the hash. undefined whenever the intro
				// player was never built -- introPlayerRef is populated only when
				// introEnabled, so the DEFAULT deployment sends no version even
				// though the user did read deterministic scripted text. That is a
				// known audit gap, not a benign omission (bd polyglot-pdf-pyebx).
				// JSON.stringify drops the key, and the route's field is Optional.
				script_version: introPlayerRef.current?.scriptVersion(),
			}),
		}).then(
			(response) => {
				if (response.ok) {
					console.log('[VoiceOverlay] [OK] Disclaimer acceptance logged to backend')
				} else {
					console.warn('[VoiceOverlay] [warn] Backend logging returned non-OK status:', response.status)
				}
			},
			(err) => {
				console.error('[VoiceOverlay] [X] Failed to log disclaimer acceptance to backend:', err)
			},
		)
	}

	const handleDisclaimerAgree = async () => {
		console.log('[VoiceOverlay] User agreed to disclaimer')

		// FIRST, before any await: stop Sol's intro clip (bd
		// polyglot-pdf-s1iex.5). The maintainer's decision is that Agree is
		// IMMEDIATE -- a clip still talking over the form's first question is
		// the bd zq9l defect this preserves against. stop() also poisons an
		// in-flight fetch, so a cold synthesis landing late cannot start
		// playing into a dismissed modal.
		introPlayerRef.current?.stop()
		setIntroClipState('idle')

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

		// INTRO PATH (bd polyglot-pdf-s1iex.6): there is NO Live session yet --
		// Sol's clip played against nothing, and the whole interrupt sequence
		// below (activity_start -> flush -> resumePlayback -> activity_end) plus
		// switchToFirstSection's teardown/100ms-sleep/re-handshake exists ONLY to
		// stop a model that was mid-disclaimer. With no session there is nothing
		// to interrupt and nothing to tear down: Agree is the FIRST and ONLY
		// connect, which is the epic's one-handshake criterion.
		//
		// The acceptance POST still runs (it is the legal record), but AFTER the
		// connect starts rather than gating it -- a slow logging call must not
		// delay the session the user is now waiting on.
		if (introEnabled) {
			// (the modal was already hidden above -- no second call needed)
			console.log('[VoiceOverlay] Intro path - single connect on Agree (no interrupt, no restart)')
			logDisclaimerAcceptance(state, selectedLanguage)
			// Set the FILL language before connecting (bd polyglot-pdf-s1iex.6,
			// fresh-eyes round 1). The legacy path set it as a side effect of
			// switchToFirstSection -- the ONLY production caller that moved it off
			// createConnectionManager's hardcoded 'English'. Skipping the restart
			// therefore silently left fill_language="English" in the handshake, so
			// a Spanish user would HEAR Spanish while every field's guidance said
			// to write the values in English. changeFillLanguage stores it when
			// not yet connected, so calling it here puts the right value INTO the
			// handshake rather than correcting it afterwards.
			if (selectedLanguage) {
				await connectionManager?.changeFillLanguage(selectedLanguage)
			}
			try {
				await handleConnect()
			} catch (err) {
				console.error('[VoiceOverlay] [X] Connect failed after Agree:', err)
				setConnectionError(err instanceof Error ? err.message : 'Connection failed')
			}
			return
		}

		// Step 1: Send activity_start FIRST to stop backend from sending more audio.
		// The user just agreed, so cut off any still-playing disclaimer read instead
		// of letting it finish (matches VoiceOverlayMobile; bd polyglot-pdf-zq9l).
		// This ALWAYS fires (bd polyglot-pdf-v1m8g): the native-VAD suppression that
		// used to make it a no-op is gone, so it opens the user turn that the
		// sendActivityEnd below closes.
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
					setConnectionError('Connection lost - please click Reconnect')
					return
				}
				reconnected = true
				console.log('[VoiceOverlay] [OK] Reconnected after disclaimer acceptance')
			} catch (err) {
				console.error('[VoiceOverlay] [X] Reconnection failed:', err)
				setConnectionError('Connection lost - please click Reconnect')
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
			// signal on a turn that never opened. On reconnect, switchToFirstSection below
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
		if (!confirm('⚠️ ' + overlayText.clearFormConfirm)) {
			return
		}

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

		// Wipes form state, the app-start form + language choice (so the
		// reload returns all the way to the language-choice modal -- this is
		// how a tester resets between clients, bd voice-ux issues), AND the
		// client-link token in one call -- a plain clear()+clearOnboardingState()
		// here left vff_client_link_token behind after an explicit
		// "Clear form" click (bd polyglot-pdf-ylokf). Placed right before the
		// reload (rather than up front) so wipeSitesReload.test.ts's nearby-
		// reload guard can actually see it -- the DOM-clearing loop above
		// runs first regardless, since sessionStorage and the DOM are
		// independent state the reload will replace either way.
		SchemaFormStateManager.clearAllClientState()
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
	// Not-listening-yet transient states (bd polyglot-pdf-3to5): the system is coming
	// up or recovering but is NOT consuming mic audio (shouldSendMicChunk drops audio
	// in these states, and the backend now drops any pre-ready frames too). Show the
	// ear CROSSED-OUT here so "the system isn't listening" is explicit + language-
	// neutral during the handshake / reconnect window, instead of the ear vanishing.
	const isNotListeningTransient = status.toLowerCase() === 'connecting' ||
		status.toLowerCase().startsWith('reconnecting') ||
		status.toLowerCase() === 'switching_section'
	// The ear is rendered while listening OR while in a not-listening-yet transient
	// (muted). It stays HIDDEN for paused / disconnected / error / idle_timeout --
	// those are explicit end/user states already carried by the status text + FAB.
	const showEar = isListening || isNotListeningTransient
	const isPausedState = status.toLowerCase() === 'paused'
	const isWarming = status.toLowerCase().includes('warming')
	const isReady = status.toLowerCase() === 'ready'
	// Sol, the avatar + status indicator (bd polyglot-pdf-2p4y). It replaces the
	// status icon and subsumes the ear/meter chip: one wordless object that says
	// whose turn it is, legible in every spoken language we ship. The mapping is a
	// pure function in ../shared/solState so both overlays share one precedence
	// rule (paused > offline > speaking > thinking > listening > idle).
	// Resolved ONCE per render, not inside the hook's argument: this component
	// re-renders ~60x/sec while the mic meter moves, and getAudioManager is a hot
	// accessor (bd polyglot-pdf-2p4y).
	const solAudioManager = connectionManager?.getAudioManager?.() ?? null
	const solSpeaking = useGeminiSpeaking(solAudioManager)
	// CLIP-ONLY, deliberately not solSpeaking: a clip is audible with no live
	// session, so it may bypass deriveSolState's live gate -- but the model's
	// own speaking flag must NOT, or a stale flag during `reconnecting` would
	// animate Sol as speaking where it must read `connecting` (the bd
	// polyglot-pdf-bxng invariant; measured regressing when the two signals
	// were conflated -- bd polyglot-pdf-s1iex.4).
	const solClipPlaying = useClipPlaying(solAudioManager)
	const solState = deriveSolState({
		status, thinking, speaking: solSpeaking, micSending,
		clipPlaying: solClipPlaying,
	})
	// Sol reads the AI's OUTPUT level for its speaking ray-breathing (the mic is
	// silent while the assistant talks). Reads the ref rather than closing over
	// the manager, since it is recreated across reconnects -- but caches the lookup
	// so the per-frame path is a property read, not a manager fetch.
	const solAudioManagerRef = useRef(solAudioManager)
	solAudioManagerRef.current = solAudioManager
	const getSolOutputEnergy = React.useCallback(
		() => solAudioManagerRef.current?.getOutputEnergy?.() ?? 0,
		[]
	)

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
						{/* Sol (bd polyglot-pdf-2p4y) replaces the emoji status icon. The
						    traffic-light emoji reported connectedness -- a fact about our
						    socket. Sol reports whose turn it is, which is the only thing
						    the user is actually asking, and does it with no letters in it
						    so it reads the same in all 17+ spoken languages. */}
						<Sol
							state={solState}
							energy={micEnergy}
							getOutputEnergy={getSolOutputEnergy}
							size={40}
							className="vff-sol"
						/>
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
						    audio-reaching-the-backend (green, --sending). Shown while
						    listening OR crossed-out (--muted) during a not-listening-yet
						    transient (connecting / reconnecting / switching_section), so the
						    handshake/reconnect window reads as "not listening" rather than
						    the ear vanishing (bd polyglot-pdf-3to5). */}
						{showEar && (
							<span
								className={
									isListening
										? `vff-listening${micSending ? ' vff-listening--sending' : ''}`
										: 'vff-listening vff-listening--muted'
								}
								title={isListening
									? (micSending
										? `Listening -- sending audio (energy ${micEnergy.toFixed(0)})`
										: `Listening -- mic active, not sending (energy ${micEnergy.toFixed(0)})`)
									: 'Not listening -- connecting to the assistant'}
								aria-label={isListening ? 'Listening' : 'Not listening'}
								role="status"
							>
								{/* Ear glyph via an ASCII-safe Unicode escape (U+1F442) so the
								    .tsx source stays ASCII per AGENTS.md; it still renders the ear
								    emoji at runtime. Language-neutral -- no word to translate. The
								    crossed-out "not listening" state is a CSS strike on this glyph
								    (.vff-listening--muted .vff-listening-ear::after), so no separate
								    "no-ear" glyph is needed. */}
								<span className="vff-listening-ear" aria-hidden="true">{'\u{1F442}'}</span>
								{/* Live mic-energy meter only while genuinely listening -- there
								    is no mic energy to show during the not-listening transient. */}
								{isListening && (
									<span className="vff-mic-meter">
										<span
											className="vff-mic-meter-bar"
											style={{ width: `${Math.min(100, micEnergy)}%` }}
										></span>
									</span>
								)}
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
							📊 {formatFieldsCompleted(overlayText, sectionFieldCount.filled, sectionFieldCount.total)}
						</div>
						{/* DEPRECATED (bd polyglot-pdf-55jg): the manual section-jump
						    dropdown is section-reset production UI; continuous-DTI is
						    the live flow (this whole block is !continuousSession-gated,
						    so it never renders in production). Kept as a fallback, not
						    deleted. Do not extend. */}
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

												// Update field count for new section (from state, before reconnect).
												// Visible-field-aware (bd polyglot-pdf-kbkd) -- see the mount effect
												// above for the full rationale.
												const state = SchemaFormStateManager.load()
												if (state) {
													// Switch section in state first
													const updatedState = SchemaFormStateManager.switchToSection(state, section.id)
													setSectionFieldCount(SchemaFormStateManager.getProgressCounts(updatedState))
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

					{/* Push-to-Talk button: holding it is the turn signal (bd
					    polyglot-pdf-v1m8g -- PTT is the only input mode). */}
					{pushToTalkMode && isConnected && (
						<div className="vff-ptt-button-container">
							<button
								className={`vff-button vff-ptt-button ${isHoldingPushToTalk ? 'active' : ''}`}
								onMouseDown={handlePushToTalkPress}
								onTouchStart={handlePushToTalkPress}
							>
								{isHoldingPushToTalk ? '🔴 ' + overlayText.recording : '⌨️ ' + overlayText.holdToTalk}
							</button>
						</div>
					)}

					{/* Controls */}
					<div className="vff-controls">
						{/* Connection is automatic after language selection - no connect button needed.
						    The Reconnect button covers the idle timeout, a generic
						    "disconnected" drop (the latter sets the "please click Reconnect"
						    error, so it must offer a button to click -- bd polyglot-pdf-b2yj),
						    AND a bare 'error' status. 'error' is set by connect()'s catch when
						    BOTH the localhost and cloud attempts fail (a completely-failed
						    initial connect or resume); without this branch it renders NO button
						    at all -- a dead end recoverable only by a page refresh
						    (bd polyglot-pdf-m77y). handleConnect retries the connection.
						    ('reconnect_failed' has its own recovery surface, the
						    connection-timeout modal, so it is deliberately not listed here.) */}
						{status === 'idle_timeout' || status === 'disconnected' || status === 'error' ? (
							<button
								className="vff-button vff-reconnect"
								onClick={handleConnect}
							>
								🔄 {overlayText.reconnect}
							</button>
						) : isPausedState ? (
							<button
								className="vff-button vff-resume"
								onClick={handleConnect}
							>
								▶️ {overlayText.resume}
							</button>
						) : isConnected ? (
							/* Manual/voice mode toggle (bd polyglot-pdf-wurj8), replacing
							   the old Pause button. Action-labelled like its neighbours:
							   the label is what the click switches TO. aria-pressed marks
							   it as the toggle it is, so a screen reader announces the
							   state rather than just a changing label. */
							<button
								className={'vff-button vff-mode-toggle' + (voiceMode === 'manual' ? ' vff-mode-manual' : '')}
								onClick={handleToggleVoiceMode}
								aria-pressed={voiceMode === 'manual'}
							>
								{voiceMode === 'voice'
									? '🤫 ' + overlayText.switchToManual
									: '🗣️ ' + overlayText.switchToVoice}
							</button>
						) : null}
						<button className="vff-button vff-clear-form" onClick={handleClearForm}>
							🗑️ {overlayText.clearForm}
						</button>
					</div>

					{/* Error Display */}
					{/* FIX #4: Show both connection errors and stream errors */}
					{(error || streamError) && (
						<div className="vff-error">
							{streamError && (
								<div><strong>🎤 {overlayText.micErrorLabel}</strong> {streamError}</div>
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

				${SOL_CSS}
				/* Sol in the desktop status row (bd polyglot-pdf-2p4y). Placement rules
				   live in shared/Sol.tsx so the dev preview renders the real treatment
				   rather than a drifting hand-copy. */
				${SOL_PLACEMENT_CSS}

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

				/* Not-listening (bd polyglot-pdf-3to5): the system is connecting /
				   reconnecting / switching and is NOT consuming mic audio. Dim the chip
				   and strike the ear glyph so it reads as "not listening yet". */
				.vff-listening--muted {
					background: #f3f4f6;
					border-color: #d1d5db;
					opacity: 0.65;
				}

				.vff-listening-ear {
					font-size: 14px;
					line-height: 1;
				}

				.vff-listening--muted .vff-listening-ear {
					position: relative;
					filter: grayscale(1);
				}

				/* Diagonal red strike across the ear -> "not listening". Pure CSS
				   pseudo-element, so no separate "no-ear" glyph is needed and the .tsx
				   source stays ASCII. */
				.vff-listening--muted .vff-listening-ear::after {
					content: "";
					position: absolute;
					left: -2px;
					right: -2px;
					top: 50%;
					height: 2px;
					background: #ef4444;
					transform: rotate(-45deg);
					transform-origin: center;
					border-radius: 2px;
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

				.vff-mode-toggle {
					background: #f59e0b;
					color: white;
				}

				/* Manual mode is a STATE the user sits in, and a silent assistant
				   is indistinguishable from a broken one unless the control says
				   so. Slate reads as "off/quiet" against the amber voice state,
				   and the label changes too -- colour is never the only cue. */
				.vff-mode-toggle.vff-mode-manual {
					background: #475569;
				}

				.vff-mode-toggle.vff-mode-manual:hover {
					background: #334155;
				}

				.vff-mode-toggle:hover {
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

			{/* RESUME CHOICE (bd polyglot-pdf-dft1). A client does not pick a
			    FORM -- their link already did -- so this is one question: start
			    fresh, or continue the file you saved. The upload is verified
			    SERVER-side against the kit's own form.pdf; this component only
			    collects the file. */}
			<ResumeUpload
				isOpen={showResumeChoice}
				// The kit id the LINK pinned at open time. NOT
				// form_metadata.form_number, which is the printed form NAME
				// ("W-7") and not the kit directory ("w7") -- every resume
				// would 404 and read as "that is not your form".
				kitId={loadOnboardingState().formId ?? ''}
				pdfFilename="form.pdf"
				selectedLanguage={selectedLanguage}
				backendUrl={getBackendHttpUrl()}
				// /api/resume-form is auth-gated: without a token it 401s in
				// every deployed environment, working only under the local
				// VFF_DISABLE_AUTH bypass.
				getToken={getToken}
				onResumed={handleResumed}
				onStartOver={() => setResumeDismissed(true)}
			/>

			{/* SAVE NUDGE (bd polyglot-pdf-dft1). The saved PDF is the only thing
			    between a client and losing every answer -- browser form state is
			    discarded after 60 minutes -- so the prompt has to find them rather
			    than wait to be found. CLIENT SESSIONS ONLY: staff have their own
			    workflow and their own machines. */}
			<SaveNudge
				isOpen={saveNudge.variant !== null}
				variant={saveNudge.variant ?? 'early'}
				selectedLanguage={selectedLanguage}
				speak={speakNotice}
				onSave={handleNudgeSave}
				onDismiss={saveNudge.dismiss}
			/>

			{/* Disclaimer Modal - shown after language selection */}
			<DisclaimerModal
				isOpen={showDisclaimerModal}
				selectedLanguage={selectedLanguage}
				onListenAgain={handleDisclaimerListenAgain}
				onAgree={handleDisclaimerAgree}
				// ONE SOURCE (bd polyglot-pdf-s1iex.5, unconditional as of bd
				// polyglot-pdf-nsb4y): the modal renders the exact paragraphs the
				// backend synthesizes -- NOT gated on introEnabled. That gate was
				// the bug: it tied the WRITTEN legal text to whether AUDIO plays,
				// so a reader got "we strongly advise" (advice) while a listener
				// got "you agree to review" (an undertaking) behind the SAME Agree
				// button. The audio flag may gate the CLIP; it must never gate
				// which legal terms the applicant accepts.
				introParagraphs={selectedLanguage
					? renderIntroParagraphs(
						selectedLanguage,
						introFormNumber,
						(BUTTON_TRANSLATIONS[selectedLanguage] || BUTTON_TRANSLATIONS['English']).agree,
					)
					: undefined}
				clipState={introEnabled ? introClipState : undefined}
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

			{/* Transient "reconnecting" notice (bd polyglot-pdf-ppfy): shown while the
			    app is auto-reconnecting after a SPONTANEOUS AI-session drop (e.g. a
			    Gemini 1011 the backend forwards as gemini_session_dropped). Passive,
			    no buttons; auto-clears when the reconnect succeeds (status ->
			    connected) or the terminal modal above takes over on give-up
			    (reconnect_failed). onReconnect is unused in this variant but required
			    by the prop shape.

			    Gated on BOTH status==='reconnecting' AND isDroppedReconnect(): the
			    "reconnecting" status is ALSO set by an ordinary WS blip's
			    attemptReconnect (network hiccup, Cloud Run reset), which has nothing
			    to do with the AI -- those must stay silent, not pop a "trouble
			    reaching the AI assistant" modal (fresh-eyes). isDroppedReconnect() is
			    true only when the reconnect was driven by a gemini_session_dropped. */}
			<ConnectionTimeoutModal
				variant="reconnecting"
				isOpen={status.toLowerCase() === 'reconnecting' && (connectionManager?.isDroppedReconnect?.() ?? false)}
				selectedLanguage={selectedLanguage}
				onReconnect={() => {}}
			/>

			{/* Spend ceiling used up (bd polyglot-pdf-cke6v). Terminal and NOT
			    dismissible: the client needs to know voice is over for this link,
			    and there is no action that would bring it back. Deliberately no
			    Reconnect -- the old behavior retried a socket that refuses every
			    time and then offered a button that could not work.
			    onReconnect is unused here but required by the prop shape.

			    SUPPRESSED WHILE THE SAVE NUDGE IS UP (Opus cross-surface r2).
			    Both dialogs now carry the SAME words -- the ending nudge and this
			    modal are both the lifted voiceEnding copy -- but this one is
			    position:fixed at z-index 10000 with a 75% scrim and no SAVE
			    action, while the nudge underneath holds the working "Save my
			    form" button. Showing both told the client to save and then covered the
			    only control that saves. The nudge wins: identical message, plus
			    an action. This modal is the fallback for a client who has already
			    dismissed or completed the nudge. */}
			<ConnectionTimeoutModal
				variant="budget_exhausted"
				isOpen={status.toLowerCase() === 'budget_exhausted'
					&& saveNudge.variant === null
					&& !budgetModalDismissed}
				selectedLanguage={selectedLanguage}
				onReconnect={() => {}}
				onCancel={() => setBudgetModalDismissed(true)}
			/>
		</>
	)
}
