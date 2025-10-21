/**
 * VAD Tuning Lab - Event Handlers
 * Manages all user interactions and bookmarklet lifecycle
 */

import { state, ExperimentData } from './state.js'
import { getElements, updateConnectionStatus, logToUI, updateScenarioDisplay, clearForm, resetMetricsDisplay, updateLiveMetrics } from './ui.js'
import { loadSavedRuns, exportAllData, clearAllData } from './metrics.js'

// State management
let isTestRunActive = false

export function initEventHandlers() {
	const elements = getElements()
	
	// Connect button - auto-starts test run
	elements.btnConnect.addEventListener('click', async () => {
		try {
			updateConnectionStatus('connecting', 'Connecting to backend...')
			logToUI('🚀 Starting Voice Form Filler bookmarklet...')

			// Check if bookmarklet loaded
			if (!window.VoiceFormFiller) {
				throw new Error('Bookmarklet not loaded! Did you run npm run build:bookmarklet?')
			}

			// Inject the bookmarklet
			window.VoiceFormFiller.inject({
				wsUrl: 'ws://localhost:8000',
				debug: true
			})

			logToUI('✅ Bookmarklet injected - connecting to backend...')

			// Open WebSocket to backend for VAD config updates
			state.ws = new WebSocket('ws://localhost:8000/ws/vad-config')
			
			state.ws.onopen = () => {
				updateConnectionStatus('connected', 'Connected')
				elements.btnConnect.disabled = true
				logToUI('✅ VAD config WebSocket connected')
				
				// Send current VAD config immediately if it's been modified
				if (state.vadConfig.startSensitivity !== 'UNSPECIFIED' || 
					state.vadConfig.endSensitivity !== 'UNSPECIFIED' ||
					state.vadConfig.prefixPadding !== 120 ||
					state.vadConfig.silenceDuration !== 250) {
					const message = {
						type: 'update_vad_config',
						config: state.vadConfig
					}
					state.ws.send(JSON.stringify(message))
					logToUI(`🎛️ Sent pre-configured VAD settings to backend`)
				}
				
				// Auto-start test run
				setTimeout(() => {
					state.testRunNumber++
					elements.testRunNumberDisplay.textContent = state.testRunNumber
					
					state.currentTestRun = new ExperimentData(state.currentScenario, state.testRunNumber)
					state.currentTestRun.addEvent('start', `🚀 Started run #${state.testRunNumber} - Scenario ${state.currentScenario}`)
					
					isTestRunActive = true
					elements.btnEndTest.disabled = false
					elements.btnAbortTest.disabled = false
					elements.scenarioCards.forEach(card => card.style.pointerEvents = 'none')
					
					logToUI(`📊 Test Run #${state.testRunNumber} started (Scenario ${state.currentScenario})`)
					logToUI('🎤 Start talking to the form!')
				}, 500) // Small delay to ensure everything is ready
			}
			
			state.ws.onerror = (error) => {
				updateConnectionStatus('error', 'VAD config connection failed')
				logToUI('⚠️ VAD config WebSocket error (this is OK if bookmarklet connected)')
				console.error(error)
			}
			
			state.ws.onclose = () => {
				logToUI('VAD config WebSocket closed')
			}

		} catch (error) {
			updateConnectionStatus('error', error.message)
			logToUI('❌ Connection failed: ' + error.message)
		}
	})

	// End test run - save metrics and cleanup
	elements.btnEndTest.addEventListener('click', () => {
		if (!confirm('This will end the test, save metrics, and disconnect. Continue?')) return
		
		// Collect hallucinated fields
		const hallucinatedFields = []
		document.querySelectorAll('.hallucination-marker').forEach(checkbox => {
			if (checkbox.checked) {
				const fieldId = checkbox.id.replace('halluc_', '')
				hallucinatedFields.push(fieldId)
			}
		})
		
		// End test run with metrics and hallucination data (SAVES to localStorage)
		endTestRun(hallucinatedFields)
		
		// Perform cleanup
		performCleanup()
	})

	// Abort test run - cleanup WITHOUT saving
	elements.btnAbortTest.addEventListener('click', () => {
		if (!confirm('This will abort the test WITHOUT saving metrics. Continue?')) return
		
		if (state.currentTestRun) {
			logToUI(`🚫 Aborted run #${state.testRunNumber} (NOT saved)`)
			state.currentTestRun = null
			isTestRunActive = false
		}
		
		// Perform cleanup (but DON'T call endTestRun, so no save)
		performCleanup()
	})

	// Update VAD config button - Now works BEFORE connecting
	elements.btnUpdateVAD.addEventListener('click', () => {
		const vadConfig = {
			startSensitivity: elements.vadStartSensitivity.value,
			endSensitivity: elements.vadEndSensitivity.value,
			prefixPadding: parseInt(elements.vadPrefixPadding.value),
			silenceDuration: parseInt(elements.vadSilenceDuration.value)
		}

		state.vadConfig = vadConfig

		elements.vadStatus.style.display = 'block'
		
		// If WebSocket is open, send immediately
		if (state.ws && state.ws.readyState === WebSocket.OPEN) {
			elements.vadStatusText.textContent = 'Sending configuration...'
			
			const message = {
				type: 'update_vad_config',
				config: vadConfig
			}

			state.ws.send(JSON.stringify(message))
			logToUI(`🎛️ Updated VAD config (sent to backend): ${JSON.stringify(vadConfig)}`)

			setTimeout(() => {
				elements.vadStatusText.textContent = 'Configuration sent! Backend should auto-reload.'
				setTimeout(() => {
					elements.vadStatus.style.display = 'none'
				}, 3000)
			}, 500)
		} else {
			// Not connected yet - just save to state for next connection
			elements.vadStatusText.textContent = 'Configuration saved! Will be used when test starts.'
			logToUI(`🎛️ Updated VAD config (will apply on connect): ${JSON.stringify(vadConfig)}`)
			
			setTimeout(() => {
				elements.vadStatus.style.display = 'none'
			}, 2000)
		}
	})

	// Reset VAD to defaults
	elements.btnResetVAD.addEventListener('click', () => {
		elements.vadStartSensitivity.value = 'UNSPECIFIED'
		elements.vadEndSensitivity.value = 'UNSPECIFIED'
		elements.vadPrefixPadding.value = '120'
		elements.vadSilenceDuration.value = '250'
		state.vadConfig = {
			startSensitivity: 'UNSPECIFIED',
			endSensitivity: 'UNSPECIFIED',
			prefixPadding: 120,
			silenceDuration: 250
		}
		logToUI('↺ Reset VAD config to defaults')
	})

	// Scenario selection
	elements.scenarioCards.forEach(card => {
		card.addEventListener('click', () => {
			if (isTestRunActive) {
				alert('Cannot change scenario during active test run!')
				return
			}
			elements.scenarioCards.forEach(c => c.classList.remove('active'))
			card.classList.add('active')
			state.currentScenario = card.dataset.scenario
			updateScenarioDisplay()
		})
	})

	// Export all data
	elements.btnExportAll.addEventListener('click', () => {
		// Handled by window.vadLab.exportAllData()
		exportAllData()
	})

	// Clear all data
	elements.btnClearData.addEventListener('click', () => {
		// Handled by window.vadLab.clearAllData()
		clearAllData()
	})

	// Update metrics every second during test run
	setInterval(() => {
		if (isTestRunActive) {
			updateLiveMetrics()
		}
	}, 1000)

	// Load saved runs on init
	loadSavedRuns()
}

