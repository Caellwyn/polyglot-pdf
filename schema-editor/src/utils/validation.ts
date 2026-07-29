import type { FormSchema, FormField, FieldStatus, ValidationError } from '../types/schema';
import { normalizeToComposite } from './normalizeToComposite';
import { overlayBlockReason } from './pdfCoordinates';
import { isToReviewSection } from './sectionOps';

// Flatten a legacy-or-composite condition to its atomic conditions (bd
// h76m.8) for reference checking. [] for absent/malformed shapes.
// Exported for ignoreField's dependents detector (bd polyglot-pdf-mzkw):
// three near-identical flatteners already exist across this file,
// fieldGrouping and fieldRename -- reuse rather than add a fourth.
export function conditionAtoms(condition: unknown) {
  const group = normalizeToComposite(condition);
  if (!group) return [];
  return [
    ...(group.all_of ?? []),
    ...(group.any_of ?? []),
    ...(group.none_of ?? []),
  ];
}

/**
 * Check if a field is complete (has all required info for editor workflow).
 *
 * `pageCount` (optional, bd polyglot-pdf-g63j) is the loaded PDF's page count.
 * When supplied, a field claiming a page outside 1..pageCount earns its own
 * distinct amber reason; when omitted (schema-only contexts with no PDF
 * loaded) that half is simply skipped -- never an error.
 */
