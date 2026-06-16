/**
 * Phase 5: Zoom Presets - Tests
 *
 * Real, asserting coverage for the Fit Width / Fit Page toolbar and manual zoom.
 *
 * NOTE (bd polyglot-pdf-840i): the fit-width/fit-page SCALE MATH (the
 * (containerWidth - padding) / pageWidth calculation and the 0.5..2.0 clamp in
 * PDFViewer.handleFitWidth / handleFitPage) is NOT unit-tested here. It depends on
 * containerRef measurements (clientWidth/clientHeight, getBoundingClientRect),
 * which all return 0 under jsdom -- so a unit test cannot observe a real fitted
 * scale, only that the button click does not error. Asserting a specific fitted
 * value here would be asserting jsdom's 0-rect behavior, not the real math. The
 * clamp/fit calculation is verified in a real browser (the PDF viewer is a
 * canvas-rendered surface; see docs/standards/testing.md on the canvas/jsdom
 * limit). The 22 `expect(true).toBe(true)` stubs that previously "documented" this
 * math were removed -- they ran no production code and would have stayed green if
 * the fit logic were deleted. What IS observable in jsdom is asserted below: the
 * buttons exist, manual zoom changes the displayed scale, and the preset clicks
 * are wired without error.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { PDFViewer } from './PDFViewer';
import type { FormSchema } from '../types/schema';
import * as pdfjsLib from 'pdfjs-dist';

// Mock PDF.js
vi.mock('pdfjs-dist', () => ({
  GlobalWorkerOptions: { workerSrc: '' },
  getDocument: vi.fn(),
}));

const mockSchema: FormSchema = {
  source: 'pdf',
  form_metadata: {
    title: 'Test PDF Form',
    form_number: 'TEST-001',
    total_widgets: 2,
    total_fields: 2,
    version: '1.0',
    language: 'en',
  },
  parts: [],
  sections: [],
  fields: [
    {
      id: 'field1',
      name: 'Test Field 1',
      type: 'text',
      pdf_field_name: 'field1',
      read_only: false,
      required: false,
      spoken_name: 'Test Field 1',
      pdf_position: { page: 1, x: 100, y: 500, width: 200, height: 20 },
    },
    {
      id: 'field2',
      name: 'Test Field 2',
      type: 'text',
      pdf_field_name: 'field2',
      read_only: false,
      required: false,
      spoken_name: 'Test Field 2',
      pdf_position: { page: 1, x: 100, y: 400, width: 200, height: 20 },
    },
  ],
};

// Mock a single-page letter-size PDF document and return it as the loaded doc.
function mockSinglePagePdf() {
  const mockGetPage = vi.fn().mockResolvedValue({
    getViewport: ({ scale }: { scale: number }) => ({
      width: 612 * scale, // standard letter width (points)
      height: 792 * scale,
    }),
    render: vi.fn().mockReturnValue({ promise: Promise.resolve() }),
    cleanup: vi.fn(),
  });
  const mockDocument = { numPages: 1, getPage: mockGetPage, destroy: vi.fn() };
  vi.mocked(pdfjsLib.getDocument).mockReturnValue({
    promise: Promise.resolve(mockDocument as any),
    destroy: vi.fn(),
  } as any);
}

function renderViewer() {
  return render(
    <PDFViewer pdfPath="/test.pdf" schema={mockSchema} selectedFieldId={null} onSelectField={vi.fn()} />
  );
}

async function renderLoadedViewer() {
  renderViewer();
  await waitFor(() => {
    expect(screen.queryByText('Loading PDF...')).not.toBeInTheDocument();
  });
}

describe('Phase 5: Zoom Presets', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSinglePagePdf();
  });

  describe('Toolbar presence', () => {
    it('renders the Fit Width button', async () => {
      await renderLoadedViewer();
      const fitWidthButton = screen.getByTitle('Fit to width');
      expect(fitWidthButton).toBeInTheDocument();
      expect(fitWidthButton).toHaveTextContent('Fit Width');
    });

    it('renders the Fit Page button', async () => {
      await renderLoadedViewer();
      const fitPageButton = screen.getByTitle('Fit entire page');
      expect(fitPageButton).toBeInTheDocument();
      expect(fitPageButton).toHaveTextContent('Fit Page');
    });
  });

  describe('Button interactions (observable in jsdom)', () => {
    it('clicking Fit Width does not throw and keeps the toolbar mounted', async () => {
      await renderLoadedViewer();
      const fitWidthButton = screen.getByTitle('Fit to width');
      // jsdom container rects are 0, so the fitted scale itself is not observable
      // here; what we assert is that the click is wired and does not error.
      expect(() => fireEvent.click(fitWidthButton)).not.toThrow();
      expect(fitWidthButton).toBeInTheDocument();
    });

    it('clicking Fit Page does not throw and keeps the toolbar mounted', async () => {
      await renderLoadedViewer();
      const fitPageButton = screen.getByTitle('Fit entire page');
      expect(() => fireEvent.click(fitPageButton)).not.toThrow();
      expect(fitPageButton).toBeInTheDocument();
    });

    it('manual zoom changes the displayed scale and presets click in cleanly alongside it', async () => {
      await renderLoadedViewer();

      // Manual zoom IS observable: the displayed percentage changes.
      expect(screen.getByText('100%')).toBeInTheDocument();
      fireEvent.click(screen.getByTitle('Zoom in'));
      expect(screen.getByText('125%')).toBeInTheDocument();

      // A preset click in the middle of manual zoom must not throw.
      expect(() => fireEvent.click(screen.getByTitle('Fit to width'))).not.toThrow();

      // Manual zoom still works afterwards.
      fireEvent.click(screen.getByTitle('Zoom out'));
      expect(screen.getByTitle('Zoom in')).toBeInTheDocument();
      expect(screen.getByTitle('Zoom out')).toBeInTheDocument();
    });
  });
});
