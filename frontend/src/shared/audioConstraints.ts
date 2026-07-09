/**
 * Canonical microphone capture constraints (bd polyglot-pdf-gnmo).
 *
 * Acoustic echo cancellation (AEC) matters for Gemini native VAD: if Gemini's
 * own playback leaks back into the mic, its server-side VAD can register the
 * echo as a user barge-in, desync the turn state, and (on 2.5 native-audio) tear
 * the WebSocket down with a 1011. The single most important lever is browser AEC
 * on the capture stream -- echoCancellation cancels the system audio output (our
 * Web Audio playback of Gemini's voice) at the device level, independent of the
 * separate playback AudioContext.
 *
 * These constraints were duplicated across four call sites with drifting values
 * (some omitted channelCount); this is the ONE definition they all consume so an
 * AEC change lands everywhere at once rather than in three of four places.
 *
 * NOTE: this deliberately uses ONLY the standard, spec'd MediaTrackConstraints.
 * The legacy Chrome-specific `goog*` echo hints were considered and rejected --
 * they are removed/ignored in modern Chrome and risk OverconstrainedError, which
 * would be a capture regression for a speculative gain. Any stronger AEC (e.g.
 * coupling capture+playback graphs, or software echo suppression) needs a live
 * echo-leak measurement first and is tracked on the bead, not shipped blind.
 */
export const MIC_AUDIO_CONSTRAINTS: MediaTrackConstraints = {
	channelCount: 1, // Mono (matches 16kHz PCM16 recording sent to Gemini)
	echoCancellation: true, // Cancel Gemini's playback leaking into the mic
	noiseSuppression: true, // Reduce background noise
	autoGainControl: true, // Normalize microphone volume
}
