/**
 * Unit tests for LanguageSelector component
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'
import { LanguageSelector } from './LanguageSelector'
import type { LanguageStatusMessage } from '../shared/halfCascadeTypes'

describe('LanguageSelector Component', () => {
	beforeEach(() => {
		sessionStorage.clear()
	})

	afterEach(() => {
		sessionStorage.clear()
	})

	describe('Desktop View', () => {
		it('should render with default settings', () => {
			render(<LanguageSelector />)

			expect(screen.getByText('Conversation Language')).toBeInTheDocument()
			expect(screen.getByLabelText('Auto-detect language')).toBeChecked()
			expect(screen.getByText('English (US)')).toBeInTheDocument()
		})

		it('should toggle auto-detect', () => {
			const onAutoDetectChange = vi.fn()
			render(<LanguageSelector onAutoDetectChange={onAutoDetectChange} />)

			const checkbox = screen.getByLabelText('Auto-detect language')
			expect(checkbox).toBeChecked()

			fireEvent.click(checkbox)

			expect(checkbox).not.toBeChecked()
			expect(onAutoDetectChange).toHaveBeenCalledWith(false)
		})

		it('should open language dropdown when clicked', () => {
			render(<LanguageSelector />)

			// Disable auto-detect first
			const checkbox = screen.getByLabelText('Auto-detect language')
			fireEvent.click(checkbox)

			// Click dropdown button
			const button = screen.getByRole('button', { name: /English/i })
			fireEvent.click(button)

			// Should show list of languages
			expect(screen.getByRole('listbox')).toBeInTheDocument()
			expect(screen.getByText('Spanish (Spain)')).toBeInTheDocument()
			expect(screen.getByText('Chinese (Simplified)')).toBeInTheDocument()
		})

		it('should select a language from dropdown', () => {
			const onLanguageChange = vi.fn()
			render(<LanguageSelector onLanguageChange={onLanguageChange} />)

			// Disable auto-detect
			const checkbox = screen.getByLabelText('Auto-detect language')
			fireEvent.click(checkbox)

			// Open dropdown
			const button = screen.getByRole('button', { name: /English/i })
			fireEvent.click(button)

			// Select Spanish
			const spanishOption = screen.getByText('Spanish (Spain)')
			fireEvent.click(spanishOption)

			expect(onLanguageChange).toHaveBeenCalledWith('es-ES')
		})

		it('should persist language preference to sessionStorage', () => {
			render(<LanguageSelector />)

			// Disable auto-detect
			const checkbox = screen.getByLabelText('Auto-detect language')
			fireEvent.click(checkbox)

			// Open dropdown and select Spanish
			const button = screen.getByRole('button', { name: /English/i })
			fireEvent.click(button)
			fireEvent.click(screen.getByText('Spanish (Spain)'))

			// Check sessionStorage
			expect(sessionStorage.getItem('vff_language_preference')).toBe('es-ES')
			expect(sessionStorage.getItem('vff_auto_detect_language')).toBe('false')
		})

		it('should load language preference from sessionStorage', () => {
			sessionStorage.setItem('vff_language_preference', 'es-ES')
			sessionStorage.setItem('vff_auto_detect_language', 'false')

			render(<LanguageSelector />)

			expect(screen.getByText('Spanish (Spain)')).toBeInTheDocument()
			expect(screen.getByLabelText('Auto-detect language')).not.toBeChecked()
		})

		it('should disable dropdown when auto-detect is enabled', () => {
			render(<LanguageSelector />)

			const button = screen.getByRole('button', { name: /English/i })
			expect(button).toBeDisabled()
		})

		it('should display detected language with confidence', () => {
			render(
				<LanguageSelector
					detectedLanguage="es-ES"
					languageConfidence={0.95}
				/>
			)

			expect(screen.getByText(/Spanish \(Spain\)/)).toBeInTheDocument()
			expect(screen.getByText(/95% confident/)).toBeInTheDocument()
		})

		it('should handle keyboard navigation (Enter key)', () => {
			const onLanguageChange = vi.fn()
			render(<LanguageSelector onLanguageChange={onLanguageChange} />)

			// Disable auto-detect
			fireEvent.click(screen.getByLabelText('Auto-detect language'))

			// Open dropdown
			const button = screen.getByRole('button', { name: /English/i })
			fireEvent.click(button)

			// Navigate with keyboard and press Enter
			const spanishOption = screen.getByText('Spanish (Spain)')
			fireEvent.keyDown(spanishOption, { key: 'Enter' })

			expect(onLanguageChange).toHaveBeenCalledWith('es-ES')
		})

		it('should handle keyboard navigation (Space key)', () => {
			const onLanguageChange = vi.fn()
			render(<LanguageSelector onLanguageChange={onLanguageChange} />)

			// Disable auto-detect
			fireEvent.click(screen.getByLabelText('Auto-detect language'))

			// Open dropdown
			const button = screen.getByRole('button', { name: /English/i })
			fireEvent.click(button)

			// Press Space on option
			const spanishOption = screen.getByText('Spanish (Spain)')
			fireEvent.keyDown(spanishOption, { key: ' ' })

			expect(onLanguageChange).toHaveBeenCalledWith('es-ES')
		})

		it('should close dropdown on Escape key', () => {
			render(<LanguageSelector />)

			// Disable auto-detect and open dropdown
			fireEvent.click(screen.getByLabelText('Auto-detect language'))
			const button = screen.getByRole('button', { name: /English/i })
			fireEvent.click(button)

			// Press Escape
			const spanishOption = screen.getByText('Spanish (Spain)')
			fireEvent.keyDown(spanishOption, { key: 'Escape' })

			// Dropdown should be closed
			expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
		})

		it('should respond to language status events', async () => {
			render(<LanguageSelector detectedLanguage={null} />)

			// Initially showing English
			expect(screen.getByText(/English/)).toBeInTheDocument()

			// Dispatch language status event
			const languageStatusEvent = new CustomEvent<LanguageStatusMessage>('vff:language-status', {
				detail: {
					type: 'language_status',
					detected: 'es-ES',
					current: 'es-ES',
					confidence: 0.95
				}
			})

			window.dispatchEvent(languageStatusEvent)

			// Component should log the detection (check console)
			// Note: actual display update happens via props change
		})
	})

	describe('Compact Mobile View', () => {
		it('should render compact view', () => {
			render(<LanguageSelector compact={true} />)

			expect(screen.getByText('English (US)')).toBeInTheDocument()
			expect(screen.getByLabelText(/auto-detect/i)).toBeInTheDocument()
		})

		it('should show auto-detect status in compact view', () => {
			render(<LanguageSelector compact={true} />)

			const button = screen.getByLabelText(/auto-detect/i)
			expect(button).toHaveAttribute('aria-pressed', 'true')
			expect(button.textContent).toContain('Auto')
		})

		it('should toggle auto-detect in compact view', () => {
			const onAutoDetectChange = vi.fn()
			render(
				<LanguageSelector
					compact={true}
					onAutoDetectChange={onAutoDetectChange}
				/>
			)

			const button = screen.getByLabelText(/Enable auto-detect|Disable auto-detect/i)
			fireEvent.click(button)

			expect(onAutoDetectChange).toHaveBeenCalled()
		})

		it('should display confidence in compact view', () => {
			render(
				<LanguageSelector
					compact={true}
					detectedLanguage="es-ES"
					languageConfidence={0.95}
				/>
			)

			expect(screen.getByText('(95%)')).toBeInTheDocument()
		})
	})

	describe('Accessibility', () => {
		it('should have proper ARIA attributes', () => {
			render(<LanguageSelector />)

			const button = screen.getByRole('button', { name: /English/i })
			expect(button).toHaveAttribute('aria-haspopup', 'listbox')
			expect(button).toHaveAttribute('aria-expanded', 'false')

			// Disable auto-detect and open dropdown
			fireEvent.click(screen.getByLabelText('Auto-detect language'))
			fireEvent.click(button)

			expect(button).toHaveAttribute('aria-expanded', 'true')

			// Check listbox has label
			const listbox = screen.getByRole('listbox')
			expect(listbox).toHaveAttribute('aria-label', 'Select language')
		})

		it('should have aria-selected on selected option', () => {
			render(<LanguageSelector />)

			// Disable auto-detect and open dropdown
			fireEvent.click(screen.getByLabelText('Auto-detect language'))
			const button = screen.getByRole('button', { name: /English/i })
			fireEvent.click(button)

			// English option should be selected
			const englishOption = screen.getByText('English (US)')
			expect(englishOption).toHaveAttribute('aria-selected', 'true')
		})

		it('should have live region for language status', () => {
			render(
				<LanguageSelector
					detectedLanguage="es-ES"
					languageConfidence={0.95}
				/>
			)

			const status = screen.getByRole('status')
			expect(status).toHaveAttribute('aria-live', 'polite')
			expect(status.textContent).toContain('Spanish (Spain)')
		})

		it('should support keyboard focus', () => {
			render(<LanguageSelector />)

			// Tab to checkbox
			const checkbox = screen.getByLabelText('Auto-detect language')
			checkbox.focus()
			expect(document.activeElement).toBe(checkbox)

			// Tab to dropdown button
			const button = screen.getByRole('button', { name: /English/i })
			button.focus()
			expect(document.activeElement).toBe(button)
		})
	})

	describe('Custom Props', () => {
		it('should accept custom className', () => {
			const { container } = render(<LanguageSelector className="custom-class" />)

			const selector = container.querySelector('.language-selector')
			expect(selector).toHaveClass('custom-class')
		})

		it('should call callbacks when provided', () => {
			const onLanguageChange = vi.fn()
			const onAutoDetectChange = vi.fn()

			render(
				<LanguageSelector
					onLanguageChange={onLanguageChange}
					onAutoDetectChange={onAutoDetectChange}
				/>
			)

			// Toggle auto-detect
			fireEvent.click(screen.getByLabelText('Auto-detect language'))
			expect(onAutoDetectChange).toHaveBeenCalledWith(false)

			// Select language
			const button = screen.getByRole('button', { name: /English/i })
			fireEvent.click(button)
			fireEvent.click(screen.getByText('Spanish (Spain)'))
			expect(onLanguageChange).toHaveBeenCalledWith('es-ES')
		})
	})
})
