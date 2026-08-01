/**
 * Unit tests for usePDFDocument hook
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { usePDFDocument } from './usePDFDocument';
import * as pdfjsLib from 'pdfjs-dist';

/** The module-level pdfjs-dist mock's happy-path document (src/test/setup.ts).
 * Re-established per test because resetAllMocks() strips implementations, not
 * just call history -- see the beforeEach below. */
const mockPDFDocument = () => ({
  promise: Promise.resolve({
    numPages: 1,
    getPage: vi.fn(() => Promise.resolve({
      getViewport: vi.fn(() => ({ width: 612, height: 792, scale: 1 })),
      render: vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() })),
    })),
    destroy: vi.fn(),
  }),
  destroy: vi.fn(),
});

describe('usePDFDocument', () => {
  beforeEach(() => {
    // resetAllMocks, NOT clearAllMocks: pdfjs-dist is mocked at MODULE scope,
    // so the mock outlives each test. clearAllMocks wipes call history but does
    // NOT drain queued one-time implementations, so an unconsumed
    // mockReturnValueOnce would survive and fire on the NEXT test's first call
    // (bd polyglot-pdf-kas0, same class as polyglot-pdf-79tz). resetAllMocks
    // drains the queue -- but it also strips the setup.ts factory's default
    // implementation, so the happy path is re-established here per test.
    vi.resetAllMocks();
    vi.mocked(pdfjsLib.getDocument).mockImplementation(
      () => mockPDFDocument() as any
    );
  });

  it('should return null document when pdfUrl is null', () => {
    const { result } = renderHook(() => usePDFDocument(null));

    expect(result.current.document).toBeNull();
    expect(result.current.numPages).toBe(0);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('should set isLoading to true when loading starts', () => {
    const { result } = renderHook(() => usePDFDocument('/test.pdf'));

    expect(result.current.isLoading).toBe(true);
  });

  it('should load PDF document successfully', async () => {
    const { result } = renderHook(() => usePDFDocument('/test.pdf'));

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.document).toBeTruthy();
    expect(result.current.numPages).toBe(1);
    expect(result.current.error).toBeNull();
  });

  it('should handle loading errors', async () => {
    // Mock a failing PDF load
    vi.mocked(pdfjsLib.getDocument).mockReturnValueOnce({
      promise: Promise.reject(new Error('Failed to load')),
      destroy: vi.fn(),
    } as any);

    const { result } = renderHook(() => usePDFDocument('/bad.pdf'));

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.document).toBeNull();
    expect(result.current.numPages).toBe(0);
    expect(result.current.error).toBe('Failed to load');
  });

  it('should reset state when URL changes', async () => {
    const { result, rerender } = renderHook(
      ({ url }) => usePDFDocument(url),
      { initialProps: { url: '/test1.pdf' } }
    );

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.document).toBeTruthy();

    // Change URL
    rerender({ url: '/test2.pdf' });

    expect(result.current.isLoading).toBe(true);
  });

  // --- once-mock leak guard (bd polyglot-pdf-kas0) -------------------------
  // These two run as a PAIR and must stay adjacent and in this order. The first
  // deliberately queues a once-rejection it never spends; the second is the
  // victim that would inherit it under clearAllMocks. Revert the beforeEach to
  // vi.clearAllMocks() and the second test fails -- that is the regression.

  it('queues an UNCONSUMED once-mock (setup for the leak guard below)', () => {
    // The rejection is never awaited (that is the point), so attach a no-op
    // handler: an unhandled rejection makes vitest exit NON-ZERO even when
    // every test passes, which would fail CI. The once-impl stays unconsumed,
    // so the guard below still bites.
    const neverConsumed = Promise.reject(new Error('leaked from the previous test'));
    neverConsumed.catch(() => {});
    vi.mocked(pdfjsLib.getDocument).mockReturnValueOnce({
      promise: neverConsumed,
      destroy: vi.fn(),
    } as any);
    // Intentionally never renders the hook, so the queued once-impl is left
    // unconsumed for the next test to (not) inherit.
    expect(vi.isMockFunction(pdfjsLib.getDocument)).toBe(true);
  });

  it('does not inherit the previous test\'s unconsumed once-mock', async () => {
    const { result } = renderHook(() => usePDFDocument('/clean.pdf'));

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    // If the once-rejection leaked, error would be 'leaked from the previous
    // test' and document would be null.
    expect(result.current.error).toBeNull();
    expect(result.current.document).toBeTruthy();
  });

  it('should cleanup document on unmount', async () => {
    const destroyMock = vi.fn();
    const mockDoc = {
      numPages: 1,
      destroy: destroyMock,
    };

    vi.mocked(pdfjsLib.getDocument).mockReturnValueOnce({
      promise: Promise.resolve(mockDoc as any),
      destroy: vi.fn(),
    } as any);

    const { result, unmount } = renderHook(() => usePDFDocument('/test.pdf'));

    // Wait for the load to RESOLVE so the effect captured loadedDoc -- the cleanup
    // only destroys a doc it actually loaded. Asserting on result.current (the
    // hook's real output), not the test's own mockDoc local (bd polyglot-pdf-840i).
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
      expect(result.current.document).toBe(mockDoc);
    });

    unmount();

    // The effect's cleanup must destroy the loaded document (usePDFDocument.ts:87).
    expect(destroyMock).toHaveBeenCalledTimes(1);
  });
});
