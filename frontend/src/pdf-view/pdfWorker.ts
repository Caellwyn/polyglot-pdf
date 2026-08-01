/**
 * PDF.js Worker Configuration
 *
 * Sets up the PDF.js worker for use with Vite's ES module system.
 * This must be called before any PDF.js operations.
 *
 * Ported from schema-editor/src/utils/pdfWorker.ts (copy-then-diverge,
 * bd polyglot-pdf-vfkv). Everything in pdf-view/ that imports pdfjs-dist is
 * reached only via a React.lazy() chunk, so the default bundle never pulls
 * pdf.js in -- it loads when the user first opens a preview surface.
 *
 * The LEGACY pdf.js build is required here: the modern build uses top-level
 * await, which this app's Vite target (es2020, vite.config.schema.ts) rejects
 * at build time. The editor gets away with the modern build only because its
 * own Vite config targets higher.
 */

import * as pdfjsLib from 'pdfjs-dist/legacy/build/pdf.mjs';
// The ?url import (not new URL(..., import.meta.url)) is required: Vite serves
// it through its module pipeline in dev, whereas the raw-URL form 403s under
// the worktree node_modules junction (dev-server fs allowlist).
import pdfWorkerUrl from 'pdfjs-dist/legacy/build/pdf.worker.min.mjs?url';

let isWorkerInitialized = false;

/**
 * Initialize PDF.js worker
 * Safe to call multiple times - will only initialize once
 */
export function initializePDFWorker(): void {
  if (isWorkerInitialized) {
    return;
  }

  if (typeof window !== 'undefined') {
    pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;
  }

  isWorkerInitialized = true;
}

/**
 * Get the PDF.js library instance
 */
export function getPDFLib() {
  initializePDFWorker();
  return pdfjsLib;
}
