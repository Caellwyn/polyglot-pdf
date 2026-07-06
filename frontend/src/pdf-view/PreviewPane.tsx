/**
 * PreviewPane -- the Preview view-mode surface (bd polyglot-pdf-vxwj).
 *
 * P1.1 placeholder scope: renders the BLANK form PDF so the view mode, lazy
 * chunking, and layout shell are real. The live surface -- field overlays,
 * value painting, snap-to camera -- lands in the P1.2/P1.3 beads
 * (polyglot-pdf-ogrt / 35t0) on top of this mount point.
 *
 * Lazy-loaded from SchemaForm (React.lazy), so pdfjs stays out of the default
 * bundle while the preview flag is off.
 */

import React, { useCallback, useRef, useState } from 'react';
import type { PDFPageProxy } from 'pdfjs-dist';
import { usePDFDocument } from './usePDFDocument';
import { PDFPage } from './PDFPage';
import './pdf-view.css';

export interface PreviewPaneProps {
  pdfUrl?: string;
}

const MIN_SCALE = 0.5;
const MAX_SCALE = 2.0;

export default function PreviewPane({ pdfUrl }: PreviewPaneProps) {
  const { document: pdfDoc, numPages, isLoading, error } = usePDFDocument(pdfUrl ?? null);
  const [scale, setScale] = useState(1.0);
  const paneRef = useRef<HTMLDivElement>(null);
  const fitAppliedRef = useRef(false);

  // Fit-width once, off the first rendered page's unscaled dimensions.
  const handleFirstPageLoad = useCallback((page: PDFPageProxy) => {
    if (fitAppliedRef.current || !paneRef.current) return;
    fitAppliedRef.current = true;
    const pageWidth = page.getViewport({ scale: 1.0 }).width;
    const available = paneRef.current.clientWidth - 32;
    if (pageWidth > 0 && available > 0) {
      const fit = Math.min(MAX_SCALE, Math.max(MIN_SCALE, available / pageWidth));
      setScale(Math.round(fit * 100) / 100);
    }
  }, []);

  if (!pdfUrl) {
    return (
      <div className="pdf-preview-pane__notice">
        Preview mode needs the form's PDF, which is not configured for this
        form. Switch back to Simplified view.
      </div>
    );
  }

  return (
    <div className="pdf-preview-pane">
      <div className="pdf-preview-pane__banner">
        Preview mode (early): this shows the blank form for now. Your answers
        will appear here live in an upcoming update -- until then, use
        "Preview Filled PDF" below to see them filled in.
      </div>
      <div className="pdf-preview-pane__pages" ref={paneRef}>
        {error && <p className="pdf-preview-pane__error">Could not load the form PDF: {error}</p>}
        {!error && isLoading && <p className="pdf-preview-pane__loading">Loading the form...</p>}
        {pdfDoc &&
          Array.from({ length: numPages }, (_, i) => (
            <div key={i + 1} className="pdf-preview-modal__page">
              <PDFPage
                document={pdfDoc}
                pageNumber={i + 1}
                scale={scale}
                onPageLoad={i === 0 ? handleFirstPageLoad : undefined}
              />
              <div className="pdf-preview-pane__page-label">
                Page {i + 1} of {numPages}
              </div>
            </div>
          ))}
      </div>
    </div>
  );
}
