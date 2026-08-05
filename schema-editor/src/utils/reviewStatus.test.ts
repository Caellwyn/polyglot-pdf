/**
 * Human review status precedence + serialization (bd polyglot-pdf-u8t6).
 *
 * The layered rule: a real ERROR always wins (you cannot sign off a broken
 * field); otherwise needs_followup -> 'followup', reviewed_correct -> 'complete'
 * even over an auto-amber, unreviewed -> the automatic amber/green. And a
 * reset-to-neutral field must serialize clean (no dangling _review key).
 */
import { describe, it, expect } from 'vitest';
import type { FormField, FormSchema } from '../types/schema';
import {
  effectiveStatus,
  getReview,
  isCountedReviewed,
  isReviewTargetFromFindings,
  newFindingsSinceReview,
  reviewCounts,
  statusFromFindings,
  withGuidanceAck,
  withReviewNote,
  withReviewStatus,
} from './reviewStatus';
import { findingFingerprint } from './lintFindings';
import { stripEditorState } from './fieldGrouping';
import type { LintFinding } from './remoteKitStore';

// A lint finding anchored to a field, defaulting to a WARNING.
function finding(
  fieldId: string, extra: Partial<LintFinding> = {},
): LintFinding {
  return {
    severity: 'WARNING',
    rule: 'help-instructions-too-long',
    path: `fields[0] (id=${fieldId}).help.instructions`,
    message: 'too long',
    field_id: fieldId,
    ...extra,
  };
}

// A field that is automatically COMPLETE (spoken name + real help, mapped).
function completeField(extra: Partial<FormField> = {}): FormField {
  return {
    id: 'f1', name: 'f1', type: 'text', pdf_field_name: 'pdf.f1',
    spoken_name: 'spoken f1', section_id: 'sec-1', read_only: false,
    help: { instructions: 'All set.' },
    ...extra,
  } as unknown as FormField;
}

// A field the automatic derivation flags AMBER (missing spoken name + help).
function amberField(extra: Partial<FormField> = {}): FormField {
  return completeField({ spoken_name: undefined, help: undefined, ...extra });
}

// A field the automatic derivation flags RED (no PDF mapping).
function errorField(extra: Partial<FormField> = {}): FormField {
  return completeField({ pdf_field_name: undefined, ...extra });
}

describe('reviewStatus.getReview', () => {
  it('defaults an unmarked field to unreviewed', () => {
    expect(getReview(completeField()).status).toBe('unreviewed');
  });

  it('collapses a malformed status to unreviewed but keeps a stray note', () => {
    const f = completeField({ _review: { status: 'bogus' as never, note: 'hi' } });
    const r = getReview(f);
    expect(r.status).toBe('unreviewed');
    expect(r.note).toBe('hi');
  });
});

describe('reviewStatus.effectiveStatus precedence', () => {
  it('red error always wins over a reviewed_correct sign-off', () => {
    const f = withReviewStatus(errorField(), 'reviewed_correct');
    expect(effectiveStatus(f)).toBe('error');
  });

  it('a backend lint ERROR forces red even on an auto-complete signed-off field', () => {
    const f = withReviewStatus(completeField(), 'reviewed_correct');
    expect(effectiveStatus(f, /* hasLintError */ true)).toBe('error');
  });

  it('reviewed_correct turns an auto-amber field green (complete)', () => {
    const f = withReviewStatus(amberField(), 'reviewed_correct');
    expect(effectiveStatus(f)).toBe('complete');
  });

  it('needs_followup flags a field regardless of the automatic status', () => {
    expect(effectiveStatus(withReviewStatus(completeField(), 'needs_followup'))).toBe('followup');
    expect(effectiveStatus(withReviewStatus(amberField(), 'needs_followup'))).toBe('followup');
  });

  it('unreviewed is ALWAYS amber -- green is human sign-off only (bd g63j)', () => {
    // Both the auto-amber field AND the machine-spotless one: nobody has
    // looked at either, so neither may render green.
    expect(effectiveStatus(amberField())).toBe('review');
    expect(effectiveStatus(completeField())).toBe('review');
  });

  it('an ERROR still outranks the un-reviewed amber (bd g63j)', () => {
    // The g63j amendment moves the green/amber line only; red is untouched.
    expect(effectiveStatus(errorField())).toBe('error');
  });
});

