/**
 * VAD Tuning Lab - Metrics Management
 * Handles saved runs, comparisons, and data export
 */

import { state, targets, scenarioNames } from './state.js'
import { getElements } from './ui.js'

export function loadSavedRuns() {
	const elements = getElements()
	const runs = []
	
	for (let i = 0; i < localStorage.length; i++) {
		const key = localStorage.key(i)
		if (key.startsWith('vad_experiment_')) {
			try {
				const data = JSON.parse(localStorage.getItem(key))
				runs.push({ key, data })
			} catch (e) {
				console.error('Failed to parse saved run:', key, e)
			}
		}
	}
	
	// Sort by timestamp (newest first)
	runs.sort((a, b) => new Date(b.data.startTime) - new Date(a.data.startTime))
	
	// Display saved runs
	if (runs.length === 0) {
		elements.savedRunsList.innerHTML = '<div class="no-data">No saved runs yet</div>'
		return
	}
	
	elements.savedRunsList.innerHTML = runs.map(({ key, data }) => `
		<div class="saved-run-card">
			<div class="run-header">
				<strong>${scenarioNames[data.scenario]}</strong>
				<span class="run-number">Run ${data.runNumber}</span>
			</div>
			<div class="run-timestamp">${new Date(data.startTime).toLocaleString()}</div>
			${data.metrics ? `
				<div class="run-metrics">
					${data.metrics.totalBargeIns > 0 ? `
						<div class="metric-item">
							<span class="metric-label">P95 Latency:</span>
							<span class="metric-value ${getLatencyClass(data.metrics.p95BargeInLatency, targets.p95BargeInLatency)}">
								${Math.round(data.metrics.p95BargeInLatency)}ms
							</span>
						</div>
						<div class="metric-item">
							<span class="metric-label">Avg Latency:</span>
							<span class="metric-value ${getLatencyClass(data.metrics.avgBargeInLatency, targets.avgBargeInLatency)}">
								${Math.round(data.metrics.avgBargeInLatency)}ms
							</span>
						</div>
						<div class="metric-item">
							<span class="metric-label">Barge-Ins:</span>
							<span class="metric-value good">
								${data.metrics.totalBargeIns}
							</span>
						</div>
					` : `
						<div class="metric-item">
							<span class="metric-label">Barge-Ins:</span>
							<span class="metric-value" style="color: #999;">
								0 (no interruptions)
							</span>
						</div>
					`}
					<div class="metric-item">
						<span class="metric-label">Tool Calls:</span>
						<span class="metric-value good">
							${data.metrics.totalToolCalls}
						</span>
					</div>
					<div class="metric-item">
						<span class="metric-label">Hallucinations:</span>
						<span class="metric-value ${data.metrics.hallucinatedToolCalls === 0 ? 'good' : 'bad'}">
							${data.metrics.hallucinatedToolCalls}
						</span>
					</div>
					<div class="metric-item">
						<span class="metric-label">False Starts:</span>
						<span class="metric-value ${data.metrics.falseStarts === 0 ? 'good' : 'bad'}">
							${data.metrics.falseStarts}
						</span>
					</div>
				</div>
			` : '<div class="no-data">Test incomplete</div>'}
			<div class="run-actions">
				<button class="btn-secondary btn-sm" onclick="window.vadLab.showRunDetails('${key}')">View Details</button>
				<button class="btn-secondary btn-sm" onclick="window.vadLab.compareRun('${key}')">Compare</button>
				<button class="btn-secondary btn-sm" onclick="window.vadLab.deleteRun('${key}')">Delete</button>
			</div>
		</div>
	`).join('')
}

function getLatencyClass(actual, target) {
	if (actual <= target) return 'good'
	if (actual <= target * 1.2) return 'warning'
	return 'bad'
}

export function showRunDetails(key) {
	const data = JSON.parse(localStorage.getItem(key))
	if (!data) return
	
	const modal = document.createElement('div')
	modal.className = 'modal'
	modal.innerHTML = `
		<div class="modal-content">
			<div class="modal-header">
				<h3>${scenarioNames[data.scenario]} - Run ${data.runNumber}</h3>
				<button class="btn-close" onclick="this.closest('.modal').remove()">×</button>
			</div>
			<div class="modal-body">
				<div class="detail-section">
					<h4>Test Configuration</h4>
					<pre>${JSON.stringify(data.vadConfig, null, 2)}</pre>
				</div>
				${data.metrics ? `
					<div class="detail-section">
						<h4>Final Statistics</h4>
						<pre>${JSON.stringify(data.metrics, null, 2)}</pre>
					</div>
				` : ''}
				${data.events && data.events.length > 0 ? `
					<div class="detail-section">
						<h4>Events Timeline (${data.events.length} events)</h4>
						<div class="events-list">
							${data.events.map(evt => `
								<div class="event-item">
									<span class="event-time">${new Date(evt.timestamp).toLocaleTimeString()}</span>
									<span class="event-type">${evt.type}</span>
									${evt.data ? `<span class="event-data">${JSON.stringify(evt.data)}</span>` : ''}
								</div>
							`).join('')}
						</div>
					</div>
				` : ''}
			</div>
		</div>
	`
	document.body.appendChild(modal)
}

