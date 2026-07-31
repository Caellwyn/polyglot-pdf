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
 * The maintainer-approved interaction is LAYERED (bd polyglot-pdf-u8t6, amended
 * by bd polyglot-pdf-g63j):
 *   - A real ERROR (red) ALWAYS wins -- you cannot sign off a structurally broken
 *     field; those block the publish gate and must be fixed, not noted.
 *   - Otherwise the human review status governs the green-vs-amber band:
 *       needs_followup   -> 'followup' (a flagged target the review-jump stops on)
 *       reviewed_correct -> 'complete' (green, EVEN over an auto-amber)
 *       unreviewed       -> 'review' (AMBER) -- ALWAYS, even when the automatic
 *                           derivation finds nothing wrong.
 *
 * That last rule is the g63j amendment (maintainer directive 2026-07-27):
 * **GREEN MEANS A HUMAN SAID SO.** Before it, a field the machine happened to
 * like rendered green while nobody had looked at it, which made the editor's
 * central signal a lie -- an un-reviewed form could look finished. The
 * automatic checkFieldComplete result is NOT discarded: its reasons still
 * populate the amber tooltip's WHY-list, and its ERRORS still win outright. It
 * simply no longer grants green on its own.
 *
 * This key is editor-only metadata: it round-trips because the hosted draft
 * save/lint routes store the raw dict verbatim and the publish gate validates
 * without re-serializing (backend FormField uses extra="ignore", so it is
 * dropped only from the VALIDATED object, never from the stored blob). It is not
 * the session STASH_KEY, so stripEditorState leaves it intact on save.
 */
