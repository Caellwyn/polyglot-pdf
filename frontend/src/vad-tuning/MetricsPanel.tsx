/**
 * Metrics Panel
 * 
 * Displays live metrics and event log
 */

import React, { useRef, useEffect } from 'react'
import { VADMetrics, VADEvent } from './types'

interface MetricsPanelProps {
	metrics: VADMetrics
	events: VADEvent[]
	onClearHistory: () => void
}

export const MetricsPanel: React.FC<MetricsPanelProps> = ({
	metrics,
	events,
	onClearHistory,
}) => {
	const eventLogRef = useRef<HTMLDivElement>(null)

	// Auto-scroll to latest event
	useEffect(() => {
		if (eventLogRef.current) {
			eventLogRef.current.scrollTop = eventLogRef.current.scrollHeight
		}
	}, [events])

	const formatTimestamp = (ts: number) => {
		const date = new Date(ts)
		const time = date.toLocaleTimeString('en-US', {
			hour12: false,
			hour: '2-digit',
			minute: '2-digit',
			second: '2-digit',
		})
		const ms = date.getMilliseconds().toString().padStart(3, '0')
		return `${time}.${ms}`
	}

	const formatDuration = (ms: number) => {
		if (ms < 1000) return `${ms}ms`
		return `${(ms / 1000).toFixed(2)}s`
	}

	return (
		<div className="metrics-panel">
			{/* Live Metrics Grid */}
			<div className="metrics-grid">
				<div className="metric-card">
					<div className="metric-label">Current Energy</div>
					<div className="metric-value energy">
						{metrics.currentEnergy.toFixed(1)}
					</div>
				</div>

				<div className="metric-card">
					<div className="metric-label">Baseline Energy</div>
					<div className="metric-value">
						{metrics.baselineEnergy.toFixed(1)}
					</div>
				</div>

				<div className="metric-card">
					<div className="metric-label">Peak Energy</div>
					<div className="metric-value">
						{metrics.peakEnergy.toFixed(1)}
					</div>
				</div>

				<div className="metric-card">
					<div className="metric-label">Speech Events</div>
					<div className="metric-value">
						{metrics.totalSpeechEvents}
					</div>
				</div>

				<div className="metric-card">
					<div className="metric-label">Misfires</div>
					<div className="metric-value warning">
						{metrics.totalMisfires}
					</div>
				</div>

				<div className="metric-card">
					<div className="metric-label">False Positive Rate</div>
					<div className="metric-value warning">
						{metrics.falsePositiveRate.toFixed(1)}%
					</div>
				</div>

				<div className="metric-card">
					<div className="metric-label">Avg Speech Duration</div>
					<div className="metric-value">
						{formatDuration(metrics.averageSpeechDuration)}
					</div>
				</div>

				<div className="metric-card">
					<div className="metric-label">Current Speech Duration</div>
					<div className="metric-value">
						{formatDuration(metrics.currentSpeechDuration)}
					</div>
				</div>
			</div>

			{/* Event Log */}
			<div className="event-log-container">
				<div className="event-log-header">
					<h3>Event Log</h3>
					<button onClick={onClearHistory} className="btn-secondary btn-sm">
						Clear
					</button>
				</div>
				<div className="event-log" ref={eventLogRef}>
					{events.length === 0 ? (
						<div className="event-empty">No events yet. Start recording to see VAD activity.</div>
					) : (
						events.map((event, idx) => {
							const eventClass = 
								event.type === 'speech_start' ? 'event-start' :
								event.type === 'speech_end' ? 'event-end' :
								event.type === 'vad_misfire' ? 'event-misfire' :
								'event-calibration'

							return (
								<div key={idx} className={`event-item ${eventClass}`}>
									<span className="event-time">{formatTimestamp(event.timestamp)}</span>
									<span className="event-type">{event.type.replace(/_/g, ' ')}</span>
									<span className="event-energy">E: {event.energy.toFixed(1)}</span>
									{event.metadata?.duration && (
										<span className="event-duration">
											Duration: {formatDuration(event.metadata.duration)}
										</span>
									)}
									{event.metadata?.baselineEnergy && (
										<span className="event-baseline">
											Baseline: {event.metadata.baselineEnergy.toFixed(1)}
										</span>
									)}
								</div>
							)
						})
					)}
				</div>
			</div>
		</div>
	)
}
