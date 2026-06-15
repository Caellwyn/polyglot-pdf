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
    const schema = schemaWith([
      field('controller', {
        controls_fields: { when_value: 'yes', shows: ['shown_later'], makes_required: ['required_later'] },
      }),
      field('shown_later'),
      field('required_later'),
    ]);

    const errors = validateSchema(schema);

    expect(errors.some(e => e.message.includes('controls_fields references non-existent field'))).toBe(false);
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
      field('controller', { controls_fields: { when_value: 'yes', unlocks: ['ghost'] } }),
      field('other'),
    ]);

    const errors = validateSchema(schema);

    const warn = errors.find(e => e.message.includes('controls_fields references non-existent field'));
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
