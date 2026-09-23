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
import { GUIDANCE_STALE_RULE, currentIdentity, needsGuidanceAck, staleFieldIds }
  from './guidanceStaleness';
import { findingFingerprint } from './lintFindings';

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
 * Rebuild a field's _review record from explicit slot values -- THE one place
 * the record is reassembled (sprint-18 C1, bd polyglot-pdf-o7y9).
 *
 * The record carries FOUR slots: status, note, guidance_ack_sha1, and
 * seen_fingerprints. Every writer routes through here so a writer can never
 * silently drop a slot it does not know about -- the three-slot hand-rebuild
 * dropping the ack on an ordinary status write is a recorded past bug
 * (fresh-eyes, bd anim closeout round 2), and this helper is the structural
 * fix rather than a per-writer convention. A fully-neutral record (unreviewed,
 * no note, no ack, no fingerprints) drops the _review key entirely so a field
 * an editor reset to neutral serializes clean.
 */
function rebuildReview(
  field: FormField,
  slots: {
    status: FieldReviewStatus;
    note?: string;
    ack?: string;
    seen?: string[];
  },
): FormField {
  const { status, note, ack, seen } = slots;
  if (status === 'unreviewed' && !note && !ack && seen === undefined) {
    const { _review, ...rest } = field;
    return rest;
  }
  return {
    ...field,
    _review: {
      status,
      ...(note ? { note } : {}),
      ...(ack ? { guidance_ack_sha1: ack } : {}),
      ...(seen !== undefined ? { seen_fingerprints: seen } : {}),
    },
  };
}

/** The current slot values of a field's _review, for a writer to preserve
 * whatever it is not itself changing. */
function currentSlots(field: FormField): {
  note?: string; ack?: string; seen?: string[];
} {
  return {
    note: field._review?.note,
    ack: field._review?.guidance_ack_sha1,
    seen: Array.isArray(field._review?.seen_fingerprints)
      ? field._review?.seen_fingerprints
      : undefined,
  };
}

/**
 * Set (or clear) a field's review status, returning a NEW field. Writing
 * 'unreviewed' with no other populated slot drops the _review key entirely so
 * a field an editor reset to neutral serializes clean (no dangling
 * {status:'unreviewed'}).
 *
 * The guidance ack (bd anim) is PRESERVED across a status write: it is a
 * separate assertion ("I read the guidance and it still fits the current
 * content") that a status change neither confirms nor withdraws. Rebuilding
 * _review without it silently un-acked a field on the ORDINARY flow -- tick
 * the ack box, then mark reviewed_correct -- re-raising the amber gate with
 * no visible cause (fresh-eyes, closeout round 2).
 *
 * `currentFindings` (sprint-18 C1): marking reviewed_correct is the SIGN-OFF,
 * and the STATUS WRITER is the single owner of the seen_fingerprints slot --
 * the sign-off stamps the fingerprints of every finding anchored to the field
 * right now (which is what makes a LATER finding demote the field back to
 * needs-review, the timeliness rule), and any transition AWAY from
 * reviewed_correct clears the stamp (it records a sign-off that no longer
 * exists; keeping it would leave a reset-to-neutral field serializing dirty).
 * Pass the field's current lint findings; with none in hand (degraded lint,
 * no report yet) the stamp is the empty set, so findings that surface later
 * are honestly NEW relative to this review. The note and ack writers preserve
 * the slot verbatim.
 */
export function withReviewStatus(
  field: FormField,
  status: FieldReviewStatus,
  currentFindings?: LintFinding[],
): FormField {
  const { note, ack } = currentSlots(field);
  const nextSeen = status === 'reviewed_correct'
    ? (currentFindings ?? []).map(findingFingerprint)
    : undefined;
  return rebuildReview(field, { status, note, ack, seen: nextSeen });
}

/**
 * Set (or clear) a field's review note, returning a NEW field. A whitespace-only
 * note counts as empty (so it never lands as a "   " tooltip); an empty note on
 * an otherwise-neutral field drops the _review key so it serializes clean. The
 * note is stored AS TYPED (internal spacing preserved) once it has real
 * content. The guidance ack and the sign-off fingerprints survive a note edit
 * for the same reason they survive a status write (see withReviewStatus).
 */
export function withReviewNote(field: FormField, note: string): FormField {
  const status = getReview(field).status;
  const { ack, seen } = currentSlots(field);
  const hasContent = note.trim().length > 0;
  return rebuildReview(field, {
    status, note: hasContent ? note : undefined, ack, seen,
  });
}

