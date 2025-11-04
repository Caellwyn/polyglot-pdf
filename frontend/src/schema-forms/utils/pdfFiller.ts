/**
 * PDF Filler Utility
 *
 * Calls backend API to fill PDF forms using PyMuPDF (supports XFA forms).
 * Backend is stateless: receives data → fills PDF → returns bytes.
 *
 * @module pdfFiller
 */

import type { FormSchema } from '../types/schema';

/**
 * Get backend HTTP URL based on environment
 *
 * Development: http://localhost:8000
 * Production: https://voice-form-filler-773443099751.us-central1.run.app
 */
function getBackendHttpUrl(): string {
  // Check for custom URL override (for local dev)
  const customUrl = (window as any).__VFF_BACKEND_URL;
  if (customUrl) {
    // Convert WebSocket URL to HTTP if needed
    return customUrl.replace('ws://', 'http://').replace('wss://', 'https://').replace('/ws/fill', '');
  }

  // Use environment variable if set (production builds)
  if (import.meta.env.VITE_BACKEND_HTTP_URL) {
    return import.meta.env.VITE_BACKEND_HTTP_URL;
  }

  // Development mode: use localhost
  if (import.meta.env.DEV) {
    return 'http://localhost:8000';
  }

  // Production fallback
  return 'https://voice-form-filler-773443099751.us-central1.run.app';
}

/**
 * Fill a PDF form with field values from schema form state
 *
 * Calls backend /api/fill-pdf endpoint which uses PyMuPDF to handle XFA forms.
 *
 * @param pdfUrl - URL to the original PDF file (e.g., '/pdfs/i-90.pdf')
 * @param fieldValues - Current form values (field_id → value)
 * @param schema - Form schema containing field metadata and PDF mappings
 * @returns Filled PDF as Uint8Array ready for download
 *
 * @example
 * const filledPDF = await fillPDF(
 *   '/pdfs/i-90.pdf',
 *   { 'p1_line1_aliennumber': '123456789' },
 *   schema
 * );
 * downloadPDF(filledPDF, 'i-90-filled.pdf');
 */
export async function fillPDF(
  pdfUrl: string,
  fieldValues: Record<string, any>,
  schema: FormSchema
): Promise<Uint8Array> {
  const backendUrl = getBackendHttpUrl();
  console.log('[pdfFiller] Calling backend to fill PDF:', pdfUrl);
  console.log('[pdfFiller] Backend URL:', backendUrl);
  console.log('[pdfFiller] Field values to fill:', Object.keys(fieldValues).length);

  // Extract PDF filename from URL
  const pdfFilename = pdfUrl.split('/').pop() || 'form.pdf';

  // Call backend endpoint
  const response = await fetch(`${backendUrl}/api/fill-pdf`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      pdf_filename: pdfFilename,
      field_values: fieldValues,
      form_schema: schema,
    }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    console.error('[pdfFiller] Backend error:', errorText);
    throw new Error(`PDF filling failed: ${response.statusText}`);
  }

  // Get PDF bytes from response
  const pdfBytes = await response.arrayBuffer();
  console.log('[pdfFiller] Received filled PDF:', pdfBytes.byteLength, 'bytes');

  return new Uint8Array(pdfBytes);
}


/**
 * Download a filled PDF to the user's computer
 *
 * @param pdfBytes - Filled PDF as Uint8Array
 * @param filename - Desired filename for download
 */
export function downloadPDF(pdfBytes: Uint8Array, filename: string): void {
  const blob = new Blob([pdfBytes], { type: 'application/pdf' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
  console.log(`[pdfFiller] Downloaded PDF: ${filename}`);
}