describe('reviewStatus review targets (the pinned count predicate, s18 C1)', () => {
  it('only a current reviewed_correct is NOT a target; everything un-signed-off IS', () => {
    expect(isReviewTargetFromFindings(
      withReviewStatus(amberField(), 'reviewed_correct'))).toBe(false);
    expect(isReviewTargetFromFindings(
      withReviewStatus(completeField(), 'needs_followup'))).toBe(true);
    expect(isReviewTargetFromFindings(amberField())).toBe(true);
    // bd g63j: a machine-spotless but un-reviewed field is still a target --
    // "Next to review" must stop on it, because nobody has reviewed it.
    expect(isReviewTargetFromFindings(completeField())).toBe(true);
  });

  it('a lint ERROR keeps a signed-off field a target (and out of the count)', () => {
    const f = withReviewStatus(completeField(), 'reviewed_correct');
    const lintError = [finding('f1', { severity: 'ERROR', rule: 'field-unbacked' })];
    // The sign-off saw the error (fingerprint stamped) -- the ERROR clause
    // alone must keep it out of the reviewed count.
    const signedSeeing = withReviewStatus(
      completeField(), 'reviewed_correct', lintError);
    expect(isReviewTargetFromFindings(f, lintError)).toBe(true);
    expect(isReviewTargetFromFindings(signedSeeing, lintError)).toBe(true);
    expect(isCountedReviewed(signedSeeing, lintError)).toBe(false);
  });

  it('an unmapped CHOICE field never counts reviewed (the uncovered-rule clause)', () => {
    // A radio/checkbox_group/select whose field AND options all lack a PDF
    // widget is genuinely unfillable, yet NO backend lint rule errors on it
    // (the ledger exempts choice types; claim rules need a non-empty claim).
    // Without this clause the strip read a confident 100% beside a red row
    // (Opus fresh-eyes round 2). Schema-derived, so the server can compute
    // the identical clause.
    const unmappedChoice = completeField({
      type: 'radio', pdf_field_name: undefined,
      options: [{ label: 'A', value: 'a' }, { label: 'B', value: 'b' }],
    } as Partial<FormField>);
    const signed = withReviewStatus(unmappedChoice, 'reviewed_correct', []);
    expect(isCountedReviewed(signed, [])).toBe(false);
    expect(isReviewTargetFromFindings(signed, [])).toBe(true);
    expect(reviewCounts([signed], undefined))
      .toEqual({ reviewed: 0, toReview: 1, total: 1, percentage: 0 });
    // A properly mapped choice field (options carry widgets) is unaffected.
    const mappedChoice = completeField({
      type: 'radio', pdf_field_name: undefined,
      options: [
        { label: 'A', value: 'a', pdf_field_name: 'A[0]' },
        { label: 'B', value: 'b', pdf_field_name: 'B[0]' },
      ],
    } as Partial<FormField>);
    expect(isCountedReviewed(
      withReviewStatus(mappedChoice, 'reviewed_correct', []), [])).toBe(true);
    // A field with no id or type at all (hand-edited kit) is likewise never
    // counted reviewed -- no lint rule names that class either (Opus outer
    // review, pass 1).
    const idless = completeField({ id: '' } as Partial<FormField>);
    expect(isCountedReviewed(
      withReviewStatus(idless, 'reviewed_correct', []), [])).toBe(false);
  });

  it('a CLIENT-only error no longer excludes a signed-off field from the count (decision 2)', () => {
    // checkFieldComplete leaves the count: the pinned predicate reads _review
    // + lint findings only, inputs the server also possesses. The row icon
    // still shows red for this field (statusFromFindings below) -- the named
    // corner accepted with the pinning.
    const signedError = withReviewStatus(errorField(), 'reviewed_correct');
    expect(isCountedReviewed(signedError)).toBe(true);
    expect(isReviewTargetFromFindings(signedError)).toBe(false);
    expect(statusFromFindings(signedError)).toBe('error');
  });
});

