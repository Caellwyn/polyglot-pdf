/**
 * Unit tests for PDF.js Worker Configuration
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { initializePDFWorker, getPDFLib, isWorkerReady } from './pdfWorker';
import * as pdfjsLib from 'pdfjs-dist';

describe('pdfWorker', () => {
  beforeEach(() => {
    // Reset worker initialization state
    vi.resetModules();
  });

  describe('initializePDFWorker', () => {
    it('should set GlobalWorkerOptions.workerSrc when window is defined', () => {
      initializePDFWorker();
      expect(pdfjsLib.GlobalWorkerOptions.workerSrc).toBeTruthy();
    });

    it('should only initialize once when called multiple times', () => {
      initializePDFWorker();
      const firstWorkerSrc = pdfjsLib.GlobalWorkerOptions.workerSrc;

      initializePDFWorker();
      initializePDFWorker();

      expect(pdfjsLib.GlobalWorkerOptions.workerSrc).toBe(firstWorkerSrc);
    });

    it('should set isWorkerReady to true after initialization', () => {
      initializePDFWorker();
      expect(isWorkerReady()).toBe(true);
    });
  });

  describe('getPDFLib', () => {
    it('should initialize worker and return pdfjsLib', () => {
      const lib = getPDFLib();
      expect(lib).toBe(pdfjsLib);
      expect(isWorkerReady()).toBe(true);
    });
  });

  describe('isWorkerReady', () => {
    it('should return true after worker is initialized', () => {
      initializePDFWorker();
      expect(isWorkerReady()).toBe(true);
    });
  });
});
