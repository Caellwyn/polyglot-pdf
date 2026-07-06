/**
 * PDFPage Component
 *
 * Renders a single page of a PDF document on a canvas element.
 *
 * Ported from schema-editor/src/components/PDFPage.tsx (copy-then-diverge,
 * bd polyglot-pdf-vfkv); the editor's Tailwind classes are replaced with the
 * pdf-view.css classes since the main app has no Tailwind.
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
      // The cancelled run skips its own setIsRendering(false) (it must not set
      // state after cleanup); clear it here so a superseded-but-still-mounted
      // page cannot be left stuck showing the rendering spinner.
      setIsRendering(false);
      if (renderTaskRef.current) {
        renderTaskRef.current.cancel();
        renderTaskRef.current = null;
      }
    };
  }, [document, pageNumber, scale, onPageLoad]);

  return (
    <div className={`pdf-view-page ${className}`}>
      <canvas ref={canvasRef} className="pdf-view-page__canvas" />
      {isRendering && (
        <div className="pdf-view-page__overlay">
          <div className="pdf-view-page__spinner" aria-label="Rendering page" />
        </div>
      )}
      {error && (
        <div className="pdf-view-page__overlay pdf-view-page__overlay--error">
          <p className="pdf-view-page__error-text">{error}</p>
        </div>
      )}
    </div>
  );
};
