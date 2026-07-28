/**
 * FieldEditor per-option backing-widget selector (bd polyglot-pdf-mrdj).
 * The option's pdf_field_name is a DROPDOWN of real widgets, never a free-text
 * box: an editor may reassign an option to a different real widget but can
 * never invent a pdf_field_name (a typo silently breaks that option's
 * round-trip fill). Choices = current + sibling-option widgets + (hosted mode)
 * the kit's unclaimed widgets.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
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
  options: [
    { value: 'a', label: 'A', pdf_field_name: 'form1[0].r[0]' },
    { value: 'b', label: 'B', pdf_field_name: 'form1[0].r[1]' },
  ],
} as unknown as FormField;

describe('FieldEditor option backing-widget selector (bd mrdj)', () => {
  it('renders the widget ref as a SELECT, never a free-text input', () => {
    render(
      <FieldEditor field={GROUP} schema={makeSchema([GROUP])}
        onUpdateField={vi.fn()} authorTier />,
    );
    const sel = screen.getByLabelText('Option 1 PDF widget');
    expect(sel.tagName).toBe('SELECT');
    // no free-text widget input exists anywhere
    expect(sel).not.toHaveAttribute('type', 'text');
  });

  it('offers the current value plus sibling-option widgets as choices (local mode, no loader)', () => {
    render(
      <FieldEditor field={GROUP} schema={makeSchema([GROUP])}
        onUpdateField={vi.fn()} authorTier />,
    );
    const sel = screen.getByLabelText('Option 1 PDF widget') as HTMLSelectElement;
    const opts = within(sel).getAllByRole('option').map(o => (o as HTMLOptionElement).value);
    // both in-group widgets are selectable; current is selected
    expect(opts).toContain('form1[0].r[0]');
    expect(opts).toContain('form1[0].r[1]');
    expect(sel.value).toBe('form1[0].r[0]');
  });

  it('reassigning the dropdown updates ONLY that option pdf_field_name to the chosen REAL widget', () => {
    const onUpdateField = vi.fn();
    render(
      <FieldEditor field={GROUP} schema={makeSchema([GROUP])}
        onUpdateField={onUpdateField} authorTier />,
    );
    const sel = screen.getByLabelText('Option 1 PDF widget');
    fireEvent.change(sel, { target: { value: 'form1[0].r[1]' } });
    const updated = onUpdateField.mock.calls[0][0] as FormField;
    expect(updated.options![0].pdf_field_name).toBe('form1[0].r[1]');
    expect(updated.options![1].pdf_field_name).toBe('form1[0].r[1]'); // untouched sibling
  });

  it('includes unclaimed widgets from the loader (hosted author mode) on focus', async () => {
    const UNCLAIMED: UnclaimedWidget[] = [
      { name: 'form1[0].r[9]', type: 'checkbox', on_value: '9', tooltip: 'X', page: 0 },
    ];
    const onLoad = vi.fn().mockResolvedValue(UNCLAIMED);
    render(
      <FieldEditor field={GROUP} schema={makeSchema([GROUP])}
        onUpdateField={vi.fn()} authorTier onLoadUnclaimedWidgets={onLoad} />,
    );
    const sel = screen.getByLabelText('Option 1 PDF widget');
    fireEvent.focus(sel);
    await waitFor(() => expect(onLoad).toHaveBeenCalled());
    await waitFor(() => {
      const opts = within(sel).getAllByRole('option').map(o => (o as HTMLOptionElement).value);
      expect(opts).toContain('form1[0].r[9]');
    });
  });
});
