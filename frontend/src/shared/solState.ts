/**
 * solState -- the pure status -> Sol-state mapping (bd polyglot-pdf-2p4y).
 *
 * Sol is the single avatar that replaced the connection dot, the level meter and
 * the mobile pulsing circle. It has SEVEN visual states; the app, however, carries
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

/** The states Sol can render. Drives the `data-state` attribute. */
export type SolState =
	| 'idle'
	| 'connecting'
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
	/**
	 * A synthesized CLIP is audible right now (spell-back, or Sol's scripted
	 * intro) -- bd polyglot-pdf-s1iex.4.
	 *
	 * Separate from `speaking` because it is NOT gated on a live session: the
	 * intro clip plays with no Gemini session at all (the epic deletes the
	 * pre-Agree connect), and a clip can also outlive a socket drop. The
	 * stale-flag hazard the live gate exists to prevent does not apply here --
	 * this flag is set and cleared by the audio element's own lifecycle
	 * (attach -> ended/error/cancel), not by a backend message that can be
	 * left armed by a dropped connection.
	 *
	 * It does NOT outrank `paused` or `offline`: a user who paused, or a
	 * session that failed, must not see an animated Sol.
	 */
	clipPlaying?: boolean
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
		s === 'reconnect_failed' ||
		// The link's spend ceiling is used up (bd polyglot-pdf-cke6v). Voice is
		// over for good, so Sol LEAVES rather than dimming -- dimming reads as
		// "paused, coming back", which is the one thing this state is not.
		s === 'budget_exhausted'
	)
}

/**
 * Coming up, or recovering: a session exists (or is being (re)established) but is
 * not yet carrying audio.
 *
 * This is deliberately NOT folded into `idle`. The invariant from bd
 * polyglot-pdf-bxng is that a live-but-transient session must stay visually
 * distinguishable from one that is not running -- and on the collapsed mobile
 * FAB, Sol is the ONLY status the user can see (there is no accompanying status
 * text there). Mapping `reconnecting` to the same picture as a cold, never-
 * started session would reintroduce exactly the bug bxng fixed, in a new guise.
 */
function isConnecting(s: string): boolean {
	return (
		s === 'connecting' ||
		s === 'switching_section' ||
		s.startsWith('reconnecting') ||
		s.includes('warming') ||
		s.startsWith('setting up')
	)
}

/**
 * Map the app's session signals onto one of Sol's seven states.
 *
 * Precedence, highest first:
 *   1. paused   -- an explicit user choice; it outranks everything, because
 *                  showing "listening" or "thinking" while the user has paused
 *                  would be a lie about whether we are consuming their mic.
 *   2. offline  -- something is actually wrong; never dress it up as activity.
 *   3. speaking -- Gemini's audio is audible RIGHT NOW, so it beats `thinking`
 *                  (the backend can leave agent_processing armed into the first
 *                  audio frames) and beats `listening`. A synthesized CLIP
 *                  (`clipPlaying`) also lands here and is NOT gated on a live
 *                  session -- Sol's intro clip speaks before any session
 *                  exists (bd polyglot-pdf-s1iex.4).
 *   4. thinking -- turn taken, working, no audio yet.
 *   5. listening-- live session actually forwarding mic audio.
 *   6. connecting-- coming up or recovering: 'connecting', 'reconnecting',
 *                  'switching_section', 'warming', 'Setting up audio...'.
 *                  Distinct from idle so a live-but-transient session never
 *                  looks like a cold one (bd polyglot-pdf-bxng).
 *   7. idle     -- everything else, i.e. genuinely pre-session ('Ready').
 *                  Warm and awake, committing to nothing.
 *
 * Note 3-5 are gated on a live session: a stale `speaking`/`thinking` flag left
 * over from a dropped socket must not animate Sol while the session is down.
 */
export function deriveSolState(inputs: SolStateInputs): SolState {
	const s = (inputs.status || '').toLowerCase()

	if (s === 'paused') return 'paused'
	if (isOffline(s)) return 'offline'

	// A clip is real audible speech with no session behind it -- checked before
	// the live gate, but AFTER paused/offline above (bd polyglot-pdf-s1iex.4).
	if (inputs.clipPlaying) return 'speaking'

	const live = isLiveSession(s)
	if (live && inputs.speaking) return 'speaking'
	if (live && inputs.thinking) return 'thinking'
	if (live && inputs.micSending) return 'listening'

	// Checked AFTER the live-session activity states: `switching_section` is
	// "connecting" only in the sense that audio is briefly not flowing, and a
	// steady `connected` session never reaches here anyway.
	if (isConnecting(s)) return 'connecting'

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
	connecting: 'Connecting',
	listening: 'Listening',
	thinking: 'Working',
	speaking: 'Speaking',
	paused: 'Paused',
	offline: 'Not connected',
}
