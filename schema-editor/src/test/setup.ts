/**
 * Vitest Setup File
 * Runs before all tests
 */

import { expect, afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
import * as matchers from '@testing-library/jest-dom/matchers';
// Augment Vitest's `expect` type with the jest-dom matcher signatures so `tsc`
// recognizes toBeInTheDocument/toBeDisabled/etc. The runtime extension below is
// what makes them work; this import is what makes the TYPES resolve under tsc.
import '@testing-library/jest-dom/vitest';

// Extend Vitest's expect with jest-dom matchers
expect.extend(matchers);

// jsdom does not implement Element.scrollIntoView; FieldList's auto-scroll
// effect calls it from a deferred setTimeout when a field is selected, which
// otherwise throws an uncaught TypeError after the test body completes. Stub it
// so selection-driven tests run clean.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = vi.fn();
}

// Cleanup after each test
afterEach(() => {
  cleanup();
});

// Mock PDF.js worker for tests
vi.mock('pdfjs-dist', () => ({
  GlobalWorkerOptions: {
    workerSrc: '',
  },
  getDocument: vi.fn(() => ({
    promise: Promise.resolve({
      numPages: 1,
      getPage: vi.fn(() => Promise.resolve({
        getViewport: vi.fn(() => ({ width: 612, height: 792, scale: 1 })),
        render: vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() })),
      })),
      destroy: vi.fn(),
    }),
    destroy: vi.fn(),
  })),
}));