export function checkFieldComplete(
  field: FormField,
  pageCount?: number,
): FieldStatus {
  const errors: string[] = [];

  // Check required properties
  if (!field.id) errors.push('Missing field ID');
  if (!field.type) errors.push('Missing field type');

  // PDF mapping: a plain field carries pdf_field_name itself; a CONSOLIDATED
  // choice field (select/radio/checkbox_group built from per-widget checkboxes)
  // legitimately has NO field-level name -- each option carries its own
  // pdf_field_name instead. Flagging those as "Missing PDF field name" marked
  // every merged group red with nothing actually wrong (bd polyglot-pdf-0x10.6).
  const options = field.options ?? [];
  const isChoice =
    field.type === 'select' || field.type === 'radio' || field.type === 'checkbox_group';
  if (isChoice && options.length > 0) {
    if (!field.pdf_field_name) {
      const unmapped = options.filter(o => !o.pdf_field_name);
      if (unmapped.length === options.length) {
        errors.push('No PDF mapping: neither the field nor its options name a PDF widget');
      } else if (unmapped.length > 0) {
        const names = unmapped.map(o => o.label || String(o.value ?? '?')).join(', ');
        errors.push(`Options missing a PDF widget mapping: ${names}`);
      }
    }
  } else if (!field.pdf_field_name) {
    errors.push('Missing PDF field name');
  }

  // Check for placeholder help text
  const hasPlaceholderHelp =
    field.help?.instructions?.includes('[TODO]') ||
    field.help?.instructions === undefined;

  const hasSpokenName = Boolean(field.spoken_name && field.spoken_name.trim() !== '');

  // Un-highlightable position (bd polyglot-pdf-g63j): a field that NAMES a
  // widget but has no drawable rect -- or claims a page the PDF does not have
  // -- shows nothing in the preview. Reported in plain language naming the
  // widget, NEVER as the false "Missing PDF field name" (a name IS set; that
  // wrong message is what made two mis-labeled W-7 fields read as phantoms).
  //
  // An amber REASON, not a red error: the editor cannot prove the field is
  // unfillable. The backend filler resolves widgets by NAME, not by the
  // schema's rect, and extraction can legitimately leave a real widget
  // rect-less -- so this is "a human should look", not "this is broken".
  //
  // SCOPING -- deliberately NOT the same as the mapping check above, which is
  // gated on !isChoice because a consolidated group's field-level NAME is
  // legitimately absent (identity lives per option). Position is a different
  // question: PDFViewer draws an overlay from `field.pdf_position` for ANY
  // field that has one, choice types included (the shipped i-90 has several
  // single-widget radios with real field-level rects). So the check runs:
  //   - whenever the field CARRIES a position, of any type; and
  //   - for a named NON-CHOICE field that carries none at all.
  // Both are cases where the author would otherwise stare at a field that
  // paints nowhere with no explanation.
  //
  // A named CHOICE field with no field-level rect is deliberately silent (the
  // !isChoice on the second clause): that is a true shared-name AcroForm radio
  // group -- one name, rects per option -- and PDFViewer never draws option
  // rects, so flagging it would fire on every real radio group in every kit
  // rather than name a defect. A consolidated group with neither name nor
  // rect is likewise silent.
  const hasOwnPosition = field.pdf_position !== undefined;
  const namedButPositionless = Boolean(field.pdf_field_name) && !hasOwnPosition && !isChoice;
  const positionProblem =
    hasOwnPosition || namedButPositionless
      ? overlayBlockReason(field.pdf_position, pageCount)
      : null;

  const needsReview = hasPlaceholderHelp || !hasSpokenName || positionProblem !== null;

  // Name the review reasons so the UI can SAY why a field is amber instead of
  // showing a bare clock icon (bd polyglot-pdf-0x10.6).
  const reviewReasons: string[] = [];
  if (hasPlaceholderHelp) reviewReasons.push('Help instructions are missing or a placeholder');
  if (!hasSpokenName) reviewReasons.push('Missing spoken name');
  if (positionProblem) {
    // Name the widget when the field carries one; a choice group with a
    // field-level rect but no field-level name is identified by its own id.
    const subject = field.pdf_field_name
      ? `PDF widget "${field.pdf_field_name}"`
      : `Field "${field.id}"`;
    reviewReasons.push(`${subject}: ${positionProblem}`);
  }

  return {
    isComplete: errors.length === 0 && !needsReview,
    needsReview,
    errors,
    reviewReasons,
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
 * Get completion statistics for schema.
 *
 * Counts the EFFECTIVE status so the numbers agree with the FieldList icons and
 * the PDF overlay (bd polyglot-pdf-u8t6, amended by bd polyglot-pdf-g63j).
 *
 * `complete` counts ONLY human sign-off (reviewed_correct) -- the g63j
 * amendment: green means a human said so, so the progress figure now answers
 * "how much has a person actually reviewed?", not "how much did the machine
 * fail to complain about". An un-reviewed field counts as needs-review even
 * when its automatic derivation is spotless; a needs_followup field likewise. A
 * real ERROR is neither -- it counts toward total only, exactly as before.
 *
 * The layering is inlined (not imported from reviewStatus.ts) to keep
 * validation.ts free of a reviewStatus <-> validation import cycle; the ordering
 * mirrors reviewStatus.effectiveStatus (error wins, then the review status
 * decides). Any change here MUST be mirrored there.
 *
 * `needsAck` (bd anim) is the guidance-staleness gate, pre-computed by the
 * caller via guidanceStaleness.needsAckFieldIds(schema.fields, lintFindings)
 * -- passed as a plain id set so this module stays free of lint-store imports.
 * A field in the set cannot count complete even when reviewed_correct: the
 * sign-off predates the drift, exactly as effectiveStatus demotes it to amber.
 * Callers WITHOUT lint findings in hand (the kit catalogue's disk/remote scan)
 * omit it and stay gate-blind -- tracked as a known limitation (bd
 * polyglot-pdf-2onl) rather than silently plumbed here.
 */
export function getCompletionStats(schema: FormSchema, needsAck?: Set<string>): {
  complete: number;
  needsReview: number;
  total: number;
  percentage: number;
} {
  let complete = 0;
  let needsReview = 0;

  for (const field of schema.fields) {
    const status = checkFieldComplete(field);
    // Red always wins: an ERROR field is neither complete nor needs-review.
    if (status.errors.length > 0) continue;
    const review = (field as { _review?: { status?: string } })._review?.status;
    if (review === 'reviewed_correct' && !needsAck?.has(field.id)) {
      complete++;
    } else {
      // unreviewed / needs_followup / malformed -> needs review (bd g63j:
      // green is human sign-off only; the machine's opinion never grants it).
      needsReview++;
    }
  }

  const total = schema.fields.length;
  const percentage = total > 0 ? Math.round((complete / total) * 100) : 0;

  return { complete, needsReview, total, percentage };
}
