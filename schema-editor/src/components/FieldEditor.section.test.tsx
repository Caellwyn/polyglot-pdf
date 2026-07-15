/**
 * The FieldEditor 'Section' dropdown must keep section.fields[] and
 * field.section_id in lockstep (bd polyglot-pdf-w7rg). Before the fix the
 * dropdown patched only field.section_id, so the moved field kept rendering
 * under its OLD section (FieldList renders from section.fields[]) and the
 * later remove/merge ops trusted a stale listing. The dropdown now commits the
 * whole {fields, sections} atomically via onUpdateFields.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FieldEditor } from './FieldEditor';
import type { FormSchema, FormField } from '../types/schema';

function textField(id: string, section_id: string): FormField {
  return {
    id, name: id, type: 'text', section_id,
    pdf_field_name: '', read_only: false,
  } as unknown as FormField;
}

function twoSectionSchema(): FormSchema {
  return {
    source: 'pdf',
    form_metadata: {
      title: 'W-7', form_number: 'W-7', version: '1', language: 'en',
      total_widgets: 2, total_fields: 2,
    },
    parts: [{ id: 'p1', label: 'P1', order: 1, section_ids: ['s1', 's2'] }],
    sections: [
      { id: 's1', label: 'One', order: 1, fields: ['f1', 'f2'] },
      { id: 's2', label: 'Two', order: 2, fields: [] },
    ],
    fields: [textField('f1', 's1'), textField('f2', 's1')],
  } as unknown as FormSchema;
}

describe('FieldEditor Section dropdown (bd polyglot-pdf-w7rg)', () => {
  it('moving a field commits BOTH section.fields[] arrays and section_id', () => {
    const onUpdateFields = vi.fn();
    const schema = twoSectionSchema();
    render(
      <FieldEditor
        field={schema.fields[0]}
        schema={schema}
        onUpdateField={vi.fn()}
        onUpdateFields={onUpdateFields}
      />,
    );
    const select = screen.getByLabelText('Section') as HTMLSelectElement;
    expect(select.value).toBe('s1');
    fireEvent.change(select, { target: { value: 's2' } });

    expect(onUpdateFields).toHaveBeenCalledTimes(1);
    const [fields, sections] = onUpdateFields.mock.calls[0] as [
      FormField[], { id: string; fields: string[] }[],
    ];
    const byId = new Map(fields.map(f => [f.id, f]));
    expect(byId.get('f1')!.section_id).toBe('s2');
    const s1 = sections.find(s => s.id === 's1')!;
    const s2 = sections.find(s => s.id === 's2')!;
    expect(s1.fields).toEqual(['f2']);   // f1 removed from old section
    expect(s2.fields).toEqual(['f1']);   // f1 added to new section
    // Never double-listed.
    const listed = sections.flatMap(s => s.fields);
    expect(new Set(listed).size).toBe(listed.length);
  });

  it('reassigning to "No section" clears section_id and every listing', () => {
    const onUpdateFields = vi.fn();
    const schema = twoSectionSchema();
    render(
      <FieldEditor
        field={schema.fields[0]}
        schema={schema}
        onUpdateField={vi.fn()}
        onUpdateFields={onUpdateFields}
      />,
    );
    const select = screen.getByLabelText('Section') as HTMLSelectElement;
    fireEvent.change(select, { target: { value: '' } });

    const [fields, sections] = onUpdateFields.mock.calls[0] as [
      FormField[], { id: string; fields: string[] }[],
    ];
    const byId = new Map(fields.map(f => [f.id, f]));
    expect(byId.get('f1')!.section_id).toBeUndefined();
    expect(sections.some(s => s.fields.includes('f1'))).toBe(false);
  });

  it('falls back to the single-field patch when onUpdateFields is absent', () => {
    const onUpdateField = vi.fn();
    const schema = twoSectionSchema();
    render(
      <FieldEditor
        field={schema.fields[0]}
        schema={schema}
        onUpdateField={onUpdateField}
      />,
    );
    const select = screen.getByLabelText('Section') as HTMLSelectElement;
    fireEvent.change(select, { target: { value: 's2' } });
    expect(onUpdateField).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'f1', section_id: 's2' }),
    );
  });
});
