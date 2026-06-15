import type { FormSchema, FormField, FieldStatus, ValidationError } from '../types/schema';

/**
 * Check if a field is complete (has all required info for editor workflow)
 */
export function checkFieldComplete(field: FormField): FieldStatus {
  const errors: string[] = [];

  // Check required properties
  if (!field.id) errors.push('Missing field ID');
  if (!field.type) errors.push('Missing field type');
  if (!field.pdf_field_name) errors.push('Missing PDF field name');

  // Check for placeholder help text
  const hasPlaceholderHelp =
    field.help?.instructions?.includes('[TODO]') ||
    field.help?.instructions === undefined;

  const needsReview =
    hasPlaceholderHelp ||
    !field.spoken_name ||
    field.spoken_name.trim() === '';

  return {
    isComplete: errors.length === 0 && !needsReview,
    needsReview,
    errors,
  };
}

/**
 * Validate entire schema structure
 */
export function validateSchema(schema: FormSchema): ValidationError[] {
  const errors: ValidationError[] = [];

  // Check metadata
  if (!schema.form_metadata?.form_number) {
    errors.push({
      field_id: '_metadata',
      message: 'Missing form number in metadata',
      type: 'error',
    });
  }

  // Check fields
  const fieldIds = new Set<string>();
  for (const field of schema.fields) {
    // Check for duplicate IDs
    if (fieldIds.has(field.id)) {
      errors.push({
        field_id: field.id,
        message: 'Duplicate field ID',
        type: 'error',
      });
    }
    fieldIds.add(field.id);

    // Check section references
    if (field.section_id) {
      const sectionExists = schema.sections.some(s => s.id === field.section_id);
      if (!sectionExists) {
        errors.push({
          field_id: field.id,
          message: `References non-existent section: ${field.section_id}`,
          type: 'error',
        });
      }
    }

    // Check conditional logic references
    if (field.show_if?.field) {
      const targetExists = fieldIds.has(field.show_if.field);
      if (!targetExists) {
        errors.push({
          field_id: field.id,
          message: `show_if references non-existent field: ${field.show_if.field}`,
          type: 'warning',
        });
      }
    }

    // Check controls_fields references. controls_fields is a LIST of controls,
    // each with up to six action arrays of target field ids (see schema.ts /
    // backend ConditionalControl).
    if (field.controls_fields) {
      for (const control of field.controls_fields) {
        const allControlledFields = [
          ...(control.shows || []),
          ...(control.hides || []),
          ...(control.unlocks || []),
          ...(control.locks || []),
          ...(control.makes_required || []),
          ...(control.makes_optional || []),
        ];

        for (const controlledId of allControlledFields) {
          if (!fieldIds.has(controlledId)) {
            errors.push({
              field_id: field.id,
              message: `controls_fields references non-existent field: ${controlledId}`,
              type: 'warning',
            });
          }
        }
      }
    }
  }

  // Check sections reference existing fields
  for (const section of schema.sections) {
    for (const fieldId of section.fields) {
      if (!fieldIds.has(fieldId)) {
        errors.push({
          field_id: section.id,
          message: `Section references non-existent field: ${fieldId}`,
          type: 'error',
        });
      }
    }
  }

  return errors;
}

/**
 * Get completion statistics for schema
 */
export function getCompletionStats(schema: FormSchema): {
  complete: number;
  needsReview: number;
  total: number;
  percentage: number;
} {
  let complete = 0;
  let needsReview = 0;

  for (const field of schema.fields) {
    const status = checkFieldComplete(field);
    if (status.isComplete) {
      complete++;
    } else if (status.needsReview) {
      needsReview++;
    }
  }

  const total = schema.fields.length;
  const percentage = total > 0 ? Math.round((complete / total) * 100) : 0;

  return { complete, needsReview, total, percentage };
}
