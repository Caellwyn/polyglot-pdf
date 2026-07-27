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
  isReviewTarget,
  withReviewNote,
  withReviewStatus,
} from './reviewStatus';
import { stripEditorState } from './fieldGrouping';

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

  it('unreviewed falls through to the automatic amber/green', () => {
    expect(effectiveStatus(amberField())).toBe('review');
    expect(effectiveStatus(completeField())).toBe('complete');
  });
});

describe('reviewStatus.isReviewTarget', () => {
  it('reviewed_correct is NOT a target; needs_followup and auto-amber ARE', () => {
    expect(isReviewTarget(withReviewStatus(amberField(), 'reviewed_correct'))).toBe(false);
    expect(isReviewTarget(withReviewStatus(completeField(), 'needs_followup'))).toBe(true);
    expect(isReviewTarget(amberField())).toBe(true);
    expect(isReviewTarget(completeField())).toBe(false);
  });

  it('an ERROR field is a target even when signed off', () => {
    expect(isReviewTarget(withReviewStatus(errorField(), 'reviewed_correct'))).toBe(true);
  });
});

describe('reviewStatus write helpers serialize clean', () => {
  it('resetting to unreviewed with no note drops the _review key entirely', () => {
    const marked = withReviewStatus(completeField(), 'reviewed_correct');
    expect(marked._review).toEqual({ status: 'reviewed_correct' });
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