// Cleanup function for disconnecting and resetting
function performCleanup() {
	const elements = getElements()
	
	// Destroy the bookmarklet - force destroy even if isActive returns false
	if (window.VoiceFormFiller) {
		try {
			window.VoiceFormFiller.destroy()
			logToUI('🛑 Bookmarklet destroyed')
		} catch (e) {
			console.error('Error destroying bookmarklet:', e)
			logToUI('⚠️ Error destroying bookmarklet (may already be destroyed)')
		}
	}
	
	// Close VAD config WebSocket
	if (state.ws) {
		state.ws.close()
		state.ws = null
		logToUI('🔌 VAD config WebSocket closed')
	}
	
	// Clear sessionStorage (used by bookmarklet for form state)
	sessionStorage.clear()
	logToUI('🗑️ Session storage cleared')
	
	// Clear form fields
	clearForm()
	
	// Reset connection state
	updateConnectionStatus('idle', 'Not Connected')
	elements.btnConnect.disabled = false
	elements.btnEndTest.disabled = true
	elements.btnAbortTest.disabled = true
	// VAD Config button stays enabled - can configure before connecting
	elements.scenarioCards.forEach(card => card.style.pointerEvents = 'auto')
	
	// Reset metrics display
	resetMetricsDisplay()
	
	logToUI('🔌 Disconnected and reset')
	
	// Force a small delay to ensure everything is cleaned up
	setTimeout(() => {
		console.log('[VAD Lab] Cleanup complete. Ready for new session.')
	}, 100)
}

function endTestRun(hallucinatedFields = []) {
	if (!state.currentTestRun) return
	
	console.log('[VAD Lab] Ending test run, checking metrics...')
	console.log('[VAD Lab] window.__VFF_METRICS__ exists:', !!window.__VFF_METRICS__)
	
	const metrics = window.__VFF_METRICS__?.getStats() || null
	
	console.log('[VAD Lab] Metrics retrieved:', metrics)
	
	if (!metrics) {
		logToUI('⚠️ Warning: No metrics available - session may not have started properly')
		console.warn('[VAD Lab] No metrics available. Possible reasons:')
		console.warn('  1. Session never connected (onSessionReady not fired)')
		console.warn('  2. No barge-ins or interactions occurred')
		console.warn('  3. Metrics not properly initialized')
	}
	
	state.currentTestRun.complete(metrics, hallucinatedFields)
	state.currentTestRun.addEvent('end', `⏹️ Ended run #${state.testRunNumber}`)
	state.currentTestRun.save()

	logToUI('💾 Saved to localStorage')
	if (metrics) {
		logToUI(`📈 P95: ${Math.round(metrics.p95BargeInLatency)}ms, Hallucinations: ${metrics.hallucinatedToolCalls}`)
	}
	if (hallucinatedFields.length > 0) {
		logToUI(`⚠️ User marked ${hallucinatedFields.length} field(s) as hallucinated: ${hallucinatedFields.join(', ')}`)
	}

	isTestRunActive = false
	state.currentTestRun = null
	
	// Reload saved runs to show the new one
	loadSavedRuns()
}
