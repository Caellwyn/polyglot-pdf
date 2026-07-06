/**
 * PreviewPane -- the Preview view-mode surface (bd polyglot-pdf-vxwj shell,
 * live surface bd polyglot-pdf-ogrt).
 *
 * Renders the blank form PDF with fill-state field overlays: the user's
 * answers paint into their printed rects live as the voice session (or a
 * manual edit) fills them. SchemaForm passes the wrapped FieldValue map down
 * on every schemaFormStateChange, so no extra subscription lives here.
 * Read-only; click-to-edit and the snap-to camera are later beads
 * (phase 2 / polyglot-pdf-35t0).
 *
 * Lazy-loaded from SchemaForm (React.lazy), so pdfjs stays out of the default
 * bundle while the preview flag is off.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import type { PDFPageProxy } from 'pdfjs-dist';
import type { FormSchema } from '../schema-forms/types/schema';
import { usePDFDocument } from './usePDFDocument';
import { hasValidCoordinates } from './pdfCoordinates';
import { PDFViewer } from './PDFViewer';
import './pdf-view.css';

export interface PreviewPaneProps {
  pdfUrl?: string;
  schema: FormSchema;
  /** Wrapped FieldValue map from SchemaFormState (fresh on every change). */
  fieldValues: Record<string, any>;
  currentFieldId?: string | null;
}

const MIN_SCALE = 0.5;
const MAX_SCALE = 2.0;

export default function PreviewPane({
  pdfUrl,
  schema,
  fieldValues,
  currentFieldId,
}: PreviewPaneProps) {
  const { document: pdfDoc, numPages, isLoading, error } = usePDFDocument(pdfUrl ?? null);
  const [scale, setScale] = useState(1.0);
  const paneRef = useRef<HTMLDivElement>(null);
  const fitAppliedRef = useRef(false);

  // QA surface: any field that cannot paint (no usable rect) is listed once.
  useEffect(() => {
    const unpositioned = schema.fields.filter((f) => !hasValidCoordinates(f.pdf_position));
    if (unpositioned.length > 0) {
      console.debug(
        `[PreviewPane] ${unpositioned.length} field(s) lack a usable pdf_position and will not paint:`,
        unpositioned.map((f) => f.id)
      );
    }
  }, [schema]);

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
        Preview mode: your answers appear on the real form as you go. Colors:
        orange = current field, blue = filled, green = confirmed. For the
        exact print output, use "Preview Filled PDF" below.
      </div>
      <div className="pdf-preview-pane__pages" ref={paneRef}>
        {error && <p className="pdf-preview-pane__error">Could not load the form PDF: {error}</p>}
        {!error && isLoading && <p className="pdf-preview-pane__loading">Loading the form...</p>}
        {pdfDoc && (
          <PDFViewer
            document={pdfDoc}
            numPages={numPages}
            scale={scale}
            fields={schema.fields}
            fieldValues={fieldValues}
            currentFieldId={currentFieldId}
            onFirstPageLoad={handleFirstPageLoad}
          />
        )}
      </div>
    </div>
  );
}
