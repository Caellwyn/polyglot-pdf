/**
 * PDF Filler Utility
 *
 * Calls backend API to fill PDF forms using PyMuPDF (supports XFA forms).
 * Backend is stateless: receives data -> fills PDF -> returns bytes.
 *
 * @module pdfFiller
 */

import type { FormSchema } from '../types/schema';
import { getDevConfig } from '../../shared/config';

/**
 * Get backend HTTP URL based on environment
 *
 * Development: http://localhost:8000
 * Production: Uses current domain (Firebase Hosting with rewrites to Cloud Run)
 */
export function getBackendHttpUrl(): string {
  // Check for custom URL override (for local dev). Use getDevConfig() so the
  // override is read from window OR (localhost-gated) localStorage -- the SAME
  // resolution config.ts uses for the WS URL. Reading window.__VFF_BACKEND_URL
  // directly here meant the HTTP form-list/PDF fetches ignored a localStorage
  // override that the WS honored, so they hit the wrong backend after a reload
  // (bd polyglot-pdf-g8w; the harness sets the override in localStorage).
  const dev = getDevConfig();
  if (dev.enabled) {
    // Convert WebSocket URL to HTTP if needed
    return dev.backendUrl.replace('ws://', 'http://').replace('wss://', 'https://').replace('/ws/fill', '');
  }

  // Use environment variable if set (production builds)
  if (import.meta.env.VITE_BACKEND_HTTP_URL) {
    return import.meta.env.VITE_BACKEND_HTTP_URL;
  }

  // Production: Use current domain (Firebase Hosting rewrites to Cloud Run)
  // Check if NOT in dev mode to ensure this runs in production
  if (!import.meta.env.DEV || import.meta.env.PROD) {
    const protocol = window.location.protocol; // http: or https:
    const host = window.location.host;
    return `${protocol}//${host}`;
  }

  // Development mode fallback: use localhost
  return 'http://localhost:8000';
}

/**
 * Fill a PDF form with field values from schema form state
 *
 * Calls backend /api/fill-pdf endpoint which uses PyMuPDF to handle XFA forms.
 *
 * @param kitId - Selected form kit identifier (matches manifest entry)
 * @param pdfUrl - URL to the original PDF file (e.g., '/form-kits/i-90/form.pdf')
 * @param fieldValues - Current form values (field_id -> value)
 * @param schema - Form schema containing field metadata and PDF mappings
 * @returns Filled PDF as Uint8Array ready for download
 *
 * @example
 * const filledPDF = await fillPDF(
 *   '/form-kits/i-90/form.pdf',
 *   { 'p1_line1_aliennumber': '123456789' },
 *   schema
 * );
 * downloadPDF(filledPDF, 'i-90-filled.pdf');
 */
