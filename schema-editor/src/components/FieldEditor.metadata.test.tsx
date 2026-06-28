/**
 * Tests for the form-metadata editor (bd polyglot-pdf-s4dp.2). When no field is
 * selected, FieldEditor shows an editable Form-metadata panel; editing a field
 * (version/edition/OMB/expiration) commits a single-key patch through
 * onUpdateMetadata, and a low-confidence / "unknown" version shows a verify hint.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FieldEditor } from './FieldEditor';
import type { FormSchema } from '../types/schema';

function schemaWith(meta: Partial<FormSchema['form_metadata']>): FormSchema {
  return {
    source: 'pdf',
    form_metadata: { title: 'I-90', form_number: 'I-90', version: 'unknown', language: 'en', total_widgets: 0, total_fields: 0, ...meta },
    parts: [],
    sections: [],
    fields: [],
  } as unknown as FormSchema;
}

describe('FieldEditor form-metadata panel (no field selected)', () => {
  it('renders the metadata editor with the current version values', () => {
    const schema = schemaWith({ version: 'December 2024', omb_number: '1545-0074', version_confidence: 0.9 });
    render(<FieldEditor field={null} schema={schema} onUpdateField={vi.fn()} onUpdateMetadata={vi.fn()} />);
    expect(screen.getByText('Form metadata')).toBeInTheDocument();
    expect(screen.getByDisplayValue('December 2024')).toBeInTheDocument();
    expect(screen.getByDisplayValue('1545-0074')).toBeInTheDocument();
  });

  it('commits a single-key patch when a metadata field is edited', () => {
    const onUpdateMetadata = vi.fn();
    const schema = schemaWith({ version: 'unknown' });
    render(<FieldEditor field={null} schema={schema} onUpdateField={vi.fn()} onUpdateMetadata={onUpdateMetadata} />);
    const versionInput = screen.getByLabelText('Version / Revision');
    fireEvent.change(versionInput, { target: { value: 'January 2025' } });
    expect(onUpdateMetadata).toHaveBeenCalledWith({ version: 'January 2025' });
  });

  it('shows the verify hint for an unknown / low-confidence version', () => {
    const schema = schemaWith({ version: 'unknown', version_confidence: 0 });
    render(<FieldEditor field={null} schema={schema} onUpdateField={vi.fn()} onUpdateMetadata={vi.fn()} />);
    expect(screen.getByText(/could not be confidently detected/i)).toBeInTheDocument();
  });

  it('does NOT show the verify hint for a confident version', () => {
    const schema = schemaWith({ version: '01/20/25', edition_date: '01/20/25', version_confidence: 0.9 });
    render(<FieldEditor field={null} schema={schema} onUpdateField={vi.fn()} onUpdateMetadata={vi.fn()} />);
    expect(screen.queryByText(/could not be confidently detected/i)).not.toBeInTheDocument();
  });

  it('clears a field to undefined when emptied', () => {
    const onUpdateMetadata = vi.fn();
    const schema = schemaWith({ omb_number: '1545-0074' });
    render(<FieldEditor field={null} schema={schema} onUpdateField={vi.fn()} onUpdateMetadata={onUpdateMetadata} />);
    fireEvent.change(screen.getByLabelText('OMB number'), { target: { value: '' } });
    expect(onUpdateMetadata).toHaveBeenCalledWith({ omb_number: undefined });
  });
});
