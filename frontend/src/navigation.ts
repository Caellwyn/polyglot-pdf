/**
 * Navigation - Client-side form field navigation logic
 *
 * Purpose: Determine which field to fill next, calculate progress,
 * and detect form completion. All logic is client-side for stateless
 * backend architecture.
 *
 * Implemented Features:
 * - [OK] Linear iteration (field order from schema)
 * - [OK] Skip confirmed fields
 * - [OK] Required field prioritization
 * - [OK] Progress calculation
 * - [OK] Completion detection
 * - [OK] Section-based navigation (Nov 23, 2025)
 * - [OK] Conditional field visibility (Nov 22, 2025)
 * - [OK] Field dependencies (Nov 22, 2025)
 *
 * Out of Scope:
 * - [X] Hidden fields (display:none)
 * - [X] Disabled fields
 */

import type { SchemaFormState } from './schema-forms/state/schemaFormState';
import type { FormSchema, FormField } from './schema-forms/types/schema';
import { shouldShowField } from './schema-forms/utils/validation';

// Navigation operates on the canonical schema FormField (it iterates
// state.schema.fields and returns those objects). Re-export it under the same
// name so existing `import { FormField } from './navigation'` consumers keep
// working, instead of declaring an incompatible local shape.
export type { FormField };

/**
 * Options for customizing navigation behavior
 */
export interface NavigationOptions {
  /** Only return required fields */
  requiredOnly?: boolean;
  
  /** Filter by section name (not used in MVP) */
  section?: string;
  
  /** Skip fields that are already confirmed (default: true) */
  skipConfirmed?: boolean;
}

/**
 * Progress metrics for form completion
 */
export interface ProgressMetrics {
  /** Total number of fields in the form */
  total: number;
  
  /** Number of fields that have been confirmed */
  confirmed: number;
  
  /** Number of required fields */
  required: number;
  
  /** Number of required fields that have been confirmed */
  requiredConfirmed: number;
  
  /** Completion percentage (0-100) */
  percentage: number;
}

/**
 * Compute the next field that should be filled
 * 
 * Implements linear navigation: iterates through schema fields in order,
 * skipping fields that are already confirmed (unless options specify otherwise).
 * 
 * @param state - Current form state from sessionStorage
 * @param options - Navigation options for filtering
 * @returns Next field to fill, or null if all applicable fields are confirmed
 * 
 * @example
 * ```typescript
 * const nextField = computeNextField(state);
 * if (nextField) {
 *   console.log(`Please fill: ${nextField.name}`);
 * } else {
 *   console.log('Form is complete!');
 * }
 * ```
 * 
 * @example
 * ```typescript
 * // Only get required fields
 * const nextRequired = computeNextField(state, { requiredOnly: true });
 * ```
 */
export function computeNextField(
  state: SchemaFormState,
  options?: NavigationOptions
): FormField | null {
  const {
    requiredOnly = false,
    skipConfirmed = true,
  } = options || {};

  // Handle empty schema
  if (!state.schema || !state.schema.fields || state.schema.fields.length === 0) {
    return null;
  }

  // Get current section to limit field search
  const currentSection = state.schema.sections?.find(s => s.id === state.currentSectionId);

  // Filter to only fields in current section
  const currentSectionFieldIds = new Set(currentSection?.fields || []);
  const fieldsToCheck = currentSectionFieldIds.size > 0
    ? state.schema.fields.filter(f => currentSectionFieldIds.has(f.id))
    : state.schema.fields; // Fallback to all fields if no section structure

  console.log('[computeNextField] [search] Current section:', {
    sectionId: state.currentSectionId,
    sectionLabel: currentSection?.label,
    totalFieldsInSection: fieldsToCheck.length,
    sectionFieldIds: Array.from(currentSectionFieldIds).slice(0, 5) // Show first 5 for brevity
  });

  // When skipConfirmed=false, just return first field (no prioritization)
  if (!skipConfirmed) {
    for (const field of fieldsToCheck) {
      // Apply required filter if requested
      if (requiredOnly && !field.validation?.required) {
        continue;
      }
      return field;
    }
    return null;
  }

  // PRIORITY 1: Find first filled but UNCONFIRMED field
  // This ensures Gemini must confirm fields before moving on
  for (const field of fieldsToCheck) {
    // Skip locked/hidden fields (Nov 22, 2025 - dependency checking)
    if (field.hidden || !shouldShowField(field, state.fieldValues, state.schema.fields)) {
      continue;
    }

    // Apply required filter if requested
    if (requiredOnly && !field.validation?.required) {
      continue;
    }

    const currentValue = state.fieldValues[field.id];
    const isConfirmed = currentValue?.confirmed === true;
    const hasValue = currentValue?.value !== null
      && currentValue?.value !== undefined
      && currentValue?.value !== '';

    // Return first field with value but NOT confirmed
    if (hasValue && !isConfirmed) {
      return field;
    }
  }

  // PRIORITY 2: Find first EMPTY field (skipping confirmed fields)
  for (const field of fieldsToCheck) {
    // Skip locked/hidden fields (Nov 22, 2025 - dependency checking)
    if (field.hidden || !shouldShowField(field, state.fieldValues, state.schema.fields)) {
      continue;
    }

    // Apply required filter if requested
    if (requiredOnly && !field.validation?.required) {
      continue;
    }

    const currentValue = state.fieldValues[field.id];
    const isConfirmed = currentValue?.confirmed === true;

    // Skip confirmed fields (skipConfirmed=true at this point)
    if (isConfirmed) {
      continue;
    }

    // Check if field has a value (null, undefined, or empty string means not filled)
    const hasValue = currentValue?.value !== null
      && currentValue?.value !== undefined
      && currentValue?.value !== '';

    // Return first empty field
    if (!hasValue) {
      return field;
    }
  }

  // All applicable fields in current section are confirmed/filled
  return null;
}

