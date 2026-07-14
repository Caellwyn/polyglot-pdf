/**
 * PDFViewer overlay []-alias read (bd polyglot-pdf-7sdc): the in-browser PDF
 * overlay preview must resolve a field's value even when it is stored under the
 * OTHER bracket variant than the schema id. Gemini inconsistently adds/drops the
 * trailing [] on checkbox-group ids (bd polyglot-pdf-5k52), and after the got6
 * dedup (bd polyglot-pdf-got6) exactly ONE fieldValues entry survives under the
 * last-written key -- so a schema id 'race[]' can have its value sitting under
 * 'race' (or vice-versa). A bare fieldValues[field.id] read then rendered the
 * overlay BLANK ('empty') for a field that actually has a value. The overlay now
 * reads via readFieldEntryWithAlias, matching the validator projection and the
 * backend fill.
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

function overlayField(id: string): FormField {
  return {
    id,
    name: id,
    spoken_name: id,
    section_id: 's1',
    type: 'checkbox_group',
    pdf_position: rect,
  } as any;
}

function renderViewer(fields: FormField[], fieldValues: Record<string, any>) {
  return render(
    <PDFViewer
      document={{} as any}
      numPages={1}
      scale={1}
      fields={fields}
      fieldValues={fieldValues}
    />
  );
}

describe('PDFViewer overlay []-alias resolution', () => {
  it('renders a bracketed schema id whose value is stored under the unbracketed key', () => {
    // schema id 'x[]', post-got6 single entry stored ONLY under 'x'.
    const fields = [overlayField('x[]')];
    renderViewer(fields, { x: { value: ['Asian'], confirmed: true } });
    const box = screen.getByTestId('pdf-field-overlay-x[]');
    // Not blank: the confirmed value under the alias key resolves.
    expect(box.getAttribute('data-fill-state')).toBe('confirmed');
  });

  it('renders an unbracketed schema id whose value is stored under the bracketed key', () => {
    // The reverse direction: schema id 'x', value stored ONLY under 'x[]'.
    const fields = [overlayField('x')];
    renderViewer(fields, { 'x[]': { value: ['Asian'], confirmed: false } });
    const box = screen.getByTestId('pdf-field-overlay-x');
    expect(box.getAttribute('data-fill-state')).toBe('filled');
  });

  it('still renders empty when neither bracket variant carries a value', () => {
    const fields = [overlayField('x[]')];
    renderViewer(fields, { x: { value: [], confirmed: false } });
    expect(screen.getByTestId('pdf-field-overlay-x[]').getAttribute('data-fill-state')).toBe(
      'empty'
    );
  });
});
