/**
 * FilledPreviewModal -- true preview of the filled PDF (bd polyglot-pdf-vfkv).
 *
 * Sends the user's current values through the SAME backend fill the
 * download/print buttons use (/api/fill-pdf, PyMuPDF) and renders the returned
 * bytes with pdf.js. What this modal shows IS the backend's own output -- not a
 * client-side approximation -- so it matches a downloaded fill exactly.
 *
 * Reached only via React.lazy(), so pdfjs-dist lives in this chunk and is
 * fetched only once the user actually opens a preview surface.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import type { PDFPageProxy } from 'pdfjs-dist';
import type { FormSchema } from '../schema-forms/types/schema';
import { fillPDF } from '../schema-forms/utils/pdfFiller';
import { unwrapFieldValue } from '../schema-forms/utils/fieldValue';
import { usePDFDocument } from './usePDFDocument';
import { PDFPage } from './PDFPage';
import './pdf-view.css';

export interface FilledPreviewModalProps {
  kitId: string;
  pdfUrl: string;
  schema: FormSchema;
  /** Wrapped FieldValue map straight from SchemaFormState (unwrapped here). */
  fieldValues: Record<string, any>;
  onClose: () => void;
}

const MIN_SCALE = 0.5;
const MAX_SCALE = 2.0;
const SCALE_STEP = 0.25;

export default function FilledPreviewModal({
  kitId,
  pdfUrl,
  schema,
  fieldValues,
  onClose,
}: FilledPreviewModalProps) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [fillError, setFillError] = useState<string | null>(null);
  const [scale, setScale] = useState(1.0);
  const pagesRef = useRef<HTMLDivElement>(null);
  const fitAppliedRef = useRef(false);

  // Fill exactly once per modal open, snapshotting the values as of opening
  // (a field changing mid-preview does not re-trigger the backend call; the
  // user reopens the preview for fresh values).
  useEffect(() => {
    let cancelled = false;
    let url: string | null = null;

    const unwrapped: Record<string, any> = {};
    for (const [fieldId, value] of Object.entries(fieldValues)) {
      unwrapped[fieldId] = unwrapFieldValue(value);
    }

    fillPDF(kitId, pdfUrl, unwrapped, schema)
      .then((bytes) => {
        if (cancelled) return;
        // Re-wrap so the Uint8Array is a plain-ArrayBuffer BlobPart (see the
        // same pattern in pdfFiller.downloadPDF).
        const blob = new Blob([new Uint8Array(bytes)], { type: 'application/pdf' });
        url = URL.createObjectURL(blob);
        setBlobUrl(url);
      })
      .catch((err) => {
        if (cancelled) return;
        console.error('[FilledPreviewModal] Fill for preview failed:', err);
        setFillError(err instanceof Error ? err.message : String(err));
      });

    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per open by design
  }, []);

  const { document: pdfDoc, numPages, isLoading, error: loadError } = usePDFDocument(blobUrl);

  // Fit-width once, off the first rendered page's unscaled dimensions.
  const handleFirstPageLoad = useCallback((page: PDFPageProxy) => {
    if (fitAppliedRef.current || !pagesRef.current) return;
    fitAppliedRef.current = true;
    const pageWidth = page.getViewport({ scale: 1.0 }).width;
    const available = pagesRef.current.clientWidth - 32;
    if (pageWidth > 0 && available > 0) {
      const fit = Math.min(MAX_SCALE, Math.max(MIN_SCALE, available / pageWidth));
      setScale(Math.round(fit * 100) / 100);
    }
  }, []);

  // Escape closes the modal.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const error = fillError || loadError;

  return (
    <div
      className="pdf-preview-modal__backdrop"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Filled PDF preview"
    >
      <div className="pdf-preview-modal" onClick={(e) => e.stopPropagation()}>
        <div className="pdf-preview-modal__toolbar">
          <span className="pdf-preview-modal__title">
            Preview: your form so far, exactly as it will print
          </span>
          <div className="pdf-preview-modal__controls">
            <button
              type="button"
              onClick={() => setScale((s) => Math.max(MIN_SCALE, s - SCALE_STEP))}
              disabled={scale <= MIN_SCALE}
              aria-label="Zoom out"
            >
              -
            </button>
            <span className="pdf-preview-modal__zoom">{Math.round(scale * 100)}%</span>
            <button
              type="button"
              onClick={() => setScale((s) => Math.min(MAX_SCALE, s + SCALE_STEP))}
              disabled={scale >= MAX_SCALE}
              aria-label="Zoom in"
            >
              +
            </button>
            <button
              type="button"
              className="pdf-preview-modal__close"
              onClick={onClose}
              aria-label="Close preview"
            >
              Close
            </button>
          </div>
        </div>
        <div className="pdf-preview-modal__pages" ref={pagesRef}>
          {error && (
            <p className="pdf-preview-modal__error">Could not generate the preview: {error}</p>
          )}
          {!error && (!blobUrl || isLoading) && (
            <p className="pdf-preview-modal__loading">Generating preview...</p>
          )}
          {pdfDoc &&
            Array.from({ length: numPages }, (_, i) => (
              <div key={i + 1} className="pdf-preview-modal__page">
                <PDFPage
                  document={pdfDoc}
                  pageNumber={i + 1}
                  scale={scale}
                  onPageLoad={i === 0 ? handleFirstPageLoad : undefined}
                />
                <div className="pdf-preview-modal__page-label">
                  Page {i + 1} of {numPages}
                </div>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}
