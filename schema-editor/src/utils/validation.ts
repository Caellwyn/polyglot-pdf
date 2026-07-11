import type { FormSchema, FormField, FieldStatus, ValidationError } from '../types/schema';
import { normalizeToComposite } from './normalizeToComposite';
import { isToReviewSection } from './sectionOps';

// Flatten a legacy-or-composite condition to its atomic conditions (bd
// h76m.8) for reference checking. [] for absent/malformed shapes.
function conditionAtoms(condition: unknown) {
  const group = normalizeToComposite(condition);
  if (!group) return [];
  return [
    ...(group.all_of ?? []),
    ...(group.any_of ?? []),
    ...(group.none_of ?? []),
  ];
}

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

  // Build the COMPLETE set of field ids up front so reference checks below see
  // every field regardless of declaration order. Building it incrementally inside
  // the reference loop falsely flagged a FORWARD reference -- a show_if / require_if
  // target that appears LATER in schema.fields -- as non-existent
  // (bd polyglot-pdf-y61i). Duplicate-ID detection still needs an incremental
  // "seen so far" set, so it keeps its own (`seenIds`) in the loop below.
  const fieldIds = new Set<string>();
  for (const field of schema.fields) {
    fieldIds.add(field.id);
  }

  // Check fields
  const seenIds = new Set<string>();
  for (const field of schema.fields) {
    // Check for duplicate IDs (incremental: a dup is an id seen EARLIER in the list)
    if (seenIds.has(field.id)) {
      errors.push({
        field_id: field.id,
        message: 'Duplicate field ID',
        type: 'error',
      });
    }
    seenIds.add(field.id);

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
      // 'To review' gate (bd polyglot-pdf-6cfu.3): the deterministic
      // derivation filed this field for a human to re-file; the backend's
      // to-review-pending lint rule blocks publishing until it moves. Mirror
      // it client-side so the panel explains the block before the author
      // hits the publish gate.
      if (isToReviewSection(field.section_id)) {
        errors.push({
          field_id: field.id,
          message: "Field is in a 'To review' section -- re-file it into a "
            + 'real section (Sections panel) before the form can be marked '
            + 'complete',
          type: 'error',
        });
      }
    }

    // Check conditional logic references (against the full id set -- forward
    // refs OK). show_if/require_if may be legacy single conditions or v2
    // composite groups (bd h76m.8): every atom's trigger must resolve.
    for (const [kind, condition] of [
      ['show_if', field.show_if],
      ['require_if', field.require_if],
    ] as const) {
      for (const atom of conditionAtoms(condition)) {
        if (!fieldIds.has(atom.field)) {
          errors.push({
            field_id: field.id,
            message: `${kind} references non-existent field: ${atom.field}`,
            type: 'warning',
          });
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
