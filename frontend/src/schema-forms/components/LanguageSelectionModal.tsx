/**
 * LanguageSelectionModal - Initial modal to select spoken language
 *
 * Appears when user first opens the form. Forces language selection before proceeding.
 * After language is selected, the disclaimer modal will appear.
 *
 * Design: Minimal English text - uses icons and native language names for accessibility
 */

import React from 'react'
import { SPOKEN_LANGUAGES } from '../../shared/languages'
import './DisclaimerModal.css'

interface LanguageSelectionModalProps {
	onLanguageSelect: (language: string) => void
}

export function LanguageSelectionModal({ onLanguageSelect }: LanguageSelectionModalProps) {
	const [selectedLanguage, setSelectedLanguage] = React.useState('')

	const handleSubmit = () => {
		if (selectedLanguage) {
			onLanguageSelect(selectedLanguage)
		}
	}

	return (
		<div
			className="disclaimer-modal-overlay"
			onClick={(e) => e.stopPropagation()}
		>
			<div
				className="disclaimer-modal-content"
				role="dialog"
				aria-modal="true"
				aria-labelledby="language-selection-title"
			>
				{/* Large icon - universally understood */}
				<div style={{ fontSize: '64px', textAlign: 'center', marginBottom: '24px' }}>🌍</div>

				{/* Minimal title - icon makes it clear */}
				<h2 id="language-selection-title" className="disclaimer-modal-title" style={{ marginBottom: '32px' }}>
					🗣️💬
				</h2>

				{/* Language selector - uses native names */}
				<div style={{ marginBottom: '32px' }}>
					<select
						id="language-select"
						value={selectedLanguage}
						onChange={(e) => setSelectedLanguage(e.target.value)}
						autoFocus
						style={{
							width: '100%',
							padding: '16px 20px',
							fontSize: '20px',
							border: '3px solid #2563eb',
							borderRadius: '12px',
							backgroundColor: 'white',
							cursor: 'pointer',
							transition: 'all 0.2s',
							textAlign: 'center',
							fontWeight: 600
						}}
					>
						<option value="">🌍 ⬇️</option>
						{SPOKEN_LANGUAGES.map(lang => (
							<option key={lang.code} value={lang.name}>
								{lang.flag} {lang.nativeName}
							</option>
						))}
					</select>
				</div>

				{/* Continue button - arrow is universal */}
				<div className="disclaimer-modal-buttons">
					<button
						className="disclaimer-modal-button disclaimer-modal-button--primary"
						onClick={handleSubmit}
						disabled={!selectedLanguage}
						type="button"
						style={{
							opacity: selectedLanguage ? 1 : 0.5,
							cursor: selectedLanguage ? 'pointer' : 'not-allowed',
							fontSize: '24px',
							padding: '20px'
						}}
					>
						✓ ➜
					</button>
				</div>
			</div>
		</div>
	)
}
