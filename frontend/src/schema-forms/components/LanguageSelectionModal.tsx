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

import { useState } from 'react'
import { SPOKEN_LANGUAGES } from '../../shared/languages'
import type { FormKitDescriptor } from '../types/formKit'
import './DisclaimerModal.css'

interface LanguageSelectionModalProps {
	/**
	 * Available forms, already resolved by the parent (SchemaFormDemo). The parent
	 * owns the backend/static-manifest fetch (with its local-dev fallback), so the
	 * modal never fetches the form list itself -- it is only rendered once the
	 * parent has a non-empty forms list. See bd polyglot-pdf-jzvs: the modal used
	 * to fetch /api/form-kits directly with no static fallback, so it showed
	 * "Unable to load available forms" in backend-less local dev even though the
	 * parent's static /form-kits/index.json fetch succeeded.
	 *
	 * Optional because the VoiceOverlay callers always pass `preselectedFormId`, so
	 * the form-selection step (the only consumer of this list) is unreachable there.
	 */
	forms?: FormKitDescriptor[]
	onSelection: (formId: string, language: string) => void
	/** Optional: Pre-selected form ID (skips form selection if provided) */
	preselectedFormId?: string
}

type WizardStep = 'form-selection' | 'language-selection'

export function LanguageSelectionModal({ forms = [], onSelection, preselectedFormId }: LanguageSelectionModalProps) {
	const [selectedFormId, setSelectedFormId] = useState(preselectedFormId || '')
	const [selectedLanguage, setSelectedLanguage] = useState('')
	// Initial step is ALWAYS language selection; forms arrive fully resolved as a prop.
	const [step, setStep] = useState<WizardStep>('language-selection')

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
