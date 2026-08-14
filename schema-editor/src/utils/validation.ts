import type {
  FormSchema, FormField, FieldOption, FieldStatus, ValidationError,
} from '../types/schema';
import { normalizeToComposite } from './normalizeToComposite';
import { overlayBlockReason } from './pdfCoordinates';
import { isToReviewSection } from './sectionOps';

/**
 * A field's options as a SAFELY ITERABLE array of option objects (bd
 * polyglot-pdf-8bjdx). THE one place malformed `options` is normalized --
 * reuse it rather than hand-rolling `field.options ?? []` at each call site,
 * which is exactly how this set drifted apart in the first place.
 *
 * Two shapes a hand-edited or script-drifted kit can carry escape the
 * ordinary `?? []` / `|| []` guards, because both are TRUTHY and both have a
 * `.length`:
 *   1. a NON-ARRAY value (e.g. the string "not-a-list") -- `?? []` does not
 *      replace it, `.length` is the string's length, and any array method
 *      (`.filter`/`.every`/`.map`/`.some`) then throws "is not a function";
 *   2. an array containing NULL / non-object entries (e.g. `[null, "junk"]`)
 *      -- the array methods run, then `o.pdf_field_name` on `null` throws
 *      "Cannot read properties of null".
 *
 * A throw here is not a wrong number, it is a BLANK SCREEN: these consumers
 * sit on the per-field RENDER path (FieldList rows + tooltips, the PDF
 * overlay boxes, FieldEditor's completeness panel), so one malformed field
 * takes down the whole list rather than degrading its own row.
 *
 * Mirrors the backend's own guards (publish_readiness.has_uncovered_structural_error:
 * `options if isinstance(options, list) else []` plus `o.get(...) if
 * isinstance(o, dict) else None`), and the sibling fix bd polyglot-pdf-93p8
 * already applied inline in reviewStatus.ts.
 *
 * A bare STRING option is coerced to `{value, label}`, matching every other
 * surface (see normalizeOption below). Only entries carrying nothing readable
 * at all -- null, a number, a nested array -- are dropped, because they have
 * no `value`/`label`/`pdf_field_name` any consumer could use.
 */
export function safeOptions(field: { options?: unknown }): FieldOption[] {
  const raw = field.options;
  if (!Array.isArray(raw)) return [];
  return raw.map(normalizeOption).filter((o): o is FieldOption => o !== null);
}

/**
 * One entry -> a usable FieldOption, or null if it carries nothing readable.
 *
 * A BARE STRING is a legitimate legacy option, NOT malformed (bd
 * polyglot-pdf-fzt0a / Opus outer review). Every other surface already accepts
 * it and coerces the same way: the backend's
 * `FormField.normalize_options` (`[FieldOption(value=opt, label=opt) for opt in
 * v]` -- it is a DOCUMENTED accepted input, "Accepts both List[str] and
 * List[FieldOption] formats"), the voice frontend's `optionValue()`, and
 * schema_lint's ref-option-value rule, which builds its legal-value set
 * INCLUDING `isinstance(o, str)` entries.
 *
 * Dropping it here instead of coercing broke that agreement in the editor's
 * favour-of-nothing: a string-option field rendered zero option rows, so the
 * Options panel fell through to its empty-state branch whose "+ Add Option"
 * OVERWRITES `options` wholesale rather than appending -- silently destroying
 * every option, invisibly, because the rows the author would have noticed
 * missing were the ones not rendering. It also made isChoiceTrigger false, so
 * ConditionBuilder offered a free-text value box for a field whose values the
 * publish gate constrains, inviting exactly the ERROR the gate then raises.
 */
function normalizeOption(o: unknown): FieldOption | null {
  if (typeof o === 'string') return { value: o, label: o };
  // `typeof [] === 'object'`, so an array has to be excluded explicitly or a
  // nested `[]` counts as an option carrying nothing (caught by this file's
  // own "genuinely unreadable entries" test).
  if (!!o && typeof o === 'object' && !Array.isArray(o)) return o as FieldOption;
  return null;
}

/**
 * Like safeOptions, but KEEPS non-object entries as `null` placeholders so a
 * consumer that must not change its option COUNT (e.g. checkFieldComplete's
 * "N of M options are unmapped" message, or anything indexing options
 * positionally) still sees the real arity. A `null` slot reads as an option
 * with no `pdf_field_name` / no `value`, matching the backend mirror
 * (`o.get("pdf_field_name") if isinstance(o, dict) else None`).
 */
export function safeOptionsPreservingArity(
  field: { options?: unknown },
): Array<FieldOption | null> {
  const raw = field.options;
  if (!Array.isArray(raw)) return [];
  return raw.map(normalizeOption);
}

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
  // safeOptionsPreservingArity, not `field.options ?? []` (bd
  // polyglot-pdf-8bjdx): a non-array or null-bearing `options` threw out of
  // the .filter/.map below, and this function is on the per-field RENDER path
  // (FieldList rows + tooltips, FieldOverlay boxes, FieldEditor's panel), so
  // one malformed field blanked the whole list. Arity-preserving because the
  // "N of M unmapped" branch below compares counts -- a dropped entry would
  // silently change which message fires.
  const options = safeOptionsPreservingArity(field);
  const isChoice =
    field.type === 'select' || field.type === 'radio' || field.type === 'checkbox_group';
  if (isChoice && options.length > 0) {
    if (!field.pdf_field_name) {
      const unmapped = options.filter(o => !o?.pdf_field_name);
      if (unmapped.length === options.length) {
        errors.push('No PDF mapping: neither the field nor its options name a PDF widget');
      } else if (unmapped.length > 0) {
        const names = unmapped.map(o => o?.label || String(o?.value ?? '?')).join(', ');
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
