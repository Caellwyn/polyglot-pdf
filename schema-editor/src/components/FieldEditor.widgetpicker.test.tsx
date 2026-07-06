/**
 * FieldEditor "Add from PDF widgets" picker (bd polyglot-pdf-nivy, P5.3c).
 * An author adds a missed checkbox to a group from the kit's unclaimed PDF
 * widgets; the appended option carries a minted slug value, the widget name on
 * pdf_field_name, and the on-state on pdf_on_value.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { FieldEditor } from './FieldEditor';
import type { FormSchema, FormField } from '../types/schema';
import type { UnclaimedWidget } from '../utils/remoteKitStore';

function makeSchema(fields: FormField[]): FormSchema {
  return {
    source: 'pdf',
    form_metadata: { title: 'T', form_number: 'T-1', version: '1', language: 'en' },
    parts: [],
    sections: [{ id: 's1', label: 'S1', order: 1, fields: fields.map(f => f.id) }],
    fields,
  } as unknown as FormSchema;
}

const GROUP: FormField = {
  id: 'reasons', name: 'Reasons', spoken_name: 'reasons', type: 'checkbox_group',
  section_id: 's1',
  options: [{ value: 'employment', label: 'Employment',
              pdf_field_name: 'form1[0].reason[0]' }],
} as unknown as FormField;

const UNCLAIMED: UnclaimedWidget[] = [
  { name: 'form1[0].reason[1]', type: 'checkbox', on_value: '2',
    tooltip: 'Family', page: 0 },
];

describe('FieldEditor Add from PDF widgets picker', () => {
  it('adds a missed checkbox from the picker with the right mapping', async () => {
    const onUpdateField = vi.fn();
    const onLoad = vi.fn().mockResolvedValue(UNCLAIMED);
    render(
      <FieldEditor
        field={GROUP}
        schema={makeSchema([GROUP])}
        onUpdateField={onUpdateField}
        authorTier
        onLoadUnclaimedWidgets={onLoad}
      />,
    );
    // Open the picker -> it fetches, then lists the unclaimed widget.
    fireEvent.click(screen.getByText('+ Add from PDF widgets'));
    await waitFor(() => expect(onLoad).toHaveBeenCalled());
    const choice = await screen.findByText('Family');
    fireEvent.click(choice);

    expect(onUpdateField).toHaveBeenCalledTimes(1);
    const updated = onUpdateField.mock.calls[0][0] as FormField;
    // The new option is appended after the existing one.
    expect(updated.options).toHaveLength(2);
    const added = updated.options![1];
    expect(added.label).toBe('Family');
    expect(added.value).toBe('family');            // slug minted from the label
    expect(added.pdf_field_name).toBe('form1[0].reason[1]');
    expect(added.pdf_on_value).toBe('2');
  });

  it('mints a UNIQUE slug against existing option VALUES, not labels (fresh-eyes)', async () => {
    // The existing option's VALUE is 'family' but its LABEL is different
    // ('Family member') -- minting against labels would miss this collision and
    // produce a duplicate 'family' value (an option-value-duplicate lint ERROR).
    // The picker must dedupe against the VALUE.
    const group: FormField = {
      ...GROUP,
      options: [{ value: 'family', label: 'Family member',
                  pdf_field_name: 'form1[0].r[0]' }],
    } as unknown as FormField;
    const onUpdateField = vi.fn();
    render(
      <FieldEditor
        field={group}
        schema={makeSchema([group])}
        onUpdateField={onUpdateField}
        authorTier
        onLoadUnclaimedWidgets={vi.fn().mockResolvedValue(UNCLAIMED)}
      />,
    );
    fireEvent.click(screen.getByText('+ Add from PDF widgets'));
    fireEvent.click(await screen.findByText('Family'));  // widget tooltip 'Family' -> slug 'family'
    const added = (onUpdateField.mock.calls[0][0] as FormField).options![1];
    // 'family' is taken by the existing option's VALUE -> the new one bumps.
    expect(added.value).toBe('family_2');
  });

  it('shared-name radio kid: option gets pdf_on_value, FIELD gets pdf_field_name (Opus fallback)', async () => {
    // A true shared-name radio group kid (shared_name=true): the picker must put
    // the widget name on the FIELD and only pdf_on_value on the option -- putting
    // the shared name on option.pdf_field_name would multiclaim (lint ERROR).
    const radio: FormField = {
      id: 'sex', name: 'Sex', spoken_name: 'sex', type: 'radio', section_id: 's1',
      options: [{ value: 'male', label: 'Male', pdf_on_value: 'M' }],
      // note: no field-level pdf_field_name yet -- the pick must set it.
    } as unknown as FormField;
    const shared: UnclaimedWidget[] = [
      { name: 'form1[0].sex[0]', type: 'radio', on_value: 'F', tooltip: 'Female',
        page: 0, shared_name: true },
    ];
    const onUpdateField = vi.fn();
    render(
      <FieldEditor
        field={radio}
        schema={makeSchema([radio])}
        onUpdateField={onUpdateField}
        authorTier
        onLoadUnclaimedWidgets={vi.fn().mockResolvedValue(shared)}
      />,
    );
    fireEvent.click(screen.getByText('+ Add from PDF widgets'));
    fireEvent.click(await screen.findByText('Female'));
    const updated = onUpdateField.mock.calls[0][0] as FormField;
    // The field now carries the shared widget name...
    expect(updated.pdf_field_name).toBe('form1[0].sex[0]');
    const added = updated.options![1];
    // ...and the added option carries ONLY pdf_on_value, NOT pdf_field_name.
    expect(added.pdf_on_value).toBe('F');
    expect(added.pdf_field_name).toBeUndefined();
    expect(added.value).toBe('female');
  });

  it('shows a friendly note when there are no unclaimed widgets', async () => {
    render(
      <FieldEditor
        field={GROUP}
        schema={makeSchema([GROUP])}
        onUpdateField={vi.fn()}
        authorTier
        onLoadUnclaimedWidgets={vi.fn().mockResolvedValue([])}
      />,
    );
    fireEvent.click(screen.getByText('+ Add from PDF widgets'));
    await waitFor(() =>
      expect(screen.getByText(/every button is already mapped/)).toBeInTheDocument());
  });

  it('is not offered without the onLoadUnclaimedWidgets callback (local/editor)', () => {
    render(
      <FieldEditor field={GROUP} schema={makeSchema([GROUP])} onUpdateField={vi.fn()} authorTier />,
    );
    expect(screen.queryByText('+ Add from PDF widgets')).toBeNull();
  });

  it('surfaces a load error inline', async () => {
    render(
      <FieldEditor
        field={GROUP}
        schema={makeSchema([GROUP])}
        onUpdateField={vi.fn()}
        authorTier
        onLoadUnclaimedWidgets={vi.fn().mockRejectedValue(new Error('backend down'))}
      />,
    );
    fireEvent.click(screen.getByText('+ Add from PDF widgets'));
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('backend down'));
  });
});
