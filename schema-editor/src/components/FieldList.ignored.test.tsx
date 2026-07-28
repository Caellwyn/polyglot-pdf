/**
 * The grey Ignored bucket in the field list (bd polyglot-pdf-mzkw).
 *
 * Quarantined fields stay VISIBLE (ignoring is reversible -- an invisible
 * escape hatch would be a delete) but must sit outside every other list
 * computation: no review-jump stop, no counting, and no overlay.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FieldList } from './FieldList';
import { ignoreField } from '../utils/ignoreField';
import type { FormSchema, FormField } from '../types/schema';

function field(id: string, extra: Partial<FormField> = {}): FormField {
  return {
    id, name: id, type: 'text', pdf_field_name: `pdf.${id}`,
    spoken_name: `spoken ${id}`, section_id: 'sec-1', read_only: false,
    help: { instructions: 'All set.' },
    pdf_position: { page: 1, x: 10, y: 10, width: 50, height: 12 },
    _review: { status: 'reviewed_correct' },
    ...extra,
  } as unknown as FormField;
}

function schemaWith(fields: FormField[]): FormSchema {
  return {
    source: 'pdf',
    form_metadata: {
      title: 'T', form_number: 'T', total_widgets: fields.length,
      total_fields: fields.length, version: '1', language: 'en',
    },
    parts: [],
    sections: [{ id: 'sec-1', label: 'Section 1', order: 1, fields: fields.map(f => f.id) }],
    fields,
  } as unknown as FormSchema;
}

function renderList(schema: FormSchema, opts: {
  onSelectField?: (id: string) => void;
  onRestoreField?: (id: string) => void;
} = {}) {
  render(
    <FieldList
      schema={schema}
      selectedFieldId={null}
      onSelectField={opts.onSelectField ?? vi.fn()}
      onRestoreField={opts.onRestoreField}
      pageCount={3}
    />,
  );
}

describe('FieldList Ignored bucket (bd mzkw)', () => {
  it('renders no bucket when nothing is ignored', () => {
    renderList(schemaWith([field('a')]));
    expect(screen.queryByText(/Ignored -- not on this form/)).toBeNull();
  });

  it('lists a quarantined field in its own group with a count', () => {
    const s = ignoreField(schemaWith([field('a'), field('b')]), 'b');
    renderList(s);
    const header = screen.getByText(/Ignored -- not on this form/);
    expect(header).toBeInTheDocument();
    // The count lives in the Ignored header's own row (the section header
    // carries its own count, so scope the lookup rather than matching "(1)"
    // anywhere on screen).
    expect(header.closest('button')).toHaveTextContent('(1)');
    // ...and the field is gone from the ordinary section listing.
    expect(screen.queryByText('b')).toBeNull();
  });

  it('shows the field once expanded, with an Un-ignore button', () => {
    const s = ignoreField(schemaWith([field('a'), field('b')]), 'b');
    const onRestoreField = vi.fn();
    renderList(s, { onRestoreField });
    fireEvent.click(screen.getByText(/Ignored -- not on this form/));
    expect(screen.getByTestId('ignored-row-b')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Un-ignore'));
    expect(onRestoreField).toHaveBeenCalledWith('b');
  });

  it('renders the bucket read-only when no restore handler is wired', () => {
    const s = ignoreField(schemaWith([field('a'), field('b')]), 'b');
    renderList(s);
    fireEvent.click(screen.getByText(/Ignored -- not on this form/));
    expect(screen.queryByText('Un-ignore')).toBeNull();
  });

  it('surfaces the review note as the ignored row tooltip', () => {
    const noted = field('ghost', {
      _review: { status: 'needs_followup', note: 'phantom field' },
    } as Partial<FormField>);
    const s = ignoreField(schemaWith([field('a'), noted]), 'ghost');
    renderList(s);
    fireEvent.click(screen.getByText(/Ignored -- not on this form/));
    expect(screen.getByTestId('field-status-ghost').getAttribute('title'))
      .toContain('phantom field');
  });

  it('an ignored field is NOT a review-jump target', () => {
    // 'a' is signed off and 'b' is quarantined, so there is no work left --
    // the button must read as done rather than cycling to a parked field.
    const s = ignoreField(schemaWith([field('a'), field('b')]), 'b');
    renderList(s);
    expect(screen.getByText('Next to review').closest('button')).toBeDisabled();
  });

  it('does not count toward the ordinary section field count', () => {
    const s = ignoreField(schemaWith([field('a'), field('b'), field('c')]), 'b');
    renderList(s);
    // Section header shows its remaining resolvable fields, not the parked one.
    expect(screen.getByText('(2)')).toBeInTheDocument();
  });
});
