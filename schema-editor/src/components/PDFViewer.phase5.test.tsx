/**
 * Phase 5: Zoom Presets - Tests
 *
 * Real, asserting coverage for the Fit Width / Fit Page toolbar and manual zoom.
 *
 * NOTE (bd polyglot-pdf-840i): the fit-width/fit-page SCALE MATH (the
 * (containerWidth - padding) / pageWidth calculation and the 0.5..2.0 clamp in
 * PDFViewer.handleFitWidth / handleFitPage) IS exercised here.
 *
 * What gates the handlers (read the handler bodies in PDFViewer.tsx): they
 * early-return ONLY when `pageDimensions` is empty / page-1 dims are missing / the
 * `.overflow-auto` scroll container is absent -- NOT on a zero clientWidth. So with
 * pageDimensions populated, a click ALWAYS runs the math: at the jsdom-default
 * clientWidth/clientHeight of 0 it computes (0 - 64) / pageWidth (negative) and
 * Math.max(0.5, ...) clamps it to 0.5 -- which the two "no-stub -> 50%" tests below
 * assert (that is real lower-clamp coverage, not a degenerate no-op). The "Fit math
 * (clientWidth/clientHeight stubbed)" describe block then defines NON-zero
 * clientWidth/clientHeight on the real scroll-container node to drive the in-range
 * and upper-clamp cases, asserting the EXACT readout percentage. Deleting the
 * handler body or the clamp changes an asserted percentage and fails a test.
 *
 * The gating dependency is therefore pageDimensions, which PDFPage fills LATER via
 * renderTask.promise.then(onPageLoad) -- so the helper below waits for the canvas
 * AND flushes that promise chain before any fit click, or the handler would take
 * its pageDimensions-empty early return and the assertions would flake. onPageLoad
 * itself fires only when the canvas 2d context exists -- jsdom has no canvas
 * backend, so getContext is stubbed in beforeEach (the same stub phase2 uses).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
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
      
      spoken_name: 'Test Field 1',
      pdf_position: { page: 1, x: 100, y: 500, width: 200, height: 20 },
    },
    {
      id: 'field2',
      name: 'Test Field 2',
      type: 'text',
      pdf_field_name: 'field2',
      read_only: false,
      
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
    // render task exposes both promise and cancel (PDFPage's cleanup calls
    // renderTaskRef.current.cancel() on rerender/unmount).
    render: vi.fn().mockReturnValue({ promise: Promise.resolve(), cancel: vi.fn() }),
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

// Render the loaded viewer AND wait until pageDimensions is actually populated --
// the fit handlers early-return on pageDimensions.size === 0, and pageDimensions is
// filled LATER (a ref set in PDFPage's renderTask.promise.then(onPageLoad)), so a
// canvas being present does NOT prove it is ready (Codex review). We flush that
// promise chain, then wait for a pageDimensions-DRIVEN signal: the field overlays
// only mount once pageDimensions.has(pageNum) is true (PDFViewer gates them on it),
// so an overlay in the DOM is direct proof the fit math will not take its empty
// early return. Returns the render() result so callers can reach the container.
async function renderLoadedViewerWithPage() {
  const result = renderViewer();
  await waitFor(() => {
    expect(document.querySelectorAll('canvas').length).toBe(1);
  });
  // Flush the render-task promise chain so onPageLoad fires and pageDimensions is set.
  await act(async () => { await Promise.resolve(); });
  // Overlays mount only after pageDimensions is populated -- wait for one (mockSchema
  // has field1 on page 1), proving the fit handlers will read real page dims.
  await screen.findByTestId('field-overlay-field1');
  return result;
}

// Define a non-zero clientWidth/clientHeight on the live `.overflow-auto` scroll
// container so handleFitWidth/handleFitPage compute an IN-RANGE / upper-clamp scale
// instead of the negative-then-lower-clamped 0.5 they produce at jsdom's default 0
// (the handlers do NOT early-return on a 0 clientWidth -- only on empty
// pageDimensions). The handlers query the node fresh on each click, so defining the
// property on the node itself is sufficient.
function stubScrollContainerSize(
  container: HTMLElement,
  width: number,
  height: number
) {
  const scrollContainer = container.querySelector('.overflow-auto');
  if (!scrollContainer) {
    throw new Error('scroll container (.overflow-auto) not found');
  }
  Object.defineProperty(scrollContainer, 'clientWidth', {
    configurable: true,
    value: width,
  });
  Object.defineProperty(scrollContainer, 'clientHeight', {
    configurable: true,
    value: height,
  });
}

describe('Phase 5: Zoom Presets', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // jsdom has no canvas backend, so getContext returns null and PDFPage bails
    // before onPageLoad -- which is what populates pageDimensions (the page-size
    // reference the fit math divides by). Stub a minimal 2d context so onPageLoad
    // fires. (Same stub phase2 uses.)
    HTMLCanvasElement.prototype.getContext = vi.fn(() => ({})) as any;
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
    it('clicking Fit Width with no stubbed container size clamps to the 0.5 lower bound', async () => {
      await renderLoadedViewerWithPage();
      const fitWidthButton = screen.getByTitle('Fit to width');
      // No clientWidth stub here, so the live `.overflow-auto` node reports the
      // jsdom default clientWidth = 0. The math then computes
      // (0 - 64) / 612 = -0.1045, which Math.max(0.5, ...) clamps up to 0.5 -> "50%".
      // This proves the handler runs end-to-end (no throw) AND that the lower clamp
      // protects against a degenerate/zero container width.
      expect(() => fireEvent.click(fitWidthButton)).not.toThrow();
      await waitFor(() => {
        expect(screen.getByText('50%')).toBeInTheDocument();
      });
    });

    it('clicking Fit Page with no stubbed container size clamps to the 0.5 lower bound', async () => {
      await renderLoadedViewerWithPage();
      const fitPageButton = screen.getByTitle('Fit entire page');
      // Same as above: clientWidth = clientHeight = 0 -> both scaleForWidth and
      // scaleForHeight are negative -> min is negative -> Math.max(0.5, ...) -> "50%".
      expect(() => fireEvent.click(fitPageButton)).not.toThrow();
      await waitFor(() => {
        expect(screen.getByText('50%')).toBeInTheDocument();
      });
    });

    it('manual zoom and a Fit Width preset both change the scale, interleaved', async () => {
      // Use the page-ready helper + a stubbed container size so the preset actually
      // RUNS the fit math (not the pageDimensions-empty early return) and we can
      // assert the readout CHANGES to the fitted value -- a bare not.toThrow() would
      // pass even if Fit Width lost its onClick (Codex review).
      const { container } = await renderLoadedViewerWithPage();

      // Manual zoom is observable: 100% -> 125%.
      expect(screen.getByText('100%')).toBeInTheDocument();
      fireEvent.click(screen.getByTitle('Zoom in'));
      expect(screen.getByText('125%')).toBeInTheDocument();

      // A Fit Width preset mid-zoom OVERRIDES the manual scale with the fitted value:
      // clientWidth 1000 -> (1000 - 64) / 612 = 1.52941... -> "153%".
      stubScrollContainerSize(container, 1000, 800);
      fireEvent.click(screen.getByTitle('Fit to width'));
      await waitFor(() => {
        expect(screen.getByText('153%')).toBeInTheDocument();
      });
      expect(screen.queryByText('125%')).not.toBeInTheDocument();

      // Manual zoom still works AFTER the preset: 153% -> zoom out one step (0.25).
      // 1.52941 - 0.25 = 1.27941 -> round(127.94) = "128%".
      fireEvent.click(screen.getByTitle('Zoom out'));
      await waitFor(() => {
        expect(screen.getByText('128%')).toBeInTheDocument();
      });
    });
  });

  // These tests stub the scroll container's clientWidth/clientHeight to non-zero
  // values so the fit math produces an IN-RANGE / upper-clamp scale (at the jsdom
  // default of 0 it would instead clamp to the 0.5 lower bound -- see the no-stub
  // tests above; the handlers never early-return on a 0 clientWidth), then assert
  // the EXACT percentage the readout shows. The page is letter size: getViewport at
  // scale 1.0 returns width 612, height 792 (mockSinglePagePdf), so the fit math's
  // pageWidth = 612, pageHeight = 792. Padding subtracted is 64 (p-8 = 32px * 2).
  describe('Fit math (clientWidth/clientHeight stubbed)', () => {
    it('Fit Width sets scale to (clientWidth - 64) / pageWidth, rounded for display', async () => {
      const { container } = await renderLoadedViewerWithPage();
      expect(screen.getByText('100%')).toBeInTheDocument();

      // clientWidth 1000 -> (1000 - 64) / 612 = 936 / 612 = 1.52941...
      // -> Math.round(1.52941 * 100) = 153 -> "153%". In [0.5, 2.0], so no clamp.
      stubScrollContainerSize(container, 1000, 800);
      fireEvent.click(screen.getByTitle('Fit to width'));

      await waitFor(() => {
        expect(screen.getByText('153%')).toBeInTheDocument();
      });
      // The old 100% readout is gone -- proves the scale actually changed.
      expect(screen.queryByText('100%')).not.toBeInTheDocument();
    });

    it('Fit Width clamps to the UPPER bound 2.0 when the container is very wide', async () => {
      const { container } = await renderLoadedViewerWithPage();

      // clientWidth 3000 -> (3000 - 64) / 612 = 2936 / 612 = 4.797... -> the
      // Math.min(2.0, ...) clamp pins it to 2.0 -> "200%".
      stubScrollContainerSize(container, 3000, 4000);
      fireEvent.click(screen.getByTitle('Fit to width'));

      await waitFor(() => {
        expect(screen.getByText('200%')).toBeInTheDocument();
      });
    });

    it('Fit Width clamps to the LOWER bound 0.5 when the container is very narrow', async () => {
      const { container } = await renderLoadedViewerWithPage();

      // clientWidth 200 -> (200 - 64) / 612 = 136 / 612 = 0.2222... -> the
      // Math.max(0.5, ...) clamp pins it to 0.5 -> "50%".
      stubScrollContainerSize(container, 200, 300);
      fireEvent.click(screen.getByTitle('Fit to width'));

      await waitFor(() => {
        expect(screen.getByText('50%')).toBeInTheDocument();
      });
    });

    it('Fit Page uses the smaller of width-fit and height-fit (height-constrained here)', async () => {
      const { container } = await renderLoadedViewerWithPage();
      expect(screen.getByText('100%')).toBeInTheDocument();

      // Fit Page = min(scaleForWidth, scaleForHeight), then clamped to [0.5, 2.0].
      //   scaleForWidth  = (1000 - 64) / 612 = 936 / 612  = 1.52941...
      //   scaleForHeight = (900  - 64) / 792 = 836 / 792  = 1.05555...
      // min = 1.05555 -> Math.round(105.55) = 106 -> "106%". Height constrains.
      stubScrollContainerSize(container, 1000, 900);
      fireEvent.click(screen.getByTitle('Fit entire page'));

      await waitFor(() => {
        expect(screen.getByText('106%')).toBeInTheDocument();
      });
      expect(screen.queryByText('100%')).not.toBeInTheDocument();
    });

    it('Fit Page is width-constrained when width is the tighter dimension', async () => {
      const { container } = await renderLoadedViewerWithPage();
      expect(screen.getByText('100%')).toBeInTheDocument();

      // A tall+narrow container makes WIDTH the limiting dimension:
      //   scaleForWidth  = (700 - 64) / 612  = 636 / 612  = 1.03921...
      //   scaleForHeight = (2000 - 64) / 792 = 1936 / 792 = 2.44444... (would clamp)
      // min = 1.03921 -> Math.round(103.92) = 104 -> "104%". Width constrains, and
      // the result is taken BEFORE the height scale's would-be 2.0 clamp -- proving
      // Fit Page uses the smaller scale, not always height.
      stubScrollContainerSize(container, 700, 2000);
      fireEvent.click(screen.getByTitle('Fit entire page'));

      await waitFor(() => {
        expect(screen.getByText('104%')).toBeInTheDocument();
      });
      expect(screen.queryByText('100%')).not.toBeInTheDocument();
    });

    it('Fit Page clamps to the UPPER bound 2.0 when BOTH dimensions are very large', async () => {
      const { container } = await renderLoadedViewerWithPage();

      // Both dimensions huge -> both scales > 2.0 -> min still > 2.0 ->
      // Math.min(2.0, ...) pins it to 2.0 -> "200%".
      //   scaleForWidth  = (3000 - 64) / 612  = 4.797...
      //   scaleForHeight = (4000 - 64) / 792  = 4.969...
      stubScrollContainerSize(container, 3000, 4000);
      fireEvent.click(screen.getByTitle('Fit entire page'));

      await waitFor(() => {
        expect(screen.getByText('200%')).toBeInTheDocument();
      });
    });
  });
});
