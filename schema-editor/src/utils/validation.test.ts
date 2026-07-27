import { describe, it, expect } from 'vitest';
import { checkFieldComplete, getCompletionStats, validateSchema } from './validation';
import type { FormSchema, FormField } from '../types/schema';

// Minimal valid field; override per test. read_only/pdf_field_name are the
// non-optional FormField props validateSchema does not itself require, but the
// type does.
function field(id: string, extra: Partial<FormField> = {}): FormField {
  return {
    id,
    name: id,
    type: 'text',
    pdf_field_name: id,
    read_only: false,
    section_id: 'sec-1',
    ...extra,
  };
}

function schemaWith(fields: FormField[]): FormSchema {
  return {
    source: 'pdf',
    form_metadata: {
      title: 'Test',
      form_number: 'T-1',
      total_widgets: fields.length,
      total_fields: fields.length,
      version: '1',
      language: 'en',
    },
    parts: [],
    sections: [{ id: 'sec-1', label: 'Section 1', order: 1, fields: fields.map(f => f.id) }],
    fields,
  };
}

describe('validateSchema conditional-reference checks (bd polyglot-pdf-y61i)', () => {
  it('does NOT flag a show_if that targets a field declared LATER (forward ref)', () => {
    // trigger appears AFTER the field that references it -- the incremental-set bug
    // falsely flagged this as "references non-existent field".
    const schema = schemaWith([
      field('dependent', { show_if: { field: 'trigger', operator: 'equals', value: 'yes' } }),
      field('trigger'),
    ]);

    const errors = validateSchema(schema);

    expect(errors.some(e => e.message.includes('show_if references non-existent field'))).toBe(false);
  });

  it('flags composite show_if and require_if atoms referencing non-existent fields (bd h76m.8)', () => {
    const schema = schemaWith([
      field('dependent', {
        show_if: { all_of: [{ field: 'ghost_a', operator: 'is_not_empty' }] },
        require_if: { field: 'ghost_b', operator: 'is_checked' },
      }),
      field('trigger'),
    ]);

    const errors = validateSchema(schema);

    expect(errors.some(e => e.message.includes('show_if references non-existent field: ghost_a'))).toBe(true);
    expect(errors.some(e => e.message.includes('require_if references non-existent field: ghost_b'))).toBe(true);
  });

  it('does NOT flag composite/require_if references that resolve (incl. forward refs)', () => {
    const schema = schemaWith([
      field('dependent', {
        show_if: { any_of: [{ field: 'trigger', operator: 'is_not_empty' }] },
        require_if: { none_of: [{ field: 'later', operator: 'is_checked' }] },
      }),
      field('trigger'),
      field('later'),
    ]);

    const errors = validateSchema(schema);

    expect(errors.some(e => e.message.includes('references non-existent field'))).toBe(false);
  });

  it('STILL flags a show_if that targets a field that does not exist anywhere', () => {
    const schema = schemaWith([
      field('dependent', { show_if: { field: 'ghost', operator: 'equals', value: 'yes' } }),
      field('trigger'),
    ]);

    const errors = validateSchema(schema);

    const warn = errors.find(e => e.message.includes('show_if references non-existent field'));
    expect(warn).toBeDefined();
    expect(warn?.message).toContain('ghost');
    expect(warn?.type).toBe('warning');
  });

  it('still detects a genuine duplicate field ID (incremental seen-set preserved)', () => {
    const schema = schemaWith([field('dup'), field('dup')]);

    const errors = validateSchema(schema);

    expect(errors.some(e => e.message === 'Duplicate field ID' && e.field_id === 'dup')).toBe(true);
  });
});

describe("validateSchema 'To review' gate mirror (bd polyglot-pdf-6cfu.3)", () => {
  it("errors on a field still filed in a sec_to_review section", () => {
    const schema = {
      form_metadata: { title: 'T', version: '1' },
      sections: [
        { id: 'sec_real', label: 'Real', order: 1, fields: [] },
        { id: 'sec_to_review_p1', label: 'To review', order: 2, fields: ['f1'] },
      ],
      fields: [
        { id: 'f1', name: 'F1', type: 'text', section_id: 'sec_to_review_p1' },
      ],
    } as unknown as FormSchema;
    const errs = validateSchema(schema).filter(e =>
      e.message.includes("'To review'"));
    expect(errs).toHaveLength(1);
    expect(errs[0]).toMatchObject({ field_id: 'f1', type: 'error' });
  });

  it('stays quiet once the field is re-filed', () => {
    const schema = {
      form_metadata: { title: 'T', version: '1' },
      sections: [
        { id: 'sec_real', label: 'Real', order: 1, fields: ['f1'] },
        { id: 'sec_to_review_p1', label: 'To review', order: 2, fields: [] },
      ],
      fields: [
        { id: 'f1', name: 'F1', type: 'text', section_id: 'sec_real' },
      ],
    } as unknown as FormSchema;
    expect(validateSchema(schema).filter(e =>
      e.message.includes("'To review'"))).toHaveLength(0);
  });
});

