/**
 * PDFViewer show_if dimming wiring (bd polyglot-pdf-lp5v, epic rubric R4):
 * hidden-by-condition fields get the dimmed overlay, dimming flips live when
 * the controlling field's value changes, and a dimmed field that becomes
 * `current` is not dimmed. PDFPage is mocked -- the canvas render is not
 * under test here.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import React from 'react';
import { render, screen, cleanup } from '@testing-library/react';
import type { FormField } from '../schema-forms/types/schema';

afterEach(() => cleanup());

vi.mock('./PDFPage', () => ({
  PDFPage: () => <div data-testid="mock-pdf-page" />,
}));

import { PDFViewer } from './PDFViewer';

const rect = { page: 1, x: 100, y: 100, width: 40, height: 12 };

const controller: FormField = {
  id: 'has_apt',
  name: 'Has apartment',
  spoken_name: 'has apartment',
  section_id: 's1',
  type: 'checkbox',
  pdf_position: { ...rect, y: 80 },
} as any;

const dependent: FormField = {
  id: 'apt_number',
  name: 'Apartment number',
  spoken_name: 'apartment number',
  section_id: 's1',
  type: 'text',
  pdf_position: rect,
  show_if: { field: 'has_apt', operator: 'is_checked' },
} as any;

const fields = [controller, dependent];

function renderViewer(fieldValues: Record<string, any>, currentFieldId?: string) {
  return render(
    <PDFViewer
      document={{} as any}
      numPages={1}
      scale={1}
      fields={fields}
      fieldValues={fieldValues}
      currentFieldId={currentFieldId}
    />
  );
}

describe('PDFViewer show_if dimming', () => {
  it('dims a field whose show_if condition is unmet', () => {
    renderViewer({ has_apt: { value: false, confirmed: false } });
    expect(screen.getByTestId('pdf-field-overlay-apt_number').getAttribute('data-dimmed')).toBe(
      'true'
    );
    // The controlling field itself is never dimmed.
    expect(screen.getByTestId('pdf-field-overlay-has_apt').getAttribute('data-dimmed')).toBeNull();
  });

  it('undims live when the controlling field value changes (wrapped map)', () => {
    const { rerender } = renderViewer({ has_apt: { value: false, confirmed: false } });
    expect(
      screen.getByTestId('pdf-field-overlay-apt_number').getAttribute('data-dimmed')
    ).toBe('true');
    rerender(
      <PDFViewer
        document={{} as any}
        numPages={1}
        scale={1}
        fields={fields}
        fieldValues={{ has_apt: { value: true, confirmed: true } }}
      />
    );
    expect(
      screen.getByTestId('pdf-field-overlay-apt_number').getAttribute('data-dimmed')
    ).toBeNull();
  });

  it('never dims the current field, even when its show_if is unmet', () => {
    renderViewer({ has_apt: { value: false, confirmed: false } }, 'apt_number');
    const box = screen.getByTestId('pdf-field-overlay-apt_number');
    expect(box.getAttribute('data-dimmed')).toBeNull();
    expect(box.getAttribute('data-fill-state')).toBe('current');
  });

  it('dimmed overlays are not clickable (pointer-events stays off)', () => {
    renderViewer({ has_apt: { value: false, confirmed: false } });
    const box = screen.getByTestId('pdf-field-overlay-apt_number');
    // The overlay layer is pointer-events:none and the dimmed class pins it
    // off with !important (P2.3 click-to-edit must not re-enable it); at the
    // component level nothing attaches a click handler or button role.
    expect(box.className).toContain('pdf-field-overlay--dimmed');
    expect(box.getAttribute('role')).toBeNull();
    expect(box.onclick).toBeNull();
  });
});
