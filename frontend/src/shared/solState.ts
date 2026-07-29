/**
 * solState -- the pure status -> Sol-state mapping (bd polyglot-pdf-2p4y).
 *
 * Sol is the single avatar that replaced the connection dot, the level meter and
 * the mobile pulsing circle. It has SIX visual states; the app, however, carries
 * session state in three separate loosely-typed signals:
 *
 *   - `status`   a string that is NOT the ConnectionStatus union in practice --
 *                the UI layer injects extra values ('Ready', 'Setting up audio...',
 *                'paused', '*warming*', 'connected <suffix>'), so this maps
 *                defensively over lowercased substrings rather than a switch on
 *                the union.
 *   - `thinking` the backend agent_processing flag (user turn ended, no audio yet).
 *   - `speaking` whether Gemini's audio is currently playing out.
 *
 * Keeping the mapping here -- pure, with no React and no DOM -- is what lets the
 * precedence rules be unit-tested against every status string the overlays can
 * actually receive, instead of being re-derived (and drifting) inside each of the
 * two hand-duplicated overlay components.
 */

/** The six states Sol can render. Drives the `data-state` attribute. */
export type SolState =
	| 'idle'
	| 'listening'
	| 'thinking'
	| 'speaking'
	| 'paused'
	| 'offline'

export interface SolStateInputs {
	/** Raw overlay status string (see the caveat above -- not a clean union). */
	status: string
	/** Backend agent_processing flag: the turn is being worked on. */
	thinking?: boolean
	/** Gemini audio is playing out right now. */
	speaking?: boolean
	/**
	 * Mic audio is genuinely reaching the backend (the connection send gate said
	 * yes). Only then is "listening" honest -- see the isListening comments in the
	 * overlays: during `reconnecting` / `switching_section` the socket may drop
	 * audio, so a listening cue there would lie.
	 */
	micSending?: boolean
}

/**
 * True for a steady, audio-carrying session. Mirrors the `isListening` gate in
 * both overlays: `connected` or `connected <suffix>` ONLY -- deliberately NOT the
 * broader isConnected (which stays true through `reconnecting`) and NOT
 * `switching_section`, where the socket can be closed mid-switch.
 */
function isLiveSession(s: string): boolean {
	return s === 'connected' || s.startsWith('connected ')
}

/**
 * Terminal / not-connected states where Sol should LEAVE rather than dim. The
 * prototype's rule: connection loss is the one state allowed to be unreassuring,
 * so it is visually distinct from paused rather than a shade of it.
 */
function isOffline(s: string): boolean {
	return (
		s === 'disconnected' ||
		s === 'error' ||
		s === 'idle_timeout' ||
		s === 'reconnect_failed'
	)
}

/**
 * Map the app's session signals onto one of Sol's six states.
 *
 * Precedence, highest first:
 *   1. paused   -- an explicit user choice; it outranks everything, because
 *                  showing "listening" or "thinking" while the user has paused
 *                  would be a lie about whether we are consuming their mic.
 *   2. offline  -- something is actually wrong; never dress it up as activity.
 *   3. speaking -- Gemini's audio is audible RIGHT NOW, so it beats `thinking`
 *                  (the backend can leave agent_processing armed into the first
 *                  audio frames) and beats `listening`.
 *   4. thinking -- turn taken, working, no audio yet.
 *   5. listening-- live session actually forwarding mic audio.
 *   6. idle     -- everything else: pre-connect ('Ready'), 'connecting',
 *                  'Setting up audio...', 'warming', 'switching_section',
 *                  'reconnecting'. Warm and awake, committing to nothing.
 *
 * Note 3-5 are gated on a live session: a stale `speaking`/`thinking` flag left
 * over from a dropped socket must not animate Sol while the session is down.
 */
export function deriveSolState(inputs: SolStateInputs): SolState {
	const s = (inputs.status || '').toLowerCase()

	if (s === 'paused') return 'paused'
	if (isOffline(s)) return 'offline'

	const live = isLiveSession(s)
	if (live && inputs.speaking) return 'speaking'
	if (live && inputs.thinking) return 'thinking'
	if (live && inputs.micSending) return 'listening'

	return 'idle'
}

/**
 * Short, language-neutral-ish label for the state. Used for the accessible name
 * (aria-label / title) -- Sol itself carries NO text, by design, so this exists
 * only for screen readers and tooltips, where an English string is correct
 * because the surrounding assistive tech is already language-configured.
 */
export const SOL_STATE_LABEL: Record<SolState, string> = {
	idle: 'Ready',
	listening: 'Listening',
	thinking: 'Working',
	speaking: 'Speaking',
	paused: 'Paused',
	offline: 'Not connected',
}
