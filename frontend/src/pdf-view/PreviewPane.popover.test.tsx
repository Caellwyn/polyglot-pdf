/**
 * PreviewPane's ownership of the click-to-edit editor state (bd
 * polyglot-pdf-7esr): voice-advance (currentFieldId change) dismisses the
 * popover, dimmed fields are not clickable, and the surface stays read-only
 * when the edit handlers are absent. pdfjs internals mocked.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import React from 'react';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import type { FormSchema } from '../schema-forms/types/schema';

afterEach(() => cleanup());

vi.mock('./usePDFDocument', () => ({
  usePDFDocument: () => ({
    document: {} as any,
    numPages: 1,
    isLoading: false,
    error: null,
  }),
}));
vi.mock('./PDFPage', () => ({
  PDFPage: () => <div data-testid="mock-pdf-page" />,
}));

import PreviewPane from './PreviewPane';

const rect = (y: number) => ({ page: 1, x: 100, y, width: 120, height: 14 });

const schema: FormSchema = {
  source: 'pdf',
  form_metadata: { title: 'T', version: '1', language: 'en', form_number: 'T-1' },
  sections: [{ id: 's1', label: 'S1', order: 1, fields: ['name', 'apt'] }],
  fields: [
    {
      id: 'name',
      name: 'Name',
      spoken_name: 'name',
      section_id: 's1',
      type: 'text',
      pdf_position: rect(100),
    } as any,
    {
      id: 'apt',
      name: 'Apt number',
      spoken_name: 'apartment number',
      section_id: 's1',
      type: 'text',
      pdf_position: rect(200),
      show_if: { field: 'has_apt', operator: 'is_checked' },
    } as any,
  ],
} as any;

function renderPane(props: Partial<React.ComponentProps<typeof PreviewPane>> = {}) {
  return render(
    <PreviewPane
      pdfUrl="/fake.pdf"
      schema={schema}
      fieldValues={{}}
      validationErrors={{}}
      onFieldChange={vi.fn()}
      onFieldBlur={vi.fn()}
      {...props}
    />
  );
}

describe('PreviewPane click-to-edit state (bd polyglot-pdf-7esr)', () => {
  it('a voice advance (currentFieldId change) dismisses an open popover', () => {
    const { rerender } = renderPane({ currentFieldId: null });
    fireEvent.click(screen.getByTestId('pdf-field-overlay-name'));
    expect(screen.getByTestId('pdf-field-edit-popover-name')).toBeTruthy();

    rerender(
      <PreviewPane
        pdfUrl="/fake.pdf"
        schema={schema}
        fieldValues={{}}
        validationErrors={{}}
        onFieldChange={vi.fn()}
        onFieldBlur={vi.fn()}
        currentFieldId="apt"
      />
    );
    expect(screen.queryByTestId('pdf-field-edit-popover-name')).toBeNull();
  });

  it('a dimmed (show_if-hidden) field is not clickable and never opens the editor', () => {
    renderPane(); // has_apt unset -> apt is dimmed
    const dimmedBox = screen.getByTestId('pdf-field-overlay-apt');
    expect(dimmedBox.getAttribute('data-dimmed')).toBe('true');
    expect(dimmedBox.getAttribute('role')).toBeNull();
    fireEvent.click(dimmedBox);
    expect(screen.queryByTestId('pdf-field-edit-popover-apt')).toBeNull();
  });

  it('without edit handlers the surface is read-only (no button role, click opens nothing)', () => {
    render(
      <PreviewPane pdfUrl="/fake.pdf" schema={schema} fieldValues={{}} currentFieldId={null} />
    );
    const box = screen.getByTestId('pdf-field-overlay-name');
    expect(box.getAttribute('role')).toBeNull();
    fireEvent.click(box);
    expect(screen.queryByTestId('pdf-field-edit-popover-name')).toBeNull();
  });

  it('auto-closes when the edited field show_if flips false mid-edit (no chrome-only popover)', () => {
    // apt is visible while has_apt is checked...
    const visible = { has_apt: { value: true, confirmed: true } };
    const { rerender } = renderPane({ fieldValues: visible });
    fireEvent.click(screen.getByTestId('pdf-field-overlay-apt'));
    expect(screen.getByTestId('pdf-field-edit-popover-apt')).toBeTruthy();

    // ...then the controlling field flips (voice session / another edit)
    // WITHOUT a currentFieldId or scale change.
    rerender(
      <PreviewPane
        pdfUrl="/fake.pdf"
        schema={schema}
        fieldValues={{ has_apt: { value: false, confirmed: true } }}
        validationErrors={{}}
        onFieldChange={vi.fn()}
        onFieldBlur={vi.fn()}
      />
    );
    expect(screen.queryByTestId('pdf-field-edit-popover-apt')).toBeNull();
  });

  it('the clickable overlay is keyboard-activatable (Enter opens the editor)', () => {
    renderPane();
    const box = screen.getByTestId('pdf-field-overlay-name');
    expect(box.getAttribute('role')).toBe('button');
    fireEvent.keyDown(box, { key: 'Enter' });
    expect(screen.getByTestId('pdf-field-edit-popover-name')).toBeTruthy();
  });
});
