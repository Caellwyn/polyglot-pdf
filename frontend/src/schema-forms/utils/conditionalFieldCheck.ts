/**
 * Conditional field checking and field availability evaluation
 *
 * Determines if a field is available, locked, or hidden based on conditional dependencies.
 * Provides human-readable dependency information for Gemini error responses.
 */

import type { FormField, FormSchema, FieldValue, FieldAvailability } from "../types/schema";
import { unwrapFieldValue } from "./fieldValue";
import { shouldShowField } from "./validation";

export interface FieldAccessResult {
  /** Whether the field can be accessed/updated */
  accessible: boolean;

  /** Reason if not accessible */
  reason?: "field_hidden" | "field_read_only" | "field_not_found";

  /** Human-readable message */
  message?: string;

  /** Required fields that must be filled first */
  required_fields?: Array<{
    field_id: string;
    spoken_name: string;
    required_value?: any;
    current_value?: any;
  }>;
}

/**
 * Check if a field can be accessed (for get_field_value or update_form_fields)
 *
 * A field is NOT accessible if:
 * 1. It doesn't exist in the schema (field_not_found)
 * 2. It's conditionally hidden (show_if condition not met)
 * 3. It's read-only due to conditional logic
 *
 * If not accessible, provides information about what fields need to be filled first.
 *
 * @param spokenName - The spoken name Gemini is trying to access
 * @param schema - The full form schema
 * @param fieldValues - Current form field values
 * @returns FieldAccessResult with accessibility info and dependencies
 */
export function checkFieldAccess(
  spokenName: string,
  schema: FormSchema,
  fieldValues: Record<string, any>
): FieldAccessResult {
  // Find the field by spoken name
  const field = schema.fields.find(f => f.spoken_name === spokenName);

  if (!field) {
    return {
      accessible: false,
      reason: "field_not_found",
      message: `The field '${spokenName}' was not found. Please check the spoken name and try again.`
    };
  }

  // Check if field is conditionally hidden
  if (field.show_if) {
    const isVisible = shouldShowField(field, fieldValues);

    if (!isVisible) {
      // Field is hidden - determine what needs to be filled first
      const triggerFieldId = field.show_if.field;
      const triggerField = schema.fields.find(f => f.id === triggerFieldId);

      if (triggerField) {
        const currentValue = unwrapFieldValue(fieldValues[triggerFieldId]);
        const requiredValue = field.show_if.value;

        return {
          accessible: false,
          reason: "field_hidden",
          message: `The field '${spokenName}' is not yet available. First, you need to fill the field '${triggerField.spoken_name}' with the value '${requiredValue}'.`,
          required_fields: [{
            field_id: triggerFieldId,
            spoken_name: triggerField.spoken_name || triggerField.name,
            required_value: requiredValue,
            current_value: currentValue
          }]
        };
      }

      // Couldn't find trigger field (schema error), but still block access
      return {
        accessible: false,
        reason: "field_hidden",
        message: `The field '${spokenName}' is not currently available. It may depend on other fields being filled first.`
      };
    }
  }

  // Check if field is read-only
  if (field.read_only) {
    return {
      accessible: false,
      reason: "field_read_only",
      message: `The field '${spokenName}' is read-only and cannot be modified.`
    };
  }

  // Field is accessible
  return {
    accessible: true
  };
}

/**
 * Get dependency chain for a field
 *
 * Finds all fields that must be filled before this field becomes accessible.
 * Useful for more complex conditional logic.
 *
 * @param field - The target field
 * @param schema - The full form schema
 * @param fieldValues - Current form values
 * @returns Array of fields that are blocking access
 */
export function getDependencyChain(
  field: FormField,
  schema: FormSchema,
  fieldValues: Record<string, any>
): FormField[] {
  const dependencies: FormField[] = [];

  if (!field.show_if) {
    return dependencies; // No dependencies
  }

  // Get immediate dependency
  const triggerFieldId = field.show_if.field;
  const triggerField = schema.fields.find(f => f.id === triggerFieldId);

  if (triggerField) {
    dependencies.push(triggerField);

    // Recursively check if trigger field has dependencies
    const nestedDeps = getDependencyChain(triggerField, schema, fieldValues);
    dependencies.push(...nestedDeps);
  }

  return dependencies;
}

/**
 * Evaluate field availability state
 *
 * Determines if a field is available, locked, or hidden based on current form values.
 * Returns availability state and human-readable reason if locked.
 *
 * @param field - The field to evaluate
 * @param fieldValues - Current form field values
 * @param schema - Full form schema (for dependency lookup)
 * @returns Object with availability state and optional locked reason
 */
export function evaluateFieldAvailability(
  field: FormField,
  fieldValues: Record<string, FieldValue>,
  schema: FormSchema
): { availability: FieldAvailability; lockedReason?: string } {
  // Field explicitly hidden in schema
  if (field.hidden) {
    return { availability: 'hidden' };
  }

  // Field is read-only (treat as locked since user can't modify it). The reason
  // is a name-FREE clause: the sole consumer (webFormConnection composes
  // "Cannot update '<name>': <reason>") already names the field, so restating it
  // here produced "Cannot update 'X': The field 'X' is read-only..." -- the field
  // name twice (bd polyglot-pdf-34wc, mirroring the z6xs hidden-field fix).
  if (field.read_only) {
    return {
      availability: 'locked',
      lockedReason: 'it is read-only and cannot be modified.'
    };
  }

  // Check conditional visibility (show_if logic)
  if (field.show_if) {
    const isVisible = shouldShowField(field, fieldValues);

    if (!isVisible) {
      // Field is conditionally hidden - find the blocking field
      const triggerFieldId = field.show_if.field;
      const triggerField = schema.fields.find(f => f.id === triggerFieldId);

      if (triggerField) {
        const currentValue = unwrapFieldValue(fieldValues[triggerFieldId]?.value);
        const requiredValue = field.show_if.value;
        const operator = field.show_if.operator || 'equals';

        // Build human-readable reason
        let reason: string;
        if (operator === 'equals') {
          reason = `Complete the '${triggerField.spoken_name || triggerField.name}' field first and select '${requiredValue}'.`;
        } else if (operator === 'not_equals') {
          reason = `Complete the '${triggerField.spoken_name || triggerField.name}' field first. It must NOT be '${requiredValue}'.`;
        } else if (operator === 'is_checked') {
          reason = `Check the '${triggerField.spoken_name || triggerField.name}' checkbox first.`;
        } else {
          reason = `Complete the '${triggerField.spoken_name || triggerField.name}' field first.`;
        }

        return {
          availability: 'locked',
          lockedReason: reason
        };
      }

      // Couldn't find trigger field (schema error)
      return {
        availability: 'locked',
        lockedReason: `This field depends on other fields being filled first.`
      };
    }
  }

  // Field is available
  return { availability: 'available' };
}
