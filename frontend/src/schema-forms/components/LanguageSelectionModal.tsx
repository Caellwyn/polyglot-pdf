/**
 * LanguageSelectionModal - Initial modal to select form and spoken language
 *
 * Appears when user first opens the app. Forces both selections before proceeding.
 * After selections are made, the disclaimer modal will appear.
 *
 * Design: Minimal English text - uses icons and native language names for accessibility
 */

import React, { useEffect, useState } from 'react'
import { SPOKEN_LANGUAGES } from '../../shared/languages'
import { getBackendHttpUrl } from '../utils/pdfFiller'
import './DisclaimerModal.css'

interface FormKitInfo {
	id: string
	label: string
	description?: string
}

interface LanguageSelectionModalProps {
	onSelection: (formId: string, language: string) => void
	/** Optional: Pre-selected form ID (skips form selection if provided) */
	preselectedFormId?: string
}

export function LanguageSelectionModal({ onSelection, preselectedFormId }: LanguageSelectionModalProps) {
	const [forms, setForms] = useState<FormKitInfo[]>([])
	const [selectedFormId, setSelectedFormId] = useState(preselectedFormId || '')
	const [selectedLanguage, setSelectedLanguage] = useState('')
	const [loading, setLoading] = useState(true)
	const [error, setError] = useState<string | null>(null)

	// Load available forms from backend
	useEffect(() => {
		async function loadForms() {
			// Skip loading if form is preselected
			if (preselectedFormId) {
				setSelectedFormId(preselectedFormId)
				setLoading(false)
				return
			}

			try {
				setLoading(true)
				setError(null)
				const backendUrl = getBackendHttpUrl()
				const response = await fetch(`${backendUrl}/api/form-kits`)

				if (!response.ok) {
					throw new Error(`Failed to load forms: ${response.statusText}`)
				}

				const data = await response.json()
				setForms(data.forms || [])

			} catch (err) {
				console.error('[LanguageSelectionModal] Failed to load forms:', err)
				setError('Unable to load available forms')
			} finally {
				setLoading(false)
			}
		}

		loadForms()
	}, [preselectedFormId])

	const handleSubmit = () => {
		if (selectedFormId && selectedLanguage) {
			onSelection(selectedFormId, selectedLanguage)
		}
	}

	const canSubmit = selectedFormId && selectedLanguage
	const showFormSelector = !preselectedFormId && forms.length >= 1

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
					📋 🗣️💬
				</h2>

				{loading ? (
					<div style={{ textAlign: 'center', padding: '20px' }}>
						<span style={{ fontSize: '32px' }}>⏳</span>
					</div>
				) : error ? (
					<div style={{ textAlign: 'center', padding: '20px', color: '#dc2626' }}>
						<span style={{ fontSize: '32px' }}>⚠️</span>
						<p style={{ marginTop: '8px', fontSize: '14px' }}>{error}</p>
					</div>
				) : (
					<>
						{/* Form selector - only show if multiple forms available */}
						{showFormSelector && (
							<div style={{ marginBottom: '24px' }}>
								<div style={{ fontSize: '24px', textAlign: 'center', marginBottom: '8px' }}>📋</div>
								<select
									id="form-select"
									value={selectedFormId}
									onChange={(e) => setSelectedFormId(e.target.value)}
									style={{
										width: '100%',
										padding: '16px 20px',
										fontSize: '18px',
										border: '3px solid #2563eb',
										borderRadius: '12px',
										backgroundColor: 'white',
										cursor: 'pointer',
										transition: 'all 0.2s',
										textAlign: 'center',
										fontWeight: 600
									}}
								>
									<option value="">📋 ⬇️</option>
									{forms.map(form => (
										<option key={form.id} value={form.id}>
											{form.label}
										</option>
									))}
								</select>
							</div>
						)}

						{/* Language selector - uses native names */}
						<div style={{ marginBottom: '32px' }}>
							<div style={{ fontSize: '24px', textAlign: 'center', marginBottom: '8px' }}>🗣️</div>
							<select
								id="language-select"
								value={selectedLanguage}
								onChange={(e) => setSelectedLanguage(e.target.value)}
								autoFocus={!showFormSelector}
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
									<option key={lang.name} value={lang.name}>
										{lang.nativeName}
									</option>
								))}
							</select>
						</div>
					</>
				)}

				{/* Continue button - arrow is universal */}
				<div className="disclaimer-modal-buttons">
					<button
						className="disclaimer-modal-button disclaimer-modal-button--primary"
						onClick={handleSubmit}
						disabled={!canSubmit || loading}
						type="button"
						style={{
							opacity: canSubmit && !loading ? 1 : 0.5,
							cursor: canSubmit && !loading ? 'pointer' : 'not-allowed',
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
