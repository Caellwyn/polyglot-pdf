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
import { stripEditorState } from '../utils/fieldGrouping';
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

  // Exit criterion 1: the round-trip through the ACTUAL save path (not just the
  // in-memory patch). saveRemoteSchema/fileSystemAccess both persist a kit as
  // JSON.stringify(stripEditorState(schema)); this reproduces that exact
  // serialization and asserts validation.required survives with no top-level
  // required key -- the shape backend schema_lint's required-top-level rule
  // accepts (bd polyglot-pdf-8n2s).
  it('the check -> save serialization round-trips validation.required and emits no top-level required key', () => {
    let field = textField('f1');
    let schema = oneFieldSchema(field);
    const onUpdateField = (updated: FormField) => {
      field = updated;
      schema = { ...schema, fields: [updated] };
    };
    const { rerender } = render(
      <FieldEditor field={field} schema={schema} onUpdateField={onUpdateField} />,
    );

    fireEvent.click(screen.getByLabelText('Required'));
    rerender(<FieldEditor field={field} schema={schema} onUpdateField={onUpdateField} />);
    expect((screen.getByLabelText('Required') as HTMLInputElement).checked).toBe(true);

    // The exact save serialization the remote + local save paths apply.
    const persisted = JSON.parse(JSON.stringify(stripEditorState(schema))) as FormSchema;
    const savedField = persisted.fields[0] as unknown as Record<string, unknown>;
    expect((savedField.validation as Record<string, unknown>).required).toBe(true);
    expect(savedField.required).toBeUndefined();
  });
});
