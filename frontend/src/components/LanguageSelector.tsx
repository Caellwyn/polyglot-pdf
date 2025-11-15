/**
 * Language Selector Component - Phase 4B
 *
 * Provides language selection UI for half-cascade mode:
 * - Dropdown with 20+ supported languages
 * - Auto-detect toggle (default: on)
 * - Current language indicator with confidence
 * - sessionStorage persistence
 * - Keyboard accessible (WCAG 2.1)
 * - Mobile-friendly
 */

import React, { useState, useEffect, useCallback } from 'react'
import {
	SUPPORTED_LANGUAGE_CODES,
	LANGUAGE_DISPLAY_NAMES,
	type LanguageCode,
	getLanguageDisplayName
} from '../shared/halfCascadeTypes'
import type { LanguageStatusMessage } from '../shared/halfCascadeTypes'

const LANGUAGE_PREFERENCE_KEY = 'vff_language_preference'
const AUTO_DETECT_KEY = 'vff_auto_detect_language'

interface LanguagePreference {
	selectedLanguage: LanguageCode
	autoDetect: boolean
}

export interface LanguageSelectorProps {
	/** Current detected language (from backend) */
	detectedLanguage?: string | null
	/** Confidence of language detection (0-1) */
	languageConfidence?: number | null
	/** Callback when user manually selects a language */
	onLanguageChange?: (language: LanguageCode) => void
	/** Callback when auto-detect toggle changes */
	onAutoDetectChange?: (enabled: boolean) => void
	/** Compact mode for mobile */
	compact?: boolean
	/** Custom CSS class */
	className?: string
}

/**
 * Load language preference from sessionStorage
 */
function loadLanguagePreference(): LanguagePreference {
	try {
		const stored = sessionStorage.getItem(LANGUAGE_PREFERENCE_KEY)
		const autoDetectStored = sessionStorage.getItem(AUTO_DETECT_KEY)

		return {
			selectedLanguage: (stored as LanguageCode) || 'en-US',
			autoDetect: autoDetectStored !== 'false'  // Default to true
		}
	} catch (error) {
		console.error('[LanguageSelector] Failed to load preference:', error)
		return {
			selectedLanguage: 'en-US',
			autoDetect: true
		}
	}
}

/**
 * Save language preference to sessionStorage
 */
function saveLanguagePreference(preference: LanguagePreference): void {
	try {
		sessionStorage.setItem(LANGUAGE_PREFERENCE_KEY, preference.selectedLanguage)
		sessionStorage.setItem(AUTO_DETECT_KEY, String(preference.autoDetect))
	} catch (error) {
		console.error('[LanguageSelector] Failed to save preference:', error)
	}
}