/**
 * Record (or clear) a human's acknowledgment that the authored guidance still
 * reads correctly for this field's CURRENT identity, after the backend flagged
 * it as drifted (bd polyglot-pdf-anim). `currentIdentity` is the hash the
 * backend reports for the field's CONTENT RIGHT NOW -- storing that (never the
 * frozen bake-time hash, which does not move when a human edits) is what makes
 * a LATER edit re-raise the gate instead of one click becoming a permanent
 * waiver. Returns a NEW field; clearing drops the key (and the whole _review
 * record when nothing else remains) so it serializes clean.
 */
export function withGuidanceAck(
  field: FormField,
  currentIdentity: string | undefined,
  acknowledged: boolean,
): FormField {
  const status = getReview(field).status;
  const { note, ack, seen } = currentSlots(field);
  if (!acknowledged || !currentIdentity) {
    if (!ack) return field;
    return rebuildReview(field, { status, note, ack: undefined, seen });
  }
  return rebuildReview(field, { status, note, ack: currentIdentity, seen });
}

/**
 * The timeliness rule (sprint-18 C1, decision 3): has any finding anchored to
 * this field appeared SINCE its reviewed_correct sign-off? Compared by
 * fingerprint (rule + field + path-sans-identity, message excluded) against
 * the seen_fingerprints the sign-off stamped. An EFFECTIVE-status derivation,
 * never a stored write -- exactly like the ack gate.
 *
 * A sign-off with NO seen_fingerprints slot predates the slot's existence:
 * those are grandfathered (no demotion) rather than mass-demoted the day this
 * ships -- the same fail-open the guidance gate takes when it has nothing to
 * pin against. Every sign-off from now on stamps the slot (empty set
 * included), so the rule is live for all new reviews.
 */
