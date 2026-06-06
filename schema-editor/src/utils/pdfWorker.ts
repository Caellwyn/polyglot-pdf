/**
 * PDF.js Worker Configuration
 *
 * Sets up the PDF.js worker for use with Vite's ES module system.
 * This must be called before any PDF.js operations.
 */

import * as pdfjsLib from 'pdfjs-dist';

let isWorkerInitialized = false;

/**
 * Initialize PDF.js worker
 * Safe to call multiple times - will only initialize once
 */
export function initializePDFWorker(): void {
  if (isWorkerInitialized) {
    return;
  }

  // Configure worker source for Vite
  // In production, this will be bundled correctly
  if (typeof window !== 'undefined') {
    pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
      'pdfjs-dist/build/pdf.worker.min.mjs',
      import.meta.url
    ).toString();
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

/**
 * Check if worker is initialized
 */
export function isWorkerReady(): boolean {
  return isWorkerInitialized;
}
