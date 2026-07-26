/**
 * FieldEditor Details textarea (bd polyglot-pdf-wsao.1): the authoring surface
 * for help.details -- verbatim official-booklet excerpts, AI-facing only. Pins
 * that (1) the textarea renders and shows the stored value, and (2) an edit
 * writes help.details while PRESERVING the sibling help keys (the spread in
 * updateField must not drop instructions/format_hint).
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { FieldEditor } from './FieldEditor';
import type { FormSchema, FormField } from '../types/schema';

const FIELD: FormField = {
  id: 'reason', name: 'Reason for applying', type: 'radio',
  pdf_field_name: 'c1_01[0]', read_only: false,
  spoken_name: 'reason for applying',
  help: {
    instructions: 'Check the one box that best applies.',
    details: '## a. Tax treaty benefit\nMust also check box h.',
    format_hint: 'one box',
  },
} as FormField;

const SCHEMA: FormSchema = {
  form_metadata: { title: 'W-7', version: '1', form_number: 'W-7' },
  sections: [], fields: [FIELD],
} as unknown as FormSchema;

afterEach(cleanup);

describe('FieldEditor Details textarea (bd wsao.1)', () => {
  it('renders the stored help.details value', () => {
    render(
      <FieldEditor field={FIELD} schema={SCHEMA} onUpdateField={() => {}} />,
    );
    expect(
      screen.getByDisplayValue(/## a\. Tax treaty benefit/),
    ).toBeTruthy();
  });

  it('writes help.details on edit and preserves sibling help keys', () => {
    const onUpdateField = vi.fn();
    render(
      <FieldEditor
        field={FIELD}
        schema={SCHEMA}
        onUpdateField={onUpdateField}
      />,
    );
    const textarea = screen.getByDisplayValue(/## a\. Tax treaty benefit/);
    fireEvent.change(textarea, { target: { value: 'new reference text' } });

    expect(onUpdateField).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 'reason',
        help: expect.objectContaining({
          details: 'new reference text',
          instructions: 'Check the one box that best applies.',
          format_hint: 'one box',
        }),
      }),
    );
  });
});
