/**
 * Load-time legacy `required` migration (bd polyglot-pdf-0x10.4).
 *
 * A kit saved by the pre-8n2s editor carries top-level `required` keys that
 * nothing reads but that JSON round-trips re-save forever, tripping the
 * backend's required-top-level lint ERROR with no UI recourse. Loading must
 * self-heal: truthy values move into validation.required (so the Required
 * checkbox shows CHECKED for previously-required fields), the canonical key
 * is never clobbered, and the save serialization carries no top-level key.
 */
import { describe, it, expect } from 'vitest';
import { migrateLegacyRequired } from './schemaMigrate';
import { stripEditorState } from './fieldGrouping';
import type { FormSchema } from '../types/schema';

function schemaWith(fields: object[]): FormSchema {
  return {
    source: 'pdf',
    form_metadata: {
      title: 'T', form_number: 'T', total_widgets: fields.length,
      total_fields: fields.length, version: '1', language: 'en',
    },
    parts: [],
    sections: [{ id: 's1', label: 'S1', order: 0, fields: fields.map((f: any) => f.id) }],
    fields: fields as FormSchema['fields'],
  } as unknown as FormSchema;
}

const base = { name: 'F', type: 'text', section_id: 's1', read_only: false, pdf_field_name: 'p' };

describe('migrateLegacyRequired (bd 0x10.4)', () => {
  it('moves a truthy top-level required into validation.required (checkbox shows checked)', () => {
    const out = migrateLegacyRequired(schemaWith([
      { ...base, id: 'a', required: true },
    ]));
    const a = out.fields[0] as any;
    expect(a.required).toBeUndefined();
    expect(a.validation?.required).toBe(true);
  });

  it('drops a falsy top-level required without inventing validation', () => {
    const out = migrateLegacyRequired(schemaWith([
      { ...base, id: 'a', required: false },
    ]));
    const a = out.fields[0] as any;
    expect('required' in a).toBe(false);
    expect(a.validation).toBeUndefined();
  });

  it('never clobbers an explicit validation.required, preserves sibling validation keys', () => {
    const out = migrateLegacyRequired(schemaWith([
      { ...base, id: 'a', required: true, validation: { required: false } },
      { ...base, id: 'b', required: true, validation: { max_length: 5 } },
    ]));
    expect((out.fields[0] as any).validation).toEqual({ required: false });
    expect((out.fields[1] as any).validation).toEqual({ max_length: 5, required: true });
  });

  it('is identity (same reference) on an already-clean schema', () => {
    const clean = schemaWith([{ ...base, id: 'a', validation: { required: true } }]);
    expect(migrateLegacyRequired(clean)).toBe(clean);
  });

  it('the REAL save serialization of a migrated legacy kit carries no top-level required', () => {
    const migrated = migrateLegacyRequired(schemaWith([
      { ...base, id: 'a', required: true },
      { ...base, id: 'b', required: false },
    ]));
    const saved = JSON.stringify(stripEditorState(migrated));
    expect(saved).not.toContain('"required":true,"');
    const parsed = JSON.parse(saved);
    for (const f of parsed.fields) {
      expect('required' in f).toBe(false);
    }
    expect(parsed.fields[0].validation.required).toBe(true);
  });
});
