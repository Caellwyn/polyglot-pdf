/**
 * Energy Monitoring Hook
 * 
 * Connects to audioManager to receive real-time energy data and VAD events.
 * Maintains rolling buffer of energy data for graphing.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { EnergyDataPoint, VADEvent, VADMetrics } from './types'
import type { AudioEnergyCallback } from '../shared/audioManager'

const ENERGY_BUFFER_SIZE = 500 // Keep last 500 data points (~10 seconds at 50Hz)
const METRICS_UPDATE_INTERVAL_MS = 100 // Update metrics 10 times per second

export interface UseEnergyMonitorResult {
	energyData: EnergyDataPoint[]
	events: VADEvent[]
	metrics: VADMetrics
	clearHistory: () => void
	registerEnergyCallback: () => AudioEnergyCallback
	onSpeechStart: () => void
	onSpeechEnd: (duration: number) => void
	onVADMisfire: () => void
	onCalibration: (baselineEnergy: number) => void
	/** NEW: Add VAD probability data point (for Ricky VAD visualization) */
	addVADProbability: (probability: number, energyPercent: number) => void
}

/**
 * Hook for monitoring audio energy and VAD events
 * 
 * Usage:
 * ```ts
 * const monitor = useEnergyMonitor(userSpeaking, geminiSpeaking)
 * const energyCallbacks = monitor.registerEnergyCallback()
 * audioManager.startRecording(onAudioData, energyCallbacks)
 * ```
 */
