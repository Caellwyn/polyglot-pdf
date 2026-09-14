/**
 * Connection Manager - Step S5
 * 
 * Manages WebSocket connection to backend using warmup -> upgrade flow.
 * Reuses WebFormConnection logic from main app.
 */

// Extend Window interface for activity watchdog callbacks
declare global {
	interface Window {
		vffOnAudioPlaybackEnd?: () => void
		vffOnAudioPlaybackStart?: () => void  // Called when Gemini starts speaking (pause timer)
		// Fired when a synthesized CLIP (spell-back, Sol's intro) starts or
		// stops (bd polyglot-pdf-s1iex.4). Distinct from the two above, which
		// also fire for the model's own PCM: only the clip-scoped signal may
		// animate Sol without a live session.
		vffOnClipStateChange?: (playing: boolean) => void
		vffOnSectionChanged?: () => void  // Called when Gemini switches sections
		// TEST-ONLY (bd polyglot-pdf-fa4x): fired whenever the backend agent_processing
		// signal arrives, so the voice harness can assert the thinking indicator armed
		// (processing:true at the user's turn end) without a human at the mic. Undefined in production; only the harness sets it.
		vffOnAgentProcessing?: (processing: boolean) => void
		// vffOnTurnComplete removed - now using audio silence detection (100ms threshold)
		// TEST-ONLY (bd polyglot-pdf-g8w): dev gate + injection handle for the E2E
		// voice harness. Double-gated install below; never set in production.
		__VFF_LOCAL_DEV?: boolean
		__VFF_TEST_HARNESS?: boolean
		__VFF_TEST_INJECT?: {
			sendAudio: (audioData: ArrayBuffer) => void
			sendActivityStart: () => void
			sendActivityEnd: () => Promise<void>
			getLastNextField: () => string | null
			// bd polyglot-pdf-o1c: clear one field's state through the canonical
			// SchemaFormStateManager path (save + schemaFormStateChange dispatch) AND
			// refresh the live connection's in-memory state, so a SAME-PAGE harness
			// rerun (no reload) does not read a stale filled/confirmed value.
			resetFieldState: (fieldId: string) => void
			// bd polyglot-pdf-8k8: seed a field as filled-AND-confirmed via the same
			// SchemaFormStateManager write path the real confirm uses, so the
			// multi-section scenario can confirm one VOICE field and trigger the real
			// section auto-advance. Returns false if no form state is loaded yet.
			seedFieldConfirmed: (fieldId: string, value: string) => boolean
			// MEASUREMENT-ONLY (bd 0rpu experiment branch): playback-backlog read
			// used by the harness pacing arms. Never merged to dev.
			getPlaybackBacklog: () => { aheadSec: number; activeSources: number; blocked: boolean }
		}
	}
}

import { WebFormConnection, type ConnectionCallbacks, type ConnectionStatus, type SpellbackPlaybackResult } from '../webFormConnection'
import { getBackendHttpUrl } from '../schema-forms/utils/pdfFiller'
import { createSpellbackPlayer } from './spellbackPlayer'
import type { FormSchema } from '../schema-forms/types/schema'
import { SchemaFormStateManager, type SchemaFormState } from '../schema-forms/state/schemaFormState'
import { BUTTON_TRANSLATIONS } from '../schema-forms/components/DisclaimerModal'
import { createFieldManager, type FieldManager } from './fieldManager'
import { createAudioManager, type AudioManager } from './audioManager'
import { metrics } from './metrics'
import { getBackendUrl as getBackendUrlFromConfig, getCloudBackendUrl, isTestHarnessEnabled } from './config'
import { groupInputsFor } from './groupMembership'

/**
 * Pure gate function: should the mic audio chunk be forwarded to the backend?
 *
 * Rules:
 *   - 'connected': always send.
 *   - 'switching_section' + socket OPEN: send (same-socket section-switch path keeps
 *     the socket alive). Safe on BOTH switch paths because the backend drops
 *     switch-window audio server-side: the WS route's drop_audio flag on the manual
 *     path (websocket_routes.py manual_section_switch handler), and
 *     FormFillingService.stream_audio's _switch_lock.locked() backstop, which covers
 *     the AI-initiated switch too (fresh-eyes round 2, PR #150).
 *   - All other statuses, or socket not open: drop (and the caller warns).
 */
export function shouldSendMicChunk(status: ConnectionStatus, socketOpen: boolean): boolean {
	if (status === 'connected') return true;
	if (status === 'switching_section' && socketOpen) return true;
	return false;
}

/**
 * Manual/voice mode (bd polyglot-pdf-wurj8) -- the sticky half of the two-control
 * voice UI (the other is PTT, which is non-sticky). Named for the two modes
 * rather than for an action, because it is a state the user sits in.
 */
export type VoiceMode = 'manual' | 'voice'

export interface ConnectionManager {
	connect: () => Promise<void>
	pause: () => void  // Pause recording but keep connection warm
	resume: () => Promise<void>  // Resume from pause
	disconnect: () => void  // True disconnect (cleanup everything)
	getStatus: () => ConnectionStatus
	isDroppedReconnect: () => boolean  // bd polyglot-pdf-ppfy: is the current "reconnecting" driven by a spontaneous Gemini drop (vs an ordinary WS blip)? Gates the "trouble reaching the AI" modal.
	getThinking: () => boolean  // bd polyglot-pdf-wpw.5: is the agent currently processing a turn?
	isSendingMicAudio: () => boolean  // bd polyglot-pdf-s3zv: would a mic chunk be forwarded to the backend right now (the real shouldSendMicChunk gate, incl. socket state)? Drives the energy meter's green "sending" state.
	sendAudio: (audioData: ArrayBuffer) => void
	sendActivityStart: () => void  // Send activity_start signal (user started speaking)
	sendActivityEnd: () => Promise<void>    // Send activity_end signal (user stopped speaking) - async to wait for buffer drain
	sendPrompt: (prompt: string) => void  // Send text prompt to Gemini (for recovery, nudges, etc.)
	sendRecoveryPrompt: (level: number, nextFieldHint?: string) => void  // Send recovery prompt (activity watchdog)
	endGeminiSession: () => void  // End Gemini session only (keep WebSocket alive)
	setPushToTalkMode: (enabled: boolean) => void  // Enable/disable PTT mode
	getPushToTalkMode: () => boolean  // Current PTT mode (so a remounted overlay restores the user's choice; bd polyglot-pdf-6vo)
	setPushToTalkHeld: (held: boolean) => void  // Track whether PTT is CURRENTLY held down (bd polyglot-pdf-qt7w), so a reconnect's audio rehydration does not re-mute an active hold
	/**
	 * Notify the model of a field's current STATE through the established
	 * manual_field_update protocol (bd polyglot-pdf-96um6). Exposed because a
	 * VERIFY does not reach the model on its own: the internal notify fires from
	 * a DOM change listener, and verifying changes only a flag, not the input's
	 * value -- measured, 0 notify calls after a pure verify. The React verify
	 * modal therefore has to call this itself.
	 */
	sendManualFieldUpdate: (fieldId: string, fieldName: string, value: any, verified?: boolean) => void
	getFieldManager: () => FieldManager | null
	getAudioManager: () => AudioManager | null
	startRecording: () => Promise<void>
	stopRecording: () => void
	isRecording: () => boolean
	isPaused: () => boolean
	// Manual/voice mode (bd polyglot-pdf-wurj8). Replaces the old pause button.
	// MANUAL: the model neither speaks nor elicits, but the session stays LIVE,
	// the mic stays usable, and field/focus tracking keeps running underneath --
	// so the assistant is correctly oriented the instant it is wanted. VOICE:
	// today's behaviour. Distinct from pause() above, which SUSPENDS the session
	// (mic torn down, in-flight question destroyed, a paid re-ask to come back);
	// pause() survives only as the idle/reconnect machinery's internal state.
	setVoiceMode: (mode: VoiceMode) => void
	getVoiceMode: () => VoiceMode
	// Subscribe to mode changes so a UI can render the CURRENT mode rather than
	// the one it last set itself. Needed because the mode also changes WITHOUT a
	// click: a PTT press auto-leaves manual mode (see sendActivityStart). Returns
	// an unsubscribe function. Both overlays consume the manager as a PROP (it is
	// built in SchemaForm), so a constructor callback could not reach them.
	onVoiceModeChange: (listener: (mode: VoiceMode) => void) => () => void
	// Re-arm mic capture after an overlay remount onto an already-live session
	// (e.g. a desktop<->mobile resize flip). The WebSocket and Gemini session
	// survive the flip; only the old overlay's unmount tears down audio capture,
	// so the new overlay must re-arm. No-ops if already recording (bd nlfc).
	rearmAudioCapture: () => Promise<void>
	changeFillLanguage: (language: string) => Promise<void>
	readDisclaimer: (language: string, disclaimerText: string) => void  // Read disclaimer in specified language
	// Section management (schema-based navigation)
	switchToFirstSection: (language: string) => Promise<void>  // Switch to first section (used after disclaimer acceptance)
	startSection: (sectionId: string) => Promise<void>
	switchToSection: (sectionId: string) => Promise<void>
	completeSection: () => Promise<void>
	getCurrentSectionId: () => string | undefined
	getCompletedSectionIds: () => Set<string>
	// VAD-based barge-in callbacks
	onVADSpeechStart: () => void
	onVADSpeechEnd: () => void
}

