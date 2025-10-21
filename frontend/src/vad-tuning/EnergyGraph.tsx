/**
 * Energy Graph Component
 * 
 * Real-time streaming line chart showing microphone energy levels with:
 * - Smooth, fixed-window scrolling display
 * - Threshold overlays
 * - VAD event markers
 * - User/Gemini speaking indicators
 * 
 * PERFORMANCE OPTIMIZATIONS:
 * - Uses requestAnimationFrame for smooth 60fps updates
 * - Fixed time window prevents X-axis jumping
 * - Throttled chart updates (no animation mode)
 * - Efficient data filtering with time-based indexing
 */

import React, { useEffect, useRef, useMemo } from 'react'
import {
	Chart as ChartJS,
	CategoryScale,
	LinearScale,
	PointElement,
	LineElement,
	Title,
	Tooltip,
	Legend,
	Filler,
	ChartOptions,
} from 'chart.js'
import { Line } from 'react-chartjs-2'
import annotationPlugin from 'chartjs-plugin-annotation'
import { EnergyDataPoint, VADEvent, VADConfig } from './types'

// Register Chart.js components
ChartJS.register(
	CategoryScale,
	LinearScale,
	PointElement,
	LineElement,
	Title,
	Tooltip,
	Legend,
	Filler,
	annotationPlugin
)

interface EnergyGraphProps {
	energyData: EnergyDataPoint[]
	events: VADEvent[]
	config: VADConfig
	baselineEnergy: number
	onThresholdChange?: (threshold: 'positive' | 'negative', value: number) => void
}

// Tunable graph configuration
const GRAPH_CONFIG = {
	TIME_WINDOW_MS: 8000,        // Show last 8 seconds
	UPDATE_FPS: 20,               // Update at 20 FPS for smooth animation
	MAX_POINTS: 160,              // 8000ms / 50ms = 160 points max
	DECIMATION_THRESHOLD: 200,    // Decimate if we have more than this
} as const


