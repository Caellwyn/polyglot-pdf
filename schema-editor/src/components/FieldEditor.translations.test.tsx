/**
 * Tests for label-edit translation invalidation (bd polyglot-pdf-d25e).
 * Baked label_translations (bd 2h9j) translate the option's CURRENT label text
 * and are keyed by language on the option itself -- so editing the label must
 * DROP them (a renamed option would otherwise show/speak the OLD text's
 * translations via the runtime kit-precedence path). Non-label edits and
 * untouched sibling options keep theirs; the Translate-options action / CLI
 * re-bakes on demand.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FieldEditor } from './FieldEditor';
import type { FormSchema, FormField } from '../types/schema';

function radioField(): FormField {
  return {
    id: 'application_type',
    name: 'Application type',
    type: 'radio',
    section_id: 's1',
    pdf_field_name: '',
    read_only: false,
    options: [
      { value: 'apply', label: 'Apply',
        label_translations: { spanish: 'Solicitar', french: 'Demander' } },
      { value: 'renew', label: 'Renew',
        label_translations: { spanish: 'Renovar', french: 'Renouveler' } },
    ],
  } as unknown as FormField;
}

function schemaWith(field: FormField): FormSchema {
  return {
    source: 'pdf',
    form_metadata: { title: 'W-7', form_number: 'W-7', version: '1', language: 'en', total_widgets: 2, total_fields: 1 },
    parts: [],
    sections: [{ id: 's1', label: 'S1', order: 0, fields: [field.id] }],
    fields: [field],
  } as unknown as FormSchema;
}

describe('FieldEditor label edit drops stale label_translations (bd d25e)', () => {
  it('editing an option label removes ITS translations, keeps the sibling\'s', () => {
    const onUpdateField = vi.fn();
    const field = radioField();
    render(
      <FieldEditor
        field={field}
        schema={schemaWith(field)}
        onUpdateField={onUpdateField}
      />,
    );

    const labelInput = screen.getByDisplayValue('Apply') as HTMLInputElement;
    fireEvent.change(labelInput, { target: { value: 'Apply now' } });

    expect(onUpdateField).toHaveBeenCalled();
    const updated = onUpdateField.mock.calls.at(-1)![0];
    const [edited, sibling] = updated.options;
    expect(edited.label).toBe('Apply now');
    expect('label_translations' in edited).toBe(false);
    // Untouched sibling keeps its translations verbatim.
    expect(sibling.label_translations).toEqual(
      { spanish: 'Renovar', french: 'Renouveler' });
    // The slug is untouched by the keystroke path (it re-mints on blur).
    expect(edited.value).toBe('apply');
  });

  it('only the EDITED option loses translations; blur without change drops nothing', () => {
    const onUpdateField = vi.fn();
    const field = radioField();
    render(
      <FieldEditor
        field={field}
        schema={schemaWith(field)}
        onUpdateField={onUpdateField}
      />,
    );

    // Focus + blur with no text change: no update at all (translations stay).
    const untouched = screen.getByDisplayValue('Apply') as HTMLInputElement;
    fireEvent.blur(untouched);
    expect(onUpdateField).not.toHaveBeenCalled();

    // Editing the SIBLING drops only the sibling's translations.
    const siblingInput = screen.getByDisplayValue('Renew') as HTMLInputElement;
    fireEvent.change(siblingInput, { target: { value: 'Renew it' } });
    const updated = onUpdateField.mock.calls.at(-1)![0];
    const [first, edited] = updated.options;
    expect(first.label_translations).toEqual(
      { spanish: 'Solicitar', french: 'Demander' });
    expect('label_translations' in edited).toBe(false);
  });
});
