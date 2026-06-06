/**
 * Vitest Setup File
 * Runs before all tests
 */

import { expect, afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
import * as matchers from '@testing-library/jest-dom/matchers';

// Extend Vitest's expect with jest-dom matchers
expect.extend(matchers);

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
      getPage: vi.fn((pageNum) => Promise.resolve({
        getViewport: vi.fn(() => ({ width: 612, height: 792, scale: 1 })),
        render: vi.fn(() => ({ promise: Promise.resolve() })),
      })),
      destroy: vi.fn(),
    }),
    destroy: vi.fn(),
  })),
}));
