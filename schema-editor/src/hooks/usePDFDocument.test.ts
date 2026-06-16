/**
 * Unit tests for usePDFDocument hook
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { usePDFDocument } from './usePDFDocument';
import * as pdfjsLib from 'pdfjs-dist';

describe('usePDFDocument', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
