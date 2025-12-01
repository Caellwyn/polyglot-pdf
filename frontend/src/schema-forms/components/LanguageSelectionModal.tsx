/**
 * LanguageSelectionModal - Initial modal to select form and spoken language
 *
 * Appears when user first opens the app. Forces both selections before proceeding.
 * After selections are made, the disclaimer modal will appear.
 *
 * Design: Wizard-style flow with large, clickable cards for accessibility.
 * Step 1: Language Selection (large native names)
 * Step 2: Form Selection (if multiple forms available)
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

type WizardStep = 'loading' | 'form-selection' | 'language-selection' | 'error'

export function LanguageSelectionModal({ onSelection, preselectedFormId }: LanguageSelectionModalProps) {
	const [forms, setForms] = useState<FormKitInfo[]>([])
	const [selectedFormId, setSelectedFormId] = useState(preselectedFormId || '')
	const [selectedLanguage, setSelectedLanguage] = useState('')
	const [step, setStep] = useState<WizardStep>('loading')
	const [error, setError] = useState<string | null>(null)

	// Load available forms from backend
	useEffect(() => {
		async function loadForms() {
			try {
				setStep('loading')
				setError(null)
				const backendUrl = getBackendHttpUrl()
				const response = await fetch(`${backendUrl}/api/form-kits`)

				if (!response.ok) {
					throw new Error(`Failed to load forms: ${response.statusText}`)
				}

				const data = await response.json()
				const loadedForms = data.forms || []
				setForms(loadedForms)

				// Initial step is ALWAYS language selection
				setStep('language-selection')

				// If preselected form, set it
				if (preselectedFormId) {
					setSelectedFormId(preselectedFormId)
				}

			} catch (err) {
				console.error('[LanguageSelectionModal] Failed to load forms:', err)
				setError('Unable to load available forms')
				setStep('error')
			}
		}

		loadForms()
	}, [preselectedFormId])

	const handleLanguageSelect = (language: string) => {
		setSelectedLanguage(language)

		// If form is already selected (preselected or single option), we are done
		if (selectedFormId) {
			onSelection(selectedFormId, language)
		} else {
			// Otherwise, move to form selection
			setStep('form-selection')
		}
	}

	const handleFormSelect = (formId: string) => {
		setSelectedFormId(formId)
		// We have language (from step 1) and form (now), so we are done
		if (selectedLanguage) {
			onSelection(formId, selectedLanguage)
		}
	}

	const handleBack = () => {
		// Back from form selection goes to language selection
		if (step === 'form-selection') {
			setStep('language-selection')
			// setSelectedLanguage('') // Optional: clear language if going back? Or keep it? keeping for now.
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
				aria-labelledby="wizard-title"
				style={{ maxWidth: '800px' }} // Wider for card grid
			>
				{step === 'loading' && (
					<div style={{ textAlign: 'center', padding: '40px' }}>
						<div style={{ fontSize: '48px', marginBottom: '20px' }}>⏳</div>
						<h2 style={{ fontSize: '24px', color: '#666' }}>Loading...</h2>
					</div>
				)}

				{step === 'error' && (
					<div style={{ textAlign: 'center', padding: '20px', color: '#dc2626' }}>
						<div style={{ fontSize: '48px', marginBottom: '20px' }}>⚠️</div>
						<h2 style={{ fontSize: '24px', marginBottom: '10px' }}>Error</h2>
						<p>{error}</p>
					</div>
				)}

				{step === 'language-selection' && (
					<div className="wizard-step">
						<h2 id="wizard-title" className="disclaimer-modal-title">
							🗣️ Select Language / Seleccione Idioma
						</h2>

						<div className="card-grid language-grid">
							{SPOKEN_LANGUAGES.map(lang => (
								<button
									key={lang.name}
									className="selection-card language-card"
									onClick={() => handleLanguageSelect(lang.name)}
									type="button"
								>
									<div className="card-native-name">{lang.nativeName}</div>
									<div className="card-english-name">{lang.name}</div>
								</button>
							))}
						</div>
					</div>
				)}

				{step === 'form-selection' && (
					<div className="wizard-step">
						<div style={{ display: 'flex', alignItems: 'center', marginBottom: '24px' }}>
							<button
								onClick={handleBack}
								className="back-button"
								title="Back"
							>
								⬅️
							</button>
							<h2 id="wizard-title" className="disclaimer-modal-title" style={{ margin: 0, flex: 1 }}>
								📋 Select Form / Seleccione Formulario
							</h2>
						</div>
						<div className="card-grid">
							{forms.map(form => (
								<button
									key={form.id}
									className="selection-card"
									onClick={() => handleFormSelect(form.id)}
									type="button"
								>
									<div className="card-icon">📄</div>
									<div className="card-label">{form.label}</div>
									{form.description && (
										<div className="card-sublabel">{form.description}</div>
									)}
								</button>
							))}
						</div>
					</div>
				)}
			</div>
		</div>
	)
}