export function useEnergyMonitor(
	userSpeaking: boolean,
	geminiSpeaking: boolean
): UseEnergyMonitorResult {
	const [energyData, setEnergyData] = useState<EnergyDataPoint[]>([])
	const [events, setEvents] = useState<VADEvent[]>([])
	const [metrics, setMetrics] = useState<VADMetrics>({
		totalSpeechEvents: 0,
		totalMisfires: 0,
		averageSpeechDuration: 0,
		falsePositiveRate: 0,
		falseNegativeRate: 0,
		lastSpeechStartTime: null,
		lastSpeechEndTime: null,
		currentSpeechDuration: 0,
		currentEnergy: 0,
		baselineEnergy: 0,
		peakEnergy: 0,
	})

	const speechDurations = useRef<number[]>([])
	const currentEnergy = useRef<number>(0)
	const baselineEnergy = useRef<number>(0)
	const peakEnergy = useRef<number>(0)

	// Update metrics periodically
	useEffect(() => {
		const interval = setInterval(() => {
			const now = Date.now()
			const currentSpeechDuration = 
				userSpeaking && metrics.lastSpeechStartTime
					? now - metrics.lastSpeechStartTime
					: 0

			setMetrics(prev => ({
				...prev,
				currentEnergy: currentEnergy.current,
				baselineEnergy: baselineEnergy.current,
				peakEnergy: peakEnergy.current,
				currentSpeechDuration,
			}))
		}, METRICS_UPDATE_INTERVAL_MS)

		return () => clearInterval(interval)
	}, [userSpeaking, metrics.lastSpeechStartTime])

	// Add energy data point
	const addEnergyData = useCallback((energy: number) => {
		const dataPoint: EnergyDataPoint = {
			timestamp: Date.now(),
			energy,
			userSpeaking,
			geminiSpeaking,
		}

		setEnergyData(prev => {
			const newData = [...prev, dataPoint]
			// Keep only last N points
			if (newData.length > ENERGY_BUFFER_SIZE) {
				return newData.slice(-ENERGY_BUFFER_SIZE)
			}
			return newData
		})

		// Update current metrics
		currentEnergy.current = energy
		if (energy > peakEnergy.current) {
			peakEnergy.current = energy
		}
	}, [userSpeaking, geminiSpeaking])

	// Register energy callback for audioManager
	const registerEnergyCallback = useCallback((): AudioEnergyCallback => {
		return {
			onEnergyChange: (energy: number, isActive: boolean, reason) => {
				addEnergyData(energy)
			},
			onCalibrationComplete: (baseline: number) => {
				baselineEnergy.current = baseline
				setMetrics(prev => ({ ...prev, baselineEnergy: baseline }))
			},
		}
	}, [addEnergyData])

	// VAD event handlers
	const onSpeechStart = useCallback(() => {
		const now = Date.now()
		const event: VADEvent = {
			timestamp: now,
			type: 'speech_start',
			energy: currentEnergy.current,
		}
		
		setEvents(prev => [...prev, event])
		setMetrics(prev => ({
			...prev,
			totalSpeechEvents: prev.totalSpeechEvents + 1,
			lastSpeechStartTime: now,
		}))
	}, [])

	const onSpeechEnd = useCallback((duration: number) => {
		const now = Date.now()
		const event: VADEvent = {
			timestamp: now,
			type: 'speech_end',
			energy: currentEnergy.current,
			metadata: { duration },
		}
		
		setEvents(prev => [...prev, event])
		speechDurations.current.push(duration)
		
		// Calculate average speech duration
		const avgDuration = 
			speechDurations.current.reduce((sum, d) => sum + d, 0) / 
			speechDurations.current.length

		setMetrics(prev => ({
			...prev,
			lastSpeechEndTime: now,
			averageSpeechDuration: avgDuration,
		}))
	}, [])

	const onVADMisfire = useCallback(() => {
		const event: VADEvent = {
			timestamp: Date.now(),
			type: 'vad_misfire',
			energy: currentEnergy.current,
		}
		
		setEvents(prev => [...prev, event])
		setMetrics(prev => ({
			...prev,
			totalMisfires: prev.totalMisfires + 1,
			falsePositiveRate: 
				((prev.totalMisfires + 1) / (prev.totalSpeechEvents + 1)) * 100,
		}))
	}, [])

	const onCalibration = useCallback((baseline: number) => {
		const event: VADEvent = {
			timestamp: Date.now(),
			type: 'calibration_complete',
			energy: baseline,
			metadata: { baselineEnergy: baseline },
		}
		
		setEvents(prev => [...prev, event])
		baselineEnergy.current = baseline
		setMetrics(prev => ({ ...prev, baselineEnergy: baseline }))
	}, [])

	const clearHistory = useCallback(() => {
		setEnergyData([])
		setEvents([])
		speechDurations.current = []
		peakEnergy.current = 0
		setMetrics({
			totalSpeechEvents: 0,
			totalMisfires: 0,
			averageSpeechDuration: 0,
			falsePositiveRate: 0,
			falseNegativeRate: 0,
			lastSpeechStartTime: null,
			lastSpeechEndTime: null,
			currentSpeechDuration: 0,
			currentEnergy: currentEnergy.current,
			baselineEnergy: baselineEnergy.current,
			peakEnergy: 0,
		})
	}, [])

	// NEW: Add VAD probability as energy data (for Ricky VAD)
	const addVADProbability = useCallback((probability: number, energyPercent: number) => {
		const dataPoint: EnergyDataPoint = {
			timestamp: Date.now(),
			energy: energyPercent,  // 0-100 scale for graph
			userSpeaking,
			geminiSpeaking,
		}

		setEnergyData(prev => {
			const newData = [...prev, dataPoint]
			// Keep only last N points
			if (newData.length > ENERGY_BUFFER_SIZE) {
				return newData.slice(-ENERGY_BUFFER_SIZE)
			}
			return newData
		})

		// Update current metrics
		currentEnergy.current = energyPercent
		if (energyPercent > peakEnergy.current) {
			peakEnergy.current = energyPercent
		}
	}, [userSpeaking, geminiSpeaking])

	return {
		energyData,
		events,
		metrics,
		clearHistory,
		registerEnergyCallback,
		onSpeechStart,
		onSpeechEnd,
		onVADMisfire,
		onCalibration,
		addVADProbability,
	}
}
