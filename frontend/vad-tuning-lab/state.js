/**
 * VAD Tuning Lab - State Management
 * Handles application state, data models, and configuration
 */

// Target metrics for comparison
export const targets = {
	p95BargeInLatency: 180,
	avgBargeInLatency: 150,
	hallucinationRate: 1,
	falseStartRate: 3,
	cancelAckLatency: 150
}

// Application state
export const state = {
	currentScenario: 'A',
	testRunNumber: 0,
	currentTestRun: null,
	isTestRunActive: false,
	selectedSavedRun: null,
	ws: null, // WebSocket for VAD config updates
	vadConfig: {
		startSensitivity: 'UNSPECIFIED',
		endSensitivity: 'UNSPECIFIED',
		prefixPadding: 120,
		silenceDuration: 250
	}
}

// Experiment data model
export class ExperimentData {
	constructor(scenario, runNumber) {
		this.scenario = scenario
		this.runNumber = runNumber
		this.startTime = new Date().toISOString()
		this.endTime = null
		this.duration = null
		this.metrics = null
		this.hallucinatedFields = []
		this.events = []
		this.vadConfig = { ...state.vadConfig } // Capture current VAD config
	}

	addEvent(type, message, data = {}) {
		this.events.push({
			timestamp: new Date().toISOString(),
			type,
			message,
			data
		})
		// Note: logToUI is called from the UI module
	}

	complete(metrics, hallucinatedFields) {
		this.endTime = new Date().toISOString()
		this.duration = new Date(this.endTime) - new Date(this.startTime)
		this.metrics = metrics
		this.hallucinatedFields = hallucinatedFields
	}

	save() {
		const key = `vad_experiment_${this.scenario}_run${this.runNumber}_${Date.now()}`
		localStorage.setItem(key, JSON.stringify(this))
	}
}

// Scenario names mapping
export const scenarioNames = {
	'A': 'A - Baseline',
	'B': 'B - Gentle Barge-In',
	'C': 'C - Aggressive Barge-In',
	'D': 'D - False Starts'
}

// Status icons mapping
export const statusIcons = {
	idle: '⚪',
	connecting: '🟡',
	connected: '🟢',
	error: '🔴'
}