export const LanguageSelector: React.FC<LanguageSelectorProps> = ({
	detectedLanguage,
	languageConfidence,
	onLanguageChange,
	onAutoDetectChange,
	compact = false,
	className = ''
}) => {
	const [preference, setPreference] = useState<LanguagePreference>(loadLanguagePreference())
	const [isOpen, setIsOpen] = useState(false)

	// Listen for language status updates from backend
	useEffect(() => {
		const handleLanguageStatus = (event: Event) => {
			const customEvent = event as CustomEvent<LanguageStatusMessage>
			const message = customEvent.detail

			// Auto-update displayed language when detected
			if (preference.autoDetect && message.detected) {
				console.log('[LanguageSelector] Auto-detected language:', message.detected)
			}
		}

		window.addEventListener('vff:language-status', handleLanguageStatus)

		return () => {
			window.removeEventListener('vff:language-status', handleLanguageStatus)
		}
	}, [preference.autoDetect])

	// Handle language selection
	const handleLanguageSelect = useCallback((language: LanguageCode) => {
		const newPreference = {
			...preference,
			selectedLanguage: language
		}

		setPreference(newPreference)
		saveLanguagePreference(newPreference)
		setIsOpen(false)

		if (onLanguageChange) {
			onLanguageChange(language)
		}
	}, [preference, onLanguageChange])

	// Handle auto-detect toggle
	const handleAutoDetectToggle = useCallback(() => {
		const newPreference = {
			...preference,
			autoDetect: !preference.autoDetect
		}

		setPreference(newPreference)
		saveLanguagePreference(newPreference)

		if (onAutoDetectChange) {
			onAutoDetectChange(newPreference.autoDetect)
		}
	}, [preference, onAutoDetectChange])

	// Handle keyboard navigation
	const handleKeyDown = useCallback((event: React.KeyboardEvent, language: LanguageCode) => {
		if (event.key === 'Enter' || event.key === ' ') {
			event.preventDefault()
			handleLanguageSelect(language)
		} else if (event.key === 'Escape') {
			setIsOpen(false)
		}
	}, [handleLanguageSelect])

	// Get display language (detected or selected)
	const displayLanguage = preference.autoDetect && detectedLanguage
		? detectedLanguage
		: preference.selectedLanguage

	const displayName = getLanguageDisplayName(displayLanguage)

	// Confidence indicator
	const confidencePercent = languageConfidence !== null && languageConfidence !== undefined
		? Math.round(languageConfidence * 100)
		: null

	if (compact) {
		// Compact mobile view
		return (
			<div className={`language-selector-compact ${className}`}>
				<div className="language-indicator">
					<span className="language-flag" role="img" aria-label="Language">
						🌐
					</span>
					<span className="language-name">{displayName}</span>
					{confidencePercent !== null && preference.autoDetect && (
						<span className="language-confidence" title="Detection confidence">
							({confidencePercent}%)
						</span>
					)}
				</div>

				<button
					className="auto-detect-toggle-compact"
					onClick={handleAutoDetectToggle}
					aria-label={preference.autoDetect ? 'Disable auto-detect' : 'Enable auto-detect'}
					aria-pressed={preference.autoDetect}
				>
					{preference.autoDetect ? '🔍 Auto' : '✋ Manual'}
				</button>
			</div>
		)
	}

	// Full desktop view
	return (
		<div className={`language-selector ${className}`}>
			<div className="language-selector-header">
				<label htmlFor="language-dropdown" className="language-label">
					Conversation Language
				</label>

				<label className="auto-detect-toggle">
					<input
						type="checkbox"
						checked={preference.autoDetect}
						onChange={handleAutoDetectToggle}
						aria-label="Auto-detect language"
					/>
					<span className="toggle-label">Auto-detect</span>
				</label>
			</div>

			<div className="language-dropdown-container">
				<button
					id="language-dropdown"
					className="language-dropdown-button"
					onClick={() => setIsOpen(!isOpen)}
					aria-haspopup="listbox"
					aria-expanded={isOpen}
					disabled={preference.autoDetect}
				>
					<span className="language-flag" role="img" aria-label="Language">
						🌐
					</span>
					<span className="language-name">{displayName}</span>
					{confidencePercent !== null && preference.autoDetect && (
						<span className="language-confidence" title="Detection confidence">
							{confidencePercent}% confidence
						</span>
					)}
					<span className="dropdown-arrow" aria-hidden="true">
						{isOpen ? '▲' : '▼'}
					</span>
				</button>

				{isOpen && !preference.autoDetect && (
					<ul
						className="language-dropdown-list"
						role="listbox"
						aria-label="Select language"
					>
						{SUPPORTED_LANGUAGE_CODES.map((code) => (
							<li
								key={code}
								role="option"
								tabIndex={0}
								className={`language-option ${preference.selectedLanguage === code ? 'selected' : ''}`}
								onClick={() => handleLanguageSelect(code)}
								onKeyDown={(e) => handleKeyDown(e, code)}
								aria-selected={preference.selectedLanguage === code}
							>
								{LANGUAGE_DISPLAY_NAMES[code]}
							</li>
						))}
					</ul>
				)}
			</div>

			{preference.autoDetect && detectedLanguage && (
				<div className="language-status" role="status" aria-live="polite">
					Detected: {displayName}
					{confidencePercent !== null && (
						<> ({confidencePercent}% confident)</>
					)}
				</div>
			)}
		</div>
	)
}

export default LanguageSelector
