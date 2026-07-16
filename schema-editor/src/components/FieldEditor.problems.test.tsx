/**
 * FieldEditor "Why this field is flagged" banner (bd polyglot-pdf-0x10.6).
 *
 * Selecting a red/amber field now explains the problem AT the field: local
 * completeness errors plus any backend lint findings App passes in. Clean
 * field with no findings -> no banner.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { FieldEditor } from './FieldEditor';
import type { FormSchema, FormField } from '../types/schema';
import type { LintFinding } from '../utils/remoteKitStore';

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

describe('FieldEditor problems banner (bd 0x10.6)', () => {
  it('shows local completeness errors for the selected field', () => {
    const f = field({ pdf_field_name: undefined });
    render(<FieldEditor field={f} schema={schemaWith(f)} onUpdateField={vi.fn()} />);
    const banner = screen.getByTestId('field-problems');
    expect(banner).toHaveTextContent('Why this field is flagged');
    expect(banner).toHaveTextContent('Missing PDF field name');
  });

  it('shows backend lint findings passed in for the field', () => {
    const f = field();
    const findings: LintFinding[] = [{
      severity: 'ERROR',
      rule: 'required-top-level',
      path: 'fields.f1',
      message: 'required must live at validation.required, not the field top level',
      field_id: 'f1',
    }];
    render(
      <FieldEditor field={f} schema={schemaWith(f)} onUpdateField={vi.fn()} lintFindings={findings} />,
    );
    expect(screen.getByTestId('field-problems')).toHaveTextContent(
      'required must live at validation.required',
    );
  });

  it('renders no banner for a clean field with no findings', () => {
    const f = field();
    render(<FieldEditor field={f} schema={schemaWith(f)} onUpdateField={vi.fn()} />);
    expect(screen.queryByTestId('field-problems')).toBeNull();
  });
});
