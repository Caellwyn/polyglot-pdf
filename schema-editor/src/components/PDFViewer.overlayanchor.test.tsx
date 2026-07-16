/**
 * Overlay-anchor regression (bd polyglot-pdf-0x10.3).
 *
 * The field overlays are absolutely positioned from the page WRAPPER's origin
 * (left = pdfX * scale). That is only correct when the wrapper's box coincides
 * with the canvas's box. The old markup let them diverge: the wrapper spanned
 * the full pane width while the canvas centered itself inside it with
 * margin: 0 auto -- so at any zoom where the page was narrower than the pane,
 * every overlay sat LEFT of its field by half the leftover width (alignment
 * only looked right at fit-width, ~150% on the reporting user's pane).
 *
 * The fix: the wrapper shrinks to the canvas (w-fit) and centers ITSELF
 * (mx-auto); the canvas no longer self-centers. These tests pin that layout
 * contract -- they fail on the old markup.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { PDFViewer } from './PDFViewer';
import type { FormSchema } from '../types/schema';
import * as pdfjsLib from 'pdfjs-dist';

const schema: FormSchema = {
  source: 'pdf',
  form_metadata: {
    title: 'W-7',
    form_number: 'W-7',
    total_widgets: 1,
    total_fields: 1,
    version: '1.0',
    language: 'en',
  },
  parts: [],
  sections: [
    { id: 'section-1', label: 'Part 1', order: 1, fields: ['field-1'] },
  ],
  fields: [
    {
      id: 'field-1',
      name: 'Field 1',
      type: 'text',
      section_id: 'section-1',
      pdf_field_name: 'field_1',
      read_only: false,
      pdf_position: { page: 1, x: 100, y: 200, width: 150, height: 30 },
    },
  ],
} as unknown as FormSchema;

describe('PDFViewer overlay anchoring (bd 0x10.3)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // jsdom has no canvas backend; stub a minimal 2d context so PDFPage's
    // render path (and onPageLoad -> pageDimensions) runs.
    HTMLCanvasElement.prototype.getContext = vi.fn(() => ({})) as any;
    vi.mocked(pdfjsLib.getDocument).mockReturnValue({
      promise: Promise.resolve({
        numPages: 1,
        getPage: vi.fn(() =>
          Promise.resolve({
            getViewport: vi.fn(() => ({ width: 612, height: 792, scale: 1 })),
            render: vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() })),
          })
        ),
        destroy: vi.fn(),
      } as any),
      destroy: vi.fn(),
    } as any);
  });

  it('sizes the page wrapper to the canvas and centers the wrapper itself', async () => {
    const { container } = render(
      <PDFViewer
        pdfPath="/test.pdf"
        schema={schema}
        selectedFieldId={null}
        onSelectField={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('field-overlay-field-1')).toBeInTheDocument();
    });

    // The overlay layer's positioning context is the wrapper that also holds
    // the canvas -- it must shrink to the canvas (w-fit) and center itself
    // (mx-auto) so overlay coordinates measure from the canvas's left edge.
    const overlay = screen.getByTestId('field-overlay-field-1');
    const wrapper = overlay.closest('.relative') as HTMLElement;
    expect(wrapper).not.toBeNull();
    expect(wrapper.className).toContain('w-fit');
    expect(wrapper.className).toContain('mx-auto');

    // And the canvas must NOT center itself inside the wrapper -- a
    // margin: 0 auto here is exactly the offset bug this test pins against.
    const canvas = container.querySelector('canvas') as HTMLCanvasElement;
    expect(canvas).not.toBeNull();
    expect(canvas.style.margin).toBe('');
  });
});
