/**
 * VAD Configuration Management Hook
 * 
 * Manages loading, saving, and hot-reloading of VAD configuration parameters.
 * Config is stored in localStorage and can be applied to live VAD instance.
 */

import { useState, useEffect, useCallback } from 'react'
import { VADConfig, VAD_PRESETS } from './types'
import { DEFAULT_VAD_CONFIG } from '../demo/useDemoVAD'

const LOCAL_STORAGE_KEY = 'vad-tuning-config'

// Import production defaults from useDemoVAD (single source of truth)
const DEFAULT_CONFIG: VADConfig = DEFAULT_VAD_CONFIG

export interface UseVADConfigResult {
	config: VADConfig
	updateConfig: (updates: Partial<VADConfig>) => void
	resetConfig: () => void
	loadPreset: (presetName: string) => void
	saveToFile: () => void
	isDirty: boolean
}

/**
 * Hook for managing VAD configuration
 * 
 * Features:
 * - Persistent storage in localStorage
 * - Hot-reload capability (config changes trigger callbacks)
 * - Preset management
 * - Export to file (for saving to useDemoVAD.ts / frontend.config.ts)
 */
export function useVADConfig(
	onConfigChange?: (config: VADConfig) => void
): UseVADConfigResult {
	const [config, setConfig] = useState<VADConfig>(() => {
		// Try to load from localStorage
		const stored = localStorage.getItem(LOCAL_STORAGE_KEY)
		if (stored) {
			try {
				return JSON.parse(stored) as VADConfig
			} catch (e) {
				console.error('Failed to parse stored VAD config:', e)
			}
		}
		return DEFAULT_CONFIG
	})

	const [initialConfig] = useState(config)
	const isDirty = JSON.stringify(config) !== JSON.stringify(initialConfig)

	// Save to localStorage whenever config changes
	useEffect(() => {
		localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(config))
		onConfigChange?.(config)
	}, [config, onConfigChange])

	const updateConfig = useCallback((updates: Partial<VADConfig>) => {
		setConfig(prev => ({ ...prev, ...updates }))
	}, [])

	const resetConfig = useCallback(() => {
		setConfig(DEFAULT_CONFIG)
	}, [])

	const loadPreset = useCallback((presetName: string) => {
		const preset = VAD_PRESETS.find(p => p.name === presetName)
		if (preset) {
			setConfig(preset.config)
		}
	}, [])

	const saveToFile = useCallback(() => {
		// Generate code snippets for copying to source files
		const useDemoVADSnippet = `// Update these values in useDemoVAD.ts:
positiveSpeechThreshold: ${config.positiveSpeechThreshold},
negativeSpeechThreshold: ${config.negativeSpeechThreshold},
minSpeechMs: ${config.minSpeechMs},
redemptionMs: ${config.redemptionMs},`

		const output = `// VAD Configuration Export
// Generated: ${new Date().toISOString()}

${useDemoVADSnippet}

// Full config object (for reference):
${JSON.stringify(config, null, 2)}`

		// Create download
		const blob = new Blob([output], { type: 'text/plain' })
		const url = URL.createObjectURL(blob)
		const a = document.createElement('a')
		a.href = url
		a.download = `vad-config-${Date.now()}.txt`
		document.body.appendChild(a)
		a.click()
		document.body.removeChild(a)
		URL.revokeObjectURL(url)

		console.log('📄 Config exported:\n', output)
	}, [config])

	return {
		config,
		updateConfig,
		resetConfig,
		loadPreset,
		saveToFile,
		isDirty,
	}
}
