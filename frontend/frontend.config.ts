/**
 * Frontend Configuration
 * 
 * Centralized tunable parameters for the voice form filler.
 * These values control timing, thresholds, and behavior that may need adjustment.
 */

export const FRONTEND_CONFIG = {
	// === VAD (Voice Activity Detection) ===
	// NOTE: VAD parameters are now in useDemoVAD.ts (minSpeechMs, redemptionMs, thresholds)
	// This config file is for non-VAD frontend parameters only
	
	// === Activity Watchdog (Inactivity Recovery) ===
	
	/** How often to check for inactivity (ms) */
	WATCHDOG_CHECK_INTERVAL_MS: 1000,
	
	/** How long without activity before triggering intervention (ms) */
	INACTIVITY_TIMEOUT_MS: 6000,  // 6 seconds
	
	/** Maximum number of escalation levels before disconnect */
	MAX_ESCALATION_LEVEL: 3,  // 3 levels (6s, 12s, 18s = 18 seconds total)
	
	/** Delay after Level 3 prompt before disconnect (ms) - allows TTS to finish */
	LEVEL_3_DISCONNECT_DELAY_MS: 2000,
	
	// === Audio & Connection ===
	
	/** Audio sample rate for recording (Hz) */
	AUDIO_SAMPLE_RATE: 16000,
	
	/** WebSocket reconnect delay (ms) */
	WS_RECONNECT_DELAY_MS: 1000,
	
	// === UI Timing ===
	
	/** Delay after connect before starting recording (ms) */
	CONNECT_STARTUP_DELAY_MS: 100,
} as const

// Type for config (useful for type checking)
export type FrontendConfig = typeof FRONTEND_CONFIG
