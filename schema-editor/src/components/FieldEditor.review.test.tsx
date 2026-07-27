/**
 * FieldEditor review-status control + notes (bd polyglot-pdf-u8t6).
 *
 * The editor can set a field to unreviewed / reviewed-correct / needs-follow-up
 * and leave a note; each change commits a NEW field through onUpdateField via
 * the _review helpers. A reset-to-neutral drops the key so it serializes clean.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FieldEditor } from './FieldEditor';
import type { FormSchema, FormField } from '../types/schema';

function field(extra: Partial<FormField> = {}): FormField {
  return {
    id: 'f1', name: 'F1', type: 'text', pdf_field_name: 'pdf.f1',
    spoken_name: 'field one', section_id: 's1', read_only: false,
    help: { instructions: 'All set.' },
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

describe('FieldEditor review control (bd u8t6)', () => {
  it('renders the review section with the current status and note', () => {
    const f = field({ _review: { status: 'needs_followup', note: 'verify this' } });
    render(<FieldEditor field={f} schema={schemaWith(f)} onUpdateField={vi.fn()} />);
    expect(screen.getByTestId('field-review')).toBeInTheDocument();
    expect((screen.getByLabelText('Review status') as HTMLSelectElement).value).toBe('needs_followup');
    expect((screen.getByLabelText('Review notes') as HTMLTextAreaElement).value).toBe('verify this');
  });

  it('committing a status change carries the _review key', () => {
    const f = field();
    const onUpdateField = vi.fn();
    render(<FieldEditor field={f} schema={schemaWith(f)} onUpdateField={onUpdateField} />);
    fireEvent.change(screen.getByLabelText('Review status'), {
      target: { value: 'reviewed_correct' },
    });
    expect(onUpdateField).toHaveBeenCalledWith(
      expect.objectContaining({ _review: { status: 'reviewed_correct' } }),
    );
  });

  it('resetting to unreviewed with no note drops the _review key', () => {
    const f = field({ _review: { status: 'reviewed_correct' } });
    const onUpdateField = vi.fn();
    render(<FieldEditor field={f} schema={schemaWith(f)} onUpdateField={onUpdateField} />);
    fireEvent.change(screen.getByLabelText('Review status'), {
      target: { value: 'unreviewed' },
    });
    const committed = onUpdateField.mock.calls[0][0] as FormField;
    expect('_review' in committed).toBe(false);
  });

  it('typing a note commits it under the current status', () => {
    const f = field({ _review: { status: 'needs_followup' } });
    const onUpdateField = vi.fn();
    render(<FieldEditor field={f} schema={schemaWith(f)} onUpdateField={onUpdateField} />);
    fireEvent.change(screen.getByLabelText('Review notes'), {
      target: { value: 'a-number needs checking' },
    });
    expect(onUpdateField).toHaveBeenCalledWith(
      expect.objectContaining({
        _review: { status: 'needs_followup', note: 'a-number needs checking' },
      }),
    );
  });
});
