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

describe('FieldEditor option widget -- shared-name radio group (bd mrdj fresh-eyes / 0a4e)', () => {
  // A shared-name radio group: the FIELD carries pdf_field_name; each option
  // carries only pdf_on_value (no per-option pdf_field_name). Offering a
  // reassignable name select here would let an option acquire BOTH keys ->
  // dump-widget-multiclaim + wrong fill branch.
  const SHARED: FormField = {
    id: 'sex', name: 'Sex', spoken_name: 'sex', type: 'radio',
    section_id: 's1', pdf_field_name: 'form1[0].sex[0]',
    options: [
      { value: 'male', label: 'Male', pdf_on_value: 'M' },
      { value: 'female', label: 'Female', pdf_on_value: 'F' },
    ],
  } as unknown as FormField;

  it('shows the field widget + on-state READ-ONLY, not a reassign select', () => {
    const onLoad = vi.fn().mockResolvedValue([
      { name: 'form1[0].sex[0]', type: 'radio', on_value: 'X', shared_name: true, page: 0 },
    ]);
    render(
      <FieldEditor field={SHARED} schema={makeSchema([SHARED])}
        onUpdateField={vi.fn()} authorTier onLoadUnclaimedWidgets={onLoad} />,
    );
    // no reassign select for a shared-name kid (neither option's control)
    expect(screen.queryByLabelText('Option 1 PDF widget')).toBeNull();
    expect(screen.queryByLabelText('Option 2 PDF widget')).toBeNull();
    // the fixed field widget + this kid's on-state are shown read-only
    expect(screen.getByText(/on: M/)).toBeInTheDocument();
  });

  it('never lets a shared-name kid acquire a per-option pdf_field_name (no both-keys)', () => {
    // the widget SELECT (the only writer of option.pdf_field_name) is not
    // rendered for any shared-name kid -- the Review-status select is
    // unrelated, so assert specifically on the widget-select aria-labels
    render(
      <FieldEditor field={SHARED} schema={makeSchema([SHARED])}
        onUpdateField={vi.fn()} authorTier />,
    );
    expect(screen.queryByLabelText('Option 1 PDF widget')).toBeNull();
    expect(screen.queryByLabelText('Option 2 PDF widget')).toBeNull();
  });
});

describe('FieldEditor option widget -- Add Option offers the same select (bd mrdj exit criterion 2)', () => {
  it('a freshly added option renders the select in the empty state', () => {
    let current: FormField = { ...GROUP };
    const onUpdateField = vi.fn((f: FormField) => { current = f; });
    const { rerender } = render(
      <FieldEditor field={current} schema={makeSchema([current])}
        onUpdateField={onUpdateField} authorTier />,
    );
    fireEvent.click(screen.getByText('+ Add Option'));
    // re-render with the field the update produced
    rerender(
      <FieldEditor field={current} schema={makeSchema([current])}
        onUpdateField={onUpdateField} authorTier />,
    );
    const sel = screen.getByLabelText('Option 3 PDF widget') as HTMLSelectElement;
    expect(sel.tagName).toBe('SELECT');
    expect(sel.value).toBe('');
    expect(within(sel).getByText('(no widget assigned)')).toBeInTheDocument();
  });
});

describe('FieldEditor option widget -- mixed-shape + shared-name filtering (bd mrdj fresh-eyes round 2)', () => {
  it('a MIXED radio field renders each option by its OWN shape (per-option, not per-field)', () => {
    // field carries a field-level pdf_field_name AND has one distinct-name
    // option (its own pdf_field_name) plus one shared-name kid (pdf_on_value
    // only). Each must render by its own shape, not a field-level switch.
    const mixed: FormField = {
      id: 'mix', name: 'Mix', spoken_name: 'mix', type: 'radio',
      section_id: 's1', pdf_field_name: 'form1[0].shared[0]',
      options: [
        { value: 'own', label: 'Own', pdf_field_name: 'form1[0].distinct[0]' },
        { value: 'kid', label: 'Kid', pdf_on_value: 'K' },
      ],
    } as unknown as FormField;
    render(
      <FieldEditor field={mixed} schema={makeSchema([mixed])}
        onUpdateField={vi.fn()} authorTier />,
    );
    // option 1 (distinct-name) gets the reassign select showing ITS widget
    const sel = screen.getByLabelText('Option 1 PDF widget') as HTMLSelectElement;
    expect(sel.tagName).toBe('SELECT');
    expect(sel.value).toBe('form1[0].distinct[0]');
    // option 2 (shared-name kid) gets read-only, no select, its on-state shown
    expect(screen.queryByLabelText('Option 2 PDF widget')).toBeNull();
    expect(screen.getByText(/on: K/)).toBeInTheDocument();
  });

  it('the reassign dropdown EXCLUDES shared-name widgets from the loader', async () => {
    const onLoad = vi.fn().mockResolvedValue([
      { name: 'form1[0].distinct[9]', type: 'radio', on_value: 'A', shared_name: false, page: 0 },
      { name: 'form1[0].shared[0]', type: 'radio', on_value: 'B', shared_name: true, page: 0 },
    ]);
    render(
      <FieldEditor field={GROUP} schema={makeSchema([GROUP])}
        onUpdateField={vi.fn()} authorTier onLoadUnclaimedWidgets={onLoad} />,
    );
    const sel = screen.getByLabelText('Option 1 PDF widget');
    fireEvent.focus(sel);
    await waitFor(() => expect(onLoad).toHaveBeenCalled());
    await waitFor(() => {
      const opts = within(sel).getAllByRole('option').map(o => (o as HTMLOptionElement).value);
      expect(opts).toContain('form1[0].distinct[9]');    // distinct-name: offered
      expect(opts).not.toContain('form1[0].shared[0]');  // shared-name: excluded
    });
  });
});
