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
	 * The inputs of a radio/checkbox GROUP, or [] for a single control.
	 *
	 * SHARED by every id-vs-name resolution in this file, deliberately. Since bd
	 * polyglot-pdf-96um6 a group's FIRST option carries id={field.id}, so
	 * getElementById no longer returns null for a group -- and any site that
	 * resolves by id FIRST silently narrows the group to that one option. That
	 * broke setupAllFieldListeners (non-first options stopped notifying) and then
	 * applyUpdates 70 lines below it (a voice fill of a radio group selected
	 * NOTHING). Two sites, the same mistake twice -- hence one helper rather than
	 * two guards.
	 *
	 * Identified by NAME SHAPE, not by counting: a '[]' suffix is a checkbox group
	 * at any option count (a ONE-option group is a real shape here, validation.ts's
	 * isSingleOptionCheckbox), and a shared plain name on type=radio is a radio
	 * group.
	 *
	 * DUPLICATED, deliberately and unavoidably: tests/e2e/voice-harness/harness.js
	 * carries the same rule as groupInputs(), because it is injected into a live
	 * page and cannot import this module. If you change the rule here, change it
	 * there -- two sites holding one rule is precisely the shape that cost this
	 * bead two regressions already.
	 */
	function groupInputsFor(fieldId: string): HTMLInputElement[] {
		const bracketed = document.querySelectorAll(`input[name="${fieldId}[]"]`)
		if (bracketed.length) return Array.from(bracketed) as HTMLInputElement[]
		const plain = Array.from(
			document.querySelectorAll(`input[name="${fieldId}"]`)
		) as HTMLInputElement[]
		const radios = plain.filter(el => el.type === 'radio')
		return radios.length ? radios : []
	}

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
			
			// Groups resolve by NAME even when the id now resolves (bd
			// polyglot-pdf-96um6) -- see groupInputsFor. Binding only the id'd
			// option would leave every OTHER option unlistened, so selecting any
			// but the first would stop notifying the model.
			const groupEls = groupInputsFor(fieldId)
			if (groupEls.length) {
				groupEls.forEach(input => setupEditListener(input as HTMLElement, fieldId))
				continue
			}

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
		console.log('[VFF FieldManager] [note] Applying', updates.length, 'field update(s)')
		
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

			// Same rule as the listener site above: a group is resolved by NAME, not
			// by the id its first option now carries. Without this, getElementById
			// returns option[0] and the group falls into the SINGLE-control path --
			// handleSingleRadio returns false and a voice fill selects NOTHING.
			// Measured: filling 'Female' checked it TRUE before the id existed and
			// FALSE after, on 14 radio fields in i-90_v2 alone.
			if (groupInputsFor(update.fieldId).length) element = null

		// Special handling for radio buttons, checkbox groups, and comboboxes which may not have IDs
		if (!element) {
			// Try to find by name attribute (for radio groups, checkbox groups, or table fields)
			const inputs = document.querySelectorAll(`input[name="${update.fieldId}"], textarea[name="${update.fieldId}"], select[name="${update.fieldId}"]`) as NodeListOf<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
			if (inputs.length > 0) {
				const firstInput = inputs[0] as HTMLInputElement
				
				// Check if it's a radio group or checkbox group (multiple with same name)
				if (inputs.length > 1) {
					if (firstInput.type === 'radio') {
						// This is a radio group. Gate success on the actual match
						// (bd polyglot-pdf-c6t0e) -- this branch never reaches the
						// blanket "if (element)" badge block below, so an
						// unconditional push here was the ONLY success-tracking
						// site for radio groups, and it reported success (with
						// NO badge at all, since handleRadioGroup itself only
						// badges on a real match) even when nothing was selected.
						const groupMatched = handleRadioGroup(inputs as NodeListOf<HTMLInputElement>, newValue, update.fieldId)
						if (groupMatched) {
							results.success.push(update.fieldId)
						} else {
							results.notFound.push(update.fieldId)
						}
						continue
					} else if (firstInput.type === 'checkbox') {
						// This is a checkbox group (multiple checkboxes with same
						// name). Same fix as the radio group above.
						const groupMatched = handleCheckboxGroup(inputs as NodeListOf<HTMLInputElement>, newValue, update.fieldId)
						if (groupMatched) {
							results.success.push(update.fieldId)
						} else {
							results.notFound.push(update.fieldId)
						}
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
				console.warn('[VFF FieldManager] [X] Field not found:', update.fieldId)
				results.notFound.push(update.fieldId)
				// RELEASE THE FLAG BEFORE BAILING. It is set unconditionally above, and
				// cleared only on the two paths that reach the end of the loop -- so this
				// `continue` used to strand it set FOREVER, and setupEditListener's
				// `if (aiUpdatingFields.has(fieldId)) return` then swallowed EVERY later
				// manual edit to that field: no state write, no notify to the model. That
				// is the precise failure this bead exists to prevent, so a field the AI
				// could not fill must not also become uneditable by hand.
				// Same 50ms settle as the success paths, for the same reason.
				setTimeout(() => {
					aiUpdatingFields.delete(update.fieldId)
				}, 50)
				continue
			}
		}		// Apply value to field based on element type
		const inputEl = element as HTMLInputElement
		const inputType = inputEl.type?.toLowerCase()

		// Whether this element's value was actually applied (bd
		// polyglot-pdf-c6t0e): defaults true for handler shapes that always
		// succeed at doing exactly what was asked (checkbox toggle, plain
		// text/textarea write) -- only select/single-radio can silently
		// fail to match, so only they can flip this to false.
		let matched = true

		// Handle different input types
		if (element.tagName === 'SELECT') {
			matched = handleSelect(element as HTMLSelectElement, newValue, update.fieldId)

		} else if (inputType === 'checkbox') {
			handleCheckbox(inputEl, newValue, update.fieldId)

		} else if (inputType === 'radio') {
			// Single radio button - should have been caught by name selector above
			matched = handleSingleRadio(inputEl, newValue, update.fieldId)

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
			console.log('[VFF FieldManager] Updated text field:', update.fieldId, '->', displayValue)
		}

		// Listen for manual edits regardless of match outcome (bd
		// polyglot-pdf-c6t0e, Opus cross-surface round 3): this used to live
		// INSIDE the matched-only branch below, which meant a no-match fill
		// left the field with NO listener at all -- for any field not yet
		// in the DOM at FieldManager construction time (setupAllFieldListeners
		// only finds elements present then; SchemaForm renders one section
		// at a time), this call is the field's ONLY chance to ever get one.
		// A subsequent manual correction on that field would then be
		// silently dropped: onManualEdit never fires, so the correction
		// never reaches SchemaFormStateManager or the AI -- exactly the
		// "the user fixed it and nothing noticed" failure this bead exists
		// to prevent, just relocated from the badge to the listener.
		if (element) {
			setupEditListener(element, update.fieldId)
		}

		// Mark as AI-confirmed -- ONLY when the value was actually applied
		// (bd polyglot-pdf-c6t0e). Previously this ran unconditionally
		// whenever `element` resolved, so a select/radio that matched
		// nothing (a total non-match, or an ambiguous fuzzy match since bd
		// polyglot-pdf-jbek5) still got the green outline + checkmark badge
		// and was listed as a success -- an empty field decorated as
		// AI-confirmed on a legal intake form.
		if (element && matched) {
			element.setAttribute('data-vff-confirmed', 'true')
			confirmedFields.add(update.fieldId)

			// Add visual confirmation (green outline + checkmark)
			addConfirmationBadge(element)

			// Track success
			results.success.push(update.fieldId)

			// Clear AI updating flag after a brief delay (allow events to settle)
			setTimeout(() => {
				aiUpdatingFields.delete(update.fieldId)
			}, 50)
		} else if (element) {
			console.warn('[VFF FieldManager] [warn] No value applied, skipping confirmation badge:', update.fieldId)
			results.notFound.push(update.fieldId)

			// Same 50ms deferral as the matched branch above, for the same
			// reason (bd polyglot-pdf-pg0m6): setupEditListener's handleEdit
			// (registered on 'change' for every schema field at construction
			// time, before any applyUpdates call) is the only thing standing
			// between a genuinely-coincident LATER 'change' event -- e.g. a
			// controlled re-render, or a user interaction landing in the
			// same tick right after applyUpdates returns -- and a false
			// "manual edit" report. A synchronous clear here leaves that
			// window open immediately; the deferral is what keeps it closed
			// long enough. Pinned by a test that dispatches a SECOND change
			// event after applyUpdates returns and asserts onManualEdit is
			// not misfired (mutation-verified: a synchronous clear here
			// reddens that test).
			setTimeout(() => {
				aiUpdatingFields.delete(update.fieldId)
			}, 50)
		}
	}
	
	// Log summary of results
	console.log('[VFF FieldManager] [chart] Update summary:', {
		total: updates.length,
		success: results.success.length,
		notFound: results.notFound.length,
		errors: results.errors.length
	})
	
	if (results.notFound.length > 0) {
		console.warn('[VFF FieldManager] [warn] Fields not found:', results.notFound)
	}
	
	if (results.errors.length > 0) {
		console.error('[VFF FieldManager] [X] Errors:', results.errors)
	}
	
	if (results.success.length > 0) {
		console.log('[VFF FieldManager] [OK] Successfully updated:', results.success)
	}
}
	
	/**
	 * Handle select dropdown. Returns whether an option was actually selected
	 * (bd polyglot-pdf-c6t0e): a caller must not badge/confirm a field this
	 * left unfilled -- a clear (empty newValue) counts as handled, since
	 * that is the AI's actual intent, not a failed match.
	 */
	function handleSelect(selectEl: HTMLSelectElement, newValue: string, fieldId: string): boolean {
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
			console.log('[VFF FieldManager] [check] Cleared select:', fieldId)
			return true
		}

		// Try exact match first
		let matched = false
		for (let i = 0; i < selectEl.options.length; i++) {
			const option = selectEl.options[i]
			if (option.value === newValue || option.text === newValue) {
				selectEl.selectedIndex = i
				matched = true
				console.log('[VFF FieldManager] [check] Exact match for select:', fieldId, '->', option.text)
				break
			}
		}

		// Case-insensitive EXACT match next (bd polyglot-pdf-jbek5): 'AL'
		// against option value 'al' or text 'AL' is a real, unambiguous
		// signal -- an export code spoken/echoed back in a different case --
		// and must win even though 'al' also happens to be a SUBSTRING of
		// 'Alaska'/'Alabama'. This tier is exact equality (case-folded), not
		// containment, so it cannot itself collide the way the fuzzy
		// substring tier below can; a value equal to more than one option's
		// text/value case-insensitively (a genuinely duplicate-labeled kit)
		// still only takes the first, matching the exact-match tier above's
		// existing first-hit behavior.
		if (!matched) {
			const lowerValue = newValue.toLowerCase()
			for (let i = 0; i < selectEl.options.length; i++) {
				const option = selectEl.options[i]
				if (option.value.toLowerCase() === lowerValue || option.text.toLowerCase() === lowerValue) {
					selectEl.selectedIndex = i
					matched = true
					console.log('[VFF FieldManager] [check] Case-insensitive exact match for select:', fieldId, '->', option.text)
					break
				}
			}
		}

		// Try fuzzy (substring) match if exact match failed. This was
		// written when a select's option.value was a long minted slug
		// ('wyoming'), where accidental substring containment was unlikely.
		// Since bd polyglot-pdf-4we6j a select's option.value can be the PDF's
		// own short export code ('WY', 'AL', 'AK', 'AR'), and short codes
		// collide readily under bidirectional substring matching -- 'al'
		// is a substring of BOTH 'alaska' and 'alabama' by TEXT containment
		// (the case-insensitive exact-match tier above already resolves the
		// common real case -- an export code equal to an option's own value
		// -- before reaching here). Collect every candidate FIRST and only
		// apply the match when it is UNIQUE; an ambiguous value selects
		// nothing and logs the same "no match" warning a genuinely unmatched
		// value gets, rather than writing a silently wrong answer onto a
		// legal form.
		if (!matched) {
			const lowerValue = newValue.toLowerCase()
			const candidates: number[] = []
			for (let i = 0; i < selectEl.options.length; i++) {
				const option = selectEl.options[i]
				const lowerText = option.text.toLowerCase()
				const lowerOptionValue = option.value.toLowerCase()

				if (lowerText.includes(lowerValue) || lowerValue.includes(lowerText) ||
				    lowerOptionValue.includes(lowerValue) || lowerValue.includes(lowerOptionValue)) {
					candidates.push(i)
				}
			}
			if (candidates.length === 1) {
				const i = candidates[0]
				selectEl.selectedIndex = i
				matched = true
				console.log('[VFF FieldManager] ~= Fuzzy match for select:', fieldId, '->', selectEl.options[i].text)
			} else if (candidates.length > 1) {
				console.warn(
					'[VFF FieldManager] [warn] Ambiguous fuzzy match for:', newValue, 'in', fieldId,
					'-- matches', candidates.map((i) => selectEl.options[i].text), '-- selecting none')
			}
		}

		if (!matched) {
			console.warn('[VFF FieldManager] [warn] No matching option found for:', newValue, 'in', fieldId)
		}

		// Dispatch change event for form handlers
		selectEl.dispatchEvent(new Event('change', { bubbles: true }))
		selectEl.dispatchEvent(new Event('input', { bubbles: true }))

		return matched
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
		
		console.log('[VFF FieldManager] [check] Updated checkbox:', fieldId, '->', shouldCheck, `(from ${typeof newValue}: ${newValue})`)
	}
	
	/**
	 * Handle checkbox group (multiple checkboxes with same name)
	 * Example: name="reason[]" with values ["Depressed Mood", "Divorce/Custody"]
	 *
	 * Returns whether AT LEAST ONE requested value was actually matched and
	 * checked (bd polyglot-pdf-c6t0e) -- a caller must not badge/confirm a
	 * group where every requested value failed to match (previously reported
	 * unconditional success even when unmatchedValues covered the whole
	 * request). A clear (empty newValue) counts as handled. This is
	 * deliberately ANY-matched, not ALL-matched: a partial match still
	 * changed real DOM state the confirmation badge should reflect, and the
	 * per-checkbox unmatched list is already logged separately for whoever
	 * reads the console.
	 */
	function handleCheckboxGroup(checkboxInputs: NodeListOf<HTMLInputElement>, newValue: any, fieldId: string): boolean {
		// Empty means clear all checkboxes (bd polyglot-pdf-qc46): the bare '' that
		// applyUpdates passes (it coerces null/undefined to '' via `value || ''`), or
		// an all-empty / empty array (the AI's "no selection" shape, which survives
		// that coercion as a truthy array). Without this guard,
		// normalizedCheckbox.includes('') is true for every option in the fuzzy-match
		// loop below, so every checkbox would be CHECKED instead of cleared.
		const isEmpty =
			newValue === '' ||
			(Array.isArray(newValue) && newValue.every(v => v === '' || v == null))
		if (isEmpty) {
			for (const checkbox of checkboxInputs) {
				checkbox.checked = false
				checkbox.dispatchEvent(new Event('change', { bubbles: true }))
				checkbox.dispatchEvent(new Event('input', { bubbles: true }))
			}
			console.log('[VFF FieldManager] [check] Cleared checkbox group:', fieldId)
			return true
		}

		// Convert single value to array
		const values = Array.isArray(newValue) ? newValue : [newValue]

		console.log('[VFF FieldManager] [clip] Checkbox group:', fieldId)
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
		
		console.log('[VFF FieldManager] [OK] Checkbox group result:', {
			fieldId,
			requested: values.length,
			matched: matchedValues.length,
			unmatched: unmatchedValues.length,
			total: checkboxInputs.length
		})
		
		if (matchedValues.length > 0) {
			console.log('  [check] Matched & checked:', matchedValues)
		}

		if (unmatchedValues.length > 0) {
			console.warn('  [warn] Could not match:', unmatchedValues)
			console.warn('  [idea] Try one of:', availableValues)
		}

		return matchedValues.length > 0
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
	 * Handle radio group (multiple radio inputs with same name). Returns
	 * whether a radio was actually selected (bd polyglot-pdf-c6t0e) -- this
	 * function badges/confirms internally on a real match already, but its
	 * caller in applyUpdates pushed results.success UNCONDITIONALLY on
	 * every call (this function never falls through to applyUpdates' own
	 * blanket badge block, so that unconditional push was the only place a
	 * no-match radio group still reported success with no badge at all,
	 * a silent-failure state worse than the badged-but-empty case that
	 * bug also covers). A clear (empty newValue) counts as handled.
	 */
	function handleRadioGroup(radioInputs: NodeListOf<HTMLInputElement>, newValue: string, fieldId: string): boolean {
		// Empty string means clear: uncheck all (bd polyglot-pdf-qc46).
		// Without this guard, lowerRadioValue.includes('') is true for every option
		// so the fuzzy-match loop below would select the FIRST radio instead of clearing.
		if (newValue === '') {
			for (const radio of radioInputs) {
				radio.checked = false
				radio.dispatchEvent(new Event('change', { bubbles: true }))
				radio.dispatchEvent(new Event('input', { bubbles: true }))
			}
			console.log('[VFF FieldManager] [check] Cleared radio group:', fieldId)
			return true
		}

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
				
				console.log('[VFF FieldManager] [check] Selected radio:', fieldId, '->', newValue)
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
					
					console.log('[VFF FieldManager] ~= Fuzzy match radio:', fieldId, '->', radio.value)
					break
				}
			}
		}
		
		if (!matched) {
			console.warn('[VFF FieldManager] [warn] No matching radio option found for:', newValue, 'in', fieldId)
		}

		return matched
	}

	/**
	 * Handle single radio button (fallback). Returns whether it was
	 * actually selected (bd polyglot-pdf-c6t0e): unlike handleRadioGroup,
	 * this handler applies NO badge internally on match either -- both the
	 * match and no-match paths previously relied on applyUpdates' blanket
	 * badge block, which does not check the outcome. A clear (empty
	 * newValue) counts as handled.
	 */
	function handleSingleRadio(radioEl: HTMLInputElement, newValue: string, fieldId: string): boolean {
		// Empty string means clear: uncheck (bd polyglot-pdf-qc46). Without this,
		// a clear request on a single radio found by id is silently ignored (the
		// value-mismatch warn branch) instead of unchecking.
		if (newValue === '') {
			radioEl.checked = false
			radioEl.dispatchEvent(new Event('change', { bubbles: true }))
			radioEl.dispatchEvent(new Event('input', { bubbles: true }))
			console.log('[VFF FieldManager] [check] Cleared single radio:', fieldId)
			return true
		}

		// Check if value matches
		if (radioEl.value === newValue) {
			radioEl.checked = true

			// Dispatch events
			radioEl.dispatchEvent(new Event('change', { bubbles: true }))
			radioEl.dispatchEvent(new Event('input', { bubbles: true }))

			console.log('[VFF FieldManager] [check] Selected single radio:', fieldId)
			return true
		}

		console.warn('[VFF FieldManager] [warn] Radio value mismatch:', radioEl.value, '!==', newValue)
		return false
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
		console.warn('[VFF FieldManager] [warn] Combobox filling not fully supported yet:', fieldId)
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
