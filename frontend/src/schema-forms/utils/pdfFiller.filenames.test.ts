// @vitest-environment jsdom
//
// Pins for the private-kit serving seam (bd polyglot-pdf-vccy):
// 1. fillPDF must POST the kit's REAL pdf filename when the caller passes it
//    -- a PRIVATE kit's pdfUrl is the backend route .../pdf, whose last URL
//    segment is the literal "pdf"; a URL-split filename 404s the fill in
//    store.load_pdf_bytes.
// 2. resolveKitAssetUrl must resolve /api/ manifest paths against the
//    backend base (a relative /api/ fetch works on Hosting via the rewrite
//    but not against the Vite dev server) and pass everything else through.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { fillPDF, resolveKitAssetUrl, getBackendHttpUrl } from './pdfFiller';
import type { FormSchema } from '../types/schema';

const SCHEMA = { fields: [] } as unknown as FormSchema;

function mockFetchCapture() {
  const calls: { url: string; init: RequestInit }[] = [];
  const fetchMock = vi.fn(async (url: any, init?: any) => {
    calls.push({ url: String(url), init: init ?? {} });
    return {
      ok: true,
      status: 200,
      statusText: 'OK',
      arrayBuffer: async () => new ArrayBuffer(8),
    } as unknown as Response;
  });
  vi.stubGlobal('fetch', fetchMock);
  return calls;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('fillPDF explicit pdf filename (bd vccy)', () => {
  it('POSTs the explicit pdfFile, not the URL tail, for a backend-route pdfUrl', async () => {
    // Mutation: drop the `pdfFile ||` half of the filename resolution in
    // fillPDF -- this goes red (payload would carry the literal "pdf").
    const calls = mockFetchCapture();

    await fillPDF(
      'priv-kit', '/api/form-kits/priv-kit/pdf', {}, SCHEMA,
      undefined, 'intake.pdf',
    );

    expect(calls).toHaveLength(1);
    const payload = JSON.parse(String(calls[0].init.body));
    expect(payload.pdf_filename).toBe('intake.pdf');
  });

  it('falls back to the URL tail when no pdfFile is given (legacy static path)', async () => {
    const calls = mockFetchCapture();

    await fillPDF('i-90', '/form-kits/i-90/form.pdf', {}, SCHEMA);

    const payload = JSON.parse(String(calls[0].init.body));
    expect(payload.pdf_filename).toBe('form.pdf');
  });
});

describe('resolveKitAssetUrl (bd vccy)', () => {
  it('resolves /api/ paths against the backend base', () => {
    // Mutation: make resolveKitAssetUrl the identity function -- red.
    expect(resolveKitAssetUrl('/api/form-kits/priv-kit/schema')).toBe(
      `${getBackendHttpUrl()}/api/form-kits/priv-kit/schema`,
    );
  });

  it('passes static, blob:, and absolute URLs through untouched', () => {
    for (const url of [
      '/form-kits/i-90/form.pdf',
      'blob:http://localhost/abc-123',
      'https://example.com/x.pdf',
    ]) {
      expect(resolveKitAssetUrl(url)).toBe(url);
    }
  });
});