describe('seen_fingerprints + the timeliness demotion (s18 C1, decision 3)', () => {
  it('the sign-off stamps the fingerprints of the findings in hand', () => {
    const f = finding('f1');
    const signed = withReviewStatus(completeField(), 'reviewed_correct', [f]);
    expect(signed._review?.seen_fingerprints).toEqual([findingFingerprint(f)]);
  });

  it('a finding NEW since the sign-off demotes the field to needs-review', () => {
    const seenAtSignoff = finding('f1');
    const signed = withReviewStatus(
      completeField(), 'reviewed_correct', [seenAtSignoff]);
    // The same finding again: covered by the sign-off, stays complete.
    expect(newFindingsSinceReview(signed, [seenAtSignoff])).toBe(false);
    expect(statusFromFindings(signed, [seenAtSignoff])).toBe('complete');
    expect(isCountedReviewed(signed, [seenAtSignoff])).toBe(true);
    // A different rule on the same field: NEW -> amber, out of the count.
    const fresh = finding('f1', {
      rule: 'help-instructions-screen-ref',
      path: 'fields[0] (id=f1).help.instructions',
    });
    expect(newFindingsSinceReview(signed, [seenAtSignoff, fresh])).toBe(true);
    expect(statusFromFindings(signed, [seenAtSignoff, fresh])).toBe('review');
    expect(isCountedReviewed(signed, [seenAtSignoff, fresh])).toBe(false);
  });

  it('a message-only rewording does NOT demote (fingerprint excludes the message)', () => {
    const before = finding('f1', { message: 'old wording' });
    const signed = withReviewStatus(completeField(), 'reviewed_correct', [before]);
    const reworded = finding('f1', { message: 'brand new plain-language wording' });
    expect(findingFingerprint(before)).toBe(findingFingerprint(reworded));
    expect(newFindingsSinceReview(signed, [reworded])).toBe(false);
    expect(statusFromFindings(signed, [reworded])).toBe('complete');
  });

  it('an identity-hash move does NOT change the fingerprint (suffix stripped)', () => {
    const a = finding('f1', {
      rule: 'guidance-identity-stale',
      path: 'fields (id=f1).help[identity:aaa111]',
    });
    const b = finding('f1', {
      rule: 'guidance-identity-stale',
      path: 'fields (id=f1).help[identity:bbb222]',
    });
    expect(findingFingerprint(a)).toBe(findingFingerprint(b));
  });

  it('a legacy sign-off with NO fingerprint slot is grandfathered (no demotion)', () => {
    const legacy = completeField({
      _review: { status: 'reviewed_correct' },
    });
    expect(newFindingsSinceReview(legacy, [finding('f1')])).toBe(false);
    expect(statusFromFindings(legacy, [finding('f1')])).toBe('complete');
  });

  it('a sign-off with no report in hand stamps the empty set, so later findings demote', () => {
    const signedBlind = withReviewStatus(completeField(), 'reviewed_correct');
    expect(signedBlind._review?.seen_fingerprints).toEqual([]);
    expect(newFindingsSinceReview(signedBlind, [finding('f1')])).toBe(true);
  });

  it('the STALENESS finding never demotes via timeliness -- the ack gate owns it', () => {
    // Sign-off-then-drift-then-ack is the anim gate's core scenario. The ack
    // writer preserves seen_fingerprints, so counting the stale finding in
    // the timeliness rule made the ack a dead end: permanently amber, no
    // control able to clear it (Opus outer review, pass 5).
    const staleFinding = finding('f1', {
      rule: 'guidance-identity-stale',
      path: 'fields (id=f1).help[identity:abc123]',
    });
    const signed = withReviewStatus(completeField(), 'reviewed_correct', []);
    // Drift arrives after the sign-off; the reviewer ticks the ack box.
    const acked = withGuidanceAck(signed, 'abc123', true);
    expect(newFindingsSinceReview(acked, [staleFinding])).toBe(false);
    expect(statusFromFindings(acked, [staleFinding])).toBe('complete');
    expect(isCountedReviewed(acked, [staleFinding])).toBe(true);
    // UN-acked drift still demotes -- through the ack gate, as designed.
    expect(statusFromFindings(signed, [staleFinding])).toBe('review');
    expect(isCountedReviewed(signed, [staleFinding])).toBe(false);
  });
});

describe('_review writers carry all four slots (s18 C1 preservation contract)', () => {
  const f = finding('f1');
  // A field with every slot populated: status + note + ack + fingerprints.
  function fullyLoaded(): FormField {
    let field = withReviewStatus(completeField(), 'reviewed_correct', [f]);
    field = withReviewNote(field, 'looks right');
    field = withGuidanceAck(field, 'deadbeef', true);
    return field;
  }

  it('the note writer preserves status, ack and fingerprints', () => {
    const next = withReviewNote(fullyLoaded(), 'updated note');
    expect(next._review).toEqual({
      status: 'reviewed_correct',
      note: 'updated note',
      guidance_ack_sha1: 'deadbeef',
      seen_fingerprints: [findingFingerprint(f)],
    });
  });

  it('the ack writer preserves status, note and fingerprints', () => {
    const next = withGuidanceAck(fullyLoaded(), 'cafe1234', true);
    expect(next._review).toEqual({
      status: 'reviewed_correct',
      note: 'looks right',
      guidance_ack_sha1: 'cafe1234',
      seen_fingerprints: [findingFingerprint(f)],
    });
  });

  it('clearing the ack preserves the other three slots', () => {
    const next = withGuidanceAck(fullyLoaded(), 'deadbeef', false);
    expect(next._review).toEqual({
      status: 'reviewed_correct',
      note: 'looks right',
      seen_fingerprints: [findingFingerprint(f)],
    });
  });

  it('the status writer owns the fingerprint slot: re-sign-off restamps, un-sign-off clears', () => {
    const fresh = finding('f1', { rule: 'help-instructions-screen-ref' });
    const restamped = withReviewStatus(fullyLoaded(), 'reviewed_correct', [fresh]);
    expect(restamped._review?.seen_fingerprints)
      .toEqual([findingFingerprint(fresh)]);
    const flagged = withReviewStatus(fullyLoaded(), 'needs_followup');
    expect(flagged._review).toEqual({
      status: 'needs_followup',
      note: 'looks right',
      guidance_ack_sha1: 'deadbeef',
    });
  });
});

