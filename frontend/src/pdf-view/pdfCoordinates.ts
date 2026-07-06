/**
 * PDF-to-screen coordinate transforms for field overlays.
 *
 * Ported from schema-editor/src/utils/pdfCoordinates.ts (copy-then-diverge,
 * bd polyglot-pdf-ogrt). Schema `pdf_position` coordinates are already
 * top-left-origin PDF points (PyMuPDF widget rects), so the screen transform
 * is a pure multiply by the render scale -- no Y-flip.
 */

import type { PDFPosition } from '../schema-forms/types/schema';

export interface ScreenPosition {
  x: number;
  y: number;
  width: number;
  height: number;
}

export function pdfToScreenCoords(pdfPos: PDFPosition, scale: number = 1.0): ScreenPosition {
  return {
    x: (pdfPos.x ?? 0) * scale,
    y: (pdfPos.y ?? 0) * scale,
    width: (pdfPos.width ?? 0) * scale,
    height: (pdfPos.height ?? 0) * scale,
  };
}

export function hasValidCoordinates(pos: PDFPosition | undefined): pos is PDFPosition {
  return (
    !!pos &&
    typeof pos.x === 'number' &&
    typeof pos.y === 'number' &&
    typeof pos.width === 'number' &&
    typeof pos.height === 'number' &&
    pos.width > 0 &&
    pos.height > 0
  );
}
