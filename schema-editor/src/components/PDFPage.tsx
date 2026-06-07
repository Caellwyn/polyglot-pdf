/**
 * PDFPage Component
 *
 * Renders a single page of a PDF document on a canvas element.
 */

import React, { useRef, useEffect, useState } from 'react';
import type { PDFDocumentProxy, PDFPageProxy } from 'pdfjs-dist';

export interface PDFPageProps {
  document: PDFDocumentProxy;
  pageNumber: number;
  scale?: number;
  onPageLoad?: (page: PDFPageProxy) => void;
  className?: string;
}

/**
 * Component to render a single PDF page
 *
 * @param document - The PDF document proxy from PDF.js
 * @param pageNumber - Page number to render (1-indexed)
 * @param scale - Scale factor for rendering (default: 1.0)
 * @param onPageLoad - Callback when page is loaded and rendered
 * @param className - Additional CSS classes
 */
export const PDFPage: React.FC<PDFPageProps> = ({
  document,
  pageNumber,
  scale = 1.0,
  onPageLoad,
  className = '',
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [isRendering, setIsRendering] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const renderTaskRef = useRef<any>(null);

  useEffect(() => {
    if (!document || !canvasRef.current) {
      return;
    }

    const canvas = canvasRef.current;
    const context = canvas.getContext('2d');
    if (!context) {
      setError('Failed to get canvas context');
      return;
    }

    setIsRendering(true);
    setError(null);

    // Per-run cancellation flag. React 18 StrictMode invokes effects twice in
    // dev, and getPage()/render() are async -- without this guard a stale run
    // can call render() on the same canvas while a newer run is mid-render
    // ("Cannot use the same canvas during multiple render() operations").
    let cancelled = false;

    // Cancel any in-flight render task before starting a new one.
    if (renderTaskRef.current) {
      renderTaskRef.current.cancel();
      renderTaskRef.current = null;
    }

    // Load and render the page
    document
      .getPage(pageNumber)
      .then((page) => {
        // A newer effect run (or unmount) superseded this one while getPage was
        // resolving -- do not touch the canvas.
        if (cancelled) {
          return;
        }

        const viewport = page.getViewport({ scale });

        // Set canvas dimensions to match viewport
        canvas.height = viewport.height;
        canvas.width = viewport.width;

        // Prepare render context
        const renderContext = {
          canvasContext: context,
          viewport: viewport,
        };

        // Render the page
        const renderTask = page.render(renderContext);
        renderTaskRef.current = renderTask;

        return renderTask.promise.then(() => {
          if (cancelled) {
            return;
          }
          setIsRendering(false);
          if (onPageLoad) {
            onPageLoad(page);
          }
        });
      })
      .catch((err) => {
        // Ignore cancelled renders
        if (err.name === 'RenderingCancelledException') {
          return;
        }

        console.error(`Failed to render page ${pageNumber}:`, err);
        setError(err.message || 'Failed to render page');
        setIsRendering(false);
      });

    // Cleanup
    return () => {
      cancelled = true;
      if (renderTaskRef.current) {
        renderTaskRef.current.cancel();
        renderTaskRef.current = null;
      }
    };
  }, [document, pageNumber, scale, onPageLoad]);

  return (
    <div className={`pdf-page relative ${className}`}>
      <canvas
        ref={canvasRef}
        className="shadow-lg"
        style={{ display: 'block', margin: '0 auto' }}
      />
      {isRendering && (
        <div className="absolute inset-0 flex items-center justify-center bg-gray-100 bg-opacity-50">
          <div className="animate-spin w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full" />
        </div>
      )}
      {error && (
        <div className="absolute inset-0 flex items-center justify-center bg-red-50">
          <p className="text-red-600 text-sm">{error}</p>
        </div>
      )}
    </div>
  );
};