import type { FormField, FieldReview, FieldReviewStatus } from '../types/schema';
import type { LintFinding } from './remoteKitStore';
import { checkFieldComplete } from './validation';
import { currentIdentity, needsGuidanceAck, staleFieldIds }
  from './guidanceStaleness';

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
 * 'unreviewed' with no note (and no guidance ack) drops the _review key
 * entirely so a field an editor reset to neutral serializes clean (no
 * dangling {status:'unreviewed'}).
 *
 * The guidance ack (bd anim) is PRESERVED across a status write: it is a
 * separate assertion ("I read the guidance and it still fits the current
 * content") that a status change neither confirms nor withdraws. Rebuilding
 * _review without it silently un-acked a field on the ORDINARY flow -- tick
 * the ack box, then mark reviewed_correct -- re-raising the amber gate with
 * no visible cause (fresh-eyes, closeout round 2).
 */
export function withReviewStatus(field: FormField, status: FieldReviewStatus): FormField {
  const note = field._review?.note;
  const ack = field._review?.guidance_ack_sha1;
  if (status === 'unreviewed' && !note && !ack) {
    const { _review, ...rest } = field;
    return rest;
  }
  return {
    ...field,
    _review: {
      status,
      ...(note ? { note } : {}),
      ...(ack ? { guidance_ack_sha1: ack } : {}),
    },
  };
}

/**
 * Set (or clear) a field's review note, returning a NEW field. A whitespace-only
 * note counts as empty (so it never lands as a "   " tooltip); an empty note on
 * an otherwise-neutral field (no status, no guidance ack) drops the _review key
 * so it serializes clean. The note is stored AS TYPED (internal spacing
 * preserved) once it has real content. The guidance ack survives a note edit
 * for the same reason it survives a status write (see withReviewStatus).
 */
export function withReviewNote(field: FormField, note: string): FormField {
  const status = getReview(field).status;
  const ack = field._review?.guidance_ack_sha1;
  const hasContent = note.trim().length > 0;
  if (status === 'unreviewed' && !hasContent && !ack) {
    const { _review, ...rest } = field;
    return rest;
  }
  return {
    ...field,
    _review: {
      status,
      ...(hasContent ? { note } : {}),
      ...(ack ? { guidance_ack_sha1: ack } : {}),
    },
  };
}

/**
 * Record (or clear) a human's acknowledgment that the authored guidance still
 * reads correctly for this field's CURRENT identity, after the backend flagged
 * it as drifted (bd polyglot-pdf-anim). `currentIdentity` is the hash the
 * backend reports for the field's CONTENT RIGHT NOW -- storing that (never the
 * frozen bake-time hash, which does not move when a human edits) is what makes
 * a LATER edit re-raise the gate instead of one click becoming a permanent
 * waiver. Returns a NEW field; clearing
 * drops the key (and the whole _review record when nothing else remains) so it
 * serializes clean.
 */
export function withGuidanceAck(
  field: FormField,
  currentIdentity: string | undefined,
  acknowledged: boolean,
): FormField {
  const current = field._review;
  if (!acknowledged || !currentIdentity) {
    if (!current?.guidance_ack_sha1) return field;
    const { guidance_ack_sha1, ...restReview } = current;
    if (restReview.status === 'unreviewed' && !restReview.note) {
      const { _review, ...rest } = field;
      return rest as FormField;
    }
    return { ...field, _review: restReview };
  }
  return {
    ...field,
    _review: {
      status: current?.status ?? 'unreviewed',
      ...(current?.note ? { note: current.note } : {}),
      guidance_ack_sha1: currentIdentity,
    },
  };
}

/**
 * The effective status for a field, layering human review over the automatic
 * derivation per the precedence above. `hasLintError` folds in a backend lint
 * ERROR anchored to this field (the FieldList already threads these in) -- a
 * lint ERROR is as red as a local completeness error, and red always wins.
 *
 * `needsGuidanceAck` (bd polyglot-pdf-anim) is the staleness gate: when the
 * field's guidance drifted and no human has acknowledged it, the field CANNOT
 * read green, even if an editor already marked it reviewed_correct -- that
 * sign-off predates the drift and no longer covers what the assistant will
 * say. It lands in the amber 'review' band (not red): the guidance may well
 * still be fine, and confirming it is a human judgment, not a defect to fix.
 * This is the same principle as the g63j amendment one layer on -- green means
 * a human said so ABOUT THE CURRENT CONTENT.
 */
export function effectiveStatus(
  field: FormField,
  hasLintError = false,
  pageCount?: number,
  needsGuidanceAck = false,
): EffectiveStatus {
  const auto = checkFieldComplete(field, pageCount);
  // Red always wins -- a broken field cannot be signed off.
  if (auto.errors.length > 0 || hasLintError) return 'error';

  const review = getReview(field).status;
  if (review === 'needs_followup') return 'followup';
  // An un-acknowledged drift demotes even an explicit reviewed_correct: the
  // sign-off was given for different content.
  if (needsGuidanceAck) return 'review';
  if (review === 'reviewed_correct') return 'complete';

  // unreviewed -> ALWAYS amber (bd g63j). Green is a human's word, not the
  // machine's: a field nobody has looked at is "needs review" even when the
  // automatic checks find nothing to complain about. `auto` still governs the
  // WHY-list (auto.reviewReasons) and, above, the red band.
  return 'review';
}

/**
 * The effective status of a field given the RAW lint findings for it -- the
 * one place the "findings -> status" rule lives (bd polyglot-pdf-l7u0).
 *
 * effectiveStatus takes two already-derived booleans (hasLintError,
 * needsGuidanceAck). Deriving those correctly means knowing that an ERROR-
 * severity finding reds the field and that the guidance gate needs BOTH the
 * stale-id set and the current identity -- a three-call recipe FieldList had
 * open-coded and FieldOverlay simply did not perform, which is how the PDF
 * overlay could paint a field GREEN while the FieldList row for the SAME field
 * rendered AMBER. Two surfaces claiming to show "the same status" must not
 * each reimplement how to compute it.
 *
 * `findings` is this field's findings (App buckets them by field_id). Passing
 * undefined -- the honest state for a call site with no lint report -- yields
 * exactly today's no-findings behavior rather than throwing, so the overlay
 * degrades instead of breaking when it renders standalone.
 */
/**
 * The two booleans every findings-driven status call needs, derived ONCE.
 * Both statusFromFindings and isReviewTargetFromFindings go through here, so
 * the "how do findings become a lint-error flag and a gate flag" recipe has a
 * single definition (Opus outer review, pass 2).
 */
function gateFlags(field: FormField, findings?: LintFinding[]): {
  hasLintError: boolean; ackPending: boolean;
} {
  return {
    hasLintError: (findings ?? []).some(f => f.severity === 'ERROR'),
    ackPending: needsGuidanceAck(
      field,
      staleFieldIds(findings),
      currentIdentity(findings, field.id),
    ),
  };
}

export function statusFromFindings(
  field: FormField,
  findings?: LintFinding[],
  pageCount?: number,
): EffectiveStatus {
  const { hasLintError, ackPending } = gateFlags(field, findings);
  return effectiveStatus(field, hasLintError, pageCount, ackPending);
}

/**
 * Whether a field is a "review target" -- something the "Next to review" jump
 * should stop on and a work-remaining count should include. Everything except a
 * settled green field: errors, auto-amber, and human-flagged follow-ups all
 * count; a reviewed_correct field does NOT (bd polyglot-pdf-u8t6).
 */
export function isReviewTarget(
  field: FormField,
  hasLintError = false,
  pageCount?: number,
  needsGuidanceAck = false,
): boolean {
  // Must pass the guidance gate through too (bd anim): a reviewed_correct
  // field with un-acknowledged stale guidance renders amber via
  // effectiveStatus, so the review-jump has to STOP on it -- otherwise "next
  // to review: nothing left" would lie about a row the author can plainly see
  // is flagged.
  return effectiveStatus(field, hasLintError, pageCount, needsGuidanceAck)
    !== 'complete';
}

/**
 * isReviewTarget, derived from the RAW findings -- the review-jump's twin of
 * statusFromFindings (bd polyglot-pdf-l7u0).
 *
 * The row icon and the "next to review" jump must agree about the same field:
 * a jump that skips a row the author can plainly see is amber reports "nothing
 * left to review" while flagged rows sit on screen. Before this, FieldList
 * routed its icon through statusFromFindings but re-assembled the two booleans
 * by hand for the jump -- identical results today, but a change to the gate's
 * inputs would land on one path and not the other, which is the same
 * two-surfaces-disagree defect one layer in.
 */
export function isReviewTargetFromFindings(
  field: FormField,
  findings?: LintFinding[],
  pageCount?: number,
): boolean {
  // Shares gateFlags with statusFromFindings, then hands off to isReviewTarget
  // rather than re-stating its `!== 'complete'` rule. Forking either would be
  // the same duplicate-definition shape this bead set out to remove, one level
  // down (Opus outer review, pass 2) -- and it keeps isReviewTarget a live
  // production path rather than a test-only export.
  const { hasLintError, ackPending } = gateFlags(field, findings);
  return isReviewTarget(field, hasLintError, pageCount, ackPending);
}
