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
import { readFieldEntryWithAlias } from './schema-forms/utils/fieldValue';

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
 * Resolve the field-level navigation pin to a LIVE target, or null
 * (bd polyglot-pdf-jnjj.36). A pin is live while its field exists, is
 * visible, and is unconfirmed; anything else is stale and ignored (the
 * state writers -- confirm/skip/section-switch -- clear stale pins; the
 * readers here are pure). Shared by computeNextField (the pin is the next
 * field) AND isFormComplete (a live pin means the form is NOT done: the
 * user jumped somewhere to answer or correct it, so completion-gated
 * consumers -- the post-confirm hint, reconnect hints, manual-edit hints,
 * the form-complete event -- must not abandon the jump; fresh-eyes on this
 * bead).
 */
function resolveLivePin(state: SchemaFormState): FormField | null {
  if (!state.pinnedFieldId || !state.schema?.fields) {
    return null;
  }
  const pinned = state.schema.fields.find(f => f.id === state.pinnedFieldId);
  if (
    pinned &&
    !pinned.hidden &&
    shouldShowField(pinned, state.fieldValues, state.schema.fields) &&
    // `[]`-alias-aware confirmed read (bd 5k52 class): a checkbox-group's
    // entry may sit under the bracket key variant; a bare read would treat a
    // confirmed pin as live and hold the form open (outer review, jnjj.36).
    !readFieldEntryWithAlias(state.fieldValues, pinned.id)?.confirmed
  ) {
    return pinned;
  }
  return null;
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

  // Field-level navigation pin (bd polyglot-pdf-jnjj.36): the AI's
  // switch_to_field tool pins a target field; it is the next field for EVERY
  // consumer (hint, DTI schema drip, UI focus) until confirmed or skipped
  // (confirmField/markFieldSkipped release the pin). A pin that no longer
  // resolves, is hidden by a condition, or is already confirmed is treated as
  // stale and IGNORED (lazy fallback to the normal order) -- this function is
  // pure, so stale pins are cleared by the state writers, not here.
  if (skipConfirmed) {
    const pinned = resolveLivePin(state);
    if (pinned) {
      return pinned;
    }
  }

  // Get current section to limit field search
  const currentSection = state.schema.sections?.find(s => s.id === state.currentSectionId);

  // Continuous-session mode (bd polyglot-pdf-x8rt): the whole form is one session,
  // so the next-field search spans EVERY field in schema order -- never
  // section-scoped. Without this the search would stop at the first section's last
  // field and the continuous fill would stall (there is no section advance to
  // carry it onward).
  // Filter to only fields in current section
  const currentSectionFieldIds = new Set(currentSection?.fields || []);
  const fieldsToCheck = state.continuousSessionEnabled
    ? state.schema.fields
    : currentSectionFieldIds.size > 0
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
    // Mirrors webFormConnection.ts handleConfirmFieldRequest's hasUsableValue
    // predicate exactly (bd polyglot-pdf-6oe6): '' on an OPTIONAL field is a
    // USABLE value, not an empty one. The AI fill path legitimately stores ''
    // on an optional field to mean "the user said this does not apply" (the
    // SI's field-does-not-apply flow, backend/config.py), then confirms it --
    // that value is confirmed-pending, not unfilled. Without this, an optional
    // field holding a confirmed-pending '' fell through Priority 1 (this loop
    // saw hasValue=false) into Priority 2, where it was re-offered as an EMPTY
    // field to FILL instead of a filled field to CONFIRM -- an extra,
    // confusing pass for Gemini. A REQUIRED field's '' is never usable here
    // (matching hasUsableValue), so a required-empty field is untouched by
    // this change and still falls through to Priority 2 for filling.
    const fieldIsRequired = field.validation?.required === true;
    const hasValue = currentValue?.value !== null
      && currentValue?.value !== undefined
      && (currentValue?.value !== '' || !fieldIsRequired);

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

  // A LIVE navigation pin means the form is NOT complete (bd jnjj.36): the
  // AI jumped to a specific field (often an unconfirmed OPTIONAL one, e.g.
  // "let me add my middle name" after every required field confirmed).
  // Without this, the completion-gated consumers (post-confirm hint,
  // reconnect/manual-edit hints, the form-complete event) would report
  // "complete" and silently abandon the jump (fresh-eyes on this bead).
  if (resolveLivePin(state)) {
    return false;
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
 *   // A field with help.instructions also gets:
 *   //   "... . Context to briefly convey when asking: <instructions>"
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

  // Field fine-print (help.instructions) rides the hint so the qualifying
  // context reaches the model on the channel it acts on per turn (initiating
  // message / confirm_field next-field hint / manual-update hint), not only
  // as a Note: line buried in the SI field dump (bd polyglot-pdf-bo4m).
  // The lead-in phrase below is a CONTRACT with the backend spoken-hint
  // stripper (backend/services/field_utils.py strip_field_id_from_hint), which
  // peels this note off by this exact phrase so it can strip the (field_id: ...)
  // group without eating the note. Keep the two in sync if you reword it.
  const noteSuffix = field.help?.instructions
    ? `. Context to briefly convey when asking: ${field.help.instructions}`
    : '';

  // CRITICAL: Include field_id so Gemini knows exactly which field to update
  return `Next field to fill is ${orderPrefix}: '${field.name}' (field_id: '${field.id}', type: ${field.type}${requiredSuffix}${optionsSuffix})${noteSuffix}`;
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
