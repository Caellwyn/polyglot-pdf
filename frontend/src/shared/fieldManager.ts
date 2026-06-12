/**
 * Field Manager - Step S6
 * 
 * Manages form field updates and manual edit detection.
 * DOM is the source of truth - AI adapts to user changes.
 */

import { escapeHtml } from './security'

export interface FieldUpdate {
	fieldId: string
	value: any
}

export interface FieldManagerOptions {
	onManualEdit?: (fieldId: string, value: string) => void
	schema?: any // Optional schema to set up listeners on all fields
}

export interface FieldManager {
	applyUpdates: (updates: FieldUpdate[]) => void
	destroy: () => void
}

/**
 * Create field manager for bookmarklet
 */
export function createFieldManager(options: FieldManagerOptions = {}): FieldManager {
	const confirmedFields = new Set<string>()
	const eventListeners = new Map<HTMLElement, () => void>()
	const lastEditTimestamp = new Map<string, number>() // Track last edit time per field
	const aiUpdatingFields = new Set<string>() // Track fields currently being updated by AI
	
	/**
	 * Listen for manual edits to clear AI confirmation
	 */
	function setupEditListener(element: HTMLElement, fieldId: string): void {
		// Avoid duplicate listeners
		if (eventListeners.has(element)) return

		const handleEdit = () => {
			// Ignore if AI is currently updating this field
			if (aiUpdatingFields.has(fieldId)) {
				return
			}
			
			// Debounce - ignore if same field edited within 100ms
			const now = Date.now()
			const lastEdit = lastEditTimestamp.get(fieldId) || 0
			if (now - lastEdit < 100) {
				return
			}
			lastEditTimestamp.set(fieldId, now)
			
			// If AI-confirmed, clear the badge
			if (confirmedFields.has(fieldId)) {
				removeConfirmationBadge(element, fieldId)
			}
			
			// Always notify about manual edits (even if not AI-confirmed yet)
			if (options.onManualEdit) {
				const value = (element as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement).value
				if (value && value.trim()) {  // Only notify if non-empty
					options.onManualEdit(fieldId, value)
				}
			}
		}

		// Listen for blur event (when user finishes editing and moves to next field)
		element.addEventListener('blur', handleEdit)
		// Also listen for change event (for dropdowns, radio buttons, checkboxes)
		element.addEventListener('change', handleEdit)

		// Store listener for cleanup
		eventListeners.set(element, handleEdit)
	}
	
	/**
	 * Set up listeners on all fields from schema
	 */
	function setupAllFieldListeners(fields: any[]): void {
		console.log('[VFF FieldManager] Setting up listeners on', fields.length, 'schema fields')
		
		for (const field of fields) {
			const fieldId = field.id
			if (!fieldId) continue
			
			// Try to find element by ID
			let element = document.getElementById(fieldId) as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement | null
			
			// Try by name attribute (for table fields, radio groups, checkbox groups)
			if (!element) {
				const inputs = document.querySelectorAll(`input[name="${fieldId}"], textarea[name="${fieldId}"], select[name="${fieldId}"]`)
				if (inputs.length > 0) {
					// For radio/checkbox groups, listen to all inputs
					inputs.forEach(input => {
						setupEditListener(input as HTMLElement, fieldId)
					})
					continue
				}
			}
			
			if (element) {
				setupEditListener(element, fieldId)
			}
		}
	}
	
	/**
	 * Remove confirmation badge when user edits
	 */
	function removeConfirmationBadge(element: HTMLElement, fieldId: string): void {
		// Remove outline
		element.style.outline = ''
		element.style.outlineOffset = ''

		// Remove checkmark
		const badge = element.parentElement?.querySelector('.vff-field-badge')
		if (badge) {
			badge.remove()
		}

		// Remove confirmation attribute
		element.removeAttribute('data-vff-confirmed')
		confirmedFields.delete(fieldId)

		console.log('[VFF FieldManager] Cleared AI confirmation for:', fieldId)
	}
	
	// Set up listeners on all schema fields immediately (for manual edits detection)
	if (options.schema?.fields) {
		setupAllFieldListeners(options.schema.fields)
	}

	/**
	 * Apply AI field updates to DOM
	 */
	function applyUpdates(updates: FieldUpdate[]): void {
		console.log('[VFF FieldManager] 📝 Applying', updates.length, 'field update(s)')
		
		const results = {
			success: [] as string[],
			notFound: [] as string[],
			errors: [] as Array<{ fieldId: string, error: string }>
		}

		for (const update of updates) {
			// Mark field as being updated by AI (prevent manual edit callback)
			aiUpdatingFields.add(update.fieldId)
			
			const newValue = update.value || ''
			let element = document.getElementById(update.fieldId) as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement | null

		// Special handling for radio buttons, checkbox groups, and comboboxes which may not have IDs
		if (!element) {
			// Try to find by name attribute (for radio groups, checkbox groups, or table fields)
			const inputs = document.querySelectorAll(`input[name="${update.fieldId}"], textarea[name="${update.fieldId}"], select[name="${update.fieldId}"]`) as NodeListOf<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
			if (inputs.length > 0) {
				const firstInput = inputs[0] as HTMLInputElement
				
				// Check if it's a radio group or checkbox group (multiple with same name)
				if (inputs.length > 1) {
					if (firstInput.type === 'radio') {
						// This is a radio group
						handleRadioGroup(inputs as NodeListOf<HTMLInputElement>, newValue, update.fieldId)
						results.success.push(update.fieldId)
						continue
					} else if (firstInput.type === 'checkbox') {
						// This is a checkbox group (multiple checkboxes with same name)
						handleCheckboxGroup(inputs as NodeListOf<HTMLInputElement>, newValue, update.fieldId)
						results.success.push(update.fieldId)
						continue
					}
				}
				
				// Single input with name attribute (like table fields)
				// Treat it as the element and continue with normal processing
				element = firstInput
			}
			
			// Try to find combobox by aria-controls or other attributes
			if (!element) {
				const combobox = document.querySelector(`[role="combobox"][id="${update.fieldId}"], button[aria-haspopup="listbox"][id="${update.fieldId}"]`) as HTMLElement
				if (combobox) {
					handleCombobox(combobox, newValue, update.fieldId)
					results.success.push(update.fieldId)
					continue
				}
			}
			
			if (!element) {
				console.warn('[VFF FieldManager] ❌ Field not found:', update.fieldId)
				results.notFound.push(update.fieldId)
				continue
			}
		}		// Apply value to field based on element type
		const inputEl = element as HTMLInputElement
		const inputType = inputEl.type?.toLowerCase()
		
		// Handle different input types
		if (element.tagName === 'SELECT') {
			handleSelect(element as HTMLSelectElement, newValue, update.fieldId)
			
		} else if (inputType === 'checkbox') {
			handleCheckbox(inputEl, newValue, update.fieldId)
			
		} else if (inputType === 'radio') {
			// Single radio button - should have been caught by name selector above
			handleSingleRadio(inputEl, newValue, update.fieldId)
			
		} else if (element.tagName === 'INPUT' || element.tagName === 'TEXTAREA') {
			// Text, email, tel, textarea, etc.
			// Convert to string to handle numbers and other types safely
			const stringValue = String(newValue)
			;(element as HTMLInputElement | HTMLTextAreaElement).value = stringValue
			
			// Dispatch events for form handlers
			element.dispatchEvent(new Event('input', { bubbles: true }))
			element.dispatchEvent(new Event('change', { bubbles: true }))
			
			// Safe logging with truncation
			const displayValue = stringValue.substring(0, 50)
			console.log('[VFF FieldManager] Updated text field:', update.fieldId, '→', displayValue)
		}
		
		// Mark as AI-confirmed
		if (element) {
			element.setAttribute('data-vff-confirmed', 'true')
			confirmedFields.add(update.fieldId)

			// Add visual confirmation (green outline + checkmark)
			addConfirmationBadge(element)

			// Listen for manual edits
			setupEditListener(element, update.fieldId)
			
			// Track success
			results.success.push(update.fieldId)
			
			// Clear AI updating flag after a brief delay (allow events to settle)
			setTimeout(() => {
				aiUpdatingFields.delete(update.fieldId)
			}, 50)
		}
	}
	
	// Log summary of results
	console.log('[VFF FieldManager] 📊 Update summary:', {
		total: updates.length,
		success: results.success.length,
		notFound: results.notFound.length,
		errors: results.errors.length
	})
	
	if (results.notFound.length > 0) {
		console.warn('[VFF FieldManager] ⚠️ Fields not found:', results.notFound)
	}
	
	if (results.errors.length > 0) {
		console.error('[VFF FieldManager] ❌ Errors:', results.errors)
	}
	
	if (results.success.length > 0) {
		console.log('[VFF FieldManager] ✅ Successfully updated:', results.success)
	}
}
	
	/**
	 * Handle select dropdown
	 */
	function handleSelect(selectEl: HTMLSelectElement, newValue: string, fieldId: string): void {
		// An empty string means "clear this field" (bd polyglot-pdf-jbxm). Prefer
		// the explicit empty-value option when present (index 0 placeholder); fall
		// back to selectedIndex = -1 so the DOM reflects no selection.
		if (newValue === '') {
			const hasEmptyOption = selectEl.options.length > 0 && selectEl.options[0].value === ''
			if (hasEmptyOption) {
				selectEl.selectedIndex = 0
			} else {
				selectEl.selectedIndex = -1
			}
			selectEl.dispatchEvent(new Event('change', { bubbles: true }))
			selectEl.dispatchEvent(new Event('input', { bubbles: true }))
			console.log('[VFF FieldManager] ✓ Cleared select:', fieldId)
			return
		}

		// Try exact match first
		let matched = false
		for (let i = 0; i < selectEl.options.length; i++) {
			const option = selectEl.options[i]
			if (option.value === newValue || option.text === newValue) {
				selectEl.selectedIndex = i
				matched = true
				console.log('[VFF FieldManager] ✓ Exact match for select:', fieldId, '→', option.text)
				break
			}
		}

		// Try fuzzy match if exact match failed
		if (!matched) {
			const lowerValue = newValue.toLowerCase()
			for (let i = 0; i < selectEl.options.length; i++) {
				const option = selectEl.options[i]
				const lowerText = option.text.toLowerCase()
				const lowerOptionValue = option.value.toLowerCase()

				if (lowerText.includes(lowerValue) || lowerValue.includes(lowerText) ||
				    lowerOptionValue.includes(lowerValue) || lowerValue.includes(lowerOptionValue)) {
					selectEl.selectedIndex = i
					matched = true
					console.log('[VFF FieldManager] ≈ Fuzzy match for select:', fieldId, '→', option.text)
					break
				}
			}
		}

		if (!matched) {
			console.warn('[VFF FieldManager] ⚠️ No matching option found for:', newValue, 'in', fieldId)
		}

		// Dispatch change event for form handlers
		selectEl.dispatchEvent(new Event('change', { bubbles: true }))
		selectEl.dispatchEvent(new Event('input', { bubbles: true }))
	}
	
	/**
	 * Handle checkbox input
	 */
	function handleCheckbox(checkboxEl: HTMLInputElement, newValue: string | boolean, fieldId: string): void {
		// Convert value to boolean - handle both string and boolean types
		let shouldCheck = false
		if (typeof newValue === 'boolean') {
			shouldCheck = newValue
		} else if (typeof newValue === 'string') {
			shouldCheck = newValue === 'true' || newValue === 'True' ||newValue === '1' || newValue === 'yes' || 
			              newValue === 'Yes' || newValue === 'on' || newValue === 'checked'
		}
		
		checkboxEl.checked = shouldCheck
		
		// Dispatch events for form handlers
		checkboxEl.dispatchEvent(new Event('change', { bubbles: true }))
		checkboxEl.dispatchEvent(new Event('input', { bubbles: true }))
		
		console.log('[VFF FieldManager] ✓ Updated checkbox:', fieldId, '→', shouldCheck, `(from ${typeof newValue}: ${newValue})`)
	}
	
	/**
	 * Handle checkbox group (multiple checkboxes with same name)
	 * Example: name="reason[]" with values ["Depressed Mood", "Divorce/Custody"]
	 */
	function handleCheckboxGroup(checkboxInputs: NodeListOf<HTMLInputElement>, newValue: any, fieldId: string): void {
		// Convert single value to array
		const values = Array.isArray(newValue) ? newValue : [newValue]
		
		console.log('[VFF FieldManager] 📋 Checkbox group:', fieldId)
		console.log('  Requested values:', values)
		
		// Get all available checkbox values for logging
		const availableValues: string[] = []
		for (const checkbox of checkboxInputs) {
			availableValues.push(checkbox.value || getCheckboxLabel(checkbox))
		}
		console.log('  Available checkboxes:', availableValues)
		
		let checkedCount = 0
		const matchedValues: string[] = []
		const unmatchedValues: string[] = []
		
		// Track which requested values were matched
		const valueMatched = new Map<string, boolean>()
		for (const val of values) {
			valueMatched.set(String(val), false)
		}
		
		// Iterate through all checkboxes in the group
		for (const checkbox of checkboxInputs) {
			// Get the checkbox's value or associated label text
			const checkboxValue = checkbox.value || getCheckboxLabel(checkbox)
			
			// Check if this checkbox's value is in the list of values to check
			let matchedWithValue: string | null = null
			const shouldCheck = values.some(val => {
				const valStr = String(val)
				// Try exact match first
				if (checkboxValue === valStr) {
					matchedWithValue = valStr
					return true
				}
				
				// Try case-insensitive match
				if (checkboxValue.toLowerCase() === valStr.toLowerCase()) {
					matchedWithValue = valStr
					return true
				}
				
				// Normalize both strings for better matching
				// Remove punctuation, normalize whitespace, convert to lowercase
				const normalize = (s: string) => s
					.toLowerCase()
					.replace(/[\/\-_,]/g, ' ')  // Replace separators with spaces
					.replace(/\s+/g, ' ')        // Normalize whitespace
					.trim()
				
				const normalizedCheckbox = normalize(checkboxValue)
				const normalizedVal = normalize(valStr)
				
				// Try normalized exact match
				if (normalizedCheckbox === normalizedVal) {
					matchedWithValue = valStr
					return true
				}
				
				// Try fuzzy match (contains) after normalization
				if (normalizedCheckbox.includes(normalizedVal) || 
				    normalizedVal.includes(normalizedCheckbox)) {
					matchedWithValue = valStr
					return true
				}
				
				return false
			})
			
			// Track which values were matched
			if (shouldCheck && matchedWithValue) {
				valueMatched.set(matchedWithValue, true)
				matchedValues.push(checkboxValue)
			}
			
			// Update checkbox state
			checkbox.checked = shouldCheck
			
			if (shouldCheck) {
				checkedCount++
				
				// Mark as confirmed
				checkbox.setAttribute('data-vff-confirmed', 'true')
				confirmedFields.add(fieldId)
				addConfirmationBadge(checkbox)
				setupEditListener(checkbox, fieldId)
			}
			
			// Dispatch events for form handlers
			checkbox.dispatchEvent(new Event('change', { bubbles: true }))
			checkbox.dispatchEvent(new Event('input', { bubbles: true }))
		}
		
		// Identify unmatched values
		for (const [val, matched] of valueMatched.entries()) {
			if (!matched) {
				unmatchedValues.push(val)
			}
		}
		
		console.log('[VFF FieldManager] ✅ Checkbox group result:', {
			fieldId,
			requested: values.length,
			matched: matchedValues.length,
			unmatched: unmatchedValues.length,
			total: checkboxInputs.length
		})
		
		if (matchedValues.length > 0) {
			console.log('  ✓ Matched & checked:', matchedValues)
		}
		
		if (unmatchedValues.length > 0) {
			console.warn('  ⚠️ Could not match:', unmatchedValues)
			console.warn('  💡 Try one of:', availableValues)
		}
	}
	
	/**
	 * Get the label text associated with a checkbox
	 */
	function getCheckboxLabel(checkbox: HTMLInputElement): string {
		// Try to find associated label by 'for' attribute
		const labelFor = document.querySelector(`label[for="${checkbox.id}"]`)
		if (labelFor) {
			return labelFor.textContent?.trim() || ''
		}
		
		// Try to find parent label
		const parentLabel = checkbox.closest('label')
		if (parentLabel) {
			// Clone the label and remove the input to get just the text
			const clone = parentLabel.cloneNode(true) as HTMLElement
			const input = clone.querySelector('input')
			if (input) input.remove()
			return clone.textContent?.trim() || ''
		}
		
		// Fallback to next sibling text
		const nextText = checkbox.nextSibling
		if (nextText && nextText.nodeType === Node.TEXT_NODE) {
			return nextText.textContent?.trim() || ''
		}
		
		return checkbox.value
	}

	
	/**
	 * Handle radio group (multiple radio inputs with same name)
	 */
	function handleRadioGroup(radioInputs: NodeListOf<HTMLInputElement>, newValue: string, fieldId: string): void {
		let matched = false
		
		// Try to find matching radio button by value
		for (const radio of radioInputs) {
			if (radio.value === newValue) {
				radio.checked = true
				matched = true
				
				// Dispatch events
				radio.dispatchEvent(new Event('change', { bubbles: true }))
				radio.dispatchEvent(new Event('input', { bubbles: true }))
				
				// Mark as confirmed
				radio.setAttribute('data-vff-confirmed', 'true')
				confirmedFields.add(fieldId)
				addConfirmationBadge(radio)
				setupEditListener(radio, fieldId)
				
				console.log('[VFF FieldManager] ✓ Selected radio:', fieldId, '→', newValue)
				break
			}
		}
		
		// Try fuzzy match if exact match failed
		if (!matched) {
			const lowerValue = newValue.toLowerCase()
			for (const radio of radioInputs) {
				const lowerRadioValue = radio.value.toLowerCase()
				if (lowerRadioValue.includes(lowerValue) || lowerValue.includes(lowerRadioValue)) {
					radio.checked = true
					matched = true
					
					// Dispatch events
					radio.dispatchEvent(new Event('change', { bubbles: true }))
					radio.dispatchEvent(new Event('input', { bubbles: true }))
					
					// Mark as confirmed
					radio.setAttribute('data-vff-confirmed', 'true')
					confirmedFields.add(fieldId)
					addConfirmationBadge(radio)
					setupEditListener(radio, fieldId)
					
					console.log('[VFF FieldManager] ≈ Fuzzy match radio:', fieldId, '→', radio.value)
					break
				}
			}
		}
		
		if (!matched) {
			console.warn('[VFF FieldManager] ⚠️ No matching radio option found for:', newValue, 'in', fieldId)
		}
	}
	
	/**
	 * Handle single radio button (fallback)
	 */
	function handleSingleRadio(radioEl: HTMLInputElement, newValue: string, fieldId: string): void {
		// Check if value matches
		if (radioEl.value === newValue) {
			radioEl.checked = true
			
			// Dispatch events
			radioEl.dispatchEvent(new Event('change', { bubbles: true }))
			radioEl.dispatchEvent(new Event('input', { bubbles: true }))
			
			console.log('[VFF FieldManager] ✓ Selected single radio:', fieldId)
		} else {
			console.warn('[VFF FieldManager] ⚠️ Radio value mismatch:', radioEl.value, '!==', newValue)
		}
	}
	
	/**
	 * Handle combobox (React/custom dropdowns)
	 */
	function handleCombobox(comboboxEl: HTMLElement, newValue: string, fieldId: string): void {
		// For React comboboxes, we need to:
		// 1. Click to open
		// 2. Find the option
		// 3. Click it
		
		// This is complex and may not work for all React implementations
		// For now, just log a warning
		console.warn('[VFF FieldManager] ⚠️ Combobox filling not fully supported yet:', fieldId)
		console.log('[VFF FieldManager] Combobox should be filled with:', newValue)
		
		// Try to set aria-valuenow or data attribute as fallback
		comboboxEl.setAttribute('aria-valuenow', newValue)
		comboboxEl.setAttribute('data-vff-value', newValue)
		
		// Dispatch click to potentially open dropdown
		comboboxEl.click()
	}

	/**
	 * Add green outline and checkmark to confirmed field
	 */
	function addConfirmationBadge(element: HTMLElement): void {
		// Add green outline
		element.style.outline = '2px solid #10b981'
		element.style.outlineOffset = '2px'

		// Add checkmark (if not already present)
		const existingBadge = element.parentElement?.querySelector('.vff-field-badge')
		if (existingBadge) return

		const badge = document.createElement('span')
		badge.className = 'vff-field-badge'
		badge.textContent = '✓'
		badge.style.cssText = `
			position: absolute;
			top: 50%;
			right: 8px;
			transform: translateY(-50%);
			color: #10b981;
			font-weight: bold;
			font-size: 18px;
			pointer-events: none;
			z-index: 1000;
		`

		// Position relative to field
		const parent = element.parentElement
		if (parent && getComputedStyle(parent).position === 'static') {
			parent.style.position = 'relative'
		}

		element.parentElement?.appendChild(badge)
	}

	/**
	 * Cleanup all listeners
	 */
	function destroy(): void {
		console.log('[VFF FieldManager] Destroying, cleaning up', eventListeners.size, 'listeners')

		// Remove all event listeners
		for (const [element, handler] of eventListeners.entries()) {
			element.removeEventListener('blur', handler)
			element.removeEventListener('change', handler)
		}

		// Clear all confirmation badges
		document.querySelectorAll('[data-vff-confirmed]').forEach((el) => {
			el.removeAttribute('data-vff-confirmed')
			;(el as HTMLElement).style.outline = ''
			;(el as HTMLElement).style.outlineOffset = ''
		})

		document.querySelectorAll('.vff-field-badge').forEach((badge) => {
			badge.remove()
		})

		eventListeners.clear()
		confirmedFields.clear()
		lastEditTimestamp.clear()
	}

	return {
		applyUpdates,
		destroy,
	}
}
