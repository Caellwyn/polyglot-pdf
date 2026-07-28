/**
 * The Ignored option in the review dropdown (bd polyglot-pdf-mzkw).
 *
 * Ignoring is a deliberate, confirmed, reversible act -- and it is REFUSED
 * (visibly, with a reason) while the field is required or something depends on
 * it. Unlike the other three review statuses it does not ride onUpdateField:
 * quarantining relocates the field out of fields[], so it routes to its own
 * callback.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FieldEditor } from './FieldEditor';
import type { FormField, FormSchema } from '../types/schema';

function field(extra: Partial<FormField> = {}): FormField {
  return {
    id: 'f1', name: 'F1', type: 'text', pdf_field_name: 'pdf.f1',
    spoken_name: 'field one', section_id: 's1', read_only: false,
    help: { instructions: 'All set.' },
    pdf_position: { page: 1, x: 10, y: 10, width: 50, height: 12 },
    ...extra,
  } as unknown as FormField;
}

function schemaWith(f: FormField): FormSchema {
  return {
    source: 'pdf',
    form_metadata: { title: 'T', form_number: 'T', total_widgets: 1, total_fields: 1, version: '1', language: 'en' },
    parts: [],
    sections: [{ id: 's1', label: 'S1', order: 0, fields: [f.id] }],
    fields: [f],
  } as unknown as FormSchema;
}

const selectStatus = (value: string) =>
  fireEvent.change(screen.getByLabelText('Review status'), { target: { value } });

afterEach(() => vi.restoreAllMocks());

describe('FieldEditor Ignored option (bd mzkw)', () => {
  it('offers Ignored when the handler is wired', () => {
    const f = field();
    render(
      <FieldEditor field={f} schema={schemaWith(f)} onUpdateField={vi.fn()}
                   onIgnoreField={vi.fn()} />,
    );
    expect(screen.getByRole('option', { name: /Ignored/ })).toBeInTheDocument();
  });

  it('does NOT offer Ignored when no handler is wired', () => {
    const f = field();
    render(<FieldEditor field={f} schema={schemaWith(f)} onUpdateField={vi.fn()} />);
    expect(screen.queryByRole('option', { name: /Ignored/ })).toBeNull();
  });

  it('confirms before ignoring, and calls the handler on confirm', () => {
    const f = field();
    const onIgnoreField = vi.fn(() => null);
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(
      <FieldEditor field={f} schema={schemaWith(f)} onUpdateField={vi.fn()}
                   onIgnoreField={onIgnoreField} />,
    );
    selectStatus('__ignore__');
    expect(confirmSpy).toHaveBeenCalledOnce();
    // The dialog says it is reversible and not a delete -- this is an escape
    // hatch, and an author must not fear it destroys their work.
    expect(confirmSpy.mock.calls[0][0]).toContain('NOT deleted');
    expect(onIgnoreField).toHaveBeenCalledWith('f1');
  });

  it('does nothing at all when the confirmation is cancelled', () => {
    const f = field();
    const onIgnoreField = vi.fn(() => null);
    const onUpdateField = vi.fn();
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(
      <FieldEditor field={f} schema={schemaWith(f)} onUpdateField={onUpdateField}
                   onIgnoreField={onIgnoreField} />,
    );
    selectStatus('__ignore__');
    expect(onIgnoreField).not.toHaveBeenCalled();
    // And it must NOT fall through to a review-status write either.
    expect(onUpdateField).not.toHaveBeenCalled();
  });

  it('never routes Ignored through the single-field review patch', () => {
    // Guard against a future refactor collapsing it into withReviewStatus:
    // that would write status='__ignore__' onto the field and quarantine
    // nothing.
    const f = field();
    const onUpdateField = vi.fn();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(
      <FieldEditor field={f} schema={schemaWith(f)} onUpdateField={onUpdateField}
                   onIgnoreField={vi.fn(() => null)} />,
    );
    selectStatus('__ignore__');
    expect(onUpdateField).not.toHaveBeenCalled();
  });

  it('still writes the ordinary review statuses through onUpdateField', () => {
    const f = field();
    const onUpdateField = vi.fn();
    render(
      <FieldEditor field={f} schema={schemaWith(f)} onUpdateField={onUpdateField}
                   onIgnoreField={vi.fn()} />,
    );
    selectStatus('reviewed_correct');
    expect(onUpdateField).toHaveBeenCalledWith(
      expect.objectContaining({ _review: { status: 'reviewed_correct' } }),
    );
  });

  it('disables Ignored and explains why when it is blocked', () => {
    const f = field();
    render(
      <FieldEditor field={f} schema={schemaWith(f)} onUpdateField={vi.fn()}
                   onIgnoreField={vi.fn()}
                   ignoreBlocked='This field is marked required. Clear "Required" first.' />,
    );
    expect(screen.getByRole('option', { name: /Ignored/ })).toBeDisabled();
    expect(screen.getByText(/marked required/)).toBeInTheDocument();
  });

  it('surfaces a block reason returned by the handler', () => {
    const f = field();
    render(
      <FieldEditor field={f} schema={schemaWith(f)} onUpdateField={vi.fn()}
                   onIgnoreField={vi.fn(() => 'Other parts of the form depend on this field (b).')} />,
    );
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    selectStatus('__ignore__');
    expect(screen.getByRole('alert')).toHaveTextContent('depend on this field');
  });
});
