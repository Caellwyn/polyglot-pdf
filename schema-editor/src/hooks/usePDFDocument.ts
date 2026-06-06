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

    loadingTask.promise
      .then((pdfDoc) => {
        setDocument(pdfDoc);
        setNumPages(pdfDoc.numPages);
        setIsLoading(false);
        setError(null);
      })
      .catch((err) => {
        console.error('Failed to load PDF:', err);
        setError(err.message || 'Failed to load PDF');
        setIsLoading(false);
        setDocument(null);
        setNumPages(0);
      });

    // Cleanup: Destroy the document when component unmounts or URL changes
    return () => {
      loadingTask.destroy();
      if (document) {
        document.destroy();
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
