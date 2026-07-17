/**
 * Per-field error hints in the field list (bd polyglot-pdf-0x10.6).
 *
 * The red X / amber clock used to be mute: checkFieldComplete's error strings
 * were computed and thrown away, and backend lint findings only ever surfaced
 * in the bottom ValidationPanel strip. The status icon now carries every
 * reason (local completeness errors, review reasons, backend lint messages)
 * in its tooltip, and a field with a backend lint ERROR shows red even when
 * it passes the local completeness check.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { FieldList } from './FieldList';
import type { FormSchema, FormField } from '../types/schema';
import type { LintFinding } from '../utils/remoteKitStore';

function completeField(id: string, extra: Partial<FormField> = {}): FormField {
  return {
    id, name: id, type: 'text', pdf_field_name: `pdf.${id}`,
    spoken_name: `spoken ${id}`, section_id: 'sec-1', read_only: false,
    help: { instructions: 'All set.' },
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

function renderList(schema: FormSchema, lintFindingsByField?: Map<string, LintFinding[]>) {
  render(
    <FieldList
      schema={schema}
      selectedFieldId={null}
      onSelectField={vi.fn()}
      lintFindingsByField={lintFindingsByField}
    />,
  );
}

describe('FieldList per-field error hints (bd 0x10.6)', () => {
  it("puts a broken field's concrete errors in the status icon's tooltip", () => {
    const broken = completeField('broken', { pdf_field_name: undefined });
    renderList(schemaWith([broken]));
    const icon = screen.getByTestId('field-status-broken');
    expect(icon).toHaveAttribute('title', expect.stringContaining('Missing PDF field name'));
  });

  it('explains WHY a field needs review, not just that it does', () => {
    const amber = completeField('amber', { spoken_name: undefined, help: undefined });
    renderList(schemaWith([amber]));
    const icon = screen.getByTestId('field-status-amber');
    const title = icon.getAttribute('title') ?? '';
    expect(title).toContain('Missing spoken name');
    expect(title).toContain('Help instructions are missing or a placeholder');
  });

  it('leaves a clean, complete field tooltip-less', () => {
    renderList(schemaWith([completeField('clean')]));
    expect(screen.getByTestId('field-status-clean')).not.toHaveAttribute('title');
  });

  it('a backend lint ERROR turns the row red and lands its message in the tooltip', () => {
    const clean = completeField('reason_for_submission');
    const findings = new Map<string, LintFinding[]>([
      ['reason_for_submission', [{
        severity: 'ERROR',
        rule: 'required-top-level',
        path: 'fields.reason_for_submission',
        message: 'required must live at validation.required, not the field top level',
        field_id: 'reason_for_submission',
      }]],
    ]);
    renderList(schemaWith([clean]), findings);
    const icon = screen.getByTestId('field-status-reason_for_submission');
    expect(icon.getAttribute('title')).toContain('required must live at validation.required');
    // Red X, not the green check: the row agrees with the bottom strip.
    expect(icon.querySelector('svg.text-red-600')).not.toBeNull();
    expect(icon.querySelector('svg.text-green-600')).toBeNull();
  });
});
