import React from 'react';
import type { FormSchema } from '../types/schema';
import type { PDFPageProxy } from 'pdfjs-dist';
import { usePDFDocument } from '../hooks/usePDFDocument';
import { PDFPage } from './PDFPage';
import { FieldOverlay } from './FieldOverlay';

interface PDFViewerProps {
  pdfPath: string;
  schema: FormSchema;
  selectedFieldId: string | null;
  onSelectField: (fieldId: string) => void;
  // Report the loaded document's page count upward (bd polyglot-pdf-g63j) so
  // the field list can flag a field claiming a page this PDF does not have --
  // such a field paints nowhere, exactly the invisible failure this bead
  // removes. The viewer already owns the document, so reporting beats making
  // App load the PDF a second time just to count pages. Optional: the viewer
  // works standalone without it.
  onPageCountChange?: (pageCount: number) => void;
}

export const PDFViewer: React.FC<PDFViewerProps> = ({
  pdfPath,
  schema,
  selectedFieldId,
  onSelectField,
  onPageCountChange,
}) => {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const pageRefs = React.useRef<Map<number, HTMLDivElement>>(new Map());
  const pageDimensions = React.useRef<Map<number, { width: number; height: number }>>(new Map());
  const [scale, setScale] = React.useState(1.0);
  const [currentPage, setCurrentPage] = React.useState(1);
  // Bumped whenever a page's dimensions are first stored. pageDimensions is a
  // ref (so the auto-scroll effect can read it synchronously), but the field
  // overlays are gated on pageDimensions.current.has(pageNum) -- a ref write
  // does NOT re-render, so without this counter the overlays never appear on
  // first load. Bumping state on first store forces the overlay pass to run.
  const [, setDimensionsVersion] = React.useState(0);

  // Load PDF document
  const { document, numPages, isLoading, error } = usePDFDocument(pdfPath);

  // Publish the page count upward whenever it settles (bd g63j). Reports 0
  // while a document is loading -- including the window right after a kit
  // switch, when usePDFDocument has reset numPages but the new PDF has not
  // arrived. Consumers treat 0 as "unknown" and skip the page-range check, so
  // a newly-opened kit is never judged against the PREVIOUS kit's page count
  // (fresh-eyes: that stale window produced a transient false verdict).
  React.useEffect(() => {
    onPageCountChange?.(numPages);
  }, [numPages, onPageCountChange]);

  // Store a page's unscaled dimensions when it loads. Kept stable (useCallback,
  // no deps) so PDFPage's effect does not re-run every render.
  const storePageDimensions = React.useCallback((pageNum: number, page: PDFPageProxy) => {
    const viewport = page.getViewport({ scale: 1.0 }); // Get unscaled dimensions
    const alreadyStored = pageDimensions.current.has(pageNum);
    pageDimensions.current.set(pageNum, {
      width: viewport.width,
      height: viewport.height,
    });
    // Re-render so the field overlays for this page can mount (see counter above).
    if (!alreadyStored) {
      setDimensionsVersion(v => v + 1);
    }
  }, []);

  // Memoize the per-page onPageLoad closures so each PDFPage receives a STABLE
  // callback identity (a fresh `(page) => ...` per render would thrash PDFPage's
  // render effect, which lists onPageLoad in its deps -- the root of the
  // "same canvas during multiple render()" race). Rebuilt only when numPages
  // changes.
  const pageLoadHandlers = React.useMemo(() => {
    const handlers = new Map<number, (page: PDFPageProxy) => void>();
    for (let pageNum = 1; pageNum <= numPages; pageNum++) {
      handlers.set(pageNum, (page: PDFPageProxy) => storePageDimensions(pageNum, page));
    }
    return handlers;
  }, [numPages, storePageDimensions]);

  // Zoom controls
  const handleZoomIn = () => setScale(s => Math.min(2.0, s + 0.25));
  const handleZoomOut = () => setScale(s => Math.max(0.5, s - 0.25));

  const handleFitWidth = () => {
    if (!containerRef.current || pageDimensions.current.size === 0) return;

    // Get the first page's width as reference (most PDFs have consistent page sizes)
    const firstPageDims = pageDimensions.current.get(1);
    if (!firstPageDims) return;

    // Get container width (accounting for padding: p-8 = 32px * 2 = 64px)
    const scrollContainer = containerRef.current.querySelector('.overflow-auto');
    if (!scrollContainer) return;

    const containerWidth = scrollContainer.clientWidth - 64; // Subtract padding
    const pageWidth = firstPageDims.width;

    // Calculate scale and clamp to bounds
    const newScale = Math.max(0.5, Math.min(2.0, containerWidth / pageWidth));
    setScale(newScale);
  };

  const handleFitPage = () => {
    if (!containerRef.current || pageDimensions.current.size === 0) return;

    // Get the first page's dimensions as reference
    const firstPageDims = pageDimensions.current.get(1);
    if (!firstPageDims) return;

    // Get container dimensions (accounting for padding: p-8 = 32px * 2 = 64px)
    const scrollContainer = containerRef.current.querySelector('.overflow-auto');
    if (!scrollContainer) return;

    const containerWidth = scrollContainer.clientWidth - 64; // Subtract horizontal padding
    const containerHeight = scrollContainer.clientHeight - 64; // Subtract vertical padding

    const pageWidth = firstPageDims.width;
    const pageHeight = firstPageDims.height;

    // Calculate scale for both dimensions and use the smaller (so entire page fits)
    const scaleForWidth = containerWidth / pageWidth;
    const scaleForHeight = containerHeight / pageHeight;
    const newScale = Math.max(0.5, Math.min(2.0, Math.min(scaleForWidth, scaleForHeight)));

    setScale(newScale);
  };

  // Page navigation
  const handlePrevPage = () => {
    if (currentPage > 1) {
      scrollToPage(currentPage - 1);
    }
  };

  const handleNextPage = () => {
    if (currentPage < numPages) {
      scrollToPage(currentPage + 1);
    }
  };

  const handlePageInput = (page: number) => {
    const validPage = Math.max(1, Math.min(numPages, page));
    scrollToPage(validPage);
  };

  const scrollToPage = (pageNumber: number) => {
    const pageEl = pageRefs.current.get(pageNumber);
    if (pageEl && containerRef.current) {
      pageEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
      setCurrentPage(pageNumber);
    }
  };

  // Auto-scroll to field's position when field is selected
  React.useEffect(() => {
    if (!selectedFieldId || !schema) return;

    const field = schema.fields.find(f => f.id === selectedFieldId);
    if (!field?.pdf_position?.page) return;

    const pageNum = field.pdf_position.page;
    const pageEl = pageRefs.current.get(pageNum);
    const pageDims = pageDimensions.current.get(pageNum);
    const scrollContainer = containerRef.current?.querySelector('.overflow-auto');

    if (!pageEl || !pageDims || !scrollContainer) return;

    // Calculate field position on the page
    const fieldY = field.pdf_position.y ?? 0;
    const fieldHeight = field.pdf_position.height ?? 0;
    const fieldCenterY = (fieldY + fieldHeight / 2) * scale;

    // Get page offset relative to scroll container
    const pageRect = pageEl.getBoundingClientRect();
    const containerRect = scrollContainer.getBoundingClientRect();
    
    // Calculate scroll position to center the field
    const fieldAbsoluteY = pageRect.top - containerRect.top + scrollContainer.scrollTop + fieldCenterY;
    const containerHalfHeight = scrollContainer.clientHeight / 2;
    const targetScrollTop = fieldAbsoluteY - containerHalfHeight;

    // Smooth scroll to center the field
    scrollContainer.scrollTo({
      top: targetScrollTop,
      behavior: 'smooth'
    });

    setCurrentPage(pageNum);
  }, [selectedFieldId, schema, scale]);

  // Track current page based on scroll position
  React.useEffect(() => {
    if (!containerRef.current || numPages === 0) return;

    const handleScroll = () => {
      const container = containerRef.current;
      if (!container) return;

      // Find which page is most visible
      let maxVisibility = 0;
      let mostVisiblePage = 1;

      pageRefs.current.forEach((pageEl, pageNum) => {
        const rect = pageEl.getBoundingClientRect();
        const containerRect = container.getBoundingClientRect();

        // Calculate how much of the page is visible
        const visibleTop = Math.max(rect.top, containerRect.top);
        const visibleBottom = Math.min(rect.bottom, containerRect.bottom);
        const visibleHeight = Math.max(0, visibleBottom - visibleTop);

        if (visibleHeight > maxVisibility) {
          maxVisibility = visibleHeight;
          mostVisiblePage = pageNum;
        }
      });

      setCurrentPage(mostVisiblePage);
    };

    const scrollContainer = containerRef.current.querySelector('.overflow-auto');
    scrollContainer?.addEventListener('scroll', handleScroll, { passive: true });

    return () => {
      scrollContainer?.removeEventListener('scroll', handleScroll);
    };
  }, [numPages]);

  // Count of fields placed on the PDF; drives the toolbar's "N field(s)" label.
  const positionedFieldCount = schema.fields.filter(f => f.pdf_position).length;

  return (
    <div ref={containerRef} className="h-full flex flex-col bg-gray-100">
      {/* Toolbar */}
      <div className="bg-white border-b border-gray-200 px-4 py-2 flex items-center justify-between">
        {/* Left: Page navigation */}
        <div className="flex items-center gap-3">
          {numPages > 0 && (
            <>
              <div className="flex items-center gap-1">
                <button
                  className="btn-sm btn-secondary"
                  onClick={handlePrevPage}
                  disabled={currentPage <= 1}
                  title="Previous page"
                >
                  ←
                </button>
                <button
                  className="btn-sm btn-secondary"
                  onClick={handleNextPage}
                  disabled={currentPage >= numPages}
                  title="Next page"
                >
                  →
                </button>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-sm text-gray-600">Page</span>
                <input
                  type="number"
                  min={1}
                  max={numPages}
                  value={currentPage}
                  onChange={(e) => handlePageInput(parseInt(e.target.value) || 1)}
                  className="w-12 px-2 py-1 text-sm border border-gray-300 rounded text-center"
                />
                <span className="text-sm text-gray-600">of {numPages}</span>
              </div>
            </>
          )}
          {positionedFieldCount > 0 && (
            <>
              <span className="text-gray-300">|</span>
              <span className="text-sm text-gray-600">
                {positionedFieldCount === 1
                  ? '1 field'
                  : `${positionedFieldCount} fields`}
              </span>
            </>
          )}
        </div>

        {/* Right: Zoom controls */}
        <div className="flex items-center gap-2">
          <button
            className="btn-sm btn-secondary"
            onClick={handleZoomOut}
            disabled={scale <= 0.5}
            title="Zoom out"
          >
            −
          </button>
          <span className="btn-sm bg-white px-3 py-1 text-sm border border-gray-300">
            {Math.round(scale * 100)}%
          </span>
          <button
            className="btn-sm btn-secondary"
            onClick={handleZoomIn}
            disabled={scale >= 2.0}
            title="Zoom in"
          >
            +
          </button>
          <button
            className="btn-sm btn-secondary ml-2"
            onClick={handleFitWidth}
            title="Fit to width"
          >
            Fit Width
          </button>
          <button
            className="btn-sm btn-secondary"
            onClick={handleFitPage}
            title="Fit entire page"
          >
            Fit Page
          </button>
        </div>
      </div>

      {/* PDF Content Area */}
      <div className="flex-1 overflow-auto custom-scrollbar">
        {isLoading && (
          <div className="h-full flex items-center justify-center">
            <div className="text-center">
              <div className="animate-spin w-12 h-12 border-4 border-primary-500 border-t-transparent rounded-full mx-auto mb-4" />
              <p className="text-gray-600">Loading PDF...</p>
              <p className="text-sm text-gray-500 mt-2">{pdfPath.split('/').pop()}</p>
            </div>
          </div>
        )}

        {error && (
          <div className="h-full flex items-center justify-center">
            <div className="text-center max-w-md">
              <svg
                className="w-16 h-16 text-red-500 mx-auto mb-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">Failed to Load PDF</h3>
              <p className="text-gray-600 mb-4">{error}</p>
              <p className="text-sm text-gray-500">{pdfPath}</p>
            </div>
          </div>
        )}

        {document && !isLoading && !error && (
          <div className="p-8 space-y-4">
            {/* Render all pages */}
            {Array.from({ length: numPages }, (_, i) => i + 1).map((pageNum) => (
              <div
                key={pageNum}
                ref={(el) => {
                  if (el) {
                    pageRefs.current.set(pageNum, el);
                  } else {
                    pageRefs.current.delete(pageNum);
                  }
                }}
                // w-fit + mx-auto: the wrapper shrinks to the canvas and centers
                // ITSELF, so the overlay layer (absolute at the wrapper's origin)
                // shares the canvas's coordinate space at every zoom. With a
                // full-width wrapper and a centered canvas, overlays sat left of
                // their fields by half the leftover width whenever the zoomed
                // page was narrower than the pane (bd polyglot-pdf-0x10.3).
                className="relative w-fit mx-auto"
              >
                <PDFPage
                  document={document}
                  pageNumber={pageNum}
                  scale={scale}
                  onPageLoad={pageLoadHandlers.get(pageNum)}
                  className="mb-4"
                />

                {/* Field overlays */}
                {pageDimensions.current.has(pageNum) && (
                  <div className="absolute top-0 left-0 w-full h-full pointer-events-none" style={{ zIndex: 10 }}>
                    {schema.fields
                      .filter(field => field.pdf_position?.page === pageNum)
                      .map(field => (
                        <FieldOverlay
                          key={field.id}
                          field={field}
                          pageHeight={pageDimensions.current.get(pageNum)!.height}
                          scale={scale}
                          isSelected={field.id === selectedFieldId}
                          onClick={() => onSelectField(field.id)}
                        />
                      ))}
                  </div>
                )}

                {/* Page number label */}
                <div className="absolute top-0 right-0 bg-gray-900 bg-opacity-75 text-white text-xs px-2 py-1 rounded-bl" style={{ zIndex: 5 }}>
                  Page {pageNum}
                </div>
              </div>
            ))}
          </div>
        )}

        {!document && !isLoading && !error && (
          <div className="h-full flex items-center justify-center">
            <div className="text-center text-gray-400">
              <svg
                className="w-24 h-24 mx-auto mb-4 text-gray-300"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"
                />
              </svg>
              <p className="text-lg">No PDF selected</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
