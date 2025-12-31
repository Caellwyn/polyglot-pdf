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
 * Cloud Run production WebSocket URL
 * Hardcoded because Firebase Hosting rewrites DO NOT work for WebSockets
 */
const PRODUCTION_WS_URL = 'wss://polyglot-backend-d3mhrrkwfq-uc.a.run.app/ws/fill'

/**
 * Get backend WebSocket URL
 * Uses environment variable set during build (VITE_WS_URL)
 *
 * Development (npm run dev): Defaults to localhost
 * Production: Uses Cloud Run URL directly (Firebase Hosting doesn't support WebSocket rewrites)
 */
export function getBackendUrl(): string {
	const config = getDevConfig()

	// 1. Check for explicit local dev override (window.__VFF_LOCAL_DEV = true)
	if (config.enabled) {
		console.log('[VFF Config] 🔧 LOCAL DEV MODE ENABLED')
		console.log('[VFF Config] Backend URL:', config.backendUrl)
		console.log('[VFF Config] Debug Metrics:', config.debugMetrics)
		return config.backendUrl
	}

	// 2. Use environment variable if set (production builds)
	if (import.meta.env.VITE_WS_URL) {
		console.log('[VFF Config] Using VITE_WS_URL:', import.meta.env.VITE_WS_URL)
		return import.meta.env.VITE_WS_URL
	}

	// 3. Detect production environment: NOT localhost and NOT dev server
	const isProduction = typeof window !== 'undefined' &&
		!window.location.hostname.includes('localhost') &&
		!window.location.hostname.includes('127.0.0.1') &&
		window.location.protocol === 'https:'

	if (isProduction) {
		console.log('[VFF Config] Production detected, using Cloud Run URL:', PRODUCTION_WS_URL)
		return PRODUCTION_WS_URL
	}

	// 4. Development mode fallback: use localhost
	console.log('[VFF Config] Development mode, using localhost')
	return 'ws://localhost:8000/ws/fill'
}

/**
 * Get fallback cloud URL if localhost fails
 * Returns the direct Cloud Run URL (Firebase Hosting doesn't support WebSocket rewrites)
 */
export function getCloudBackendUrl(): string {
	// Use environment variable if set, otherwise use hardcoded Cloud Run URL
	if (import.meta.env.VITE_WS_URL) {
		return import.meta.env.VITE_WS_URL
	}
	return PRODUCTION_WS_URL
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