export function compareRun(key) {
	const elements = getElements()
	const data = JSON.parse(localStorage.getItem(key))
	if (!data || !data.metrics) return
	
	// Get current live metrics
	const liveStats = window.__VFF_METRICS__?.getStats()
	if (!liveStats) {
		alert('No live metrics to compare with')
		return
	}
	
	// Build comparison table
	const comparison = {
		scenario: {
			saved: scenarioNames[data.scenario],
			live: scenarioNames[state.currentScenario]
		},
		p95Latency: {
			saved: Math.round(data.metrics.p95BargeInLatency),
			live: Math.round(liveStats.p95BargeInLatency),
			target: targets.p95BargeInLatency
		},
		avgLatency: {
			saved: Math.round(data.metrics.avgBargeInLatency),
			live: Math.round(liveStats.avgBargeInLatency),
			target: targets.avgBargeInLatency
		},
		hallucinations: {
			saved: data.metrics.hallucinatedToolCalls,
			live: liveStats.hallucinatedToolCalls,
			target: targets.hallucinationRate
		},
		falseStarts: {
			saved: data.metrics.falseStarts,
			live: liveStats.falseStarts,
			target: targets.falseStartRate
		}
	}
	
	elements.resultsComparison.innerHTML = `
		<h3>Comparison</h3>
		<table class="comparison-table">
			<thead>
				<tr>
					<th>Metric</th>
					<th>Saved Run</th>
					<th>Current Live</th>
					<th>Target</th>
					<th>Δ</th>
				</tr>
			</thead>
			<tbody>
				<tr>
					<td>Scenario</td>
					<td>${comparison.scenario.saved}</td>
					<td>${comparison.scenario.live}</td>
					<td>—</td>
					<td>—</td>
				</tr>
				<tr>
					<td>P95 Latency</td>
					<td class="${getLatencyClass(comparison.p95Latency.saved, comparison.p95Latency.target)}">${comparison.p95Latency.saved}ms</td>
					<td class="${getLatencyClass(comparison.p95Latency.live, comparison.p95Latency.target)}">${comparison.p95Latency.live}ms</td>
					<td>${comparison.p95Latency.target}ms</td>
					<td class="${getDeltaClass(comparison.p95Latency.saved, comparison.p95Latency.live)}">
						${formatDelta(comparison.p95Latency.saved, comparison.p95Latency.live)}ms
					</td>
				</tr>
				<tr>
					<td>Avg Latency</td>
					<td class="${getLatencyClass(comparison.avgLatency.saved, comparison.avgLatency.target)}">${comparison.avgLatency.saved}ms</td>
					<td class="${getLatencyClass(comparison.avgLatency.live, comparison.avgLatency.target)}">${comparison.avgLatency.live}ms</td>
					<td>${comparison.avgLatency.target}ms</td>
					<td class="${getDeltaClass(comparison.avgLatency.saved, comparison.avgLatency.live)}">
						${formatDelta(comparison.avgLatency.saved, comparison.avgLatency.live)}ms
					</td>
				</tr>
				<tr>
					<td>Hallucinations</td>
					<td class="${comparison.hallucinations.saved === 0 ? 'good' : 'bad'}">${comparison.hallucinations.saved}</td>
					<td class="${comparison.hallucinations.live === 0 ? 'good' : 'bad'}">${comparison.hallucinations.live}</td>
					<td>&lt; ${comparison.hallucinations.target}</td>
					<td class="${getDeltaClass(comparison.hallucinations.saved, comparison.hallucinations.live)}">
						${formatDelta(comparison.hallucinations.saved, comparison.hallucinations.live)}
					</td>
				</tr>
				<tr>
					<td>False Starts</td>
					<td class="${comparison.falseStarts.saved === 0 ? 'good' : 'bad'}">${comparison.falseStarts.saved}</td>
					<td class="${comparison.falseStarts.live === 0 ? 'good' : 'bad'}">${comparison.falseStarts.live}</td>
					<td>&lt; ${comparison.falseStarts.target}</td>
					<td class="${getDeltaClass(comparison.falseStarts.saved, comparison.falseStarts.live)}">
						${formatDelta(comparison.falseStarts.saved, comparison.falseStarts.live)}
					</td>
				</tr>
			</tbody>
		</table>
	`
	
	elements.resultsComparison.scrollIntoView({ behavior: 'smooth' })
}

function getDeltaClass(saved, live) {
	const delta = live - saved
	if (delta === 0) return 'neutral'
	return delta < 0 ? 'good' : 'bad'
}

function formatDelta(saved, live) {
	const delta = live - saved
	if (delta === 0) return '±0'
	return delta > 0 ? `+${delta}` : `${delta}`
}

export function exportAllData() {
	const runs = []
	
	for (let i = 0; i < localStorage.length; i++) {
		const key = localStorage.key(i)
		if (key.startsWith('vad_experiment_')) {
			try {
				const data = JSON.parse(localStorage.getItem(key))
				runs.push(data)
			} catch (e) {
				console.error('Failed to parse saved run:', key, e)
			}
		}
	}
	
	if (runs.length === 0) {
		alert('No data to export')
		return
	}
	
	const blob = new Blob([JSON.stringify(runs, null, 2)], { type: 'application/json' })
	const url = URL.createObjectURL(blob)
	const a = document.createElement('a')
	a.href = url
	a.download = `vad_tuning_results_${new Date().toISOString().slice(0, 10)}.json`
	a.click()
	URL.revokeObjectURL(url)
}

export function clearAllData() {
	if (!confirm('Delete all saved test runs? This cannot be undone.')) return
	
	const keys = []
	for (let i = 0; i < localStorage.length; i++) {
		const key = localStorage.key(i)
		if (key.startsWith('vad_experiment_')) {
			keys.push(key)
		}
	}
	
	keys.forEach(key => localStorage.removeItem(key))
	loadSavedRuns()
	
	const elements = getElements()
	elements.resultsComparison.innerHTML = '<div class="no-data">No comparisons yet</div>'
}

export function deleteRun(key) {
	if (!confirm('Delete this test run?')) return
	localStorage.removeItem(key)
	loadSavedRuns()
}
