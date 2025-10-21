/**
 * DOM Parser - Step S4
 * 
 * Scans the page for form fields and creates a unified schema.
 * Reuses the existing extractFormSchema logic.
 */

import { extractFormSchema } from '../webParser/extractFormSchema'
import type { FormSchema } from '../webFormState'

export interface ParseResult {
	success: boolean
	schema?: FormSchema
	error?: string
	stats: {
		fieldCount: number
		requiredCount: number
		parseTime: number
		firstFieldId?: string
	}
}

/**
 * Parse form fields from the current page
 */
export function parsePageForms(): ParseResult {
	const startTime = performance.now()

	try {
		// Extract schema using existing parser
		const schema = extractFormSchema(document, {
			url: window.location.href,
			title: document.title,
		})

		const parseTime = performance.now() - startTime

		// Handle no fields scenario
		if (schema.fields.length === 0) {
			return {
				success: false,
				error: 'NO_FIELDS',
				stats: {
					fieldCount: 0,
					requiredCount: 0,
					parseTime,
				},
			}
		}

		// Check field count limits
		const fieldCount = schema.fields.length
		const requiredCount = schema.fields.filter((f) => f.required).length
		const firstFieldId = schema.fields[0]?.id

		// Warning for large forms
		if (fieldCount > 150) {
			console.warn(
				`[VFF Parser] Large form detected: ${fieldCount} fields (>150 field warning threshold)`
			)
		}

		// Log parse stats
		console.log('[VFF Parser] Parse complete:', {
			fieldCount,
			requiredCount,
			firstFieldId,
			parseTime: `${parseTime.toFixed(0)}ms`,
		})

		return {
			success: true,
			schema,
			stats: {
				fieldCount,
				requiredCount,
				parseTime,
				firstFieldId,
			},
		}
	} catch (error) {
		const parseTime = performance.now() - startTime
		console.error('[VFF Parser] Parse failed:', error)

		return {
			success: false,
			error: 'PARSE_FAILED',
			stats: {
				fieldCount: 0,
				requiredCount: 0,
				parseTime,
			},
		}
	}
}

/**
 * Check if parse time is within budget
 */
export function isParseWithinBudget(parseTime: number, fieldCount: number): boolean {
	// S4 acceptance criteria:
	// - ≤1s for ≤150 fields
	// - ≤1.5s for >150 fields
	const budget = fieldCount <= 150 ? 1000 : 1500
	return parseTime <= budget
}

/**
 * Get warning message for large forms
 */
export function getLargeFormWarning(fieldCount: number): string | null {
	if (fieldCount > 200) {
		return `Very large form detected (${fieldCount} fields). Performance may be degraded. Consider using "Scan visible only" option.`
	} else if (fieldCount > 150) {
		return `Large form detected (${fieldCount} fields). This may take longer to process.`
	}
	return null
}
