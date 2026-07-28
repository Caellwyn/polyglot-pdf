/**
 * PDF Coordinate Transformation Utilities
 *
 * Scales between the schema's stored field rects and on-screen pixels.
 *
 * IMPORTANT -- both are TOP-LEFT origin, so there is NO Y-axis flip here.
 * Although PDF's NATIVE coordinate system is bottom-left origin (y up), the
 * schema's pdf_position rects are NOT in that native space: they are emitted by
 * the producer (scripts/bakeoff/acroform_dump.py) from PyMuPDF widget.rect.y0,
 * and PyMuPDF normalizes to TOP-LEFT origin (y increases downward, like the
 * screen). So converting schema rect -> screen is a pure scale, and the inverse
 * is a pure unscale. Do NOT reintroduce a `pageHeight - y - height` flip -- it
 * would mirror every overlay vertically (verified visually in bd 7a9.6).
 *
 * Schema field rects (pdf_position): top-left origin, y down, points.
 * Screen coordinates (browser/DOM):   top-left origin, y down, pixels.
 */

import type { PDFPosition } from '../types/schema';

export interface ScreenPosition {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PageDimensions {
  width: number;
  height: number;
}

/**
 * Convert PDF coordinates to screen coordinates
 *
 * @param pdfPos - Position from schema (already in top-left screen format from PDF.js extraction)
 * @param pageHeight - Height of the PDF page in points (unused - kept for API compatibility)
 * @param scale - Current zoom scale (1.0 = 100%)
 * @returns Screen position (top-left origin, scaled)
 *
 * Note: Our extracted schemas use PDF.js coordinates which are already in screen/top-left format,
 * so we only need to scale, not transform the coordinate system.
 *
 * @example
 * const screenPos = pdfToScreenCoords(
 *   { x: 100, y: 300, width: 150, height: 30 },
 *   792,  // US Letter height (unused)
 *   1.5   // 150% zoom
 * );
 * // Returns: { x: 150, y: 450, width: 225, height: 45 }
 */
export function pdfToScreenCoords(
  pdfPos: PDFPosition,
  _pageHeight: number,  // Kept for API compatibility; unused since coords are already screen format
  scale: number = 1.0
): ScreenPosition {
  // Extract PDF coordinates (default to 0 if undefined)
  const pdfX = pdfPos.x ?? 0;
  const pdfY = pdfPos.y ?? 0;
  const pdfWidth = pdfPos.width ?? 0;
  const pdfHeight = pdfPos.height ?? 0;

  // Transform coordinates
  // Note: Our PDF schema coordinates are already in screen/top-left format
  // (extracted from PDF.js which uses screen coordinates)
  // So we just need to scale, not flip the Y-axis
  
  // X: Just scale
  const screenX = pdfX * scale;

  // Y: Just scale (coordinates already in top-left origin format)
  const screenY = pdfY * scale;

  // Width and height: Just scale
  const screenWidth = pdfWidth * scale;
  const screenHeight = pdfHeight * scale;

  return {
    x: screenX,
    y: screenY,
    width: screenWidth,
    height: screenHeight,
  };
}

/**
 * Convert screen coordinates back to PDF coordinates
 * (Exact inverse of pdfToScreenCoords)
 *
 * @param screenPos - Screen position (top-left origin, scaled)
 * @param _pageHeight - Height of the PDF page in points (unused - kept for API compatibility)
 * @param scale - Current zoom scale (1.0 = 100%)
 * @returns PDF position (top-left origin, unscaled)
 *
 * Note: Our schema coordinates are PDF.js / PyMuPDF rects, which are already in
 * top-left/screen format (the producer scripts/bakeoff/acroform_dump.py emits
 * widget rect.y0 from PyMuPDF, whose y increases downward from the top). So this
 * inverse only UNSCALES -- it does not flip the Y-axis -- to stay a true inverse
 * of pdfToScreenCoords (which also does not flip).
 */
export function screenToPdfCoords(
  screenPos: ScreenPosition,
  _pageHeight: number,  // Kept for API compatibility; unused since coords are already top-left format
  scale: number = 1.0
): PDFPosition {
  // Just unscale; coordinates are already in top-left origin format (no Y-flip).
  const x = screenPos.x / scale;
  const y = screenPos.y / scale;
  const width = screenPos.width / scale;
  const height = screenPos.height / scale;

  return {
    page: 0, // Page number not tracked in this conversion
    x,
    y,
    width,
    height,
  };
}

/**
 * Check if a PDF position has all required coordinate data
 *
 * @param pos - PDF position to validate
 * @returns true if position has x, y, width, and height
 */
export function hasValidCoordinates(pos: PDFPosition | undefined): boolean {
  if (!pos) return false;

  return (
    typeof pos.x === 'number' &&
    typeof pos.y === 'number' &&
    typeof pos.width === 'number' &&
    typeof pos.height === 'number' &&
    pos.width > 0 &&
    pos.height > 0
  );
}

/**
 * Why a field would draw NO overlay on the PDF preview, in plain language --
 * or null when it would draw fine (bd polyglot-pdf-g63j).
 *
 * The editor used to fail these silently: a field whose rect is absent/
 * degenerate, or whose page number does not exist in the document, simply never
 * matched a rendered page and vanished with no explanation -- which is how two
 * mis-labeled W-7 fields read as "phantom" for a human. Each mode gets its OWN
 * wording because each has a DIFFERENT fix: a missing rect means the widget was
 * never located, while a bad page number means the coordinates exist but point
 * off the document.
 *
 * `pageCount` is optional: schema-only contexts (validation with no PDF loaded)
 * pass nothing and simply skip the page-range half, exactly as
 * hasValidCoordinates degrades on an absent position.
 *
 * NOTE the page convention: schema pdf_position.page is ONE-BASED (the
 * extraction pipeline converts the 0-based dump page with an explicit +1), and
 * PDFViewer renders pages 1..numPages, so a page of 0 -- a rect that never got
 * that conversion -- is out of range and invisible, not page one.
 */
export function overlayBlockReason(
  pos: PDFPosition | undefined,
  pageCount?: number,
): string | null {
  if (!pos) {
    return 'No position recorded for this field, so it cannot be highlighted '
      + 'on the form preview';
  }
  if (!hasValidCoordinates(pos)) {
    return 'This field has no usable position (its recorded rectangle is '
      + 'missing or has zero size), so it cannot be highlighted on the form '
      + 'preview';
  }
  if (typeof pageCount === 'number' && pageCount > 0) {
    const page = pos.page;
    if (typeof page !== 'number' || !Number.isFinite(page)
        || page < 1 || page > pageCount) {
      return `This field claims page ${String(page)}, but the form has `
        + `${pageCount} page(s) -- it can never appear on the preview`;
    }
  }
  return null;
}

/**
 * Get standard US Letter page dimensions in points
 */
export const US_LETTER_PAGE: PageDimensions = {
  width: 612,  // 8.5 inches * 72 points/inch
  height: 792, // 11 inches * 72 points/inch
};

/**
 * Get standard A4 page dimensions in points
 */
export const A4_PAGE: PageDimensions = {
  width: 595,  // 210mm = 8.27 inches * 72 points/inch
  height: 842, // 297mm = 11.69 inches * 72 points/inch
};
