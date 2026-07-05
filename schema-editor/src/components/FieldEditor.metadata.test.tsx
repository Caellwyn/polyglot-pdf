/**
 * Tests for the form-metadata editor (bd polyglot-pdf-s4dp.2). When no field is
 * selected, FieldEditor shows an editable Form-metadata panel; editing a field
 * (version/edition/OMB/expiration) commits a single-key patch through
 * onUpdateMetadata, and a low-confidence / "unknown" version shows a verify hint.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FieldEditor } from './FieldEditor';
import type { FormSchema, FormField } from '../types/schema';

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

  it('clears an OPTIONAL field to undefined when emptied', () => {
    const onUpdateMetadata = vi.fn();
    const schema = schemaWith({ omb_number: '1545-0074' });
    render(<FieldEditor field={null} schema={schema} onUpdateField={vi.fn()} onUpdateMetadata={onUpdateMetadata} />);
    fireEvent.change(screen.getByLabelText('OMB number'), { target: { value: '' } });
    expect(onUpdateMetadata).toHaveBeenCalledWith({ omb_number: undefined });
  });

  it('clearing the REQUIRED version degrades to "unknown", never undefined (Codex PR #263)', () => {
    // version is a required schema field; undefined would be dropped by
    // JSON.stringify on save and fail backend validation. Clearing also resets
    // confidence to 0 (the now-empty version is unverified).
    const onUpdateMetadata = vi.fn();
    const schema = schemaWith({ version: 'December 2024' });
    render(<FieldEditor field={null} schema={schema} onUpdateField={vi.fn()} onUpdateMetadata={onUpdateMetadata} />);
    fireEvent.change(screen.getByLabelText('Version / Revision'), { target: { value: '' } });
    expect(onUpdateMetadata).toHaveBeenCalledWith({ version: 'unknown', version_confidence: 0 });
  });

  it('a MANUAL version edit clears stale auto-confidence so the verify hint goes away (Codex PR #263 r2)', () => {
    // A low-confidence auto-extraction corrected by hand must not keep showing
    // "(verify)" -- the manual value is authoritative, so confidence is cleared.
    const onUpdateMetadata = vi.fn();
    const schema = schemaWith({ version: '2025', version_confidence: 0.4 });
    render(<FieldEditor field={null} schema={schema} onUpdateField={vi.fn()} onUpdateMetadata={onUpdateMetadata} />);
    fireEvent.change(screen.getByLabelText('Version / Revision'), { target: { value: 'December 2024' } });
    expect(onUpdateMetadata).toHaveBeenCalledWith({ version: 'December 2024', version_confidence: undefined });
  });
});

// Option metadata surfacing for v2 groups (bd h76m.10): the option VALUE is a
// read-only slug chip (never a free-text input), and the per-option PDF widget
// mapping is author-tier only, under an Advanced disclosure.
describe('FieldEditor option metadata (bd h76m.10)', () => {
  function groupField(): FormField {
    return {
      id: 'race', name: 'Race', spoken_name: 'race', type: 'checkbox_group',
      section_id: 's1', read_only: false, required: false,
      options: [
        { value: 'white', label: 'White', pdf_field_name: 'w[0]' },
        { value: 'black', label: 'Black', pdf_field_name: 'b[0]' },
      ],
    } as FormField;
  }
  function schemaWith(f: FormField): FormSchema {
    return {
      source: 'pdf',
      form_metadata: { title: 'T', form_number: 'T', total_widgets: 1, total_fields: 1, version: '1', language: 'en' },
      parts: [],
      sections: [{ id: 's1', label: 'S1', order: 0, fields: [f.id] }],
      fields: [f],
    } as FormSchema;
  }

  it('shows the option value as a read-only chip, never a text input', () => {
    const f = groupField();
    render(<FieldEditor field={f} schema={schemaWith(f)} onUpdateField={vi.fn()} />);
    // The slug appears as text (chip), and there is no input carrying it.
    expect(screen.getByText('white')).toBeInTheDocument();
    expect(screen.getByText('black')).toBeInTheDocument();
    const inputs = screen.queryAllByDisplayValue('white');
    expect(inputs).toHaveLength(0); // value is not editable
  });

  it('exposes the per-option PDF widget under Advanced for an author', () => {
    const f = groupField();
    render(<FieldEditor field={f} schema={schemaWith(f)} onUpdateField={vi.fn()} authorTier />);
    expect(screen.getAllByText('Advanced: PDF widget').length).toBe(2);
    expect(screen.getByDisplayValue('w[0]')).toBeInTheDocument();
  });

  it('hides the per-option PDF widget from an editor-tier contractor', () => {
    const f = groupField();
    render(<FieldEditor field={f} schema={schemaWith(f)} onUpdateField={vi.fn()} authorTier={false} />);
    expect(screen.queryByText('Advanced: PDF widget')).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('w[0]')).not.toBeInTheDocument();
    // The value chip and label editing remain visible.
    expect(screen.getByText('white')).toBeInTheDocument();
  });
});

// Round-3 group-editing guards (bd h76m.10, Codex PR #310 round 3).
describe('FieldEditor group guards (Codex PR #310 round 3)', () => {
  function twoOptionGroup(): FormField {
    return {
      id: 'race', name: 'Race', spoken_name: 'race', type: 'checkbox_group',
      section_id: 's1', read_only: false, required: false,
      options: [
        { value: 'white', label: 'White', pdf_field_name: 'w[0]' },
        { value: 'black', label: 'Black', pdf_field_name: 'b[0]' },
      ],
    } as FormField;
  }
  function schemaWith(f: FormField): FormSchema {
    return {
      source: 'pdf',
      form_metadata: { title: 'T', form_number: 'T', total_widgets: 1, total_fields: 1, version: '1', language: 'en' },
      parts: [],
      sections: [{ id: 's1', label: 'S1', order: 0, fields: [f.id] }],
      fields: [f],
    } as FormSchema;
  }

  it('disables Remove at the 2-option floor (a group needs >= 2)', () => {
    const f = twoOptionGroup();
    render(<FieldEditor field={f} schema={schemaWith(f)} onUpdateField={vi.fn()} />);
    const removes = screen.getAllByRole('button', { name: 'Remove' });
    expect(removes).toHaveLength(2);
    for (const b of removes) expect(b).toBeDisabled();
  });

  it('allows Remove above the floor (3 options)', () => {
    const f = twoOptionGroup();
    f.options = [...f.options!, { value: 'asian', label: 'Asian', pdf_field_name: 'a[0]' }];
    render(<FieldEditor field={f} schema={schemaWith(f)} onUpdateField={vi.fn()} />);
    const removes = screen.getAllByRole('button', { name: 'Remove' });
    expect(removes.some(b => !(b as HTMLButtonElement).disabled)).toBe(true);
  });

  it('hides the legacy Controls Fields editor for a checkbox_group', () => {
    const f = twoOptionGroup();
    render(<FieldEditor field={f} schema={schemaWith(f)} onUpdateField={vi.fn()} />);
    expect(screen.queryByText('Controls Fields')).not.toBeInTheDocument();
    expect(screen.queryByText('+ Add Control')).not.toBeInTheDocument();
  });

  it('keeps the Controls Fields editor for a plain checkbox', () => {
    const f = { id: 'cb', name: 'CB', spoken_name: 'cb', type: 'checkbox',
      section_id: 's1', pdf_field_name: 'cb[0]', read_only: false, required: false } as FormField;
    render(<FieldEditor field={f} schema={schemaWith(f)} onUpdateField={vi.fn()} />);
    expect(screen.getByText('Controls Fields')).toBeInTheDocument();
  });

  it('makes the type picker read-only for an option-bearing group', () => {
    const f = twoOptionGroup();
    render(<FieldEditor field={f} schema={schemaWith(f)} onUpdateField={vi.fn()} />);
    const typeSelect = screen.getByLabelText('Field Type') as HTMLSelectElement;
    expect(typeSelect).toBeDisabled();
  });
});