export async function fillPDF(
  kitId: string,
  pdfUrl: string | undefined,
  fieldValues: Record<string, any>,
  schema: FormSchema,
  // Fresh-token callback (mirrors the WS connection's getToken, bd wq0):
  // /api/fill-pdf is auth-gated (bd polyglot-pdf-z2is). Optional so local-dev
  // callers against a VFF_DISABLE_AUTH backend keep working without one.
  getToken?: () => Promise<string | undefined>
): Promise<Uint8Array> {
  if (!pdfUrl) {
    throw new Error("PDF URL is required to fill the form");
  }
  const backendUrl = getBackendHttpUrl();
  console.log('[pdfFiller] Calling backend to fill PDF:', pdfUrl, 'kit:', kitId);
  console.log('[pdfFiller] Backend URL:', backendUrl);
  console.log('[pdfFiller] Field values to fill:', Object.keys(fieldValues).length);

  // DEBUG: Log radio/checkbox values specifically
  console.log('[pdfFiller] === RADIO/CHECKBOX VALUES ===');
  Object.entries(fieldValues).forEach(([key, value]) => {
    if (key.includes('checkbox') || key.includes('male')) {
      console.log(`  ${key} = ${JSON.stringify(value)}`);
    }
  });
  console.log('[pdfFiller] === END RADIO/CHECKBOX VALUES ===');

  // Extract PDF filename from URL
  const pdfFilename = pdfUrl.split('/').pop() || 'form.pdf';

  const requestPayload = {
    kit_id: kitId,
    pdf_filename: pdfFilename,
    field_values: fieldValues,
    form_schema: schema,
  };

  console.log('[pdfFiller] Request URL:', `${backendUrl}/api/fill-pdf`);
  console.log('[pdfFiller] Request payload:', {
    kit_id: kitId,
    pdf_filename: pdfFilename,
    field_count: Object.keys(fieldValues).length,
    schema_fields: schema.fields?.length || 0,
  });

  try {
    // Attach the Firebase ID token when a getter was provided; the backend's
    // require_auth 401s without it (VFF_DISABLE_AUTH covers local dev).
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    const token = getToken ? await getToken() : undefined;
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    // Call backend endpoint
    const response = await fetch(`${backendUrl}/api/fill-pdf`, {
      method: 'POST',
      headers,
      body: JSON.stringify(requestPayload),
    });

    console.log('[pdfFiller] Response status:', response.status, response.statusText);

    if (!response.ok) {
      const errorText = await response.text();
      console.error('[pdfFiller] Backend error response:', errorText);
      throw new Error(`PDF filling failed: ${response.status} ${response.statusText} - ${errorText}`);
    }

    // Get PDF bytes from response
    const pdfBytes = await response.arrayBuffer();
    console.log('[pdfFiller] Received filled PDF:', pdfBytes.byteLength, 'bytes');

    return new Uint8Array(pdfBytes);
  } catch (error) {
    console.error('[pdfFiller] Fetch error:', error);
    console.error('[pdfFiller] Error details:', {
      name: error instanceof Error ? error.name : 'Unknown',
      message: error instanceof Error ? error.message : String(error),
      backendUrl,
      pdfFilename,
    });
    throw error;
  }
}


/**
 * Download a filled PDF to the user's computer
 *
 * @param pdfBytes - Filled PDF as Uint8Array
 * @param filename - Desired filename for download
 */
export function downloadPDF(pdfBytes: Uint8Array, filename: string): void {
  // Re-wrap in a fresh ArrayBuffer-backed Uint8Array: under TS 5.x lib.dom a
  // Uint8Array<ArrayBufferLike> (which may be SharedArrayBuffer-backed) is not a
  // BlobPart. new Uint8Array(view) copies into a plain ArrayBuffer, which is.
  const blob = new Blob([new Uint8Array(pdfBytes)], { type: 'application/pdf' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
  console.log(`[pdfFiller] Downloaded PDF: ${filename}`);
}

/**
 * Print a filled PDF using the browser's print dialog
 *
 * Opens the PDF in a new window and triggers the print dialog.
 * Works on tablets and desktops.
 *
 * @param pdfBytes - Filled PDF as Uint8Array
 */
export function printPDF(pdfBytes: Uint8Array): void {
  // See downloadPDF: re-wrap so the Uint8Array is a valid BlobPart under TS 5.x.
  const blob = new Blob([new Uint8Array(pdfBytes)], { type: 'application/pdf' });
  const url = URL.createObjectURL(blob);

  // Open PDF in new window
  const printWindow = window.open(url, '_blank');

  if (printWindow) {
    // Wait for PDF to load, then trigger print dialog
    printWindow.onload = () => {
      printWindow.print();
      // Clean up blob URL after a delay (to allow printing)
      setTimeout(() => {
        URL.revokeObjectURL(url);
      }, 1000);
    };
    console.log('[pdfFiller] Print dialog opened for PDF');
  } else {
    // Popup blocked - fall back to download
    console.warn('[pdfFiller] Print window blocked, falling back to download');
    const link = document.createElement('a');
    link.href = url;
    link.download = 'form-filled.pdf';
    link.click();
    URL.revokeObjectURL(url);
  }
}
