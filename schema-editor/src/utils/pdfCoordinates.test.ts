/**
 * Unit tests for PDF coordinate transformation utilities
 */

import { describe, it, expect } from 'vitest';
import {
  pdfToScreenCoords,
  screenToPdfCoords,
  hasValidCoordinates,
  US_LETTER_PAGE,
  A4_PAGE,
} from './pdfCoordinates';

describe('pdfCoordinates', () => {
  describe('pdfToScreenCoords', () => {
    it('should convert PDF coords to screen coords at scale 1.0', () => {
      const result = pdfToScreenCoords(
        { page: 1, x: 100, y: 700, width: 150, height: 30 },
        792, // US Letter height (unused; coords already top-left)
        1.0
      );

      expect(result).toEqual({
        x: 100,
        y: 700,  // already top-left; just scaled (no Y-flip)
        width: 150,
        height: 30,
      });
    });

    it('should scale coordinates correctly at 1.5x zoom', () => {
      const result = pdfToScreenCoords(
        { page: 1, x: 100, y: 700, width: 150, height: 30 },
        792,
        1.5
      );

      expect(result).toEqual({
        x: 150,   // 100 * 1.5
        y: 1050,  // 700 * 1.5 (no Y-flip)
        width: 225,  // 150 * 1.5
        height: 45,  // 30 * 1.5
      });
    });

    it('should scale coordinates correctly at 0.5x zoom', () => {
      const result = pdfToScreenCoords(
        { page: 1, x: 100, y: 700, width: 150, height: 30 },
        792,
        0.5
      );

      expect(result).toEqual({
        x: 50,    // 100 * 0.5
        y: 350,   // 700 * 0.5 (no Y-flip)
        width: 75,   // 150 * 0.5
        height: 15,  // 30 * 0.5
      });
    });

    it('should handle field at top of page (y near 0)', () => {
      const result = pdfToScreenCoords(
        { page: 1, x: 50, y: 10, width: 100, height: 20 },
        792,
        1.0
      );

      expect(result).toEqual({
        x: 50,
        y: 10,  // small y = near top (top-left origin)
        width: 100,
        height: 20,
      });
    });

    it('should handle field at bottom of page (y near pageHeight)', () => {
      const result = pdfToScreenCoords(
        { page: 1, x: 50, y: 752, width: 100, height: 20 },
        792,
        1.0
      );

      expect(result).toEqual({
        x: 50,
        y: 752,  // large y = near bottom (top-left origin)
        width: 100,
        height: 20,
      });
    });

    it('should default undefined values to 0', () => {
      const result = pdfToScreenCoords(
        { page: 1 }, // No x, y, width, height
        792,
        1.0
      );

      expect(result).toEqual({
        x: 0,
        y: 0,  // defaults to 0 (no Y-flip)
        width: 0,
        height: 0,
      });
    });

    it('should use scale 1.0 when scale not provided', () => {
      const result = pdfToScreenCoords(
        { page: 1, x: 100, y: 700, width: 150, height: 30 },
        792
        // No scale parameter
      );

      expect(result.x).toBe(100);
      expect(result.width).toBe(150);
    });
  });

  describe('screenToPdfCoords', () => {
    it('should convert screen coords back to PDF coords', () => {
      const result = screenToPdfCoords(
        { x: 100, y: 700, width: 150, height: 30 },
        792,
        1.0
      );

      expect(result).toEqual({
        page: 0, // Not tracked
        x: 100,
        y: 700,  // just unscaled (no Y-flip)
        width: 150,
        height: 30,
      });
    });

    it('should unscale coordinates at 1.5x zoom', () => {
      const result = screenToPdfCoords(
        { x: 150, y: 1050, width: 225, height: 45 },
        792,
        1.5
      );

      expect(result).toEqual({
        page: 0,
        x: 100,   // 150 / 1.5
        y: 700,   // 1050 / 1.5 (no Y-flip)
        width: 150,  // 225 / 1.5
        height: 30,  // 45 / 1.5
      });
    });

    it('should be inverse of pdfToScreenCoords', () => {
      const originalPdf = { page: 1, x: 123, y: 456, width: 200, height: 40 };
      const scale = 1.25;
      const pageHeight = 792;

      const screen = pdfToScreenCoords(originalPdf, pageHeight, scale);
      const backToPdf = screenToPdfCoords(screen, pageHeight, scale);

      expect(backToPdf.x).toBeCloseTo(originalPdf.x, 5);
      expect(backToPdf.y).toBeCloseTo(originalPdf.y, 5);
      expect(backToPdf.width).toBeCloseTo(originalPdf.width, 5);
      expect(backToPdf.height).toBeCloseTo(originalPdf.height, 5);
    });
  });

  describe('hasValidCoordinates', () => {
    it('should return true for valid coordinates', () => {
      const pos = { page: 1, x: 100, y: 200, width: 150, height: 30 };
      expect(hasValidCoordinates(pos)).toBe(true);
    });

    it('should return false for undefined position', () => {
      expect(hasValidCoordinates(undefined)).toBe(false);
    });

    it('should return false when x is missing', () => {
      const pos = { page: 1, y: 200, width: 150, height: 30 } as any;
      expect(hasValidCoordinates(pos)).toBe(false);
    });

    it('should return false when y is missing', () => {
      const pos = { page: 1, x: 100, width: 150, height: 30 } as any;
      expect(hasValidCoordinates(pos)).toBe(false);
    });

    it('should return false when width is missing', () => {
      const pos = { page: 1, x: 100, y: 200, height: 30 } as any;
      expect(hasValidCoordinates(pos)).toBe(false);
    });

    it('should return false when height is missing', () => {
      const pos = { page: 1, x: 100, y: 200, width: 150 } as any;
      expect(hasValidCoordinates(pos)).toBe(false);
    });

    it('should return false when width is 0', () => {
      const pos = { page: 1, x: 100, y: 200, width: 0, height: 30 };
      expect(hasValidCoordinates(pos)).toBe(false);
    });

    it('should return false when height is 0', () => {
      const pos = { page: 1, x: 100, y: 200, width: 150, height: 0 };
      expect(hasValidCoordinates(pos)).toBe(false);
    });

    it('should return false when width is negative', () => {
      const pos = { page: 1, x: 100, y: 200, width: -10, height: 30 };
      expect(hasValidCoordinates(pos)).toBe(false);
    });

    it('should return false when height is negative', () => {
      const pos = { page: 1, x: 100, y: 200, width: 150, height: -5 };
      expect(hasValidCoordinates(pos)).toBe(false);
    });
  });

  describe('Page dimension constants', () => {
    it('should have correct US Letter dimensions', () => {
      expect(US_LETTER_PAGE.width).toBe(612);  // 8.5" * 72 pts/in
      expect(US_LETTER_PAGE.height).toBe(792); // 11" * 72 pts/in
    });

    it('should have correct A4 dimensions', () => {
      expect(A4_PAGE.width).toBe(595);  // ~8.27" * 72 pts/in
      expect(A4_PAGE.height).toBe(842); // ~11.69" * 72 pts/in
    });
  });
});
