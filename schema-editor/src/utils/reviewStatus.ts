/**
 * Human review status for a field (bd polyglot-pdf-u8t6) -- the single source of
 * truth the FieldList, FieldEditor, and any counter share, so the icon, the
 * control, and the "Next to review" jump can never drift.
 *
 * There are TWO status systems in the editor and this module is where they meet:
 *   1. AUTOMATIC -- checkFieldComplete(field) derives green/amber/red from the
 *      field's own contents (missing spoken name, placeholder help, no PDF
 *      mapping, ...). It is a machine guess, not a human decision.
 *   2. HUMAN REVIEW -- field._review.status: unreviewed / reviewed_correct /
 *      needs_followup, set explicitly by an editor.
 *
 * The maintainer-approved interaction is LAYERED (bd polyglot-pdf-u8t6):
 *   - A real ERROR (red) ALWAYS wins -- you cannot sign off a structurally broken
 *     field; those block the publish gate and must be fixed, not noted.
 *   - Otherwise the human review status governs the green-vs-amber band:
 *       needs_followup  -> 'followup' (a flagged target the review-jump stops on)
 *       reviewed_correct -> 'complete' (green, EVEN over an auto-amber)
 *       unreviewed       -> fall through to the automatic status.
 *
 * This key is editor-only metadata: it round-trips because the hosted draft
 * save/lint routes store the raw dict verbatim and the publish gate validates
 * without re-serializing (backend FormField uses extra="ignore", so it is
 * dropped only from the VALIDATED object, never from the stored blob). It is not
 * the session STASH_KEY, so stripEditorState leaves it intact on save.
 */
import type { FormField, FieldReview, FieldReviewStatus } from '../types/schema';
import { checkFieldComplete } from './validation';

// The status a row/icon actually shows, after layering human review over the
// automatic derivation. 'followup' is the human-flagged state; the other three
// mirror the automatic vocabulary so existing consumers read the same strings.
export type EffectiveStatus = 'error' | 'followup' | 'review' | 'complete';

/** A field's review record, defaulted to the neutral 'unreviewed' state. */
export function getReview(field: FormField): FieldReview {
  const r = field._review;
  if (r && (r.status === 'reviewed_correct' || r.status === 'needs_followup')) {
    return r;
  }
  // Absent, malformed, or an explicit 'unreviewed' all collapse to the default.
  return { status: 'unreviewed', ...(r?.note ? { note: r.note } : {}) };
}

/**
 * Set (or clear) a field's review status, returning a NEW field. Writing
 * 'unreviewed' with no note drops the _review key entirely so a field an editor
 * reset to neutral serializes clean (no dangling {status:'unreviewed'}).
 */
export function withReviewStatus(field: FormField, status: FieldReviewStatus): FormField {
  const note = field._review?.note;
  if (status === 'unreviewed' && !note) {
    const { _review, ...rest } = field;
    return rest;
  }
  return { ...field, _review: { status, ...(note ? { note } : {}) } };
}

/**
 * Set (or clear) a field's review note, returning a NEW field. An empty note on
 * an otherwise-neutral field drops the _review key so it serializes clean.
 */
export function withReviewNote(field: FormField, note: string): FormField {
  const status = getReview(field).status;
  const trimmed = note;
  if (status === 'unreviewed' && !trimmed.trim()) {
    const { _review, ...rest } = field;
    return rest;
  }
  return { ...field, _review: { status, ...(trimmed ? { note: trimmed } : {}) } };
}

/**
 * The effective status for a field, layering human review over the automatic
 * derivation per the precedence above. `hasLintError` folds in a backend lint
 * ERROR anchored to this field (the FieldList already threads these in) -- a
 * lint ERROR is as red as a local completeness error, and red always wins.
 */
export function effectiveStatus(field: FormField, hasLintError = false): EffectiveStatus {
  const auto = checkFieldComplete(field);
  // Red always wins -- a broken field cannot be signed off.
  if (auto.errors.length > 0 || hasLintError) return 'error';

  const review = getReview(field).status;
  if (review === 'needs_followup') return 'followup';
  if (review === 'reviewed_correct') return 'complete';

  // unreviewed -> the automatic amber/green band shows through.
  return auto.needsReview ? 'review' : 'complete';
}

/**
 * Whether a field is a "review target" -- something the "Next to review" jump
 * should stop on and a work-remaining count should include. Everything except a
 * settled green field: errors, auto-amber, and human-flagged follow-ups all
 * count; a reviewed_correct field does NOT (bd polyglot-pdf-u8t6).
 */
export function isReviewTarget(field: FormField, hasLintError = false): boolean {
  return effectiveStatus(field, hasLintError) !== 'complete';
}
