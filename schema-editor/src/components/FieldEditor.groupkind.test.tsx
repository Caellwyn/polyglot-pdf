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
    required: false,
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

  it('does NOT render the flip control for a non-group field (plain checkbox)', () => {
    const field = {
      id: 'agree', name: 'Agree', type: 'checkbox', section_id: 's1',
      pdf_field_name: 'agree[0]', read_only: false, required: false,
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
