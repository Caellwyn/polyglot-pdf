/**
 * Vitest Setup File
 * Runs before all tests
 */

import { expect, afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';
import * as matchers from '@testing-library/jest-dom/matchers';
// Augment Vitest's `expect` type with the jest-dom matcher signatures so `tsc`
// recognizes toBeInTheDocument/toBeDisabled/etc. The runtime extension below is
// what makes them work; this import is what makes the TYPES resolve under tsc.
import '@testing-library/jest-dom/vitest';

// Extend Vitest's expect with jest-dom matchers
expect.extend(matchers);

// Cleanup after each test
afterEach(() => {
  cleanup();
});