/**
 * Restore DOM fields from sessionStorage on page load
 * Ensures DOM and sessionStorage stay in sync across page refreshes
 */
export function restoreDOMFromSessionStorage(state: SchemaFormState, schema: FormSchema): void {
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
			// A GROUP is not a single control. Since bd polyglot-pdf-96um6 gave a
			// group's option[0] an id, getElementById resolves here where it used to
			// return null -- so without this branch a checkbox group restored as
			// Boolean(['White']) === true, checking OPTION[0] regardless of what the
			// user actually picked. A silently wrong race or reason answer.
			// Gated on the RESOLVED element, not the name alone. Ids and names share
			// no namespace, so a text field id="race" can coexist with a checkbox
			// group name="race[]", and the bracket does NOT disambiguate -- the lookup
			// is keyed on the field's OWN id. Ungated, that text field restored/captured
			// nothing at all (measured).
			// MEMBERSHIP, not type. A standalone checkbox/radio whose id collides with
			// another field's group name IS a group type, so a type-only gate sent it
			// down the group branch and wrote the UNRELATED group instead of itself.
			// Mirrors fieldManager's idResolvesToNonGroup -- the rule these two modules
			// share, which diverged the moment I added the membership dimension there
			// and did not carry it here.
			// ONE shared rule (groupMembership.ts). These two inline copies had the
			// membership test but NOT the type filter, so a text field whose own name
			// is bracketed took the group branch and its value vanished -- a
			// regression against origin/dev that the green suite did not see.
			const memberEls = groupInputsFor(fieldId)
			const isGroupMember = memberEls.includes(inputEl)
			const groupEls = isGroupMember ? memberEls : []
			if (groupEls.length) {
				const picked = Array.isArray(value) ? value.map(String) : [String(value)]
				groupEls.forEach(el => { el.checked = picked.includes(el.value) })
			} else if (inputEl.type === 'radio') {
				// Likewise a radio group: select the MATCHING option rather than
				// overwriting option[0]'s value attribute (bd polyglot-pdf-sjbdm).
				//
				// MEMBERSHIP HERE TOO. RadioField renders name={field.id} with NO
				// bracket, so this plain branch -- not the bracketed one above -- is
				// what every real radio group takes. Ungated, a standalone radio whose
				// id collides with ANOTHER group's name wrote that group and dropped
				// its own answer entirely (measured: nothing selected anywhere).
				// The SHARED rule, not another inline lookup. The extraction left this
				// one behind and it was missing the TYPE FILTER -- the same rule and the
				// same dimension that produced the round-7 regression, surviving because
				// my closure guard only forbade the BRACKETED query shape.
				const radios = groupInputsFor(fieldId)
				if (radios.includes(inputEl)) {
					radios.forEach(el => { el.checked = el.value === String(value) })
				} else {
					// Not a member: it is a standalone control that merely shares the id.
					inputEl.checked = inputEl.value === String(value) || Boolean(value)
				}
			} else if (inputEl.type === 'checkbox') {
				inputEl.checked = Boolean(value)
			} else {
				inputEl.value = String(value)
			}
		} else if (element.tagName === 'TEXTAREA') {
			(element as HTMLTextAreaElement).value = String(value)
		}

		restoredCount++
	}

	if (restoredCount > 0) {
		console.log(`[VFF Connection] [OK] Restored ${restoredCount} fields from sessionStorage`)
	}
}

/**
 * Scan DOM for pre-filled values and populate sessionStorage
 * Called before connecting to capture values user entered before activating voice
 */
export function capturePreFilledValues(connection: WebFormConnection, schema: FormSchema): void {
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
		// string[] for a checkbox group -- the shape the rest of the app already
		// stores for one (see FieldValue), and what this path failed to capture.
		let value: string | string[] | boolean | null = null

		if (element.tagName === 'SELECT') {
			const selectEl = element as HTMLSelectElement
			value = selectEl.value || null
		} else if (element.tagName === 'INPUT') {
			const inputEl = element as HTMLInputElement
			// Same group-vs-single distinction as the restore above. Capturing a
			// checkbox group as inputEl.checked stored the BOOLEAN true in place of
			// the string[] selection -- and this path marks what it captures
			// {confirmed: true}, which would have contradicted this bead's whole
			// thesis that only an explicit act verifies a field.
			// Gated on the RESOLVED element, not the name alone. Ids and names share
			// no namespace, so a text field id="race" can coexist with a checkbox
			// group name="race[]", and the bracket does NOT disambiguate -- the lookup
			// is keyed on the field's OWN id. Ungated, that text field restored/captured
			// nothing at all (measured).
			// MEMBERSHIP, not type. A standalone checkbox/radio whose id collides with
			// another field's group name IS a group type, so a type-only gate sent it
			// down the group branch and wrote the UNRELATED group instead of itself.
			// Mirrors fieldManager's idResolvesToNonGroup -- the rule these two modules
			// share, which diverged the moment I added the membership dimension there
			// and did not carry it here.
			// ONE shared rule (groupMembership.ts). These two inline copies had the
			// membership test but NOT the type filter, so a text field whose own name
			// is bracketed took the group branch and its value vanished -- a
			// regression against origin/dev that the green suite did not see.
			const memberEls = groupInputsFor(fieldId)
			const isGroupMember = memberEls.includes(inputEl)
			const groupEls = isGroupMember ? memberEls : []
			if (groupEls.length) {
				const picked = Array.from(groupEls).filter(el => el.checked).map(el => el.value)
				value = picked.length ? picked : null
			} else if (inputEl.type === 'checkbox') {
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
		}
	}

	if (capturedCount > 0) {
		console.log(`[VFF Connection] [OK] Captured ${capturedCount} pre-filled values`)
	}
}

/**
 * Create a stateful rate-limited mic-drop warn function.
 * Rate-limits console.warn to at most one call per second so a stranded
 * connection status does not flood the console (~100 chunks/sec).
 * Exported so the rate-limit logic is testable without a full ConnectionManager
 * (bd polyglot-pdf-b6k4).
 */