// checkFieldComplete PDF-mapping + reasons (bd polyglot-pdf-0x10.6): a
// CONSOLIDATED choice field (per-option pdf_field_name, none at field level)
// is legitimately mapped -- the old blanket "Missing PDF field name" marked
// every merged group red with nothing actually wrong. And the status now
// carries plain-language reasons the UI can show.
describe('checkFieldComplete PDF mapping on consolidated groups (bd 0x10.6)', () => {
  const complete = { spoken_name: 'spoken', help: { instructions: 'Done.' } };

  it('accepts a consolidated group whose options each carry pdf_field_name', () => {
    const status = checkFieldComplete(field('gender', {
      ...complete,
      type: 'radio',
      pdf_field_name: undefined,
      options: [
        { value: 'male', label: 'Male', pdf_field_name: 'g[0]' },
        { value: 'female', label: 'Female', pdf_field_name: 'g[1]' },
      ],
    } as Partial<FormField>));
    expect(status.errors).toEqual([]);
    expect(status.isComplete).toBe(true);
  });

  it('names the specific unmapped options of a partially-mapped group', () => {
    const status = checkFieldComplete(field('race', {
      ...complete,
      type: 'checkbox_group',
      pdf_field_name: undefined,
      options: [
        { value: 'white', label: 'White', pdf_field_name: 'r[0]' },
        { value: 'black', label: 'Black' },
      ],
    } as Partial<FormField>));
    expect(status.errors).toEqual(['Options missing a PDF widget mapping: Black']);
  });

  it('flags a group with NO mapping anywhere (field or options)', () => {
    const status = checkFieldComplete(field('race', {
      ...complete,
      type: 'checkbox_group',
      pdf_field_name: undefined,
      options: [
        { value: 'white', label: 'White' },
        { value: 'black', label: 'Black' },
      ],
    } as Partial<FormField>));
    expect(status.errors).toEqual([
      'No PDF mapping: neither the field nor its options name a PDF widget',
    ]);
  });

  it('still requires pdf_field_name on a plain (non-group) field', () => {
    const status = checkFieldComplete(field('name', {
      ...complete,
      pdf_field_name: undefined,
    } as Partial<FormField>));
    expect(status.errors).toEqual(['Missing PDF field name']);
  });

  it('names the review reasons so the UI can say WHY a field is amber', () => {
    const status = checkFieldComplete(field('bare', {} as Partial<FormField>));
    expect(status.needsReview).toBe(true);
    expect(status.reviewReasons).toEqual([
      'Help instructions are missing or a placeholder',
      'Missing spoken name',
    ]);
    const clean = checkFieldComplete(field('done', complete as Partial<FormField>));
    expect(clean.reviewReasons).toEqual([]);
    expect(clean.isComplete).toBe(true);
  });
});

describe('getCompletionStats reflects human review status (bd u8t6)', () => {
  const complete = { spoken_name: 'spoken', help: { instructions: 'Done.' } };

  it('counts a reviewed_correct auto-amber field as complete', () => {
    // A bare field is auto-amber (no spoken name / help). Signing it off should
    // move it from needsReview into complete, matching the FieldList green icon.
    const stats = getCompletionStats(schemaWith([
      field('amber', { _review: { status: 'reviewed_correct' } } as Partial<FormField>),
    ]));
    expect(stats).toMatchObject({ complete: 1, needsReview: 0, total: 1, percentage: 100 });
  });

  it('counts a needs_followup field as needs-review even when auto-complete', () => {
    const stats = getCompletionStats(schemaWith([
      field('ok', { ...complete, _review: { status: 'needs_followup' } } as Partial<FormField>),
    ]));
    expect(stats).toMatchObject({ complete: 0, needsReview: 1, total: 1 });
  });

  it('never counts a real ERROR field as complete, even when reviewed_correct', () => {
    // No pdf_field_name -> local ERROR. A sign-off must not green it in the stats
    // any more than in the list icon (error always wins).
    const stats = getCompletionStats(schemaWith([
      field('broken', {
        ...complete, pdf_field_name: undefined,
        _review: { status: 'reviewed_correct' },
      } as Partial<FormField>),
    ]));
    expect(stats).toMatchObject({ complete: 0, needsReview: 0, total: 1 });
  });

  it('unreviewed fields keep the automatic counting', () => {
    const stats = getCompletionStats(schemaWith([
      field('done', complete as Partial<FormField>),
      field('amber', {} as Partial<FormField>),
    ]));
    expect(stats).toMatchObject({ complete: 1, needsReview: 1, total: 2, percentage: 50 });
  });
});
