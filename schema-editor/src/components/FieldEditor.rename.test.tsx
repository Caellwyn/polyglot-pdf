/**
 * FieldEditor id-rename UI (bd polyglot-pdf-0x10.1): pencil opens an edit
 * mode, Enter/Rename commits through onRenameField, a returned block reason
 * shows inline (and the editor stays in edit mode, no schema mutation),
 * Escape/Cancel backs out. Without onRenameField the header is read-only.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FieldEditor } from './FieldEditor';
import type { FormSchema, FormField } from '../types/schema';

function field(): FormField {
  return {
    id: 'treaty_country', name: 'T', spoken_name: 'treaty country',
    type: 'text', section_id: 's1', read_only: false, pdf_field_name: 't[0]',
    // Clean help + position so the flagged-reasons banner (itself
    // role="alert") stays absent -- these tests assert on the rename form's
    // OWN inline alert, and a second alert makes getByRole ambiguous (bd g63j).
    help: { instructions: 'Enter the treaty country.' },
    pdf_position: { page: 1, x: 10, y: 10, width: 50, height: 12 },
  } as unknown as FormField;
}

function schemaWith(f: FormField): FormSchema {
  return {
    source: 'pdf',
    form_metadata: { title: 'T', form_number: 'T', total_widgets: 1, total_fields: 1, version: '1', language: 'en' },
    parts: [],
    sections: [{ id: 's1', label: 'S1', order: 0, fields: [f.id] }],
    fields: [f],
  } as unknown as FormSchema;
}

describe('FieldEditor field-id rename UI (bd 0x10.1)', () => {
  it('renders a read-only header when onRenameField is absent', () => {
    const f = field();
    render(<FieldEditor field={f} schema={schemaWith(f)} onUpdateField={vi.fn()} />);
    expect(screen.getByText('treaty_country')).toBeInTheDocument();
    expect(screen.queryByLabelText('Rename field ID')).toBeNull();
  });

  it('pencil -> input -> Rename commits the new id through onRenameField', () => {
    const f = field();
    const onRenameField = vi.fn().mockReturnValue(null);
    render(
      <FieldEditor
        field={f} schema={schemaWith(f)} onUpdateField={vi.fn()}
        onRenameField={onRenameField}
      />,
    );
    fireEvent.click(screen.getByLabelText('Rename field ID'));
    const input = screen.getByLabelText('Field ID');
    fireEvent.change(input, { target: { value: 'relationship_to_us_person' } });
    fireEvent.click(screen.getByText('Rename'));
    expect(onRenameField).toHaveBeenCalledWith('treaty_country', 'relationship_to_us_person');
  });

  it('Enter commits; Escape cancels without calling onRenameField', () => {
    const f = field();
    const onRenameField = vi.fn().mockReturnValue(null);
    render(
      <FieldEditor
        field={f} schema={schemaWith(f)} onUpdateField={vi.fn()}
        onRenameField={onRenameField}
      />,
    );
    fireEvent.click(screen.getByLabelText('Rename field ID'));
    const input = screen.getByLabelText('Field ID');
    fireEvent.change(input, { target: { value: 'new_id' } });
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(onRenameField).not.toHaveBeenCalled();
    expect(screen.queryByLabelText('Field ID')).toBeNull();

    fireEvent.click(screen.getByLabelText('Rename field ID'));
    const input2 = screen.getByLabelText('Field ID');
    fireEvent.change(input2, { target: { value: 'new_id' } });
    fireEvent.keyDown(input2, { key: 'Enter' });
    expect(onRenameField).toHaveBeenCalledWith('treaty_country', 'new_id');
  });

  it('a block reason shows inline and edit mode stays open (exit criterion 2)', () => {
    const f = field();
    const onRenameField = vi.fn().mockReturnValue('A field with the ID "dup" already exists.');
    render(
      <FieldEditor
        field={f} schema={schemaWith(f)} onUpdateField={vi.fn()}
        onRenameField={onRenameField}
      />,
    );
    fireEvent.click(screen.getByLabelText('Rename field ID'));
    fireEvent.change(screen.getByLabelText('Field ID'), { target: { value: 'dup' } });
    fireEvent.click(screen.getByText('Rename'));
    expect(screen.getByRole('alert')).toHaveTextContent('already exists');
    // Still editing: the input is present for a correction.
    expect(screen.getByLabelText('Field ID')).toBeInTheDocument();
  });
});
