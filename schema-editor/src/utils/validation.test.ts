import { describe, it, expect } from 'vitest';
import { validateSchema } from './validation';
import type { FormSchema, FormField } from '../types/schema';

// Minimal valid field; override per test. read_only/required/pdf_field_name are
// the non-optional FormField props validateSchema does not itself require, but the
// type does.
function field(id: string, extra: Partial<FormField> = {}): FormField {
  return {
    id,
    name: id,
    type: 'text',
    pdf_field_name: id,
    read_only: false,
    required: false,
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

  it('does NOT flag a controls_fields entry that targets fields declared LATER', () => {
    // controls_fields is an ARRAY of control rules (the real schema shape).
    const schema = schemaWith([
      field('controller', {
        controls_fields: [
          { operator: 'equals', value: 'yes', shows: ['shown_later'], makes_required: ['required_later'] },
        ],
      }),
      field('shown_later'),
      field('required_later'),
    ]);

    const errors = validateSchema(schema);

    expect(errors.some(e => e.message.includes('controls_fields references non-existent field'))).toBe(false);
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

  it('STILL flags a controls_fields entry that targets a field that does not exist', () => {
    const schema = schemaWith([
      field('controller', {
        controls_fields: [{ operator: 'equals', value: 'yes', unlocks: ['ghost'] }],
      }),
      field('other'),
    ]);

    const errors = validateSchema(schema);

    const warn = errors.find(e => e.message.includes('controls_fields references non-existent field'));
    expect(warn).toBeDefined();
    expect(warn?.message).toContain('ghost');
    expect(warn?.type).toBe('warning');
  });

  it('checks references across MULTIPLE control rules + hides/locks/makes_optional', () => {
    // A field with two control rules; the second targets a ghost via makes_optional.
    const schema = schemaWith([
      field('controller', {
        controls_fields: [
          { operator: 'equals', value: 'a', shows: ['real_a'] },
          { operator: 'equals', value: 'b', hides: ['real_b'], makes_optional: ['ghost2'] },
        ],
      }),
      field('real_a'),
      field('real_b'),
    ]);

    const errors = validateSchema(schema);

    // real_a / real_b resolve; ghost2 (in the SECOND rule, via makes_optional) is flagged.
    const ghostWarns = errors.filter(e => e.message.includes('controls_fields references non-existent field'));
    expect(ghostWarns).toHaveLength(1);
    expect(ghostWarns[0].message).toContain('ghost2');
  });

  it('still detects a genuine duplicate field ID (incremental seen-set preserved)', () => {
    const schema = schemaWith([field('dup'), field('dup')]);

    const errors = validateSchema(schema);

    expect(errors.some(e => e.message === 'Duplicate field ID' && e.field_id === 'dup')).toBe(true);
  });
});
