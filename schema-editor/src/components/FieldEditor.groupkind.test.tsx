/**
 * Tests for the in-place group-kind flip control (bd polyglot-pdf-checkbox-radio).
 * A consolidated group (has options[]) whose base Field Type picker is read-only
 * now gets a dedicated "Group behaves as" selector that flips it between radio
 * (choose one) and checkbox_group (choose several) via onChangeGroupKind. This
 * is the fix for a group extracted as the wrong kind having no reachable path to
 * the other kind.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FieldEditor } from './FieldEditor';
import type { FormSchema, FormField } from '../types/schema';

function groupField(type: 'checkbox_group' | 'radio'): FormField {
  return {
    id: 'reason_for_submission',
    name: 'Reason',
    type,
    section_id: 's1',
    pdf_field_name: '',
    read_only: false,
    options: [
      { value: 'a', label: 'A', pdf_field_name: 'ga[0]' },
      { value: 'b', label: 'B', pdf_field_name: 'gb[0]' },
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

describe('FieldEditor group-kind flip', () => {
  it('renders the "Group behaves as" selector for a checkbox_group and calls onChangeGroupKind on flip', () => {
    const onChangeGroupKind = vi.fn();
    const field = groupField('checkbox_group');
    render(
      <FieldEditor
        field={field}
        schema={schemaWith(field)}
        onUpdateField={vi.fn()}
        onChangeGroupKind={onChangeGroupKind}
      />,
    );
    const select = screen.getByLabelText('Group behaves as') as HTMLSelectElement;
    expect(select.value).toBe('checkbox_group');
    fireEvent.change(select, { target: { value: 'radio' } });
    expect(onChangeGroupKind).toHaveBeenCalledWith('reason_for_submission', 'radio');
  });

  it('renders the selector for a radio group too (the reverse flip)', () => {
    const onChangeGroupKind = vi.fn();
    const field = groupField('radio');
    render(
      <FieldEditor
        field={field}
        schema={schemaWith(field)}
        onUpdateField={vi.fn()}
        onChangeGroupKind={onChangeGroupKind}
      />,
    );
    const select = screen.getByLabelText('Group behaves as') as HTMLSelectElement;
    expect(select.value).toBe('radio');
    fireEvent.change(select, { target: { value: 'checkbox_group' } });
    expect(onChangeGroupKind).toHaveBeenCalledWith('reason_for_submission', 'checkbox_group');
  });

  it('base Field Type picker stays disabled for a group (no raw type-switch)', () => {
    const field = groupField('checkbox_group');
    render(
      <FieldEditor
        field={field}
        schema={schemaWith(field)}
        onUpdateField={vi.fn()}
        onChangeGroupKind={vi.fn()}
      />,
    );
    expect(screen.getByLabelText('Field Type')).toBeDisabled();
  });

  it('falls back to the static hint (no flip control) when onChangeGroupKind is absent', () => {
    const field = groupField('checkbox_group');
    render(<FieldEditor field={field} schema={schemaWith(field)} onUpdateField={vi.fn()} />);
    expect(screen.queryByLabelText('Group behaves as')).not.toBeInTheDocument();
    expect(screen.getByText(/Group type is set by Merge/i)).toBeInTheDocument();
  });

  it('falls back to the static hint for an editor-tier (non-author) contractor', () => {
    const field = groupField('checkbox_group');
    render(
      <FieldEditor
        field={field}
        schema={schemaWith(field)}
        onUpdateField={vi.fn()}
        onChangeGroupKind={vi.fn()}
        authorTier={false}
      />,
    );
    expect(screen.queryByLabelText('Group behaves as')).not.toBeInTheDocument();
  });

  it('disables the checkbox_group option for a shared-name radio (no valid checkbox_group form)', () => {
    // A shared-name radio: field-level pdf_field_name + option pdf_on_value, no
    // per-option pdf_field_name -> cannot become a valid checkbox_group.
    const field = {
      id: 'reason_for_submission', name: 'Reason', type: 'radio', section_id: 's1',
      pdf_field_name: 'form1[0].reason[0]', read_only: false,
      options: [
        { value: 'a', label: 'A', pdf_on_value: 'A' },
        { value: 'b', label: 'B', pdf_on_value: 'B' },
      ],
    } as unknown as FormField;
    render(
      <FieldEditor
        field={field}
        schema={schemaWith(field)}
        onUpdateField={vi.fn()}
        onChangeGroupKind={vi.fn()}
      />,
    );
    // The control still renders (it's a valid radio), but the checkbox_group
    // target is disabled with an explanation.
    const select = screen.getByLabelText('Group behaves as');
    expect(select).toBeInTheDocument();
    const cbOption = screen.getByRole('option', { name: /Checkbox group/i }) as HTMLOptionElement;
    expect(cbOption).toBeDisabled();
    expect(screen.getByText(/can only be a radio/i)).toBeInTheDocument();
  });

  it('shows the RETARGET hint (not the PDF-widget one) when a nested in/not_in dependent blocks the flip', () => {
    // A per-option-PDF radio (so PDF widgets are fine) with a dependent whose
    // show_if nests an `in` atom in a composite -> the checkbox_group flip is
    // refused for the in/not_in reason, and the hint must say so.
    const grp = {
      id: 'grp', name: 'Group', type: 'radio', section_id: 's1',
      pdf_field_name: '', read_only: false,
      options: [
        { value: 'a', label: 'A', pdf_field_name: 'ga[0]' },
        { value: 'b', label: 'B', pdf_field_name: 'gb[0]' },
      ],
    } as unknown as FormField;
    const dep = {
      id: 'dep', name: 'Dep', type: 'text', section_id: 's1',
      pdf_field_name: 'dep[0]', read_only: false,
      show_if: { all_of: [{ field: 'grp', operator: 'in', value: ['a', 'b'] }] },
    } as unknown as FormField;
    const schema = {
      source: 'pdf',
      form_metadata: { title: 'T', form_number: 'T', version: '1', language: 'en', total_widgets: 2, total_fields: 2 },
      parts: [],
      sections: [{ id: 's1', label: 'S1', order: 0, fields: ['grp', 'dep'] }],
      fields: [grp, dep],
    } as unknown as FormSchema;
    render(
      <FieldEditor field={grp} schema={schema} onUpdateField={vi.fn()} onChangeGroupKind={vi.fn()} />,
    );
    const cbOption = screen.getByRole('option', { name: /Checkbox group/i }) as HTMLOptionElement;
    expect(cbOption).toBeDisabled();
    // The retarget hint, NOT the PDF-widget hint.
    expect(screen.getByText(/in \/ not-in/i)).toBeInTheDocument();
    expect(screen.queryByText(/shares one PDF widget/i)).not.toBeInTheDocument();
  });

  it('does NOT render the flip control for a non-group field (plain checkbox)', () => {
    const field = {
      id: 'agree', name: 'Agree', type: 'checkbox', section_id: 's1',
      pdf_field_name: 'agree[0]', read_only: false,
    } as unknown as FormField;
    render(
      <FieldEditor
        field={field}
        schema={schemaWith(field)}
        onUpdateField={vi.fn()}
        onChangeGroupKind={vi.fn()}
      />,
    );
    expect(screen.queryByLabelText('Group behaves as')).not.toBeInTheDocument();
    // A non-group field's Field Type picker is editable.
    expect(screen.getByLabelText('Field Type')).not.toBeDisabled();
  });
});
