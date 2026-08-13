/**
 * FieldEditPopover click-to-edit []-alias read (bd polyglot-pdf-1utg): the
 * popover opened by clicking an overlay must resolve a field's value even
 * when it is stored under the OTHER bracket variant than the schema id --
 * matching the overlay's own readFieldEntryWithAlias read (bd
 * polyglot-pdf-7sdc). Gemini inconsistently adds/drops the trailing [] on
 * checkbox-group ids (bd polyglot-pdf-5k52), and after the got6 dedup
 * exactly ONE fieldValues entry survives under the last-written key -- so a
 * schema id 'x[]' can have its value sitting under 'x' (or vice versa). A
 * bare fieldValues[editingHere.id] opened the popover BLANK even though the
 * overlay right next to it correctly showed the field as filled/confirmed --
 * the user would see a filled-looking box, click to edit it, and be shown an
 * empty input, risking overwriting the real answer on save.
 *
 * PDFPage is mocked -- the canvas render is not under test here.
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import React from 'react';
import { render, screen, cleanup } from '@testing-library/react';
import type { FormField } from '../schema-forms/types/schema';

afterEach(() => cleanup());

vi.mock('./PDFPage', () => ({
  PDFPage: () => <div data-testid="mock-pdf-page" />,
}));

import { PDFViewer } from './PDFViewer';

const rect = { page: 1, x: 100, y: 100, width: 40, height: 12 };

function editableTextField(id: string): FormField {
  return {
    id,
    name: id,
    spoken_name: id,
    section_id: 's1',
    type: 'text',
    pdf_position: rect,
  } as any;
}

function renderEditableViewer(fields: FormField[], fieldValues: Record<string, any>, editingFieldId: string) {
  return render(
    <PDFViewer
      document={{} as any}
      numPages={1}
      scale={1}
      fields={fields}
      fieldValues={fieldValues}
      editingFieldId={editingFieldId}
      onOverlayClick={vi.fn()}
      onCloseEditor={vi.fn()}
      onFieldChange={vi.fn()}
      onFieldBlur={vi.fn()}
    />
  );
}

describe('FieldEditPopover []-alias resolution (bd polyglot-pdf-1utg)', () => {
  it('pre-fills the editor when the value is stored under the ALIASED (bracketed) key', () => {
    // schema id 'x', post-got6 single entry stored ONLY under 'x[]'.
    const fields = [editableTextField('x')];
    renderEditableViewer(fields, { 'x[]': { value: 'Smith', confirmed: true } }, 'x');

    const input = screen.getByRole('textbox') as HTMLInputElement;
    expect(input.value).toBe('Smith');
  });

  it('pre-fills the editor when the value is stored under the UNBRACKETED (base) key', () => {
    // The reverse direction: schema id 'x[]', value stored ONLY under 'x'.
    const fields = [editableTextField('x[]')];
    renderEditableViewer(fields, { x: { value: 'Jones', confirmed: false } }, 'x[]');

    const input = screen.getByRole('textbox') as HTMLInputElement;
    expect(input.value).toBe('Jones');
  });

  it('still opens empty when neither bracket variant carries a value', () => {
    const fields = [editableTextField('x')];
    renderEditableViewer(fields, {}, 'x');

    const input = screen.getByRole('textbox') as HTMLInputElement;
    expect(input.value).toBe('');
  });

  it('prefers the EXACT key when both bracket variants happen to carry values', () => {
    const fields = [editableTextField('x')];
    renderEditableViewer(
      fields,
      { x: { value: 'exact-wins', confirmed: true }, 'x[]': { value: 'alias-loses', confirmed: true } },
      'x'
    );

    const input = screen.getByRole('textbox') as HTMLInputElement;
    expect(input.value).toBe('exact-wins');
  });
});
