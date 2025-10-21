/**
 * VAD Tuning Dashboard
 * 
 * Main component that integrates all VAD tuning tools:
 * - Real-time energy graph
 * - VAD configuration controls
 * - Metrics and event tracking
 */

import React, { useState, useCallback, useEffect } from 'react'
// TODO: Remove AudioManager - using Ricky VAD only for tuning dashboard
// import { createAudioManager, AudioManager } from '../shared/audioManager'
import { useDemoVAD } from '../demo/useDemoVAD'
import { useVADConfig } from './useVADConfig'
import { useEnergyMonitor } from './useEnergyMonitor'
import { EnergyGraph } from './EnergyGraph'
import { VADControlPanel } from './VADControlPanel'
import { MetricsPanel } from './MetricsPanel'
import './dashboard.css'

export const VADTuningDashboard: React.FC = () => {
	// TODO: Remove AudioManager state - using VAD only
	// const [audioManager, setAudioManager] = useState<AudioManager | null>(null)
	const [isRecording, setIsRecording] = useState(false)
	const [stream, setStream] = useState<MediaStream | null>(null)
	const [userSpeaking, setUserSpeaking] = useState(false)
	const [isDebugMode, setIsDebugMode] = useState(false)
	const [vadKey, setVadKey] = useState(0) // Force VAD re-mount on config change

	// VAD configuration management
	const vadConfig = useVADConfig()

	// Energy monitoring (initialize first)
	const monitor = useEnergyMonitor(userSpeaking, false)

	// Debug mode config - very aggressive for testing
	const debugConfig = {
		positiveSpeechThreshold: 0.60,
		negativeSpeechThreshold: 0.40,
		minSpeechMs: 50,
		redemptionMs: 150,
	}

	// CRITICAL: Only initialize VAD after stream exists
	// Pass stream directly so VAD can access it when it starts
	const vadCallbacks = {
		onSpeechStart: () => {
			console.log('🎤 [VAD] Speech detected!')
			setUserSpeaking(true)
			monitor.onSpeechStart()
		},
		onSpeechEnd: (audio: Float32Array) => {
			console.log('🎤 [VAD] Speech ended')
			setUserSpeaking(false)
			// Calculate duration from audio length
			const durationMs = (audio.length / 16000) * 1000
			monitor.onSpeechEnd(durationMs)
		},
		onVADMisfire: () => {
			console.log('⚠️ [VAD] Misfire detected')
			monitor.onVADMisfire()
		},
		onFrameProcessed: (probability: number, frame: Float32Array) => {
			// Convert VAD probability (0.0-1.0) to percentage (0-100) for visualization
			const energyPercent = probability * 100
			monitor.addVADProbability(probability, energyPercent)
		},
	}

	// Initialize VAD with shared stream and callbacks
	// Use debug config if enabled, otherwise use dashboard config
	const vad = useDemoVAD({
		sharedStream: stream,
		sensitivity: isDebugMode ? debugConfig : vadConfig.config,
		callbacks: vadCallbacks,
	})

	// Auto-restart VAD when config changes (if recording)
	useEffect(() => {
		if (isRecording && stream && vad) {
			console.log('🔄 Config changed, restarting VAD...')
			console.log('Current config:', isDebugMode ? debugConfig : vadConfig.config)
			vad.pause()
			// Small delay to ensure old VAD is fully stopped
			setTimeout(() => {
				vad.start()
				console.log('✅ VAD restarted with new config')
			}, 100)
		}
	}, [vadConfig.config, isDebugMode])

	// Start recording
	const startRecording = useCallback(async () => {
		try {
			// Get microphone stream with browser audio processing enabled
			const newStream = await navigator.mediaDevices.getUserMedia({
				audio: {
					echoCancellation: true,    // CRITICAL: Browser AEC
					noiseSuppression: true,     // Reduce background noise
					autoGainControl: true,      // Normalize volume
					channelCount: 1,            // Mono
					sampleRate: 16000,          // Match VAD sample rate
				},
			})
			setStream(newStream)

			// TODO: Remove AudioManager - VAD handles everything now
			// Create audio manager with the stream
			// const manager = createAudioManager(newStream)
			// setAudioManager(manager)

			// TODO: Remove AudioManager energy callbacks - using VAD probabilities
			// Register energy callbacks
			// const energyCallbacks = monitor.registerEnergyCallback()
			// energyCallbacks.onCalibrationComplete = (baseline) => {
			// 	monitor.onCalibration(baseline)
			// }

			// TODO: Remove AudioManager recording - VAD manages its own audio
			// Start recording (dummy callback - we only care about energy)
			// await manager.startRecording(() => {}, energyCallbacks)

			setIsRecording(true)

			// Start VAD after a short delay to ensure everything is ready
			// Note: VAD will use the shared stream we just created
			setTimeout(() => {
				console.log('🎙️ Starting VAD...')
				console.log('Stream available:', !!newStream)
				console.log('Stream tracks:', newStream?.getTracks().map(t => ({
					kind: t.kind,
					label: t.label,
					enabled: t.enabled,
					readyState: t.readyState
				})))
				console.log('VAD config:', isDebugMode ? debugConfig : vadConfig.config)
				vad.start()
			}, 500)

		} catch (error) {
			console.error('❌ Failed to start recording:', error)
			alert(`Failed to access microphone: ${error instanceof Error ? error.message : 'Unknown error'}`)
		}
	}, [monitor, vad, isDebugMode, debugConfig, vadConfig.config])

	// Stop recording
	const stopRecording = useCallback(() => {
		// TODO: Remove AudioManager cleanup - using VAD only
		// if (audioManager) {
		// 	audioManager.stopRecording()
		// 	audioManager.destroy()
		// 	setAudioManager(null)
		// }
		if (stream) {
			stream.getTracks().forEach(track => track.stop())
			setStream(null)
		}
		vad.pause()
		setIsRecording(false)
	}, [stream, vad])

	// Cleanup on unmount
	useEffect(() => {
		return () => {
			// TODO: Remove AudioManager cleanup - using VAD only
			// if (audioManager) {
			// 	audioManager.stopRecording()
			// 	audioManager.destroy()
			// }
			if (stream) {
				stream.getTracks().forEach(track => track.stop())
			}
		}
	}, [stream])

	// Handle config changes - VAD auto-restarts via useEffect
	const handleConfigChange = useCallback((updates: any) => {
		vadConfig.updateConfig(updates)
	}, [vadConfig])

	// Toggle debug mode
	const handleDebugMode = useCallback(() => {
		setIsDebugMode(prev => !prev)
	}, [])

	return (
		<div className="vad-dashboard">
			<header className="dashboard-header">
				<h1>🎙️ VAD Tuning Dashboard</h1>
				<div className="header-controls">
					{!isRecording ? (
						<button onClick={startRecording} className="btn-primary btn-large">
							▶️ Start Recording
						</button>
					) : (
						<button onClick={stopRecording} className="btn-danger btn-large">
							⏹️ Stop Recording
						</button>
					)}
				</div>
			</header>

			{isRecording && isDebugMode && (
				<div className="info-banner">
					🔧 Debug Mode Active - VAD is extremely sensitive for testing
				</div>
			)}

			<div className="dashboard-grid">
				{/* Left Column: Graph + Metrics */}
				<div className="dashboard-left">
					<section className="dashboard-card">
						<h2>Real-Time Energy Monitor</h2>
						<EnergyGraph
							energyData={monitor.energyData}
							events={monitor.events}
							config={vadConfig.config}
							baselineEnergy={monitor.metrics.baselineEnergy}
						/>
					</section>

					<section className="dashboard-card">
						<h2>Metrics & Events</h2>
						<MetricsPanel
							metrics={monitor.metrics}
							events={monitor.events}
							onClearHistory={monitor.clearHistory}
						/>
					</section>
				</div>

				{/* Right Column: Controls */}
				<div className="dashboard-right">
					<section className="dashboard-card">
						<VADControlPanel
							config={vadConfig.config}
							onConfigChange={handleConfigChange}
							onLoadPreset={vadConfig.loadPreset}
							onReset={vadConfig.resetConfig}
							onSave={vadConfig.saveToFile}
							onDebugMode={handleDebugMode}
							isDirty={vadConfig.isDirty}
							isDebugMode={isDebugMode}
						/>
					</section>

					{/* Status Indicators */}
					<section className="dashboard-card status-card">
						<h3>Status</h3>
						<div className="status-grid">
							<div className={`status-item ${isRecording ? 'active' : ''}`}>
								<span className="status-label">Recording</span>
								<span className="status-indicator">{isRecording ? '🔴' : '⚫'}</span>
							</div>
							<div className={`status-item ${vad.userSpeaking ? 'active' : ''}`}>
								<span className="status-label">User Speaking</span>
								<span className="status-indicator">{vad.userSpeaking ? '🟢' : '⚫'}</span>
							</div>
							<div className={`status-item ${vad.loading ? 'active' : ''}`}>
								<span className="status-label">VAD Loading</span>
								<span className="status-indicator">{vad.loading ? '🟡' : '⚫'}</span>
							</div>
							{vad.errored && (
								<div className="status-item error">
									<span className="status-label">Error</span>
									<span className="status-error">{vad.errored}</span>
								</div>
							)}
						</div>
					</section>

					{/* Help Section */}
					<section className="dashboard-card help-card">
						<h3>How to Use</h3>
						<ol className="help-list">
							<li>Click <strong>Start Recording</strong> to begin monitoring</li>
							<li>Speak into your microphone to see VAD in action</li>
							<li>Adjust sliders to tune parameters in real-time</li>
							<li>Watch the energy graph and event markers</li>
							<li>Click <strong>Export Config</strong> to save your settings</li>
							<li>Stop and restart recording to apply new configuration</li>
						</ol>
					</section>
				</div>
			</div>
		</div>
	)
}
