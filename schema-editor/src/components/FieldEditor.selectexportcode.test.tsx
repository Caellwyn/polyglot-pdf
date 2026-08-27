/**
 * A dropdown's option.value is the PDF's own EXPORT CODE, not a minted slug
 * (bd polyglot-pdf-alzbr).
 *
 * A select has no fill branch of its own: the filler writes str(option.value)
 * verbatim into the combobox and never consults pdf_on_value, and PyMuPDF does
 * not validate that write against the widget's /Opt list. So a label-derived
 * slug is accepted silently and then RENDERS CLIPPED -- measured on the I-90
 * mailing-state box (36x18pt): 'WY' prints "WY", 'wyoming' prints "wyomin".
 *
 * The editor therefore must never derive a select's option value from its
 * label, and must let an author type the code directly -- it is the only place
 * that code can come from. radio / checkbox_group keep the mint-from-label
 * behaviour: they carry widget identity in pdf_field_name / pdf_on_value, so
 * their values really are internal join keys.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FieldEditor } from './FieldEditor';
import type { FormSchema, FormField } from '../types/schema';

function makeSchema(fields: FormField[]): FormSchema {
  return {
    source: 'pdf',
    form_metadata: { title: 'T', form_number: 'T-1', version: '1', language: 'en' },
    parts: [],
    sections: [{ id: 's1', label: 'S1', order: 1, fields: fields.map(f => f.id) }],
    fields,
  } as unknown as FormSchema;
}

function selectField(options = [
  { value: 'WY', label: 'Wyoming (WY)' },
  { value: 'AL', label: 'Alabama (AL)' },
]): FormField {
  return {
    id: 'mail_state', name: 'State', spoken_name: 'state', type: 'select',
    section_id: 's1', pdf_field_name: 'form1[0].P1_Line6e_State[0]',
    options,
  } as unknown as FormField;
}

function radioField(): FormField {
  return {
    id: 'sex', name: 'Sex', spoken_name: 'sex', type: 'radio',
    section_id: 's1', pdf_field_name: 'form1[0].P1_Sex[0]',
    options: [
      { value: 'male', label: 'Male', pdf_on_value: '1' },
      { value: 'female', label: 'Female', pdf_on_value: '2' },
    ],
  } as unknown as FormField;
}

describe('select option values are PDF export codes (bd polyglot-pdf-alzbr)', () => {
  it('editing a select option LABEL does not change its value', () => {
    // Mirror the radio test's setup exactly: render with the label ALREADY
    // edited, so the blur handler reads the new label from the current prop.
    // Anything less and the handler reads the old label, takes its no-op
    // early-return, and the test passes without exercising the fix at all.
    const onUpdateField = vi.fn();
    const edited = selectField();
    (edited.options as any)[0].label = 'Wyoming';
    render(
      <FieldEditor field={edited} schema={makeSchema([edited])}
        onUpdateField={onUpdateField} authorTier />,
    );

    const input = screen.getByDisplayValue('Wyoming') as HTMLInputElement;
    fireEvent.blur(input);

    // Every committed update must leave the export codes intact. The label may
    // change; the value may not. (A minted slug would be 'wyoming'.)
    const commits = onUpdateField.mock.calls
      .map(c => c[0])
      .filter(f => f && Array.isArray(f.options));
    for (const f of commits) {
      expect(f.options.map((o: any) => o.value)).toEqual(['WY', 'AL']);
    }
  });

  it('a radio option label edit STILL re-mints its value (the carve-out is select-only)', () => {
    // The blur handler reads the option's label from the CURRENT field prop,
    // so the parent must re-render with the edited label -- exactly what the
    // real editor does. Driving change+blur against a static prop would leave
    // the handler reading the OLD label and prove nothing.
    const onUpdateField = vi.fn();
    const edited = radioField();
    (edited.options as any)[0].label = 'Gentleman';
    render(
      <FieldEditor field={edited} schema={makeSchema([edited])}
        onUpdateField={onUpdateField} authorTier />,
    );

    const input = screen.getByDisplayValue('Gentleman') as HTMLInputElement;
    fireEvent.blur(input);

    const remint = onUpdateField.mock.calls
      .map(c => c[0])
      .filter(f => f && Array.isArray(f.options))
      .some(f => f.options.some((o: any) => o.value === 'gentleman'));
    expect(remint).toBe(true);
  });

  it('a select option value is EDITABLE, so the export code can be authored', () => {
    const onUpdateField = vi.fn();
    const field = selectField();
    render(
      <FieldEditor field={field} schema={makeSchema([field])}
        onUpdateField={onUpdateField} authorTier />,
    );

    // Rendered as an input carrying the code -- not a read-only chip.
    const codeInput = screen.getByDisplayValue('WY') as HTMLInputElement;
    expect(codeInput.tagName).toBe('INPUT');

    fireEvent.change(codeInput, { target: { value: 'WV' } });
    const wrote = onUpdateField.mock.calls
      .map(c => c[0])
      .filter(p => p && Array.isArray(p.options))
      .some(p => p.options[0].value === 'WV');
    expect(wrote).toBe(true);
  });

  it('a radio option value stays a read-only chip, not an input', () => {
    const field = radioField();
    render(
      <FieldEditor field={field} schema={makeSchema([field])}
        onUpdateField={vi.fn()} authorTier />,
    );
    // present as text...
    expect(screen.getByText('male')).toBeInTheDocument();
    // ...and NOT as an editable input
    expect(screen.queryByDisplayValue('male')).toBeNull();
  });

  it('+ Add Option on a select adds an EMPTY value for the author to fill', () => {
    const onUpdateField = vi.fn();
    const field = selectField();
    render(
      <FieldEditor field={field} schema={makeSchema([field])}
        onUpdateField={onUpdateField} authorTier />,
    );

    fireEvent.click(screen.getByText('+ Add Option'));
    const added = onUpdateField.mock.calls
      .map(c => c[0])
      .filter(p => p && Array.isArray(p.options))
      .pop();
    expect(added).toBeTruthy();
    // A minted slug here would look valid and print WRONG; empty trips the
    // existing option-value-missing lint ERROR, which is the honest signal.
    expect(added.options[added.options.length - 1].value).toBe('');
  });

  it('+ Add Option on a radio still mints a slug', () => {
    const onUpdateField = vi.fn();
    const field = radioField();
    render(
      <FieldEditor field={field} schema={makeSchema([field])}
        onUpdateField={onUpdateField} authorTier />,
    );

    fireEvent.click(screen.getByText('+ Add Option'));
    const added = onUpdateField.mock.calls
      .map(c => c[0])
      .filter(p => p && Array.isArray(p.options))
      .pop();
    expect(added).toBeTruthy();
    expect(added.options[added.options.length - 1].value).toBeTruthy();
  });
});