export const EnergyGraph: React.FC<EnergyGraphProps> = ({
	energyData,
	events,
	config,
	baselineEnergy,
	onThresholdChange,
}) => {
	const chartRef = useRef<ChartJS<'line'>>(null)
	const lastUpdateTimeRef = useRef<number>(0)
	const animationFrameRef = useRef<number>()

	// Calculate threshold values from VAD config (0.0-1.0 -> 0-100%)
	// TODO: Remove AudioManager baseline calculation - using VAD thresholds
	// const positiveThresholdValue = baselineEnergy * 2.5 // ATTACK_MULTIPLIER
	// const negativeThresholdValue = baselineEnergy * 1.7 // RELEASE_MULTIPLIER
	const positiveThresholdValue = config.positiveSpeechThreshold * 100
	const negativeThresholdValue = config.negativeSpeechThreshold * 100

	// Smooth update loop using requestAnimationFrame
	useEffect(() => {
		const updateChart = (timestamp: number) => {
			// Throttle to target FPS
			const updateInterval = 1000 / GRAPH_CONFIG.UPDATE_FPS
			if (timestamp - lastUpdateTimeRef.current < updateInterval) {
				animationFrameRef.current = requestAnimationFrame(updateChart)
				return
			}
			lastUpdateTimeRef.current = timestamp

			const chart = chartRef.current
			if (!chart) {
				animationFrameRef.current = requestAnimationFrame(updateChart)
				return
			}

			// Get current time for fixed window
			const now = Date.now()
			const windowStart = now - GRAPH_CONFIG.TIME_WINDOW_MS

			// Filter to visible window and decimate if needed
			let visibleData = energyData.filter(d => d.timestamp >= windowStart)
			
			// Decimate data if we have too many points for performance
			if (visibleData.length > GRAPH_CONFIG.DECIMATION_THRESHOLD) {
				const step = Math.ceil(visibleData.length / GRAPH_CONFIG.MAX_POINTS)
				visibleData = visibleData.filter((_, i) => i % step === 0)
			}

			if (visibleData.length === 0) {
				animationFrameRef.current = requestAnimationFrame(updateChart)
				return
			}

			// Generate X-axis labels (time relative to window start)
			const labels = visibleData.map(d => {
				const secondsFromStart = (d.timestamp - windowStart) / 1000
				return secondsFromStart.toFixed(1)
			})

			// Extract energy values and speaking state
			const energyValues = visibleData.map(d => d.energy)
			const speakingHighlight = visibleData.map(d => 
				d.userSpeaking ? d.energy : null
			)

			// Update chart datasets
			chart.data.labels = labels
			chart.data.datasets[0].data = energyValues
			chart.data.datasets[1].data = speakingHighlight

			// Update annotations with current threshold values
			if (chart.options.plugins?.annotation?.annotations) {
				const annotations = chart.options.plugins.annotation.annotations as any
				
				// TODO: Remove baseline - using VAD probabilities only
				// annotations.baseline.yMin = baselineEnergy
				// annotations.baseline.yMax = baselineEnergy
				// annotations.baseline.label.content = `Baseline: ${baselineEnergy.toFixed(1)}`
				
				// Update positive threshold (VAD)
				annotations.positiveThreshold.yMin = positiveThresholdValue
				annotations.positiveThreshold.yMax = positiveThresholdValue
				annotations.positiveThreshold.label.content = 
					`Positive: ${config.positiveSpeechThreshold.toFixed(2)} (${positiveThresholdValue.toFixed(0)}%)`
				
				// Update negative threshold (VAD)
				annotations.negativeThreshold.yMin = negativeThresholdValue
				annotations.negativeThreshold.yMax = negativeThresholdValue
				annotations.negativeThreshold.label.content = 
					`Negative: ${config.negativeSpeechThreshold.toFixed(2)} (${negativeThresholdValue.toFixed(0)}%)`

				// Update event markers
				const visibleEvents = events.filter(e => e.timestamp >= windowStart)
				
				// Remove old event annotations
				Object.keys(annotations).forEach(key => {
					if (key.startsWith('event')) {
						delete annotations[key]
					}
				})

				// Add current event markers
				visibleEvents.forEach((event, idx) => {
					const secondsFromStart = (event.timestamp - windowStart) / 1000
					const color = 
						event.type === 'speech_start' ? 'rgba(34, 197, 94, 0.8)' :
						event.type === 'speech_end' ? 'rgba(239, 68, 68, 0.8)' :
						event.type === 'vad_misfire' ? 'rgba(251, 191, 36, 0.8)' :
						'rgba(59, 130, 246, 0.8)'

					annotations[`event${idx}`] = {
						type: 'line',
						xMin: secondsFromStart.toFixed(1),
						xMax: secondsFromStart.toFixed(1),
						borderColor: color,
						borderWidth: 2,
						borderDash: [5, 5],
						label: {
							display: true,
							content: event.type.replace('_', ' '),
							position: 'start',
							color: color,
							backgroundColor: 'rgba(0, 0, 0, 0.8)',
							font: { size: 10 },
						}
					}
				})
			}

			// Update chart without animation for smooth real-time feel
			chart.update('none')

			animationFrameRef.current = requestAnimationFrame(updateChart)
		}

		// Start the update loop
		animationFrameRef.current = requestAnimationFrame(updateChart)

		// Cleanup
		return () => {
			if (animationFrameRef.current) {
				cancelAnimationFrame(animationFrameRef.current)
			}
		}
	}, [energyData, events, config, baselineEnergy, positiveThresholdValue, negativeThresholdValue])

	// Prepare chart configuration (static, won't cause re-renders)
	const chartOptions: ChartOptions<'line'> = useMemo(() => ({
		responsive: true,
		maintainAspectRatio: false,
		animation: false,
		interaction: {
			mode: 'index',
			intersect: false,
		},
		scales: {
			x: {
				type: 'category',
				title: {
					display: true,
					text: `Time (seconds, last ${GRAPH_CONFIG.TIME_WINDOW_MS / 1000}s)`,
					font: { size: 12 },
				},
				ticks: {
					maxTicksLimit: 16,
					autoSkip: true,
					font: { size: 10 },
				},
			},
			y: {
				title: {
					display: true,
					text: 'VAD Probability (%)',
					font: { size: 12 },
				},
				min: 0,
				max: 100,
				ticks: {
					stepSize: 10,
					font: { size: 10 },
				},
			},
		},
		plugins: {
			legend: {
				display: true,
				position: 'top',
			},
			tooltip: {
				enabled: true,
				mode: 'index',
				intersect: false,
			},
			annotation: {
				annotations: {
					// TODO: Remove baseline - using VAD probabilities only
					// baseline: {
					// 	type: 'line',
					// 	yMin: baselineEnergy,
					// 	yMax: baselineEnergy,
					// 	borderColor: 'rgba(156, 163, 175, 0.8)',
					// 	borderWidth: 1,
					// 	borderDash: [3, 3],
					// 	label: {
					// 		display: true,
					// 		content: `Baseline: ${baselineEnergy.toFixed(1)}`,
					// 		position: 'end',
					// 		backgroundColor: 'rgba(0, 0, 0, 0.8)',
					// 		color: 'white',
					// 		font: { size: 11 },
					// 	},
					// },
					positiveThreshold: {
						type: 'line',
						yMin: positiveThresholdValue,
						yMax: positiveThresholdValue,
						borderColor: 'rgba(34, 197, 94, 0.8)',
						borderWidth: 2,
						borderDash: [5, 5],
						label: {
							display: true,
							content: `Positive: ${config.positiveSpeechThreshold.toFixed(2)} (${positiveThresholdValue.toFixed(0)}%)`,
							position: 'end',
							backgroundColor: 'rgba(34, 197, 94, 0.9)',
							color: 'white',
							font: { size: 11, weight: 'bold' },
						},
					},
					negativeThreshold: {
						type: 'line',
						yMin: negativeThresholdValue,
						yMax: negativeThresholdValue,
						borderColor: 'rgba(239, 68, 68, 0.8)',
						borderWidth: 2,
						borderDash: [5, 5],
						label: {
							display: true,
							content: `Negative: ${config.negativeSpeechThreshold.toFixed(2)} (${negativeThresholdValue.toFixed(0)}%)`,
							position: 'start',
							backgroundColor: 'rgba(239, 68, 68, 0.9)',
							color: 'white',
							font: { size: 11, weight: 'bold' },
						},
					},
				},
			},
		},
	}), [baselineEnergy, positiveThresholdValue, negativeThresholdValue, config])

	// Initial chart data structure
	const chartData = useMemo(() => ({
		labels: [],
		datasets: [
			{
				label: 'VAD Probability',
				data: [],
				borderColor: 'rgb(99, 102, 241)',
				backgroundColor: 'rgba(99, 102, 241, 0.1)',
				fill: true,
				tension: 0.3,
				pointRadius: 0,
				borderWidth: 2,
			},
			{
				label: 'Speaking',
				data: [],
				borderColor: 'rgb(34, 197, 94)',
				backgroundColor: 'rgba(34, 197, 94, 0.3)',
				fill: true,
				tension: 0.3,
				pointRadius: 0,
				borderWidth: 3,
			},
		],
	}), [])

	return (
		<div style={{ height: '450px', width: '100%', position: 'relative' }}>
			<Line ref={chartRef} data={chartData} options={chartOptions} />
		</div>
	)
}
