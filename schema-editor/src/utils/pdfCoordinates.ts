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
 * @param pdfPos - Position from schema (bottom-left origin)
 * @param pageHeight - Height of the PDF page in points
 * @param scale - Current zoom scale (1.0 = 100%)
 * @returns Screen position (top-left origin, scaled)
 *
 * @example
 * const screenPos = pdfToScreenCoords(
 *   { x: 100, y: 700, width: 150, height: 30 },
 *   792,  // US Letter height
 *   1.5   // 150% zoom
 * );
 * // Returns: { x: 150, y: 93, width: 225, height: 45 }
 */
export function pdfToScreenCoords(
  pdfPos: PDFPosition,
  pageHeight: number,
  scale: number = 1.0
): ScreenPosition {
  // Extract PDF coordinates (default to 0 if undefined)
  const pdfX = pdfPos.x ?? 0;
  const pdfY = pdfPos.y ?? 0;
  const pdfWidth = pdfPos.width ?? 0;
  const pdfHeight = pdfPos.height ?? 0;

  // Transform coordinates
  // X: Same direction, just scale
  const screenX = pdfX * scale;

  // Y: Flip axis (PDF origin is bottom-left, screen is top-left)
  // Formula: screenY = (pageHeight - pdfY - pdfHeight) * scale
  const screenY = (pageHeight - pdfY - pdfHeight) * scale;

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
 * (Inverse of pdfToScreenCoords)
 *
 * @param screenPos - Screen position (top-left origin, scaled)
 * @param pageHeight - Height of the PDF page in points
 * @param scale - Current zoom scale (1.0 = 100%)
 * @returns PDF position (bottom-left origin, unscaled)
 */
export function screenToPdfCoords(
  screenPos: ScreenPosition,
  pageHeight: number,
  scale: number = 1.0
): PDFPosition {
  // Unscale first
  const x = screenPos.x / scale;
  const width = screenPos.width / scale;
  const height = screenPos.height / scale;

  // Flip Y axis back to PDF coordinates
  const y = pageHeight - (screenPos.y / scale) - height;

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