/**
 * Calculate form completion progress
 * 
 * Provides detailed metrics about form completion including total fields,
 * confirmed fields, required fields, and completion percentage.
 * 
 * @param state - Current form state from sessionStorage
 * @returns Progress metrics object
 * 
 * @example
 * ```typescript
 * const progress = getFormProgress(state);
 * console.log(`Progress: ${progress.percentage}%`);
 * console.log(`Confirmed: ${progress.confirmed}/${progress.total}`);
 * console.log(`Required: ${progress.requiredConfirmed}/${progress.required}`);
 * ```
 */
export function getFormProgress(state: SchemaFormState): ProgressMetrics {
  // Handle empty schema
  if (!state.schema || !state.schema.fields || state.schema.fields.length === 0) {
    return {
      total: 0,
      confirmed: 0,
      required: 0,
      requiredConfirmed: 0,
      percentage: 0,
    };
  }

  const total = state.schema.fields.length;
  let confirmed = 0;
  let required = 0;
  let requiredConfirmed = 0;

  for (const field of state.schema.fields) {
    const currentValue = state.fieldValues[field.id];
    const isConfirmed = currentValue?.confirmed === true;

    // Count confirmed fields
    if (isConfirmed) {
      confirmed++;
    }

    // Count required fields
    if (field.validation?.required) {
      required++;
      if (isConfirmed) {
        requiredConfirmed++;
      }
    }
  }
  
  // Calculate percentage
  // If there are no fields, percentage is 0
  // Otherwise, percentage is (confirmed / total) * 100
  const percentage = total > 0 ? Math.round((confirmed / total) * 100) : 0;
  
  return {
    total,
    confirmed,
    required,
    requiredConfirmed,
    percentage,
  };
}

/**
 * Check if the form is complete
 * 
 * Completion criteria:
 * - If form has required fields: ALL required fields must be confirmed
 * - If form has no required fields: ALL fields must be confirmed
 * 
 * @param state - Current form state from sessionStorage
 * @returns true if form meets completion criteria, false otherwise
 * 
 * @example
 * ```typescript
 * if (isFormComplete(state)) {
 *   console.log('Form is ready to submit!');
 *   submitForm();
 * }
 * ```
 */
export function isFormComplete(state: SchemaFormState): boolean {
  // Handle empty schema - consider empty form as "complete"
  if (!state.schema || !state.schema.fields || state.schema.fields.length === 0) {
    return true;
  }

  // Check if form has any required fields
  const hasRequiredFields = state.schema.fields.some(field => field.validation?.required);

  if (hasRequiredFields) {
    // If form has required fields, ALL required fields must be confirmed
    for (const field of state.schema.fields) {
      if (field.validation?.required) {
        const currentValue = state.fieldValues[field.id];
        const isConfirmed = currentValue?.confirmed === true;

        if (!isConfirmed) {
          return false; // Found an unconfirmed required field
        }
      }
    }

    return true; // All required fields are confirmed
  } else {
    // If form has no required fields, ALL fields must be confirmed
    for (const field of state.schema.fields) {
      const currentValue = state.fieldValues[field.id];
      const isConfirmed = currentValue?.confirmed === true;

      if (!isConfirmed) {
        return false; // Found an unconfirmed field
      }
    }

    return true; // All fields are confirmed
  }
}

/**
 * Format next field information for AI context
 * 
 * Creates a human-readable hint about the next field to fill.
 * This can be sent to Gemini to guide the conversation.
 * 
 * @param field - The next field to fill
 * @param order - The field's order/index in the form (1-based)
 * @returns Formatted string for AI context
 * 
 * @example
 * ```typescript
 * const nextField = computeNextField(state);
 * if (nextField) {
 *   const hint = formatNextFieldHint(nextField, 3);
 *   // Returns: "Next field to fill is #3: 'Email Address' (type: email, required)"
 * }
 * ```
 */
export function formatNextFieldHint(
  field: FormField,
  order?: number
): string {
  const orderPrefix = order ? `#${order}` : '';
  // Required-ness lives under validation on the canonical FormField (the old
  // local navigation FormField had a flat `required`, which masked this).
  const requiredSuffix = field.validation?.required ? ', required' : '';
  // options are FieldOption objects ({value,label}), not bare strings -- list
  // their labels so the hint reads as option text, not "[object Object]".
  const optionsSuffix = field.options && field.options.length > 0
    ? `, options: [${field.options.map(o => o.label).join(', ')}]`
    : '';

  // CRITICAL: Include field_id so Gemini knows exactly which field to update
  return `Next field to fill is ${orderPrefix}: '${field.name}' (field_id: '${field.id}', type: ${field.type}${requiredSuffix}${optionsSuffix})`;
}

/**
 * Get the order/index of a field in the schema (1-based)
 *
 * @param state - Current form state
 * @param fieldId - ID of the field to find
 * @returns 1-based index of the field, or null if not found
 */
export function getFieldOrder(state: SchemaFormState, fieldId: string): number | null {
  if (!state.schema || !state.schema.fields) {
    return null;
  }

  const index = state.schema.fields.findIndex(field => field.id === fieldId);
  return index >= 0 ? index + 1 : null;
}