export function createMicDropWarn(): (status: string, socketOpen: boolean) => void {
	let lastWarnMs = 0
	return (status: string, socketOpen: boolean) => {
		const now = Date.now()
		if (now - lastWarnMs >= 1000) {
			lastWarnMs = now
			console.warn('[VFF Connection] mic chunk DROPPED -- status=' + status + ' socketOpen=' + socketOpen)
		}
	}
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
	sharedStream?: MediaStream,
	onNextField?: (fieldId: string | null) => void,
	getToken?: () => Promise<string | undefined>,
	// Thinking-indicator signal (bd polyglot-pdf-wpw.5): true while the agent is
	// processing a turn (user-turn-end -> first response audio). Optional so existing
	// callers are unaffected; the overlays pass it to drive a calm "thinking" UI.
	onThinkingChange?: (thinking: boolean) => void
): ConnectionManager {
	// Get production backend URL from environment or default
	const wsUrl = getBackendUrl()

	let connection: WebFormConnection | null = null
	let fieldManager: FieldManager | null = null
	let audioManager: AudioManager | null = null
	let fillLanguage: string = initialFillLanguage
	let paused: boolean = false
	// Manual/voice mode (bd polyglot-pdf-wurj8). Sticky, client-owned, and
	// re-asserted to the backend on every (re)connect -- the backend is stateless
	// and a reconnect builds a fresh Gemini session that would otherwise default
	// to speaking. Defaults to 'voice': a user who has expressed no preference
	// gets the assistant, since a silent-by-default app reads as broken.
	let voiceMode: VoiceMode = 'voice'
	// Listeners for the above (bd polyglot-pdf-wurj8). A Set so a remounted
	// overlay's unsubscribe cannot drop a sibling's listener.
	const voiceModeListeners = new Set<(mode: VoiceMode) => void>()
	const notifyVoiceMode = (mode: VoiceMode) => {
		for (const listener of voiceModeListeners) {
			try {
				listener(mode)
			} catch (err) {
				// A listener is UI code; one throwing must not abort the mode change
				// or starve the other listeners.
				console.error('[VFF Connection] voice-mode listener threw:', err)
			}
		}
	}
	let connectedUrl: string = wsUrl  // Track the actual URL we connected to
	// Debounced post-unpause re-prompt (bd polyglot-pdf-yo5t). pause() discards the
	// AI's in-flight audio CLIENT-side only -- Gemini finished asking its question
	// into a flushed buffer and now waits for an answer the user never heard, while
	// the user waits for the AI to speak. On a WARM resume (socket still open --
	// the reconnect path re-prompts via the backend RESUME initiating message
	// instead) we ask the backend to have Gemini re-ask the current field, on a
	// short delay so rapid pause/unpause flutter reschedules ONE re-prompt rather
	// than firing one per click. Fire-time guards (paused/socket/AI-speaking) keep
	// it silent when the moment has passed.
	const RESUME_REPROMPT_DELAY_MS = 1500
	let resumeRepromptTimer: ReturnType<typeof setTimeout> | null = null
	const clearResumeReprompt = () => {
		if (resumeRepromptTimer !== null) {
			clearTimeout(resumeRepromptTimer)
			resumeRepromptTimer = null
		}
	}
	// Single mic send callback shared by EVERY arming site (initial startRecording,
	// rearmAudioCapture, and the startSection/switchToSection re-arms) so the gate
	// policy (shouldSendMicChunk) and the drop logging stay consistent (bd xroy).
	// 'switching_section' with socket open is allowed: the same-socket section-switch
	// path keeps the WebSocket alive, and the backend drops switch-window audio
	// server-side on BOTH paths (the WS route's drop_audio flag on the manual path;
	// FormFillingService.stream_audio's _switch_lock backstop on the AI path).
	const warnMicDrop = createMicDropWarn()
	const sendMicChunkToBackend = (audioData: ArrayBuffer) => {
		if (connection && shouldSendMicChunk(connection.getStatus(), connection.isSocketOpen())) {
			connection.sendAudio(audioData)
		} else {
			const st = connection ? connection.getStatus() : 'no-connection'
			const rs = connection ? connection.isSocketOpen() : false
			warnMicDrop(st, rs)
		}
	}
	// PTT is the DEFAULT (HALLUCINATION_REDUCTION, Oct 30 2025), and this must match
	// the overlays' default so a fresh session starts gated. The overlays now lazy-init
	// their pushToTalkMode FROM this value via getPushToTalkMode() (so a remount onto a
	// live session restores the user's choice); since `false ?? true === false`, a
	// `false` here would have wrongly started every NEW session in Auto with the mic
	// open (fresh-eyes PR #119). Default true keeps PTT-as-default intact.
	let pushToTalkMode: boolean = true  // Track if PTT mode is enabled (disables energy-based barge-in)
	// Whether the user is CURRENTLY holding push-to-talk down (bd polyglot-pdf-qt7w).
	// Distinct from pushToTalkMode (is PTT the input mode) -- this is the momentary
	// "is the button pressed right now" so a reconnect's audio rehydration does not
	// re-mute an active hold mid-utterance. The overlays drive it from their PTT
	// press/release handlers via setPushToTalkHeld().
	let pushToTalkHeld: boolean = false
	// Native-VAD mode (bd polyglot-pdf-333): when true, Gemini's own VAD drives
	// turns -- we suppress all manual activity signals (PTT + Silero) and stream
	// continuous audio. Set from the backend session_ready handshake.

	// --- Deterministic spell-back playback (bd polyglot-pdf-22h1f) ---
	// The whole state machine (drain wait, TTS fetch, blocking playback,
	// pre-emption/generation guard, cancellation) lives in spellbackPlayer.ts
	// so it is unit-testable; this layer only supplies the live deps.
	const spellback = createSpellbackPlayer({
		getAudioManager: () => audioManager,
		getHttpBase: getBackendHttpUrl,
		getToken,
		// Level check for the stale-arrival guard (bd polyglot-pdf-kvrfq): a
		// spellback request that ARRIVES mid-hold is refused instead of played
		// -- the press-edge interruptForPtt() below cannot catch those, and an
		// unguarded play() would re-engage the mic hold over the user's own
		// press (worklet: spellbackHold silences even an unmuted PTT mic).
		isPttHeld: () => pushToTalkHeld,
	})

	// TEST-ONLY (bd polyglot-pdf-g8w): tracks the most recent field id Gemini
	// advanced to, so the dev-gated E2E voice harness can assert "moved to the
	// next field" without scraping transcripts. Only meaningful when the harness
	// hook below is installed; harmless otherwise (it just shadows onNextField).
	let lastNextField: string | null = null
	const trackedOnNextField = onNextField
		? (fieldId: string | null) => {
			lastNextField = fieldId
			onNextField(fieldId)
		}
		: (fieldId: string | null) => {
			lastNextField = fieldId
		}

	// Initialize state
	// A stored session skips init(), so reconcile it against the FRESH schema
	// here: restoreDOMFromSessionStorage below sets <select>.value from the
	// stored value, and a pre-migration code ('AL') selects nothing once the
	// options are slugs (bd polyglot-pdf-g2fpr, PR 3c).
	//
	// PERSIST ONLY WHEN A VALUE CHANGED. The onManualEdit handlers below read
	// SchemaFormStateManager.load() -- the raw bytes -- so an in-memory-only
	// reconcile was undone by the first manual edit (fresh-eyes). A value
	// change is a real migration and is saved; a bare schema swap is not
	// saved HERE (connection.test.ts pins that at construction). Note the
	// limit of that promise: connect() builds a WebFormConnection whose
	// constructor calls init(), and init()'s reuse branch re-persists on
	// every reuse (cross-surface, g2fpr.5) -- with the correct values.
	const stored = SchemaFormStateManager.load()
	let state: SchemaFormState = stored
		? SchemaFormStateManager.reconcileSelectValues(stored, schema)
		: SchemaFormStateManager.init(schema)
	// ...and a dangling-id reset (pinnedFieldId / searchOriginFieldId /
	// currentSectionId) is persisted for the same reason: fresh-eyes round 2
	// found it clobbered by a pre-connect manual edit through the same door.
	const reconciledSomething = stored && (
		state.fieldValues !== stored.fieldValues
		|| state.pinnedFieldId !== stored.pinnedFieldId
		|| state.searchOriginFieldId !== stored.searchOriginFieldId
		|| state.currentSectionId !== stored.currentSectionId)
	if (reconciledSomething) SchemaFormStateManager.save(state)

	// Restore DOM fields from sessionStorage (if any values exist from previous session)
	restoreDOMFromSessionStorage(state, schema)

	// Pass shared stream if provided (for VAD coordination)
	audioManager = createAudioManager(sharedStream)

	// Create field manager immediately to listen for manual edits from the start
	// This captures any fields the user fills BEFORE clicking Connect
	fieldManager = createFieldManager({
		schema: schema,
		onManualEdit: (fieldId, value) => {
			// Load the latest persisted state so this edit is applied on top of any
			// AI fills that WebFormConnection saved to sessionStorage since the last
			// time this closure's `state` variable was refreshed. Without this, a
			// manual-edit blur would call updateField with a stale base state missing
			// those AI fills, and the resulting save would clobber them -- making
			// every other field's value and badge disappear until Gemini's next
			// message re-fills them.
			const currentState = SchemaFormStateManager.load() || state
			// Typing does NOT verify (bd polyglot-pdf-uum5g). This handler is
			// registered on 'blur' AND 'change' (fieldManager.ts), so confirming
			// here meant TABBING THROUGH THREE FIELDS WROTE THREE AUDIT RECORDS --
			// a keystroke nobody intends as an assertion, standing behind a
			// per-field verification claim the firm relies on
			// (docs/standards/confirmation-and-audit.md).
			//
			// The VALUE is still stored; only the verification is withheld. The
			// field then stays in the next-field search (bd polyglot-pdf-a08po
			// already re-offers it) until an explicit act verifies it: the verbal
			// confirm, the skip control, or the Enter->modal gesture
			// (bd polyglot-pdf-96um6).
			const edited = SchemaFormStateManager.updateField(
				currentState,
				fieldId,
				value,
				{ confirmed: false }
			)
			// Resume the next-field search from the field the user just filled,
			// not the top of the form (bd polyglot-pdf-a08po). Without this the
			// model is re-targeted at the first unconfirmed field after EVERY
			// manual edit, while the user works further down.
			const updatedState = SchemaFormStateManager.setSearchOrigin(edited, fieldId)
			// Keep closure reference in sync for subsequent calls
			Object.assign(state, updatedState)

			// If connected, also notify Gemini
			if (connection) {
				const field = schema.fields.find(f => f.id === fieldId)
				const fieldName = field?.name || fieldId
				connection.sendManualFieldUpdate(fieldId, fieldName, value)
			}
		}
	})

	// Single audio-rehydration routine shared by EVERY reconnect / session-restart
	// path (bd polyglot-pdf-z9bc). Before this, "arm the mic and re-sync PTT" was
	// duplicated across resume(), startSection(), switchToSection() and
	// rearmAudioCapture(), and the automatic/internal reconnects (GoAway,
	// auto-drop, warm restart) re-armed nothing at all. Centralizing it here means
	// the condition is handled in ONE place: the callers (and the session-ready
	// callbacks) all funnel through this, so no path can silently diverge.
	//
	// IDEMPOTENT BY DESIGN -- safe to call on a path that is already recording:
	//   - no-op under the test harness (audio is injected -- bd polyglot-pdf-g8w);
	//   - no-op while paused (resume() clears `paused` before calling this);
	//   - startRecording() is skipped when already recording, and its in-flight
	//     `arming` guard (bd polyglot-pdf-z9bc) makes a concurrent call from the
	//     overlay's connect-poll and a session-ready callback await one setup
	//     instead of racing two getUserMedia calls;
	//   - PTT/mute is always re-applied (cheap, idempotent) so a freshly-armed mic
	//     starts in the correct gate state.
	// This is why routing the self-healing GoAway/auto-drop/warm-restart paths
	// through it is harmless: on those paths the mic worklet + playback context
	// survive the socket swap and `recording` stays true, so this is a no-op
	// re-sync -- NOT the isRecording()-guarded skip-the-whole-arm that made the
	// earlier fix (PR #339) wrong.
	// Re-assert the user's manual/voice choice onto a freshly-established Gemini
	// session (bd polyglot-pdf-wurj8). The backend is stateless and every
	// (re)connect builds a session that defaults to SPEAKING, so without this a
	// GoAway/auto-drop/warm-restart silently drops a user out of manual mode --
	// the assistant starts talking again with no user action, which is the exact
	// surprise manual mode exists to prevent.
	//
	// Deliberately NOT folded into rehydrateAudio: that routine early-returns
	// under the test harness and while paused, and the mode must be re-sent on
	// those paths too (it is a protocol fact, not an audio-device fact). Only
	// sent for 'manual' -- 'voice' is the backend's own default for a new
	// session, so re-sending it is pure traffic.
	const reassertVoiceMode = (reason: string): void => {
		if (voiceMode !== 'manual') return
		console.log('[VFF Connection] Re-asserting manual mode after ' + reason)
		connection?.setVoiceMode('manual')
	}

	const rehydrateAudio = async (reason: string): Promise<void> => {
		if (isTestHarnessEnabled()) {
			console.log('[VFF Connection] rehydrateAudio: TEST harness active -- skipping (' + reason + ')')
			return
		}
		if (paused) {
			console.log('[VFF Connection] rehydrateAudio: paused -- skipping (' + reason + ')')
			return
		}
		if (!audioManager) {
			console.warn('[VFF Connection] rehydrateAudio: audioManager not initialized (' + reason + ')')
			return
		}
		// Clear any STALE barge-in playback block (bd polyglot-pdf-nm7z). Every
		// flushAudioQueue() (playbackBlocked=true) is paired with a resumePlayback()
		// later in the SAME interaction flow (PTT release, VAD speech-end, resume()),
		// but a session teardown between the pair orphans the block: pause() flushes,
		// the warm connection idle-times-out during the pause, and the user comes
		// back via connect() -- resume() (the only unblocker on that path) never
		// runs, so EVERY AI audio chunk after the reconnect is silently discarded
		// (tester bugs 0/7: "Gemini still hears me but I can't hear her"). This
		// routine runs exactly at session-(re)establishment, where no legitimate
		// in-flight barge-in flush can exist (the old session's audio died with its
		// socket), so unblocking here is safe -- and it is the ONE funnel all
		// reconnect paths share. The paused guard above keeps a mid-pause block
		// intact (resume() clears `paused` before calling this).
		// ACCEPTED narrow race (Opus review, bd polyglot-pdf-nm7z): reachable only
		// with PTT off, which no longer happens (bd polyglot-pdf-v1m8g), so a
		// GoAway/auto-drop reconnect landing inside a live barge-in window unblocks
		// a moment early, so the new session's first audio could briefly overlap
		// the user's in-progress interruption -- sub-second, self-correcting on
		// speech-end, and strictly better than the audio-dead-forever bug this
		// clear fixes. A ConnectionManager-level guard was tried and REVERTED as
		// dead code: the overlay drives its own VAD flush directly, never through
		// manager.onVADSpeechStart, so no manager flag can see that window.
		audioManager.resumePlayback()
		const wasRecording = audioManager.isRecording()
		if (!wasRecording) {
			console.log('[VFF Connection] rehydrateAudio: arming mic (' + reason + ')')
			await audioManager.startRecording(sendMicChunkToBackend)
		}
		// Re-apply the PTT gate MODE to the worklet (idempotent, does not open or
		// close the mic) so the noise-gate state is correct after a reconnect.
		const am = audioManager
		am.setPTTMode(pushToTalkMode)
		// Mute/unmute state is only (re)set when we ARMED A FRESH mic (which starts
		// unmuted by default, so PTT mode must apply its resting mute). When the mic
		// was ALREADY recording -- the self-healing GoAway/auto-drop/warm-restart
		// case -- we deliberately DO NOT touch mute state: the user may be actively
		// holding push-to-talk (mic unmuted mid-utterance), and blindly re-muting
		// here would truncate their speech (bd polyglot-pdf-z9bc fresh-eyes gap).
		// Their existing mute/hold state is already correct and survives the swap.
		if (!wasRecording) {
			// Read the hold state AFTER the (awaited) arm so a PTT press that landed
			// DURING startRecording is honored (bd polyglot-pdf-qt7w): the fresh mic
			// must end unmuted if the user is now holding, muted otherwise. Reading it
			// here (last write wins) also makes a press that lands just AFTER this
			// correct -- the press's own unmuteInput() then runs and wins.
			if (pushToTalkMode && !pushToTalkHeld) {
				am.muteInput()
			} else {
				am.unmuteInput()
			}
		}
	}

	const callbacks: ConnectionCallbacks = {
		// Deterministic spell-back playback (bd polyglot-pdf-22h1f): implemented
		// here because this layer owns the audio manager and the auth token.
		onSpellbackRequest: (value: string, _fieldId: string, language?: string): Promise<SpellbackPlaybackResult> => spellback.play(value, language),
		onStatusChange: (status) => {
			// BUG FIX (Nov 10, 2025): Reset paused flag when connection is lost
			// This ensures reconnect works properly after timeout/error/disconnect
			// Keep paused flag ONLY if status is 'connected' or 'switching_section'
			if (status !== 'connected' && status !== 'switching_section') {
				if (paused) {
					console.log('[VFF Connection] [reconnect] Resetting paused flag due to status:', status)
					paused = false
				}
			}
			onStatusChange(status)
		},
		onThinkingChange: (thinking) => {
			// Forward the backend-driven thinking signal to the UI (bd polyglot-pdf-wpw.5).
			if (onThinkingChange) onThinkingChange(thinking)
		},
		onSessionReady: (sessionId) => {
			onStatusChange('connected')

			// Initialize metrics for this session
			metrics.startSession(sessionId)

			// A new Gemini session defaults to speaking -- restore the user's choice
			// before anything can elicit (bd polyglot-pdf-wurj8).
			reassertVoiceMode('onSessionReady')

			// Rehydrate audio through the shared routine (bd polyglot-pdf-z9bc). This
			// is the callback the AUTOMATIC/INTERNAL reconnects surface through --
			// GoAway (handleGoAwayReconnect) and auto-drop (attemptReconnect) -- which
			// re-armed nothing before. Audio self-heals on these paths (the worklet +
			// contexts survive the socket swap), so this is an idempotent no-op re-sync
			// there; it also covers the manual/section paths (their explicit arm ran
			// just before, so isRecording() is already true and startRecording is
			// skipped). Fire-and-forget: the callback is sync, and a re-arm failure is
			// logged but must not throw into the message loop.
			void rehydrateAudio('onSessionReady').catch((err) => {
				console.error('[VFF Connection] rehydrateAudio(onSessionReady) failed:', err)
			})

			// Field manager already created at initialization
			// Now it will start syncing manual edits to Gemini
		},
		onSessionRestarted: () => {
			// Backend confirms Gemini session has been restarted
			onStatusChange('connected')

			// A warm restart builds a fresh Gemini session too, so the mode has to
			// be re-asserted here as well (bd polyglot-pdf-wurj8).
			reassertVoiceMode('onSessionRestarted')

			// Warm restart (restart_gemini_session) keeps the SAME socket + mic, so
			// this is normally a pure PTT re-sync no-op; routed through the shared
			// routine anyway so every reconnect cause is handled in one place
			// (bd polyglot-pdf-z9bc).
			void rehydrateAudio('onSessionRestarted').catch((err) => {
				console.error('[VFF Connection] rehydrateAudio(onSessionRestarted) failed:', err)
			})
		},
		onInterrupted: () => {
			// Gemini interrupted the current generation (user barge-in, bd
			// polyglot-pdf-s7uf). Drain the SCHEDULED playback (sources + clock)
			// so the dead generation's tail stops now; the staging queue was
			// already cleared in webFormConnection before this fired.
			// resetPlaybackClock never sets playbackBlocked, so the model's NEXT
			// generation plays normally (nm7z-immune by construction).
			audioManager?.resetPlaybackClock()
		},
		onSectionChanged: () => {
			// Gemini triggered a section switch - trigger UI refresh
			console.log('[VFF Connection] Section changed, triggering UI refresh')
			// Trigger a re-render by updating the state reference
			if (connection) {
				state = connection.getState()
			}
			// Notify listeners that section changed (SchemaForm will re-render)
			if (window.vffOnSectionChanged) {
				window.vffOnSectionChanged()
			}
		},
		onFieldUpdate: (updates) => {
			console.log('[VFF Connection] [tool] Tool call: update_form_fields (' + updates.length + ' field(s))')
			// Playback-backlog snapshot at tool-response time (bd polyglot-pdf-0rpu):
			// if a wrong read-back is heard, a large aheadSec here means STALE
			// CLIENT audio was still queued (client-side fault); ~0 means the audio
			// came fresh from the model (model-side fault). Console lines are
			// captured into the dev JSONL by the console-log forwarder.
			if (audioManager) {
				const backlog = audioManager.getPlaybackBacklog()
				console.log('[VFF Audio] backlog at form_updated ' + JSON.stringify(backlog))
			}

			// Field VALUES are never logged here (bd polyglot-pdf-8v8i7): a shared
			// law-office device's console must not carry client PII. Only the
			// field id + update count above are diagnostic.

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
				console.warn('[VFF Connection] [warn] Rejected', rejectedUpdates.length, 'hallucinated update(s)')
			}

			// S6: Apply ONLY accepted field updates to DOM
			if (fieldManager && acceptedUpdates.length > 0) {
				console.log(`[VFF Connection] [note] Applying ${acceptedUpdates.length} accepted update(s) to DOM`)
				fieldManager.applyUpdates(acceptedUpdates)
			} else if (acceptedUpdates.length === 0) {
				console.warn('[VFF Connection] [warn] No updates to apply (all rejected or empty)')
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
			// BUG FIX (Nov 10, 2025): Reset paused flag on error to allow reconnect
			paused = false
			onStatusChange('error')
		},
		onNextField: trackedOnNextField,
		onStopCapture: () => {
			audioManager?.stopRecording()
		},
		onFormComplete: () => {
			console.log('[VFF Connection] form complete')
		},
	}

	const manager: ConnectionManager = {
		async connect() {
			// A (re)connect re-prompts via the backend RESUME initiating message,
			// so any pending warm-resume re-prompt is superseded (bd polyglot-pdf-yo5t).
			clearResumeReprompt()

			// BUG FIX (Nov 10, 2025): Reset paused flag on connect attempt
			// This fixes the issue where after idle timeout, isPaused() returns true
			// and handleConnect tries to resume() instead of connect()
			paused = false

			// Check if WebSocket is connected but Gemini is closed (post-Level 3 scenario)
			const isWebSocketConnected = connection && connection.getStatus() === 'connected'

			if (isWebSocketConnected && connection) {
				console.log('[VFF Connection] [reconnect] Restarting Gemini session')
				// Compute next field hint for smooth progression
				const nextFieldHint = connection.getNextFieldHint()
				// Send restart message to backend with hint
				try {
					onStatusChange('reconnecting')  // Set status to reconnecting while waiting
					connection.send({
						type: 'restart_gemini_session',
						next_field_hint: nextFieldHint
					})
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
					audioManager = createAudioManager(sharedStream)
				}

				// Reinitialize field manager if destroyed (reconnect scenario)
				if (!fieldManager) {
					fieldManager = createFieldManager({
						schema: schema,
						onManualEdit: (fieldId, value) => {
							// Load latest persisted state so this edit lands on top of any
							// AI fills saved since the closure's `state` was last refreshed.
							const currentState = SchemaFormStateManager.load() || state
							// Typing does NOT verify (bd polyglot-pdf-uum5g) -- same rule
							// as the primary onManualEdit above. These two closures are
							// duplicates and must stay in step; this is the RECONNECT
							// one, so missing it would mean typing silently verified
							// again after any reconnection.
							const edited = SchemaFormStateManager.updateField(
								currentState,
								fieldId,
								value,
								{ confirmed: false }
							)
							// Same search-origin move as the primary onManualEdit above
							// (bd polyglot-pdf-a08po) -- these two closures are duplicates
							// and must stay in step.
							const updatedState = SchemaFormStateManager.setSearchOrigin(edited, fieldId)
							Object.assign(state, updatedState)

							// If connected, also notify Gemini
							if (connection) {
								const field = schema.fields.find(f => f.id === fieldId)
								const fieldName = field?.name || fieldId
								connection.sendManualFieldUpdate(fieldId, fieldName, value)
							}
						}
					})
				}

				// Create connection if not exists
				if (!connection) {
					connection = new WebFormConnection(schema, {
						...callbacks,
						onNextField: trackedOnNextField
					}, fillLanguage)
					// Register the fresh-token callback so reconnects (startSection,
					// auto-reconnect) re-fetch a valid token (bd polyglot-pdf-wq0).
					if (getToken) connection.setGetToken(getToken)
				}

				// Capture any pre-filled values from DOM before connecting
				capturePreFilledValues(connection, schema)

				// Try to connect to localhost first
				try {
					await connection.connect(wsUrl)
					connectedUrl = wsUrl  // Track successful connection
					console.log('[VFF Connection] [OK] Connected:', wsUrl)
				} catch (localError) {
					// Localhost failed, try cloud fallback
					const cloudUrl = getCloudBackendUrl()
					console.log('[VFF Connection] Localhost failed, trying cloud:', cloudUrl)
					console.log('[VFF Connection] Local error was:', localError)

					// Create new connection for cloud attempt
					connection.disconnect()
					connection = new WebFormConnection(schema, {
						...callbacks,
						onNextField: trackedOnNextField
					}, fillLanguage)
					if (getToken) connection.setGetToken(getToken)
					capturePreFilledValues(connection, schema)

					await connection.connect(cloudUrl)
					connectedUrl = cloudUrl  // Track successful connection
					console.log('[VFF Connection] [OK] Connected to cloud')
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
			// A user-initiated pause mid-clip stops the spell-back too -- the
			// user has stopped listening; the model gets the error variant and
			// re-offers when they resume (bd 22h1f).
			spellback.cancel()
			// Flutter guard (bd polyglot-pdf-yo5t): a re-pause inside the re-prompt
			// window cancels the pending re-prompt; the next resume re-arms it.
			clearResumeReprompt()

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

			// Gate on the SAME truth the mic-send gate reads: an OPEN socket
			// (bd polyglot-pdf-l8z7). The old gate trusted connection.getStatus()
			// alone, but an idle-timeout can land DURING a pause and leave the
			// socket closed while the manager's rendered status still reads as if
			// resumable -- resume() then logged "Resumed successfully" onto a dead
			// socket, cleared `paused`, re-armed the mic, and every chunk was
			// dropped forever with no recovery affordance (tester bugs 0/7; the
			// exact 22:49Z repro). A closed socket cannot be resumed regardless of
			// what status says, so DELEGATE to connect() to recover. In the
			// idle-timeout case (status now idle_timeout) connect()'s
			// isWebSocketConnected check is false, so it runs a FULL WS reconnect.
			// In the rarer GoAway window (status deliberately kept 'connected'
			// over a transiently-null socket, webFormConnection.ts) connect() sends
			// a warm restart_gemini_session that no-ops on the dead socket -- but a
			// GoAway reconnect is already in flight there, so the socket recovers
			// regardless and audio is never stranded. Either way `paused` is
			// cleared first so connect() takes the connect path, not a re-entrant
			// resume.
			if (!connection || !connection.isSocketOpen()) {
				const currentStatus = connection?.getStatus() ?? 'no connection'
				console.warn('[VFF Connection] resume() on a closed socket (status:',
					currentStatus, ') -- routing to reconnect')
				paused = false
				await manager.connect()
				return
			}

			paused = false
			onStatusChange('connected')

			// Un-block AI playback. pause() called flushAudioQueue(), which sets
			// playbackBlocked=true to discard in-flight AI audio; without clearing it
			// here, EVERY AI audio chunk after resume is silently dropped in
			// playAudio() -- the mic re-arms but the AI's voice never returns. Nothing
			// else clears it on the default path: onVADSpeechEnd (the only other
			// resumePlayback caller) early-returns under PTT, which is the only mode.
			// So resume() must reset it itself (bd audio-resume).
			if (audioManager) {
				audioManager.resumePlayback()
			}

			// Restart recording through the shared rehydration routine (bd
			// polyglot-pdf-z9bc). `paused` was just cleared above, so this arms the
			// mic and re-syncs PTT in one place.
			await rehydrateAudio('resume')

			// Debounced re-prompt (bd polyglot-pdf-yo5t): the pause discarded
			// Gemini's question client-side, so nothing will speak until the user
			// does -- and the user is waiting for Gemini. After the debounce window
			// (flutter guard: pause() cancels, a newer resume reschedules), ask the
			// backend to have Gemini re-ask the current field -- unless the moment
			// has passed (re-paused, socket died, AI already talking, or the user
			// started a PTT turn themselves).
			clearResumeReprompt()
			resumeRepromptTimer = setTimeout(() => {
				resumeRepromptTimer = null
				if (paused) return
				if (!connection || !connection.isSocketOpen()) return
				// isModelSpeaking (bd polyglot-pdf-uxc6s): this guard exists to avoid
				// re-prompting over the model. isSpeaking() reads false during a
				// model+clip overlap, so the recovery prompt could fire mid-utterance.
				if (audioManager?.isModelSpeaking()) return
				if (pushToTalkHeld) return
				console.log('[VFF Connection] Post-resume re-prompt: asking Gemini to re-ask the current field')
				connection.sendRecoveryPrompt(1)
			}, RESUME_REPROMPT_DELAY_MS)

			// Audio will automatically resume when user starts speaking again
			// The connection stayed warm, so Gemini is still ready
			console.log('[VFF Connection] Resumed successfully')
		},

		disconnect() {
			// End metrics session and print summary
			metrics.endSession()

			// Stop an in-flight spell-back clip so audio does not keep playing
			// past the teardown (bd 22h1f).
			spellback.cancel()

			// A tear-down must not leave a pending post-resume re-prompt behind
			// (bd polyglot-pdf-yo5t).
			clearResumeReprompt()

			// BUG FIX (Nov 10, 2025): Reset paused flag on disconnect
			paused = false

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

		// Whether the current "reconnecting" is driven by a spontaneous Gemini drop
		// (bd polyglot-pdf-ppfy) -- the overlay gates the "trouble reaching the AI"
		// modal on this so an ordinary WS blip's reconnect stays silent.
		isDroppedReconnect() {
			return connection?.isDroppedReconnect() ?? false
		},

		getThinking() {
			return connection?.getThinking() ?? false
		},

		// Whether a mic chunk would actually be forwarded to the backend RIGHT NOW --
		// the SAME decision sendMicChunkToBackend applies (shouldSendMicChunk over the
		// live status + socket state). The UI energy meter (bd polyglot-pdf-s3zv) uses
		// this so "sending" reflects the real connection send gate, including the
		// valid switching_section + open-socket case, instead of re-deriving a partial
		// copy of the gate from status alone (Codex PR #203).
		isSendingMicAudio() {
			return connection
				? shouldSendMicChunk(connection.getStatus(), connection.isSocketOpen())
				: false
		},

		sendAudio(audioData: ArrayBuffer) {
			if (connection) {
				connection.sendAudio(audioData)
			}
		},

		sendActivityStart() {
			// The user started a turn -- their answer supersedes the pending
			// post-resume re-prompt. Cleared HERE (not only in onVADSpeechStart)
			// because the overlays' real manual-VAD speech-start handlers call
			// sendActivityStart() directly and never route through
			// onVADSpeechStart (fresh-eyes gap, bd polyglot-pdf-yo5t). Cleared
			// (bd polyglot-pdf-yo5t). The native-VAD suppression that used to sit
			// here is gone with the mode (bd polyglot-pdf-v1m8g): PTT owns
			// activation, so this signal is always sent.
			clearResumeReprompt()
			// A PTT press is an unambiguous request FOR the assistant, so it leaves
			// manual mode without making the user find the toggle first (bd
			// polyglot-pdf-wurj8, exit criterion 2). Routed through the manager's own
			// setter so the UI's mode state and the backend are updated the same way
			// a click would -- and BEFORE sendActivityStart, so the turn the user is
			// opening is not the one still suppressed. The backend independently
			// unmutes on vad_activity_start, which covers the case where this message
			// and the activity signal race or the socket reopened underneath us.
			if (voiceMode !== 'voice') {
				manager.setVoiceMode('voice')
			}
			console.log('[ConnectionManager] sendActivityStart called, connection:', connection, 'isNull:', connection === null)
			if (connection) {
				connection.sendActivityStart()
			} else {
				console.error('[ConnectionManager] [X] Cannot send activity_start - inner connection is null')
			}
		},

		async sendActivityEnd() {
			// PTT release is the turn boundary (bd polyglot-pdf-v1m8g). The
			// native-VAD suppression that lived here -- and the audio_stream_end
			// workaround before it (bd-6vo/PR#119, bd-zivv) -- both existed only to
			// keep manual signals from colliding with Gemini's own detector. With
			// that detector gone there is nothing to collide with, so the real
			// activity_end is always sent.
			if (connection) {
				await connection.sendActivityEnd()
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

		// Track whether PTT is CURRENTLY held (bd polyglot-pdf-qt7w). The overlays
		// call this from their PTT press (true) / release (false) handlers, alongside
		// the muteInput()/unmuteInput() they already do. rehydrateAudio reads this
		// after a fresh-arm await so a reconnect landing mid-hold does not re-mute the
		// user. Purely advisory: the audioManager's own inputMuted is still the gate.
		setPushToTalkHeld(held: boolean) {
			pushToTalkHeld = held
			// A PTT press right after an unpause means the user is answering the
			// question they remember -- cancel the pending re-prompt rather than
			// talking over their turn (bd polyglot-pdf-yo5t).
			if (held) {
				clearResumeReprompt()
				// Intentional interrupt of a spell-back clip (bd polyglot-pdf-22h1f):
				// stop the clip, release the mic hold FIRST so this press's audio
				// flows, then resolve the pending round-trip as 'interrupted' -- the
				// tool response (telling the model to listen) is sent before the
				// user's buffered speech reaches the model's turn handling.
				spellback.interruptForPtt()
			}
		},

		// Current PTT mode, so an overlay remounted onto a LIVE session (a
		// desktop<->mobile breakpoint cross) can restore the user's actual choice
		// instead of resetting its local state to the default (bd polyglot-pdf-6vo,
		// Codex review PR #119).
		getPushToTalkMode() {
			return pushToTalkMode
		},

		// Lets the UI (VoiceOverlay PTT effect) read the mode the audio layer is
		// configured with. Always true since bd polyglot-pdf-v1m8g.

		sendManualFieldUpdate(fieldId: string, fieldName: string, value: any, verified?: boolean) {
			// Guarded: a verify can land while the socket is down (the form is
			// usable offline -- the client owns all field state). The verification is
			// still recorded locally; only the model's copy is missed, and the
			// handshake re-syncs it on reconnect.
			connection?.sendManualFieldUpdate(fieldId, fieldName, value, verified)
		},

		getFieldManager() {
			return fieldManager
		},

		getAudioManager() {
			// NO logging here (bd polyglot-pdf-2p4y). This is a per-render accessor:
			// both overlays call it once per render, and they re-render ~60x/sec
			// while the mic-energy meter moves. Logging a retained manager object at
			// that rate costs real memory + main-thread time on the phones this
			// overlay targets, and buries every diagnostic log around it -- the same
			// failure the "Debug logging removed - was causing 100+ logs per second"
			// note in VoiceOverlay.tsx records. Nullness is observable via callers.
			// (Sol's per-frame loop does NOT reach here: the overlays cache the
			// manager in a ref, so getOutputEnergy is a plain property read.)
			return audioManager
		},

		async startRecording() {
			console.log('[VFF Connection] startRecording called')

			// TEST harness (bd polyglot-pdf-g8w): the E2E voice harness feeds audio
			// through window.__VFF_TEST_INJECT.sendAudio, so it needs NO microphone.
			// Skip getUserMedia/worklet setup entirely under the harness gate -- in a
			// headless/no-mic browser getUserMedia would reject and drop the session
			// into the connection-failed path even though injection would work fine
			// (Codex review, PR #123). Gated identically to the inject hook.
			if (isTestHarnessEnabled()) {
				console.log('[VFF Connection] TEST harness active -- skipping microphone capture (audio is injected)')
				return
			}

			if (!audioManager) {
				console.error('[VFF Connection] Audio manager not initialized')
				return
			}

			console.log('[VFF Connection] Requesting microphone access...')

			await audioManager.startRecording(sendMicChunkToBackend)
		},

		stopRecording() {
			if (audioManager) {
				audioManager.stopRecording()
			}
		},

		isRecording() {
			return audioManager?.isRecording() ?? false
		},

		setVoiceMode(mode: VoiceMode) {
			// Idempotent: the PTT auto-unmute path can fire on every press, and a
			// re-send per press is pointless traffic. The mode is authoritative
			// CLIENT-side (the backend is stateless and rebuilds from what we tell
			// it), so the local flag is set even when the socket is down -- the
			// (re)connect path re-asserts it.
			if (voiceMode === mode) return
			voiceMode = mode
			console.log('[VFF Connection] Voice mode ->', mode)
			// Entering manual mode: drop what is ALREADY QUEUED. The backend gate
			// stops future proactive turns, but audio authorised before the toggle
			// is already on its way, and would keep talking over a user who just
			// asked for silence. The spell-back clip is a separate audio path with
			// its own player, so it needs its own cancel (bd 22h1f).
			//
			// This is a ONE-SHOT DRAIN, not a mute: chunks of the in-flight turn
			// that arrive AFTER this still play, so a user who toggles mid-sentence
			// hears the rest of that sentence. Bounded to one turn and no worse
			// than the pause() this replaces -- silencing it properly needs a
			// server-side interrupt we do not have. Tracked as bd
			// polyglot-pdf-cdyyl. NOT closed by latching playbackBlocked: that is
			// the unpaired-flush trap (bd nm7z) that silently killed ALL later
			// audio.
			//
			// The mic is deliberately NOT touched in either direction -- manual mode
			// keeps it usable, which is the whole difference from the pause() this
			// replaces. Nothing here sets playbackBlocked, so the flush-without-a-
			// paired-resume trap (bd nm7z) cannot fire: resetPlaybackClock drains
			// what is queued without latching a block, so the NEXT model turn plays
			// normally.
			if (mode === 'manual') {
				spellback.cancel()
				// Feature-detected, not just null-guarded: `?.` protects against a
				// missing MANAGER, not a manager lacking the method, and this runs
				// straight off a click handler -- a TypeError here would blank the
				// overlay rather than merely skip a drain (the same shape as the
				// getAudioManager slip earlier in this bead).
				if (typeof audioManager?.resetPlaybackClock === 'function') {
					audioManager.resetPlaybackClock()
				}
			}
			connection?.setVoiceMode(mode)
			// Tell the UI. Fires for EVERY change, including the PTT auto-unmute
			// that no button click produced -- which is the case a UI cannot
			// observe on its own.
			notifyVoiceMode(mode)
		},

		getVoiceMode() {
			return voiceMode
		},

		onVoiceModeChange(listener: (mode: VoiceMode) => void) {
			voiceModeListeners.add(listener)
			return () => {
				voiceModeListeners.delete(listener)
			}
		},

		isPaused() {
			return paused
		},

		// Re-arm mic capture after an overlay remount onto an already-live session.
		// The WebSocket and Gemini session survive a desktop<->mobile resize flip;
		// the old overlay's unmount stops audio capture via its cleanup path, so the
		// new overlay calls this to re-arm the mic without reconnecting (bd nlfc).
		//
		// Double-arm guard: bail out immediately if audioManager reports it is
		// already recording (e.g. a rapid flip that mounts before the old overlay's
		// cleanup runs, or multiple useEffect firings).
		//
		// PTT/mute re-sync: after arming, re-apply the stored PTT mode so the new
		// overlay's mount-time PTT effect (which fires in the same React batch) sees
		// a consistent state and does not leave the input unmuted when PTT is on.
		async rearmAudioCapture() {
			// Delegates to the shared rehydration routine (bd polyglot-pdf-z9bc):
			// same harness / already-recording / PTT-resync behavior this method had,
			// now handled in one place. The overlay-remount recovery is just another
			// caller of the single arm+resync path.
			await rehydrateAudio('rearmAudioCapture')
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

		// NOTE: no changeSpokenLanguage() here by design. The spoken language is
		// PINNED for the whole form -- set once at session start and held for
		// every turn; changing it means a NEW session ('clear form' -> language
		// modal). This manager used to expose a changeSpokenLanguage() that swapped
		// it on a live session; it had no production caller and was removed
		// (bd polyglot-pdf-87a9). The `change_spoken_language` WS message still
		// exists, but its ONLY live sender is webFormConnection's reconnect opener,
		// which RE-ASSERTS the same pinned language after a socket teardown.

		readDisclaimer(language: string, disclaimerText: string) {
			// Save language to state (disclaimer being read = about to accept)
			const currentState = SchemaFormStateManager.load();
			if (currentState) {
				SchemaFormStateManager.setSelectedLanguage(currentState, language);
			}

			// Send read_disclaimer message to backend. agree_button_label is the
			// TRANSLATED label the DisclaimerModal actually shows, so the voice
			// model names the button the user sees instead of the English
			// 'I Agree' (bd polyglot-pdf-s863). Resolved here so every caller
			// gets it without a signature change.
			if (connection && connection.getStatus() === 'connected') {
				const agreeButtonLabel =
					(BUTTON_TRANSLATIONS[language] || BUTTON_TRANSLATIONS['English']).agree
				connection.send({
					type: 'read_disclaimer',
					spoken_language: language,
					disclaimer_text: disclaimerText,
					agree_button_label: agreeButtonLabel
				})
				console.log('[VFF Connection] [check] Sent read_disclaimer to backend:', language)
			} else {
				console.warn('[VFF Connection] Cannot read disclaimer - not connected')
			}
		},

		// Section management methods (schema-based navigation)

		async switchToFirstSection(language: string) {
			// The SESSION-START trigger after disclaimer accept (both overlays
			// call this). The "FirstSection" name is historical: it routes
			// through startSection, whose continuous-session guard sends the
			// WHOLE-FORM handshake (webFormConnection.startSection), so in
			// continuous mode -- the production default -- this starts the
			// single whole-form session, not a section-scoped one (bd
			// polyglot-pdf-4l7p: verified correct; deliberately not renamed
			// while the legacy section path still exists -- the deletion bead
			// polyglot-pdf-55jg owns any rename).
			// Get first section from schema (sorted by order)
			const currentState = SchemaFormStateManager.load()
			if (!currentState) {
				console.error('[VFF Connection] Cannot switch to first section - no state loaded')
				return
			}

			const sortedSections = [...currentState.schema.sections].sort((a, b) => a.order - b.order)
			const firstSection = sortedSections[0]

			if (!firstSection) {
				console.error('[VFF Connection] Cannot switch to first section - no sections in schema')
				return
			}

			console.log('[VFF Connection] Switching to first section after disclaimer:', firstSection.id)

			// Update fill language before switching
			fillLanguage = language

			// Use startSection which restarts Gemini with form-filling context
			await this.startSection(firstSection.id)
		},

		async startSection(sectionId: string) {
			if (!connection) {
				throw new Error('Connection not initialized')
			}

			// A section (re)start supersedes any pending post-resume re-prompt --
			// the new section's initiating message re-asks its own field
			// (bd polyglot-pdf-yo5t, fresh-eyes gap 2).
			clearResumeReprompt()

			// Stop recording if active
			if (audioManager?.isRecording()) {
				audioManager.stopRecording()
			}

			await connection.startSection(sectionId, connectedUrl)

			// Re-arm the mic through the shared rehydration routine (bd
			// polyglot-pdf-z9bc) -- same paused / harness / idempotency guards as
			// every other reconnect path, plus a PTT re-sync.
			await rehydrateAudio('startSection')
		},

		// DEPRECATED (bd polyglot-pdf-55jg): section-reset production path;
		// continuous-DTI is the live flow. Kept as a fallback, not deleted.
		// Do not extend. (Thin wrapper over the marked connection.switchToSection;
		// distinct from switchToFirstSection, the LIVE session-start trigger.)
		async switchToSection(sectionId: string) {
			if (!connection) {
				throw new Error('Connection not initialized')
			}

			// Same as startSection: a switch supersedes the pending re-prompt
			// (bd polyglot-pdf-yo5t, fresh-eyes gap 2).
			clearResumeReprompt()

			// Stop recording if active (buffer draining handled by WebFormConnection)
			if (audioManager?.isRecording()) {
				audioManager.stopRecording()
			}

			await connection.switchToSection(sectionId, connectedUrl)

			// Re-arm the mic through the shared rehydration routine (bd
			// polyglot-pdf-z9bc) -- same guards + PTT re-sync as every other path.
			await rehydrateAudio('switchToSection')
		},

		// DEPRECATED (bd polyglot-pdf-55jg): section-reset production path;
		// continuous-DTI is the live flow. Kept as a fallback, not deleted.
		// Do not extend. (Thin wrapper over the marked connection.completeSection.)
		async completeSection() {
			if (!connection) {
				throw new Error('Connection not initialized')
			}

			await connection.completeSection(connectedUrl)
		},

		getCurrentSectionId(): string | undefined {
			const state = SchemaFormStateManager.load()
			return state?.currentSectionId
		},

		getCompletedSectionIds(): Set<string> {
			const state = SchemaFormStateManager.load()
			return state?.completedSections || new Set()
		},


		// VAD-based barge-in: Called when VAD detects speech start
		// Sends activity_start signal before audio chunks begin streaming
		onVADSpeechStart() {
			// The user spoke first after an unpause -- their turn supersedes the
			// pending post-resume re-prompt (bd polyglot-pdf-yo5t).
			clearResumeReprompt()
			if (!audioManager) return			// PUSH-TO-TALK MODE: Disable VAD-based barge-in
			if (pushToTalkMode) return

			// Send activity_start signal to Gemini (user started speaking)
			if (connection) {
				connection.sendActivityStart()
			}

			// isModelSpeaking, not isSpeaking (bd polyglot-pdf-uxc6s): an overlap
			// of model PCM with a synthesized clip reads FALSE on isSpeaking(),
			// which skipped this flush while the model was mid-utterance.
			const geminiSpeaking = audioManager.isModelSpeaking()

			// BARGE-IN: If Gemini is currently talking, flush audio queue for instant UX
			if (geminiSpeaking) {
				console.log('[VFF Connection] [mic] VAD detected speech - flushing audio queue')

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

			// DELIBERATELY isSpeaking(), NOT isModelSpeaking (bd polyglot-pdf-uxc6s):
			// this is the RESUME half of the deadlock pair. It must stay the exact
			// complement of the suspend sites -- resuming on a model-only signal
			// while a clip still plays would leave the context suspended mid-clip.
			const geminiSpeaking = audioManager.isSpeaking()

			// Resume audio playback if Gemini stopped (allow Gemini to respond)
			// CRITICAL: This unblocks new audio chunks AND resumes the audio context
			// if it was suspended during tentative pause
			if (!geminiSpeaking) {
				audioManager.resumePlayback()
				audioManager.resumeAudioContext() // Resume context if it was paused
			}

			// Send activity_end signal to flush Gemini's cached audio buffer
			// CRITICAL: Wait for buffered audio to drain before signaling end
			if (connection) {
				connection.sendActivityEnd().catch(err => {
					console.error('[VFF Connection] Failed to send activity_end:', err)
				})
			}

			console.log('[VFF Connection] [mic] VAD speech ended - sent activity_end, audio playback resumed')
		},
	}

	// TEST-ONLY injection hook (bd polyglot-pdf-g8w). Publishes a thin handle the
	// browser E2E voice harness uses to push scripted fixture audio straight into
	// the WS (the same path mic audio takes via sendAudio), bypassing getUserMedia
	// and the worklet. DOUBLE-GATED so it can NEVER attach in production and never
	// in normal local dev: it requires both window.__VFF_LOCAL_DEV (the existing
	// dev override, see config.ts) AND an explicit window.__VFF_TEST_HARNESS opt-in.
	// Re-published on every createConnectionManager call so it tracks the live
	// manager across the disclaimer-driven session restart (switchToFirstSection).
	try {
		if (isTestHarnessEnabled()) {
			window.__VFF_TEST_INJECT = {
				sendAudio: (audioData: ArrayBuffer) => manager.sendAudio(audioData),
				sendActivityStart: () => manager.sendActivityStart(),
				sendActivityEnd: () => manager.sendActivityEnd(),
				getLastNextField: () => lastNextField,
				// bd 0rpu round 2: playback-backlog read for the pacing arms. The
				// POLITE arm injects only after the model's audio has drained
				// (aheadSec ~0); the RUDE arm injects mid-speech (aheadSec high).
				// Pure read, same dev double-gate as the rest of this hook.
				getPlaybackBacklog: () =>
					audioManager
						? audioManager.getPlaybackBacklog()
						: { aheadSec: 0, activeSources: 0, blocked: false },
				// bd polyglot-pdf-o1c: same-page-rerun-safe field clear. Route through
				// SchemaFormStateManager.save (fires schemaFormStateChange so SchemaForm's
				// React state reloads), then refresh BOTH this closure's `state` and the
				// live WebFormConnection.state so neither holds the prior attempt's value.
				resetFieldState: (fieldId: string) => {
					const current = SchemaFormStateManager.load()
					if (current) {
						// Always save + dispatch -- even if this field key is already
						// absent (e.g. a prior legacy-fallback clear removed it). The
						// dispatch is what refreshes SchemaForm's React state and re-paints
						// the DOM from the CLEARED state, so we must not skip it on the
						// already-absent path (Codex/fresh-eyes PR #126). The `field in`
						// check is only to avoid a no-op churn when nothing changed.
						if (fieldId in current.fieldValues) {
							const { [fieldId]: _removed, ...rest } = current.fieldValues
							const cleared: SchemaFormState = { ...current, fieldValues: rest }
							SchemaFormStateManager.save(cleared)
							state = cleared
						} else {
							// Key already gone: re-save the current state to re-dispatch
							// schemaFormStateChange so React/DOM resync to the cleared value.
							SchemaFormStateManager.save(current)
							state = current
						}
					}
					// Pull the (cleared) state into the connection even if storage had no
					// entry at all (keeps the in-memory copy authoritative for the rerun).
					connection?.reloadState()
				},
				// bd polyglot-pdf-8k8 (WS-A multi-section scenario): seed a field as
				// already-filled-AND-confirmed, so the harness can drive ONE numeric
				// field by voice and let the REAL section auto-advance fire when that
				// last unconfirmed field in the section is confirmed. Routes through
				// SchemaFormStateManager.updateField with confirmed:true -- the SAME
				// write path the confirm_field round-trip uses (confirmField ->
				// save) -- so the seeded confirmed flag is indistinguishable from a
				// genuine confirm to readField/computeNextField. Then refresh BOTH this
				// closure's `state` and the live WebFormConnection.state (the same
				// dual-copy discipline resetFieldState uses) so computeNextField, which
				// runs against the connection's in-memory state, sees the seed and can
				// reach the all-confirmed -> switch transition.
				seedFieldConfirmed: (fieldId: string, value: string) => {
					const current = SchemaFormStateManager.load()
					if (!current) {
						return false
					}
					const updated = SchemaFormStateManager.updateField(
						current,
						fieldId,
						value,
						{ confirmed: true, confirmationMethod: 'manual_edit' },
					)
					state = updated
					connection?.reloadState()
					return true
				},
			}
			console.log('[VFF Connection] TEST harness inject hook installed (__VFF_TEST_INJECT)')
		}
	} catch {
		// window may be undefined in non-browser contexts (tests); ignore.
	}

	return manager
}

/**
 * Get backend WebSocket URL
 * Delegates to config module for production/local dev switching
 */
function getBackendUrl(): string {
	return getBackendUrlFromConfig()
}
