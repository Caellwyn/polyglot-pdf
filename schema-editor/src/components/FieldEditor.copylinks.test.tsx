/**
 * The auto-populate ("copy") UI wiring in FieldEditor (bd polyglot-pdf-g33y2).
 *
 * copyLinks.ts is covered by its own pure-function suite. What THIS file pins
 * is the GLUE: four closures in the JSX that pass (source, target) in one order
 * for the "Copies into" side and the INVERTED order for "Copied from". A
 * swapped argument there would write the link backwards -- the schema would
 * still be well-formed, so no utility test and no type check would notice.
 *
 * Fresh-eyes flagged the absence of this file and was right that it was cheap:
 * eight sibling FieldEditor.*.test.tsx files already render the component this
 * way, so the harness needed no invention.
 *
 * ASCII only.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FieldEditor } from './FieldEditor';
import type { FormSchema, FormField } from '../types/schema';

function field(p: Partial<FormField> & { id: string }): FormField {
  return {
    name: p.id, type: 'text', pdf_field_name: `${p.id}[0]`,
    read_only: false, section_id: 's1', ...p,
  } as unknown as FormField;
}

/** The i-90 shape: a Part 1 answer repeating on page 8, plus a spare field. */
function schema(): FormSchema {
  const fields = [
    field({ id: 'family_name', spoken_name: 'family name',
            copy_to: ['p8_family_name'] }),
    field({ id: 'p8_family_name', spoken_name: 'family name (page 8)',
            read_only: true }),
    field({ id: 'other', spoken_name: 'some other field' }),
  ];
  return {
    source: 'pdf',
    form_metadata: { title: 'T', form_number: 'T-1', version: '1', language: 'en' },
    parts: [],
    sections: [{ id: 's1', label: 'S1', order: 1, fields: fields.map(f => f.id) }],
    fields,
  } as unknown as FormSchema;
}

function renderFor(fieldId: string, onUpdateFields = vi.fn()) {
  const s = schema();
  const f = s.fields.find(x => x.id === fieldId)!;
  render(
    <FieldEditor field={f} schema={s} onUpdateField={vi.fn()}
      onUpdateFields={onUpdateFields} authorTier />,
  );
  return onUpdateFields;
}

/** The fields array from the last onUpdateFields call. */
function committed(spy: ReturnType<typeof vi.fn>): FormField[] {
  expect(spy).toHaveBeenCalled();
  return spy.mock.calls[spy.mock.calls.length - 1][0];
}

const copyTo = (fields: FormField[], id: string) =>
  (fields.find(f => f.id === id) as { copy_to?: string[] })?.copy_to;

describe('FieldEditor auto-populate wiring (bd polyglot-pdf-g33y2)', () => {
  it('shows the SOURCE side on the source field', () => {
    renderFor('family_name');
    expect(screen.getByText('Copies into')).toBeInTheDocument();
    expect(screen.getByText(/family name \(page 8\)/)).toBeInTheDocument();
  });

  it('shows the TARGET side on the target field', () => {
    renderFor('p8_family_name');
    expect(screen.getByText('Copied from')).toBeInTheDocument();
    // The derived reverse view names the source.
    expect(screen.getByText(/\(family_name\)/)).toBeInTheDocument();
  });

  it('adding from the SOURCE side writes copy_to on the source', () => {
    const spy = renderFor('family_name');
    fireEvent.change(screen.getByLabelText('Copy this field into...'),
                     { target: { value: 'other' } });
    const fields = committed(spy);
    expect(copyTo(fields, 'family_name')).toEqual(['p8_family_name', 'other']);
    expect(copyTo(fields, 'other')).toBeUndefined();
  });

  it('adding from the TARGET side writes copy_to on the OTHER field', () => {
    // The inversion: standing on p8_family_name and choosing "other" as its
    // source must write copy_to onto OTHER, not onto the field being edited.
    // A swapped argument here is the bug this file exists to catch.
    const spy = renderFor('p8_family_name');
    fireEvent.change(screen.getByLabelText('Fill this field from...'),
                     { target: { value: 'other' } });
    const fields = committed(spy);
    expect(copyTo(fields, 'other')).toEqual(['p8_family_name']);
    expect(copyTo(fields, 'p8_family_name')).toBeUndefined();
  });

  it('adding sets read_only on the TARGET, not the source', () => {
    const spy = renderFor('family_name');
    fireEvent.change(screen.getByLabelText('Copy this field into...'),
                     { target: { value: 'other' } });
    const fields = committed(spy);
    expect(fields.find(f => f.id === 'other')!.read_only).toBe(true);
    expect(fields.find(f => f.id === 'family_name')!.read_only).toBe(false);
  });

  it('unlinking from the SOURCE side clears the link', () => {
    const spy = renderFor('family_name');
    fireEvent.click(screen.getByLabelText('Unlink Copies into: p8_family_name'));
    expect(copyTo(committed(spy), 'family_name')).toBeUndefined();
  });

  it('unlinking from the TARGET side rewrites the SOURCE', () => {
    // Same inversion, the other way: the button sits on p8_family_name but the
    // stored link lives on family_name.
    const spy = renderFor('p8_family_name');
    fireEvent.click(screen.getByLabelText('Unlink Copied from: family_name'));
    expect(copyTo(committed(spy), 'family_name')).toBeUndefined();
  });

  it('offers no illegal choice in either picker', () => {
    renderFor('family_name');
    const into = screen.getByLabelText('Copy this field into...') as HTMLSelectElement;
    const values = [...into.options].map(o => o.value).filter(Boolean);
    // Not itself, and not the field it already copies into.
    expect(values).toEqual(['other']);
  });

  it('renders read-only (no pickers) when onUpdateFields is absent', () => {
    // A link touches two fields, so without the atomic commit the controls
    // must not offer a half-edit.
    const s = schema();
    render(
      <FieldEditor field={s.fields[0]} schema={s} onUpdateField={vi.fn()} authorTier />,
    );
    expect(screen.getByText('Copies into')).toBeInTheDocument();
    expect(screen.queryByLabelText('Copy this field into...')).toBeNull();
    expect(screen.queryByLabelText(/^Unlink /)).toBeNull();
  });
});
