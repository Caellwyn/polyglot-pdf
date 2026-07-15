/**
 * The FieldEditor 'Required' checkbox must read/write validation.required, the
 * canonical shape every runtime consumer (frontend isFieldRequired, backend
 * ai_context.py/manifest_service.py, the Pydantic model) reads -- not a
 * top-level field.required, which is read by no consumer and is now a
 * schema_lint ERROR (bd polyglot-pdf-8n2s).
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FieldEditor } from './FieldEditor';
import type { FormSchema, FormField } from '../types/schema';

function textField(id: string, extra: Partial<FormField> = {}): FormField {
  return {
    id, name: id, type: 'text', section_id: 's1',
    pdf_field_name: '', read_only: false,
    ...extra,
  } as FormField;
}

function oneFieldSchema(field: FormField): FormSchema {
  return {
    source: 'pdf',
    form_metadata: {
      title: 'W-7', form_number: 'W-7', version: '1', language: 'en',
      total_widgets: 1, total_fields: 1,
    },
    parts: [],
    sections: [{ id: 's1', label: 'One', order: 1, fields: [field.id] }],
    fields: [field],
  };
}

describe('FieldEditor Required checkbox (bd polyglot-pdf-8n2s)', () => {
  it('checking Required patches validation.required, never a top-level required key', () => {
    const onUpdateField = vi.fn();
    const field = textField('f1');
    const schema = oneFieldSchema(field);
    render(
      <FieldEditor field={field} schema={schema} onUpdateField={onUpdateField} />,
    );

    const checkbox = screen.getByLabelText('Required') as HTMLInputElement;
    expect(checkbox.checked).toBe(false);
    fireEvent.click(checkbox);

    expect(onUpdateField).toHaveBeenCalledTimes(1);
    const patched = onUpdateField.mock.calls[0][0] as FormField;
    expect(patched.validation?.required).toBe(true);
    expect((patched as unknown as Record<string, unknown>).required).toBeUndefined();
  });

  it('unchecking Required clears validation.required', () => {
    const onUpdateField = vi.fn();
    const field = textField('f1', { validation: { required: true } });
    const schema = oneFieldSchema(field);
    render(
      <FieldEditor field={field} schema={schema} onUpdateField={onUpdateField} />,
    );

    const checkbox = screen.getByLabelText('Required') as HTMLInputElement;
    expect(checkbox.checked).toBe(true);
    fireEvent.click(checkbox);

    const patched = onUpdateField.mock.calls[0][0] as FormField;
    expect(patched.validation?.required).toBe(false);
  });

  it('renders checked when the field already carries validation.required (load -> preview)', () => {
    const field = textField('f1', { validation: { required: true } });
    const schema = oneFieldSchema(field);
    render(
      <FieldEditor field={field} schema={schema} onUpdateField={vi.fn()} />,
    );

    const checkbox = screen.getByLabelText('Required') as HTMLInputElement;
    expect(checkbox.checked).toBe(true);
  });
});
