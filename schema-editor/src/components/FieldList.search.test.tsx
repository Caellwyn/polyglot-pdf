/**
 * Component tests for the field-list search/filter (bd polyglot-pdf-j036).
 * Typing part of a field's id / spoken_name / pdf_field_name filters the
 * grouped list to matches; clearing the box restores the full list; selecting
 * a match calls onSelectField with that field's id.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { FieldList } from './FieldList';
import type { FormSchema, FormField } from '../types/schema';

function field(partial: Partial<FormField> & { id: string }): FormField {
  return {
    name: partial.id,
    type: 'text',
    pdf_field_name: partial.id,
    read_only: false,
    ...partial,
  } as FormField;
}

function makeSchema(): FormSchema {
  const fields: FormField[] = [
    field({ id: 'first_name', section_id: 's1', spoken_name: 'First name', pdf_field_name: 'P1[0].FirstName' }),
    field({ id: 'last_name', section_id: 's1', spoken_name: 'Last name', pdf_field_name: 'P1[0].LastName' }),
    field({ id: 'home_phone', section_id: 's2', spoken_name: 'Home telephone', pdf_field_name: 'P2[0].Phone' }),
  ];
  return {
    source: 'pdf',
    form_metadata: {
      title: 'Test', form_number: 'T-1', total_widgets: 3, total_fields: 3,
      version: '1', language: 'en',
    },
    parts: [],
    sections: [
      { id: 's1', label: 'Names', order: 1, fields: ['first_name', 'last_name'] },
      { id: 's2', label: 'Contact', order: 2, fields: ['home_phone'] },
    ],
    fields,
  };
}

describe('FieldList search/filter', () => {
  it('filters the list by id substring and keeps section grouping', () => {
    render(
      <FieldList schema={makeSchema()} selectedFieldId={null} onSelectField={vi.fn()} />
    );

    fireEvent.change(screen.getByLabelText('Search fields'), { target: { value: 'name' } });

    // Both name fields match; the phone field does not.
    expect(screen.getByText('first_name')).toBeInTheDocument();
    expect(screen.getByText('last_name')).toBeInTheDocument();
    expect(screen.queryByText('home_phone')).not.toBeInTheDocument();

    // Section grouping is preserved: the matched section header is still shown,
    // the unmatched one is hidden.
    expect(screen.getByText('Names')).toBeInTheDocument();
    expect(screen.queryByText('Contact')).not.toBeInTheDocument();
  });

  it('matches on spoken_name', () => {
    render(
      <FieldList schema={makeSchema()} selectedFieldId={null} onSelectField={vi.fn()} />
    );

    fireEvent.change(screen.getByLabelText('Search fields'), { target: { value: 'telephone' } });

    expect(screen.getByText('home_phone')).toBeInTheDocument();
    expect(screen.queryByText('first_name')).not.toBeInTheDocument();
  });

  it('matches on pdf_field_name', () => {
    render(
      <FieldList schema={makeSchema()} selectedFieldId={null} onSelectField={vi.fn()} />
    );

    fireEvent.change(screen.getByLabelText('Search fields'), { target: { value: 'lastname' } });

    expect(screen.getByText('last_name')).toBeInTheDocument();
    expect(screen.queryByText('first_name')).not.toBeInTheDocument();
  });

  it('shows a no-results message when nothing matches', () => {
    render(
      <FieldList schema={makeSchema()} selectedFieldId={null} onSelectField={vi.fn()} />
    );

    fireEvent.change(screen.getByLabelText('Search fields'), { target: { value: 'zzz_nope' } });

    expect(screen.getByText(/No fields match/)).toBeInTheDocument();
  });

  it('clearing the search restores the full grouped list', () => {
    render(
      <FieldList schema={makeSchema()} selectedFieldId={null} onSelectField={vi.fn()} />
    );

    const input = screen.getByLabelText('Search fields');
    fireEvent.change(input, { target: { value: 'name' } });
    expect(screen.queryByText('home_phone')).not.toBeInTheDocument();

    // Clear via the clear button.
    fireEvent.click(screen.getByLabelText('Clear search'));

    expect(screen.getByText('first_name')).toBeInTheDocument();
    expect(screen.getByText('last_name')).toBeInTheDocument();
    expect(screen.getByText('home_phone')).toBeInTheDocument();
    expect(screen.getByText('Names')).toBeInTheDocument();
    expect(screen.getByText('Contact')).toBeInTheDocument();
  });

  it('clicking a section header while filtering does not collapse it on clear', () => {
    // Regression (fresh-eyes finding, bd j036): the section toggle must be inert
    // while filtering, else a ghost click silently collapses a section once the
    // search is cleared -- breaking "clearing restores the full grouped list".
    render(
      <FieldList schema={makeSchema()} selectedFieldId={null} onSelectField={vi.fn()} />
    );

    const input = screen.getByLabelText('Search fields');
    fireEvent.change(input, { target: { value: 'name' } });

    // Click the "Names" section header while filtering (should be a no-op).
    fireEvent.click(screen.getByText('Names'));

    // Clear the filter; the section must still be expanded (its fields visible).
    fireEvent.click(screen.getByLabelText('Clear search'));

    expect(screen.getByText('first_name')).toBeInTheDocument();
    expect(screen.getByText('last_name')).toBeInTheDocument();
  });

  it('selecting a filtered match calls onSelectField with its id', () => {
    const onSelectField = vi.fn();
    render(
      <FieldList schema={makeSchema()} selectedFieldId={null} onSelectField={onSelectField} />
    );

    fireEvent.change(screen.getByLabelText('Search fields'), { target: { value: 'home_phone' } });
    fireEvent.click(within(screen.getByText('home_phone').closest('button')!).getByText('home_phone'));

    expect(onSelectField).toHaveBeenCalledWith('home_phone');
  });
});
