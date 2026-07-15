/**
 * Phase 4: PDFViewer -> FieldOverlay click-to-select wiring (bd polyglot-pdf-840i)
 *
 * This is the WIRING regression test that FieldOverlay.test.tsx cannot cover.
 * FieldOverlay.test.tsx proves a directly-supplied `onClick` prop fires when the
 * overlay is clicked -- but it constructs the overlay in isolation, so it does NOT
 * prove that PDFViewer renders an overlay per positioned field and wires
 * `onClick={() => onSelectField(field.id)}` to it. If that wiring were dropped (or
 * passed the wrong field id), FieldOverlay.test.tsx would still pass. This test
 * renders the FULL PDFViewer, waits for the real overlay to mount, clicks it, and
 * asserts PDFViewer called onSelectField with the field's id -- closing that gap.
 *
 * The overlay only mounts once pageDimensions is populated (PDFViewer gates each
 * page's overlays on pageDimensions.current.has(pageNum)), which in turn requires
 * PDFPage.onPageLoad to fire -- and that only fires when the canvas 2d context
 * exists. jsdom has no canvas backend, so getContext is stubbed in beforeEach.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import { PDFViewer } from './PDFViewer';
import type { FormSchema } from '../types/schema';
import * as pdfjsLib from 'pdfjs-dist';

vi.mock('pdfjs-dist', () => ({
  GlobalWorkerOptions: { workerSrc: '' },
  getDocument: vi.fn(),
}));

// A single-page schema with one positioned field on page 1.
const mockSchema: FormSchema = {
  source: 'pdf',
  form_metadata: {
    title: 'Test PDF Form',
    form_number: 'TEST-001',
    total_widgets: 1,
    total_fields: 1,
    version: '1.0',
    language: 'en',
  },
  parts: [],
  sections: [],
  fields: [
    {
      id: 'field-click-me',
      name: 'Clickable Field',
      type: 'text',
      pdf_field_name: 'field_click_me',
      read_only: false,
      
      spoken_name: 'Clickable Field',
      pdf_position: { page: 1, x: 100, y: 500, width: 200, height: 20 },
    },
  ],
};

function mockSinglePagePdf() {
  const mockGetPage = vi.fn().mockResolvedValue({
    getViewport: ({ scale }: { scale: number }) => ({
      width: 612 * scale,
      height: 792 * scale,
    }),
    // render task exposes promise + cancel (PDFPage's cleanup calls cancel()).
    render: vi.fn().mockReturnValue({ promise: Promise.resolve(), cancel: vi.fn() }),
    cleanup: vi.fn(),
  });
  const mockDocument = { numPages: 1, getPage: mockGetPage, destroy: vi.fn() };
  vi.mocked(pdfjsLib.getDocument).mockReturnValue({
    promise: Promise.resolve(mockDocument as any),
    destroy: vi.fn(),
  } as any);
}

describe('Phase 4: PDFViewer -> FieldOverlay click-to-select wiring', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // jsdom has no canvas backend; stub a minimal 2d context so PDFPage renders
    // and onPageLoad fires (which populates pageDimensions and lets overlays mount).
    HTMLCanvasElement.prototype.getContext = vi.fn(() => ({})) as any;
    mockSinglePagePdf();
  });

  it('clicking a rendered field overlay calls onSelectField with that field id', async () => {
    const onSelectField = vi.fn();

    render(
      <PDFViewer
        pdfPath="/test.pdf"
        schema={mockSchema}
        selectedFieldId={null}
        onSelectField={onSelectField}
      />
    );

    // Wait for the page canvas to commit.
    await waitFor(() => {
      expect(document.querySelectorAll('canvas').length).toBe(1);
    });
    // Flush the page-render microtask chain so onPageLoad fires and pageDimensions
    // is populated -- the overlay is gated on that.
    await act(async () => { await Promise.resolve(); });

    // The overlay mounts only after pageDimensions is set; wait for it.
    const overlay = await screen.findByTestId('field-overlay-field-click-me');
    expect(overlay).toBeInTheDocument();

    // Click the overlay (the overlay root carries the onClick PDFViewer wired).
    fireEvent.click(overlay);

    // PDFViewer wires onClick={() => onSelectField(field.id)} -- so the spy must
    // have been called with this field's id, proving the wiring (not just that
    // FieldOverlay forwards an onClick in isolation).
    expect(onSelectField).toHaveBeenCalledWith('field-click-me');
  });

  it('passes isSelected to the overlay so the selected field gets selected styling', async () => {
    // The other half of click-to-select: when the parent sets selectedFieldId,
    // PDFViewer must pass isSelected={field.id === selectedFieldId} into
    // FieldOverlay, which renders a THICKER (4px) border for the selected field.
    // FieldOverlay.test.tsx proves the styling given isSelected in isolation; this
    // proves PDFViewer actually DRIVES isSelected from selectedFieldId (bd 840i).
    const onSelectField = vi.fn();

    // Selecting a positioned field fires the auto-scroll effect, which calls the
    // scroll container's scrollTo -- jsdom does not implement it, so stub it.
    Element.prototype.scrollTo = vi.fn();

    const { rerender } = render(
      <PDFViewer
        pdfPath="/test.pdf"
        schema={mockSchema}
        selectedFieldId={null}
        onSelectField={onSelectField}
      />
    );

    await waitFor(() => {
      expect(document.querySelectorAll('canvas').length).toBe(1);
    });
    await act(async () => { await Promise.resolve(); });

    const overlay = await screen.findByTestId('field-overlay-field-click-me') as HTMLElement;
    // Unselected: thin 2px border, no selection box-shadow. (The border COLOR is
    // driven by field status, not selection -- so assert on width + shadow, which
    // are the selection-specific signals FieldOverlay derives from isSelected.)
    expect(overlay.style.border).toContain('2px');
    expect(overlay.style.boxShadow).toBe('none');

    // Parent selects this field -> PDFViewer must propagate isSelected=true.
    rerender(
      <PDFViewer
        pdfPath="/test.pdf"
        schema={mockSchema}
        selectedFieldId="field-click-me"
        onSelectField={onSelectField}
      />
    );

    await waitFor(() => {
      const selected = screen.getByTestId('field-overlay-field-click-me') as HTMLElement;
      // Selected: thicker 4px border AND the blue selection glow box-shadow --
      // both flip only when isSelected is true, proving PDFViewer drove it.
      expect(selected.style.border).toContain('4px');
      expect(selected.style.boxShadow).toContain('rgba(59, 130, 246');
    });
  });
});
