/**
 * Local Development Configuration
 * 
 * Override backend URL for local testing without deployment.
 * Enable by setting window.__VFF_LOCAL_DEV = true before loading bookmarklet.
 */

export interface DevConfig {
	enabled: boolean
	backendUrl: string
	debugMetrics: boolean
}

/**
 * Get development configuration from window or defaults
 */
export function getDevConfig(): DevConfig {
	// Check for local dev override
	const localDev = (window as any).__VFF_LOCAL_DEV
	const customBackendUrl = (window as any).__VFF_BACKEND_URL
	const debugMetrics = (window as any).__VFF_DEBUG_METRICS
	
	return {
		enabled: Boolean(localDev),
		backendUrl: customBackendUrl || 'ws://localhost:8000/ws/fill',
		debugMetrics: Boolean(debugMetrics) || Boolean(localDev), // Auto-enable debug in local dev
	}
}

/**
 * Get backend WebSocket URL based on environment
 * 
 * Development: Tries ws://localhost:8000/ws/fill first, falls back to cloud
 * Production: wss://voice-form-filler-4qyc6wagea-uc.a.run.app/ws/fill
 * 
 * To force local dev, run in browser console BEFORE loading bookmarklet:
 * ```javascript
 * window.__VFF_LOCAL_DEV = true
 * ```
 */
/**
 * Get backend WebSocket URL
 * Uses environment variable set during build (VITE_WS_URL)
 * Falls back to localhost for local development
 */
export function getBackendUrl(): string {
	const config = getDevConfig()
	
	if (config.enabled) {
		console.log('[VFF Config] 🔧 LOCAL DEV MODE ENABLED')
		console.log('[VFF Config] Backend URL:', config.backendUrl)
		console.log('[VFF Config] Debug Metrics:', config.debugMetrics)
		return config.backendUrl
	}
	
	// Use environment variable if set (production builds)
	if (import.meta.env.VITE_WS_URL) {
		return import.meta.env.VITE_WS_URL
	}
	
	// Default to localhost for local development
	return 'ws://localhost:8000/ws/fill'
}

/**
 * Get fallback cloud URL if localhost fails
 * This should match the production backend URL
 */
export function getCloudBackendUrl(): string {
	// Use the same URL as production (matches deploy-demo.sh)
	return 'wss://voice-form-filler-773443099751.us-central1.run.app/ws/fill'
}

/**
 * Check if debug metrics should be enabled
 */
export function isDebugMetricsEnabled(): boolean {
	return getDevConfig().debugMetrics
}

/**
 * Print development configuration help
 */
export function printDevHelp(): void {
	console.log('\n' + '='.repeat(60))
	console.log('🔧 VOICE FORM FILLER - LOCAL DEVELOPMENT MODE')
	console.log('='.repeat(60))
	console.log('\nTo test locally without deploying:')
	console.log('\n1. Start backend:')
	console.log('   cd backend')
	console.log('   source venv/bin/activate  # or venv\\Scripts\\activate on Windows')
	console.log('   uvicorn main:app --reload --port 8000')
	console.log('\n2. Enable local dev in browser console:')
	console.log('   window.__VFF_LOCAL_DEV = true')
	console.log('\n3. Load bookmarklet (will connect to localhost:8000)')
	console.log('\n4. Test VAD tuning changes:')
	console.log('   - Edit backend/adapters/live_ai_gemini.py')
	console.log('   - Backend auto-reloads (--reload flag)')
	console.log('   - Reconnect bookmarklet to test')
	console.log('\nOptional environment variables:')
	console.log('   window.__VFF_BACKEND_URL = "ws://localhost:8000/ws/fill"  // Custom URL')
	console.log('   window.__VFF_DEBUG_METRICS = true                          // Extra logging')
	console.log('\n' + '='.repeat(60) + '\n')
}

// Auto-print help if local dev mode is enabled
if (typeof window !== 'undefined' && getDevConfig().enabled) {
	printDevHelp()
}
