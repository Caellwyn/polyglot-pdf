/**
 * VAD Tuning Lab - UI Management
 * Handles UI updates, logging, and metrics display
 */

import { state, targets, scenarioNames, statusIcons } from './state.js'

// UI Elements (initialized in init())
let elements = {}

export function initUI() {
	elements = {
		scenarioCards: document.querySelectorAll('.scenario-card'),
		btnConnect: document.getElementById('btnConnect'),
		btnEndTest: document.getElementById('btnEndTest'),
		btnAbortTest: document.getElementById('btnAbortTest'),
		btnUpdateVAD: document.getElementById('btnUpdateVAD'),
		btnResetVAD: document.getElementById('btnResetVAD'),
		btnExportAll: document.getElementById('btnExportAll'),
		btnClearData: document.getElementById('btnClearData'),
		connectionStatus: document.getElementById('connectionStatus'),
		experimentLog: document.getElementById('experimentLog'),
		currentScenarioDisplay: document.getElementById('currentScenario'),
		testRunNumberDisplay: document.getElementById('testRunNumber'),
		savedRunsList: document.getElementById('savedRunsList'),
		resultsComparison: document.getElementById('resultsComparison'),
		vadStartSensitivity: document.getElementById('vadStartSensitivity'),
		vadEndSensitivity: document.getElementById('vadEndSensitivity'),
		vadPrefixPadding: document.getElementById('vadPrefixPadding'),
		vadSilenceDuration: document.getElementById('vadSilenceDuration'),
		vadStatus: document.getElementById('vadStatus'),
		vadStatusText: document.getElementById('vadStatusText')
	}
	
	updateScenarioDisplay()
}

export function getElements() {
	return elements
}

export function updateConnectionStatus(status, message) {
	elements.connectionStatus.className = `status ${status}`
	elements.connectionStatus.textContent = `${statusIcons[status]} ${message}`
}

export function logToUI(message) {
	const entry = document.createElement('div')
	entry.className = 'log-entry'
	entry.innerHTML = `
		<div class="timestamp">${new Date().toLocaleTimeString()}</div>
		<div class="message">${message}</div>
	`
	elements.experimentLog.insertBefore(entry, elements.experimentLog.firstChild)
	
	// Keep only last 50 entries
	while (elements.experimentLog.children.length > 50) {
		elements.experimentLog.removeChild(elements.experimentLog.lastChild)
	}
}

export function updateScenarioDisplay() {
	elements.currentScenarioDisplay.textContent = scenarioNames[state.currentScenario]
}

export function updateLiveMetrics() {
	if (!window.__VFF_METRICS__) return

	const stats = window.__VFF_METRICS__.getStats()
	if (!stats) return

	// Update metric values
	document.getElementById('metricBargeIns').textContent = stats.totalBargeIns || 0
	document.getElementById('metricAvgLatency').textContent = 
		stats.avgBargeInLatency > 0 ? Math.round(stats.avgBargeInLatency) : '—'
	document.getElementById('metricP95Latency').textContent = 
		stats.p95BargeInLatency > 0 ? Math.round(stats.p95BargeInLatency) : '—'
	document.getElementById('metricToolCalls').textContent = stats.totalToolCalls || 0
	document.getElementById('metricHallucinations').textContent = stats.hallucinatedToolCalls || 0
	document.getElementById('metricFalseStarts').textContent = stats.falseStarts || 0

	// Apply color coding based on targets
	const p95Box = document.getElementById('metricP95Latency').parentElement
	const avgBox = document.getElementById('metricAvgLatency').parentElement
	
	if (stats.p95BargeInLatency > 0) {
		p95Box.className = 'metric-box ' + (stats.p95BargeInLatency <= targets.p95BargeInLatency ? 'good' : 
			stats.p95BargeInLatency <= targets.p95BargeInLatency * 1.2 ? 'warning' : 'bad')
	}
	
	if (stats.avgBargeInLatency > 0) {
		avgBox.className = 'metric-box ' + (stats.avgBargeInLatency <= targets.avgBargeInLatency ? 'good' : 
			stats.avgBargeInLatency <= targets.avgBargeInLatency * 1.2 ? 'warning' : 'bad')
	}
}

export function resetMetricsDisplay() {
	document.getElementById('metricBargeIns').textContent = '0'
	document.getElementById('metricAvgLatency').textContent = '—'
	document.getElementById('metricP95Latency').textContent = '—'
	document.getElementById('metricToolCalls').textContent = '0'
	document.getElementById('metricHallucinations').textContent = '0'
	document.getElementById('metricFalseStarts').textContent = '0'
}

export function clearForm() {
	const fields = ['fullName', 'email', 'phone', 'department', 'comments']
	fields.forEach(fieldId => {
		const field = document.getElementById(fieldId)
		if (field) {
			field.value = ''
			// Also dispatch change event to ensure it's cleared
			field.dispatchEvent(new Event('change', { bubbles: true }))
		}
	})
	
	// Clear hallucination checkboxes
	document.querySelectorAll('.hallucination-marker').forEach(checkbox => {
		checkbox.checked = false
	})
	
	logToUI('🗑️ Form cleared')
}
