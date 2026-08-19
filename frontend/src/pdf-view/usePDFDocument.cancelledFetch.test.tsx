// @vitest-environment jsdom
//
// Pin for the private-kit blob-URL leak (bd polyglot-pdf-vccy, fresh-eyes
// round 1): when the effect is cancelled while the /api/ PDF fetch is still
// in flight, cleanup runs before objectUrl exists -- so the late-resolving
// fetch must revoke the blob URL it just created, or a whole PDF of bytes
// leaks for the tab's lifetime on every mid-load view toggle.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { usePDFDocument } from './usePDFDocument';

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ user: null }),
}));

vi.mock('./pdfWorker', () => ({
  getPDFLib: () => ({
    getDocument: () => ({
      promise: new Promise(() => {}), // never resolves; irrelevant here
      destroy: () => {},
    }),
  }),
}));

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('usePDFDocument cancelled /api/ fetch (bd vccy)', () => {
  it('revokes the blob URL created by a fetch that resolves AFTER cleanup', async () => {
    // Mutation: revert the revoke-on-cancelled branch in the fetch path
    // (assign the blob straight to objectUrl with no cancelled check) --
    // this goes red.
    let resolveFetch: (r: unknown) => void = () => {};
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise((res) => { resolveFetch = res; })),
    );
    const created: string[] = [];
    const revoked: string[] = [];
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL: vi.fn(() => {
        const u = `blob:mock-${created.length}`;
        created.push(u);
        return u;
      }),
      revokeObjectURL: vi.fn((u: string) => { revoked.push(u); }),
    });

    const { unmount } = renderHook(() =>
      usePDFDocument('/api/form-kits/priv-kit/pdf'),
    );
    // Cancel while the fetch is still pending.
    unmount();
    // Let the fetch resolve AFTER cleanup already ran.
    resolveFetch({ ok: true, blob: async () => new Blob(['%PDF']) });
    await vi.waitFor(() => {
      expect(created).toHaveLength(1);
      expect(revoked).toEqual(created);
    });
  });
});
