/**
 * React hook for loading and managing PDF documents
 */

import { useState, useEffect } from 'react';
import type { PDFDocumentProxy } from 'pdfjs-dist';
import { getPDFLib } from '../utils/pdfWorker';

export interface PDFDocumentState {
  document: PDFDocumentProxy | null;
  numPages: number;
  isLoading: boolean;
  error: string | null;
}

/**
 * Hook to load a PDF document from a URL
 *
 * @param pdfUrl - URL or path to the PDF file
 * @returns PDFDocumentState with document, loading status, and error
 *
 * @example
 * const { document, numPages, isLoading, error } = usePDFDocument('/path/to/file.pdf');
 */
export function usePDFDocument(pdfUrl: string | null): PDFDocumentState {
  const [document, setDocument] = useState<PDFDocumentProxy | null>(null);
  const [numPages, setNumPages] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Reset state when URL changes
    setDocument(null);
    setNumPages(0);
    setError(null);

    if (!pdfUrl) {
      return;
    }

    // Start loading
    setIsLoading(true);

    const pdfjsLib = getPDFLib();

    // Load the PDF document
    const loadingTask = pdfjsLib.getDocument(pdfUrl);

    // Per-run flag: React 18 StrictMode mounts/unmounts effects twice in dev, so
    // a stale run can resolve after its cleanup ran. Without this guard the
    // superseded run sets state on a destroyed task (surfacing as a spurious
    // "Worker was destroyed" error) and races the live run.
    let cancelled = false;
    let loadedDoc: PDFDocumentProxy | null = null;

    loadingTask.promise
      .then((pdfDoc) => {
        loadedDoc = pdfDoc;
        if (cancelled) {
          // This run was superseded; tear down the doc we just loaded.
          pdfDoc.destroy();
          return;
        }
        setDocument(pdfDoc);
        setNumPages(pdfDoc.numPages);
        setIsLoading(false);
        setError(null);
      })
      .catch((err) => {
        if (cancelled || err?.name === 'RenderingCancelledException') {
          return;
        }
        console.error('Failed to load PDF:', err);
        setError(err.message || 'Failed to load PDF');
        setIsLoading(false);
        setDocument(null);
        setNumPages(0);
      });

    // Cleanup: destroy the document/loading task when the URL changes or the
    // component unmounts. Track the loaded doc locally (the `document` state in
    // the closure is stale -- always null at cleanup time).
    return () => {
      cancelled = true;
      loadingTask.destroy();
      if (loadedDoc) {
        loadedDoc.destroy();
      }
    };
  }, [pdfUrl]);

  return {
    document,
    numPages,
    isLoading,
    error,
  };
}