export function newFindingsSinceReview(
  field: FormField,
  findings?: LintFinding[],
): boolean {
  if (getReview(field).status !== 'reviewed_correct') return false;
  const seen = field._review?.seen_fingerprints;
  if (!Array.isArray(seen)) return false; // pre-slot sign-off: grandfathered
  const seenSet = new Set(seen);
  // The guidance-staleness rule is EXCLUDED: the ack gate is that rule's sole
  // owner (its whole design is confirm-or-rewrite, bd anim), and the ack
  // writer deliberately preserves seen_fingerprints -- so counting the stale
  // finding here made sign-off-then-drift-then-ack a DEAD END (permanently
  // amber, no control able to clear it; the ack checkbox was the one exit
  // and it never touches this slot -- Opus outer review, pass 5). The three
  // rendering surfaces exclude the rule for the same one-owner reason.
  return (findings ?? []).some(f =>
    f.rule !== GUIDANCE_STALE_RULE && !seenSet.has(findingFingerprint(f)));
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
 *
 * `newSinceReview` (sprint-18 C1) is the timeliness rule's flag, derived by
 * newFindingsSinceReview: a finding that appeared after the sign-off demotes
 * the field to the same amber band, for the same reason -- the sign-off never
 * covered it.
 */
export function effectiveStatus(
  field: FormField,
  hasLintError = false,
  pageCount?: number,
  needsGuidanceAck = false,
  newSinceReview = false,
): EffectiveStatus {
  const auto = checkFieldComplete(field, pageCount);
  // Red always wins -- a broken field cannot be signed off.
  if (auto.errors.length > 0 || hasLintError) return 'error';

  const review = getReview(field).status;
  if (review === 'needs_followup') return 'followup';
  // An un-acknowledged drift -- or a finding newer than the sign-off --
  // demotes even an explicit reviewed_correct: the sign-off was given for
  // different content.
  if (needsGuidanceAck || newSinceReview) return 'review';
  if (review === 'reviewed_correct') return 'complete';

  // unreviewed -> ALWAYS amber (bd g63j). Green is a human's word, not the
  // machine's: a field nobody has looked at is "needs review" even when the
  // automatic checks find nothing to complain about. `auto` still governs the
  // WHY-list (auto.reviewReasons) and, above, the red band.
  return 'review';
}

/**
 * The three booleans every findings-driven status call needs, derived ONCE.
 * statusFromFindings, isCountedReviewed and isReviewTargetFromFindings all go
 * through here, so the "how do findings become gate flags" recipe has a
 * single definition (Opus outer review, pass 2).
 */
function gateFlags(field: FormField, findings?: LintFinding[]): {
  hasLintError: boolean; ackPending: boolean; newSinceReview: boolean;
} {
  return {
    hasLintError: (findings ?? []).some(f => f.severity === 'ERROR'),
    ackPending: needsGuidanceAck(
      field,
      staleFieldIds(findings),
      currentIdentity(findings, field.id),
    ),
    newSinceReview: newFindingsSinceReview(field, findings),
  };
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
export function statusFromFindings(
  field: FormField,
  findings?: LintFinding[],
  pageCount?: number,
): EffectiveStatus {
  const { hasLintError, ackPending, newSinceReview } = gateFlags(field, findings);
  return effectiveStatus(field, hasLintError, pageCount, ackPending, newSinceReview);
}

/**
 * The checkFieldComplete ERROR classes NO backend lint rule covers yet:
 *
 *   - a CHOICE field (select/radio/checkbox_group) with options where
 *     neither the field nor every option names a PDF widget. The ledger's
 *     field-backing rule exempts choice types (identity legitimately lives
 *     per option), and the widget-claim rules need a non-empty claim to fire
 *     -- so this genuinely unfillable shape earns a red row with no
 *     count-excluding lint ERROR (Opus fresh-eyes round 2; verified against
 *     schema_lint);
 *   - a field with no id or no type at all (hand-edited/drifted kits; no
 *     lint rule names it -- Opus outer review, pass 1);
 *   - a checkbox_group carrying a FIELD-LEVEL pdf_field_name, which v2
 *     forbids outright (form_models.py). The rule is Pydantic
 *     _collect_v2_problems, not a LintFinding, so no lint ERROR excludes it
 *     from the count (bd polyglot-pdf-ufj7);
 *   - two or more OPTIONS claiming the same widget. The backend's
 *     dump-widget-multiclaim covers it but is DUMP-GATED, so it does not fire
 *     in a schema-only view (bd polyglot-pdf-fyc7).
 *
 * KEEP THIS LIST IN STEP WITH checkFieldComplete. An error class added there
 * and not here breaks the predicate's one promise -- the strip, the review
 * filter and the "Next to review" jump are one definition, so the rows can
 * paint red while the strip reports the form fully reviewed and the jump
 * refuses to stop on it. That is exactly what happened when fyc7/ufj7 added
 * their classes (Opus cross-surface review).
 *
 * Derived from the SCHEMA alone, so the server can compute the identical
 * clause (the predicate's both-sides rule holds). Retire the choice-mapping
 * half once the backend rule ships (bd polyglot-pdf-xuub).
 */
function hasUncoveredStructuralError(field: FormField): boolean {
  if (!field.id || !field.type) return true;
  const isChoice = field.type === 'select' || field.type === 'radio'
    || field.type === 'checkbox_group';
  // Array.isArray + a per-element object guard (bd polyglot-pdf-93p8),
  // matching the Python mirror's `options if isinstance(options, list) else
  // []` + `o.get(...) if isinstance(o, dict) else None`. A hand-edited or
  // script-drifted kit can carry `options` as a non-array (e.g. a stray
  // string -- `?? []` only replaces null/undefined, and a string HAS
  // `.length`, so `options.some` threw "options.some is not a function")
  // or as an array containing a null/non-object entry (`o.pdf_field_name`
  // on null threw too). Either throw propagated out of isCountedReviewed ->
  // reviewCounts -> App.liveStats, blanking the whole review strip instead
  // of degrading one field's count -- the two mirrors must both degrade,
  // never throw, on the same malformed input.
  const options = Array.isArray(field.options) ? field.options : [];
  if (!isChoice || options.length === 0) return false;
  const optionName = (o: unknown): string | undefined =>
    o && typeof o === 'object' ? (o as { pdf_field_name?: string }).pdf_field_name : undefined;

  // A checkbox_group must not carry a field-level pdf_field_name at all (v2,
  // form_models.py), so a stray one is itself a structural error -- AND it
  // must not short-circuit the unmapped-option scan below. That gate is
  // correct only for select/radio, where a field-level name is the legitimate
  // shared-name shape (bd polyglot-pdf-ufj7).
  //
  // THIS IS THE SECOND MEMBER OF THAT SET (scar #8). The same short-circuit
  // was fixed in checkFieldComplete; fixing only there would leave the COUNT
  // predicate blind to the very fields the rows now paint red -- the strip
  // would report a form fully reviewed while a red row sat in the list, and
  // "Next to review" would refuse to stop on it. The strip, the filter and
  // the jump are one predicate by design; they must move together.
  const isCheckboxGroup = field.type === 'checkbox_group';
  if (isCheckboxGroup && field.pdf_field_name) return true;

  // NOTE THE ORDERING, and mirror checkFieldComplete's exactly. A field-level
  // name on select/radio suppresses only the UNMAPPED-OPTION scan (that is the
  // legitimate shared-name shape, where options need no own name). It must NOT
  // suppress the COLLISION scan, which runs unconditionally on the row-status
  // side. Returning false here for the whole predicate was the SAME invariant
  // break as round 1, surviving for a second shape: a radio carrying a
  // field-level name AND two options claiming one widget painted a red row
  // while the strip counted it reviewed and the jump skipped it (Opus
  // cross-surface round 2). The backend agrees this shape is an ERROR --
  // schema_lint registers the field-level claim as kind "field" and each
  // option as "option[i]", so 2+ option claimants fire dump-widget-multiclaim;
  // its benign carve-out covers only field-level PLUS EXACTLY ONE option.
  const suppressUnmappedScan = !isCheckboxGroup && Boolean(field.pdf_field_name);

  // NORMALIZE ONCE, then read only from the normalized list. The raw entries
  // are never touched by an array callback below, so a non-array `options` or
  // a null/non-object entry degrades this field's count instead of throwing
  // out through reviewCounts -> App.liveStats and blanking the whole strip
  // (bd polyglot-pdf-93p8, and the set-completeness guard in
  // optionsConsumerSet.test.ts, which caught this loop reading raw entries).
  const names: Array<string | undefined> = options.map(optionName);

  // Two OPTION-level claimants on one widget: the backend's
  // dump-widget-multiclaim ERROR, mirrored here so a collision is counted as
  // needing review rather than silently passing as reviewed
  // (bd polyglot-pdf-fyc7).
  const seen = new Set<string>();
  for (const name of names) {
    if (typeof name !== 'string' || name === '') continue;
    if (seen.has(name)) return true;
    seen.add(name);
  }

  if (suppressUnmappedScan) return false;
  return names.some(name => !name);
}

/**
 * THE pinned count predicate (sprint-18 C1, decision 2): a field counts as
 * REVIEWED exactly when its human sign-off is current --
 *
 *   _review.status == reviewed_correct,
 *   AND not demoted by the guidance-ack gate,
 *   AND not demoted by the timeliness rule (no finding newer than the
 *       sign-off's seen_fingerprints),
 *   AND no uncovered structural error (the narrow schema-derived clause
 *       above -- a stand-in until the backend rules ship),
 *   AND no lint ERROR anchored to the field.
 *
 * Inputs the client and the server both possess (_review + lint findings +
 * the schema itself), so both sides compute the identical number.
 * checkFieldComplete otherwise LEAVES this predicate: its client-only error
 * band stays the advisory WHY-list and icon input (a field red for a
 * lint-covered reason is excluded by the lint clause, not by
 * checkFieldComplete).
 */
export function isCountedReviewed(
  field: FormField,
  findings?: LintFinding[],
): boolean {
  if (getReview(field).status !== 'reviewed_correct') return false;
  if (hasUncoveredStructuralError(field)) return false;
  const { hasLintError, ackPending, newSinceReview } = gateFlags(field, findings);
  return !hasLintError && !ackPending && !newSinceReview;
}

/**
 * Whether a field is a "review target" -- something the "to review" count
 * includes and the review-jump stops on. Defined as the exact complement of
 * isCountedReviewed, so the strip's M, the jump, and the reviewed count are
 * one predicate by construction: M review targets + N reviewed = T total,
 * always (sprint-18 C1, decision 2).
 */
export function isReviewTargetFromFindings(
  field: FormField,
  findings?: LintFinding[],
): boolean {
  return !isCountedReviewed(field, findings);
}

/**
 * The strip's counts (sprint-18 C1): `reviewed` over the pinned predicate,
 * `toReview` its exact complement, `total` every non-quarantined field
 * (ignored fields live outside fields[] by construction, so they are outside
 * the denominator by construction too). No "resolved" count -- resolving a
 * finding moves a field between these two buckets, nothing else.
 */
export function reviewCounts(
  fields: FormField[],
  findingsByField: Map<string, LintFinding[]> | undefined,
): { reviewed: number; toReview: number; total: number; percentage: number } {
  let reviewed = 0;
  for (const field of fields) {
    if (isCountedReviewed(field, findingsByField?.get(field.id))) reviewed++;
  }
  const total = fields.length;
  return {
    reviewed,
    toReview: total - reviewed,
    total,
    percentage: total > 0 ? Math.round((reviewed / total) * 100) : 0,
  };
}