describe('reviewCounts (the strip tally, s18 C1)', () => {
  it('reviewed + toReview always partition total over the pinned predicate', () => {
    const seen = finding('a');
    const fields = [
      withReviewStatus(completeField({ id: 'a' }), 'reviewed_correct', [seen]),
      withReviewStatus(completeField({ id: 'b' }), 'reviewed_correct'),
      completeField({ id: 'c' }),                                  // unreviewed
      withReviewStatus(completeField({ id: 'd' }), 'needs_followup'),
    ];
    const byField = new Map([['a', [seen]]]);
    const counts = reviewCounts(fields, byField);
    expect(counts).toEqual({ reviewed: 2, toReview: 2, total: 4, percentage: 50 });
  });

  it('a lint ERROR pulls a signed-off field out of reviewed', () => {
    const err = finding('a', { severity: 'ERROR', rule: 'field-unbacked' });
    const fields = [
      withReviewStatus(completeField({ id: 'a' }), 'reviewed_correct', [err]),
    ];
    expect(reviewCounts(fields, new Map([['a', [err]]])).reviewed).toBe(0);
  });

  it('an empty form is 0 reviewed of 0 at 0%', () => {
    expect(reviewCounts([], undefined))
      .toEqual({ reviewed: 0, toReview: 0, total: 0, percentage: 0 });
  });
});

describe('reviewStatus write helpers serialize clean', () => {
  it('resetting to unreviewed with no note drops the _review key entirely', () => {
    const marked = withReviewStatus(completeField(), 'reviewed_correct');
    // The sign-off stamps the fingerprint slot (empty set with no report).
    expect(marked._review).toEqual({
      status: 'reviewed_correct', seen_fingerprints: [],
    });
    const reset = withReviewStatus(marked, 'unreviewed');
    expect('_review' in reset).toBe(false);
  });

  it('keeps _review when unreviewed but a note remains', () => {
    const noted = withReviewNote(completeField(), 'left a note');
    // A note on an otherwise-neutral field keeps the key so the note persists.
    expect(noted._review).toEqual({ status: 'unreviewed', note: 'left a note' });
  });

  it('clearing the note on a neutral field drops the key', () => {
    const noted = withReviewNote(completeField(), 'temp');
    const cleared = withReviewNote(noted, '');
    expect('_review' in cleared).toBe(false);
  });

  it('a whitespace-only note counts as empty (no "   " stored)', () => {
    // On a flagged field, a whitespace-only note must not survive as the note --
    // else the tooltip renders "Needs follow-up:    " instead of the default.
    const flagged = withReviewStatus(completeField(), 'needs_followup');
    const noted = withReviewNote(flagged, '   ');
    expect(noted._review).toEqual({ status: 'needs_followup' });
    // On a neutral field, whitespace-only clears the key entirely.
    const neutral = withReviewNote(completeField(), '  \n ');
    expect('_review' in neutral).toBe(false);
  });

  it('preserves internal spacing once a note has real content', () => {
    const noted = withReviewNote(completeField(), 'line one\n  line two');
    expect(noted._review?.note).toBe('line one\n  line two');
  });

  it('a status change preserves an existing note', () => {
    const noted = withReviewNote(completeField(), 'see comment');
    const flagged = withReviewStatus(noted, 'needs_followup');
    expect(flagged._review).toEqual({ status: 'needs_followup', note: 'see comment' });
  });
});

describe('_review survives the save filter (round-trip safety)', () => {
  it('stripEditorState preserves _review (it is not the _ungroup stash)', () => {
    const marked = withReviewStatus(completeField(), 'needs_followup');
    const withNote = withReviewNote(marked, 'circle back');
    const schema = {
      source: 'pdf',
      form_metadata: { title: 'T', form_number: 'T', total_widgets: 1, total_fields: 1, version: '1', language: 'en' },
      parts: [],
      sections: [{ id: 'sec-1', label: 'S', order: 0, fields: ['f1'] }],
      fields: [withNote],
    } as unknown as FormSchema;
    const saved = stripEditorState(schema);
    expect(saved.fields[0]._review).toEqual({ status: 'needs_followup', note: 'circle back' });
  });
});
