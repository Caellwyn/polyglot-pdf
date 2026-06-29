// Component tests for the interactive PreviewPane (bd polyglot-pdf-s4dp.4).
// Covers the epic's crit 2 VERIFY clauses: clicking two radio options -> only one
// stays selected; toggling a controller field -> a show_if-gated field hides/shows;
// and checkboxes multi-select. Also asserts crit 1: no import from the voice app's
// connection/state layer (checked statically below).

import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import PreviewPane from './PreviewPane';
import type { FormSchema, FormField } from '../types/schema';

function field(p: Partial<FormField> & { id: string }): FormField {
  return { name: p.id, type: 'text', pdf_field_name: `${p.id}[0]`, read_only: false, required: false, ...p };
}

// A W-7-style "check one box" group consolidated into one radio, plus a checkbox
// group and a show_if-gated dependent.
function buildSchema(extra: FormField[] = [], sectionFields: string[] = []): FormSchema {
  const fields: FormField[] = [
    field({ id: 'reason', type: 'radio', label: 'Reason', options: [
      { value: 'a', label: 'Reason A' },
      { value: 'b', label: 'Reason B' },
      { value: 'c', label: 'Reason C' },
    ] }),
    field({ id: 'races', type: 'checkbox', label: 'Races', options: [
      { value: 'white', label: 'White' },
      { value: 'asian', label: 'Asian' },
    ] }),
    ...extra,
  ];
  return {
    source: 'pdf',
    form_metadata: { title: 'T', form_number: 'T', total_widgets: fields.length, total_fields: fields.length, version: '1', language: 'en' },
    parts: [],
    sections: [{ id: 's', label: 'Section', order: 0, fields: ['reason', 'races', ...sectionFields] }],
    fields,
  };
}

describe('PreviewPane: radio mutual exclusivity (crit 2)', () => {
  it('selecting a second radio option deselects the first', () => {
    render(<PreviewPane schema={buildSchema()} />);
    const a = screen.getByLabelText('Reason A') as HTMLInputElement;
    const b = screen.getByLabelText('Reason B') as HTMLInputElement;

    fireEvent.click(a);
    expect(a.checked).toBe(true);
    expect(b.checked).toBe(false);

    fireEvent.click(b);
    expect(b.checked).toBe(true);
    expect(a.checked).toBe(false); // only one stays selected
  });
});

describe('PreviewPane: checkbox multi-select (crit 2)', () => {
  it('checks multiple options at once and toggles each independently', () => {
    render(<PreviewPane schema={buildSchema()} />);
    const white = screen.getByLabelText('White') as HTMLInputElement;
    const asian = screen.getByLabelText('Asian') as HTMLInputElement;

    fireEvent.click(white);
    fireEvent.click(asian);
    expect(white.checked).toBe(true);
    expect(asian.checked).toBe(true); // both selected -- multi-select

    fireEvent.click(white);
    expect(white.checked).toBe(false);
    expect(asian.checked).toBe(true); // independent toggle
  });
});

describe('PreviewPane: show_if hide/show as controller changes (crit 2)', () => {
  it('reveals a show_if-gated field only when the controlling radio matches', () => {
    const detail = field({
      id: 'detail', type: 'text', label: 'Detail',
      show_if: { field: 'reason', operator: 'equals', value: 'b' },
    });
    render(<PreviewPane schema={buildSchema([detail], ['detail'])} />);

    // hidden initially (reason unset)
    expect(screen.queryByLabelText('Detail')).toBeNull();

    // selecting Reason A (not 'b') keeps it hidden
    fireEvent.click(screen.getByLabelText('Reason A'));
    expect(screen.queryByLabelText('Detail')).toBeNull();

    // selecting Reason B reveals it
    fireEvent.click(screen.getByLabelText('Reason B'));
    expect(screen.queryByLabelText('Detail')).not.toBeNull();

    // switching away hides it again
    fireEvent.click(screen.getByLabelText('Reason C'));
    expect(screen.queryByLabelText('Detail')).toBeNull();
  });

  it('reveals a checkbox-gated field by MEMBERSHIP (any-selected semantics)', () => {
    const gated = field({
      id: 'gated', type: 'text', label: 'Asian detail',
      show_if: { field: 'races', operator: 'equals', value: 'asian' },
    });
    render(<PreviewPane schema={buildSchema([gated], ['gated'])} />);

    expect(screen.queryByLabelText('Asian detail')).toBeNull();
    fireEvent.click(screen.getByLabelText('Asian'));
    expect(screen.queryByLabelText('Asian detail')).not.toBeNull();
    // unchecking removes it
    fireEvent.click(screen.getByLabelText('Asian'));
    expect(screen.queryByLabelText('Asian detail')).toBeNull();
  });
});

describe('PreviewPane: read-only + reset', () => {
  it('disables inputs for a read_only field', () => {
    const ro = field({ id: 'ro', type: 'text', label: 'Locked', read_only: true });
    render(<PreviewPane schema={buildSchema([ro], ['ro'])} />);
    expect((screen.getByLabelText(/Locked/) as HTMLInputElement).disabled).toBe(true);
  });

  it('Reset values clears all selections', () => {
    render(<PreviewPane schema={buildSchema()} />);
    const a = screen.getByLabelText('Reason A') as HTMLInputElement;
    fireEvent.click(a);
    expect(a.checked).toBe(true);
    fireEvent.click(screen.getByText('Reset values'));
    expect((screen.getByLabelText('Reason A') as HTMLInputElement).checked).toBe(false);
  });
});

describe('PreviewPane: lone checkbox (single boolean)', () => {
  it('renders the field label ONCE (no duplicate from the inner control)', () => {
    const consent = field({ id: 'consent', type: 'checkbox', label: 'I agree' });
    render(<PreviewPane schema={buildSchema([consent], ['consent'])} />);
    // the field caption appears once; the inner checkbox affordance is "Yes", not
    // a second copy of "I agree" (fresh-eyes finding 3).
    expect(screen.getAllByText('I agree')).toHaveLength(1);
    const box = screen.getByLabelText('I agree') as HTMLInputElement;
    expect(box.type).toBe('checkbox');
    fireEvent.click(box);
    expect(box.checked).toBe(true);
  });
});

describe('PreviewPane: section grouping', () => {
  it('renders fields under their section label', () => {
    render(<PreviewPane schema={buildSchema()} />);
    const section = screen.getByText('Section').closest('div')!;
    expect(within(section).getByText('Reason')).toBeTruthy();
  });
});
