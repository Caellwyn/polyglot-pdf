/**
 * React hook for loading and managing PDF documents
 *
 * Ported from schema-editor/src/hooks/usePDFDocument.ts (copy-then-diverge,
 * bd polyglot-pdf-vfkv).
 */

import { resolveSessionToken } from "../shared/sessionCredential";
import { useState, useEffect } from 'react';
import type { PDFDocumentProxy } from 'pdfjs-dist';
import { getPDFLib } from './pdfWorker';
import { useAuth } from '../contexts/AuthContext';
import { resolveKitAssetUrl } from '../schema-forms/utils/pdfFiller';

export interface PDFDocumentState {
  document: PDFDocumentProxy | null;
  numPages: number;
  isLoading: boolean;
  error: string | null;
}

/**
 * Hook to load a PDF document from a URL
 *
 * @param pdfUrl - URL or path to the PDF file (a blob: URL works too)
 * @returns PDFDocumentState with document, loading status, and error
 */
export function usePDFDocument(pdfUrl: string | null): PDFDocumentState {
  const [document, setDocument] = useState<PDFDocumentProxy | null>(null);
  const [numPages, setNumPages] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { user } = useAuth();

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

    // Per-run flag: React 18 StrictMode mounts/unmounts effects twice in dev, so
    // a stale run can resolve after its cleanup ran. Without this guard the
    // superseded run sets state on a destroyed task (surfacing as a spurious
    // "Worker was destroyed" error) and races the live run.
    let cancelled = false;
    let loadedDoc: PDFDocumentProxy | null = null;
    let loadingTask: ReturnType<typeof pdfjsLib.getDocument> | null = null;
    let objectUrl: string | null = null;

    (async () => {
      let src = pdfUrl;
      if (pdfUrl.startsWith('/api/')) {
        // A PRIVATE kit's manifest path is the authenticated backend route
        // (bd polyglot-pdf-vccy). pdfjs getDocument cannot attach headers,
        // so fetch the bytes with the Bearer token and hand pdfjs a blob URL
        // (the same form FilledPreviewModal uses for filled bytes).
        // NO AWAIT ON THE SYNCHRONOUS PATH. This effect races its own
        // cleanup: usePDFDocument.cancelledFetch.test.tsx unmounts while the
        // fetch is pending, and even `await <non-promise>` costs a microtask
        // -- enough for cleanup to win so the fetch never starts at all.
        // resolveSessionToken returns a plain string for a client link and a
        // promise only on the Firebase path, so await ONLY when it actually
        // returned one.
        const maybeToken = resolveSessionToken(user);
        const token = typeof maybeToken === "string" || maybeToken === undefined
          ? maybeToken
          : await maybeToken;
        const resp = await fetch(resolveKitAssetUrl(pdfUrl), {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!resp.ok) {
          throw new Error(`Failed to load PDF (${resp.status})`);
        }
        const blobUrl = URL.createObjectURL(await resp.blob());
        if (cancelled) {
          // Cleanup already ran while the fetch was in flight and saw
          // objectUrl === null, so revoke HERE or the blob (a whole PDF of
          // bytes) leaks for the tab's lifetime (vccy fresh-eyes round 1).
          URL.revokeObjectURL(blobUrl);
          return;
        }
        objectUrl = blobUrl;
        src = objectUrl;
      }
      if (cancelled) {
        return;
      }
      loadingTask = pdfjsLib.getDocument(src);
      const pdfDoc = await loadingTask.promise;
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
    })().catch((err) => {
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
    // the closure is stale -- always null at cleanup time). The blob URL (only
    // set for backend-route fetches) is revoked here too.
    return () => {
      cancelled = true;
      if (loadingTask) {
        loadingTask.destroy();
      }
      if (loadedDoc) {
        loadedDoc.destroy();
      }
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [pdfUrl, user]);

  return {
    document,
    numPages,
    isLoading,
    error,
  };
}
