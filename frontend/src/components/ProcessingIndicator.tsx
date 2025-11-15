/**
 * Processing Indicator Component - Phase 4C
 *
 * Displays half-cascade processing stages with visual feedback:
 * - Buffering → Transcribing → Generating → Synthesizing
 * - Progress bar with percentage (optional)
 * - Latency warnings (>2s threshold)
 * - Smooth animations
 * - Error messages with fallback info
 */

import React, { useState, useEffect } from 'react'
import type {
	ProcessingStatusMessage,
	HalfCascadeError
} from '../shared/halfCascadeTypes'
import { formatLatency } from '../shared/halfCascadeState'

export interface ProcessingIndicatorProps {
	/** Show latency warning threshold (ms) */
	latencyWarningThreshold?: number
	/** Custom CSS class */
	className?: string
	/** Compact mode for mobile */
	compact?: boolean
}

interface ProcessingState {
	stage: ProcessingStatusMessage['stage'] | null
	progress: number | null
	startTime: number | null
	currentLatency: number | null
	error: HalfCascadeError | null
}

const STAGE_LABELS: Record<ProcessingStatusMessage['stage'], string> = {
	buffering: 'Buffering audio',
	transcribing: 'Transcribing speech',
	generating: 'Generating response',
	synthesizing: 'Synthesizing speech'
}

const STAGE_ICONS: Record<ProcessingStatusMessage['stage'], string> = {
	buffering: '📦',
	transcribing: '🎤',
	generating: '🤖',
	synthesizing: '🔊'
}

export const ProcessingIndicator: React.FC<ProcessingIndicatorProps> = ({
	latencyWarningThreshold = 2000,
	className = '',
	compact = false
}) => {
	const [state, setState] = useState<ProcessingState>({
		stage: null,
		progress: null,
		startTime: null,
		currentLatency: null,
		error: null
	})

	// Listen for processing status events
	useEffect(() => {
		const handleProcessingStatus = (event: Event) => {
			const customEvent = event as CustomEvent<ProcessingStatusMessage>
			const message = customEvent.detail

			setState(prev => {
				const newState: ProcessingState = {
					...prev,
					stage: message.stage,
					progress: message.progress ?? null
				}

				// Start timer on first stage
				if (!prev.startTime && (message.stage === 'buffering' || message.stage === 'transcribing')) {
					newState.startTime = Date.now()
				}

				// Calculate current latency
				if (newState.startTime) {
					newState.currentLatency = Date.now() - newState.startTime
				}

				// Clear on completion
				if (message.stage === 'synthesizing' && message.progress === 100) {
					newState.startTime = null
					newState.currentLatency = null
				}

				return newState
			})
		}

		const handleError = (event: Event) => {
			const customEvent = event as CustomEvent<HalfCascadeError>
			const error = customEvent.detail

			setState(prev => ({
				...prev,
				error,
				stage: null,
				progress: null
			}))
		}

		// Listen for transcript (processing complete)
		const handleTranscript = () => {
			setState({
				stage: null,
				progress: null,
				startTime: null,
				currentLatency: null,
				error: null
			})
		}

		window.addEventListener('vff:processing-status', handleProcessingStatus)
		window.addEventListener('vff:half-cascade-error', handleError)
		window.addEventListener('vff:transcript', handleTranscript)

		return () => {
			window.removeEventListener('vff:processing-status', handleProcessingStatus)
			window.removeEventListener('vff:half-cascade-error', handleError)
			window.removeEventListener('vff:transcript', handleTranscript)
		}
	}, [])

	// Don't render if not processing and no error
	if (!state.stage && !state.error) {
		return null
	}

	// Check for latency warning
	const showLatencyWarning = state.currentLatency !== null &&
		state.currentLatency > latencyWarningThreshold

	// Error display
	if (state.error) {
		return (
			<div className={`processing-indicator error ${className}`} role="alert">
				<div className="error-icon" aria-hidden="true">❌</div>
				<div className="error-content">
					<div className="error-title">Error: {state.error.error_code}</div>
					<div className="error-message">{state.error.message}</div>
					{state.error.fallback_activated && (
						<div className="error-fallback">
							✓ Fallback to Live API activated
						</div>
					)}
					{!state.error.recoverable && (
						<div className="error-nonrecoverable">
							⚠️ Manual intervention required
						</div>
					)}
				</div>
			</div>
		)
	}

	if (compact) {
		// Compact mobile view
		return (
			<div className={`processing-indicator compact ${className}`} role="status" aria-live="polite">
				<div className="stage-indicator-compact">
					<span className="stage-icon" aria-hidden="true">
						{state.stage ? STAGE_ICONS[state.stage] : '⏳'}
					</span>
					<span className="stage-label">
						{state.stage ? STAGE_LABELS[state.stage] : 'Processing...'}
					</span>
					{state.progress !== null && (
						<span className="stage-progress">{state.progress}%</span>
					)}
				</div>
				{showLatencyWarning && (
					<div className="latency-warning-compact" title="High latency detected">
						⚠️ {formatLatency(state.currentLatency)}
					</div>
				)}
			</div>
		)
	}

	// Full desktop view
	return (
		<div className={`processing-indicator ${className}`} role="status" aria-live="polite">
			<div className="stage-header">
				<div className="stage-info">
					<span className="stage-icon" aria-hidden="true">
						{state.stage ? STAGE_ICONS[state.stage] : '⏳'}
					</span>
					<span className="stage-label">
						{state.stage ? STAGE_LABELS[state.stage] : 'Processing...'}
					</span>
				</div>
				{state.currentLatency !== null && (
					<div className={`latency-display ${showLatencyWarning ? 'warning' : ''}`}>
						{formatLatency(state.currentLatency)}
					</div>
				)}
			</div>

			{state.progress !== null && (
				<div className="progress-bar-container">
					<div
						className="progress-bar"
						style={{ width: `${state.progress}%` }}
						role="progressbar"
						aria-valuenow={state.progress}
						aria-valuemin={0}
						aria-valuemax={100}
						aria-label={`Processing progress: ${state.progress}%`}
					/>
				</div>
			)}

			{showLatencyWarning && (
				<div className="latency-warning" role="alert">
					⚠️ High latency detected - processing is taking longer than usual
				</div>
			)}
		</div>
	)
}

export default ProcessingIndicator
