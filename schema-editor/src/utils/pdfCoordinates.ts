/**
 * PDF Coordinate Transformation Utilities
 *
 * Converts between PDF coordinate system and screen coordinate system.
 *
 * PDF Coordinates (from schema):
 * - Origin: bottom-left corner
 * - Y-axis: increases upward
 * - Units: points (72 points = 1 inch)
 *
 * Screen Coordinates (browser/DOM):
 * - Origin: top-left corner
 * - Y-axis: increases downward
 * - Units: pixels
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
