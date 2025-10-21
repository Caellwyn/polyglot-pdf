/**
 * VAD Control Panel
 * 
 * Slider controls for tuning VAD parameters in real-time
 */

import React from 'react'
import { VADConfig, VAD_PRESETS } from './types'

interface VADControlPanelProps {
	config: VADConfig
	onConfigChange: (updates: Partial<VADConfig>) => void
	onLoadPreset: (presetName: string) => void
	onReset: () => void
	onSave: () => void
	onDebugMode: () => void
	isDirty: boolean
	isDebugMode: boolean
}

export const VADControlPanel: React.FC<VADControlPanelProps> = ({
	config,
	onConfigChange,
	onLoadPreset,
	onReset,
	onSave,
	onDebugMode,
	isDirty,
	isDebugMode,
}) => {
	return (
		<div className="vad-control-panel">
			<div className="panel-header">
				<h2>VAD Configuration</h2>
				<div className="button-group">
					<button 
						onClick={onDebugMode} 
						className={isDebugMode ? "btn-warning" : "btn-secondary"}
						title="Apply aggressive debug settings for testing"
					>
						{isDebugMode ? '🔧 Debug Mode ON' : '🐛 Debug Mode'}
					</button>
					<button onClick={onReset} disabled={!isDirty} className="btn-secondary">
						Reset
					</button>
					<button onClick={onSave} className="btn-primary">
						Export Config
					</button>
				</div>
			</div>

			{/* Presets */}
			<div className="control-section">
				<h3>Presets</h3>
				<div className="preset-buttons">
					{VAD_PRESETS.map(preset => (
						<button
							key={preset.name}
							onClick={() => onLoadPreset(preset.name)}
							className="btn-preset"
							title={preset.description}
						>
							{preset.name}
						</button>
					))}
				</div>
			</div>

			{/* VAD Library Parameters */}
			<div className="control-section">
				<h3>VAD Thresholds</h3>
				
				<div className="control-item">
					<label>
						<span className="label-text">Positive Speech Threshold</span>
						<span className="label-value">{config.positiveSpeechThreshold.toFixed(2)}</span>
					</label>
					<input
						type="range"
						min="0.5"
						max="1.0"
						step="0.01"
						value={config.positiveSpeechThreshold}
						onChange={e => onConfigChange({
							positiveSpeechThreshold: parseFloat(e.target.value)
						})}
					/>
					<div className="help-text">
						Confidence needed to START speech detection (higher = less sensitive)
					</div>
				</div>

				<div className="control-item">
					<label>
						<span className="label-text">Negative Speech Threshold</span>
						<span className="label-value">{config.negativeSpeechThreshold.toFixed(2)}</span>
					</label>
					<input
						type="range"
						min="0.3"
						max="0.95"
						step="0.01"
						value={config.negativeSpeechThreshold}
						onChange={e => onConfigChange({
							negativeSpeechThreshold: parseFloat(e.target.value)
						})}
					/>
					<div className="help-text">
						Confidence needed to END speech detection (hysteresis)
					</div>
				</div>
			</div>

			{/* Timing Parameters */}
			<div className="control-section">
				<h3>Timing Parameters</h3>
				
				<div className="control-item">
					<label>
						<span className="label-text">Min Speech Duration</span>
						<span className="label-value">{config.minSpeechMs}ms</span>
					</label>
					<input
						type="range"
						min="50"
						max="1000"
						step="10"
						value={config.minSpeechMs}
						onChange={e => onConfigChange({
							minSpeechMs: parseInt(e.target.value)
						})}
					/>
					<div className="help-text">
						Minimum speech duration before triggering (prevents false positives)
					</div>
				</div>

				<div className="control-item">
					<label>
						<span className="label-text">Redemption Period</span>
						<span className="label-value">{config.redemptionMs}ms</span>
					</label>
					<input
						type="range"
						min="100"
						max="1000"
						step="10"
						value={config.redemptionMs}
						onChange={e => onConfigChange({
							redemptionMs: parseInt(e.target.value)
						})}
					/>
					<div className="help-text">
						Grace period before ending speech (prevents choppy cutoffs)
					</div>
				</div>
			</div>

			{isDebugMode && (
				<div className="info-banner">
					🔧 Debug Mode Active: Very sensitive thresholds for testing. 
					Click "Debug Mode" again to toggle off.
				</div>
			)}
			
			{isDirty && !isDebugMode && (
				<div className="warning-banner">
					⚠️ Configuration changed. Export and update source files to make changes permanent.
				</div>
			)}
		</div>
	)
}
