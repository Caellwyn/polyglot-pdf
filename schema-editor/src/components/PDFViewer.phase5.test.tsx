/**
 * Phase 5: Zoom Presets - Tests
 *
 * Real, asserting coverage for the Fit Width / Fit Page toolbar and manual zoom.
 *
 * NOTE (bd polyglot-pdf-840i): the fit-width/fit-page SCALE MATH (the
 * (containerWidth - padding) / pageWidth calculation and the 0.5..2.0 clamp in
 * PDFViewer.handleFitWidth / handleFitPage) IS exercised here. The scroll
 * container's clientWidth/clientHeight default to 0 under jsdom -- which is why
 * handleFitWidth/handleFitPage early-return unless those dimensions are stubbed.
 * The "Fit math (clientWidth/clientHeight stubbed)" describe block below defines
 * non-zero clientWidth/clientHeight on the real `.overflow-auto` scroll-container
 * node so the fit calculation runs, then asserts the EXACT percentage the scale
 * readout shows. This proves the (containerWidth - 64) / pageWidth math and the
 * Math.max(0.5, Math.min(2.0, ...)) clamp both run -- deleting the handler body or
 * the clamp would change the asserted percentage and fail the test.
 *
 * pageDimensions (read by the fit math as the page WIDTH/HEIGHT reference) is only
 * populated when PDFPage's onPageLoad fires, and that fires only when the canvas
 * 2d context exists -- jsdom has no canvas backend, so getContext is stubbed in
 * beforeEach (the same stub phase2 uses).
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

// Render the loaded viewer AND wait until the single page's canvas has committed,
// so PDFPage.onPageLoad has populated pageDimensions (the fit math's page-size
// reference). Returns the render() result so callers can reach the container.
async function renderLoadedViewerWithPage() {
  const result = renderViewer();
  await waitFor(() => {
    expect(document.querySelectorAll('canvas').length).toBe(1);
  });
  // Flush the page-render microtask chain so onPageLoad fires and pageDimensions
  // is set before the fit handler reads it.
  await waitFor(() => {
    expect(screen.queryByText('Loading PDF...')).not.toBeInTheDocument();
  });
  return result;
}

// Define a non-zero clientWidth/clientHeight on the live `.overflow-auto` scroll
// container so handleFitWidth/handleFitPage read real dimensions instead of jsdom's
// default 0 (which makes them early-return). The handlers query the node fresh on
// each click, so defining the property on the node itself is sufficient.
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

  // These tests stub the scroll container's clientWidth/clientHeight to non-zero
  // values so the fit MATH actually runs (it early-returns at 0), then assert the
  // EXACT percentage the readout shows. The page is letter size: getViewport at
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
