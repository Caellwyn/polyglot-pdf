// @vitest-environment jsdom
//
// Regression tests for the fillPDF auth threading (bd polyglot-pdf-z2is):
// POST /api/fill-pdf is auth-gated server-side, so fillPDF must attach
// `Authorization: Bearer <token>` when a getToken callback is provided --
// dropping that header would break every fill/download/preview for real
// signed-in users on the deployed app while every mocked test stayed green.
// Also pins the no-callback shape (local dev against a VFF_DISABLE_AUTH
// backend sends no header rather than a bogus one).
import { describe, it, expect, vi, afterEach } from 'vitest';
import { fillPDF } from './pdfFiller';
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

describe('fillPDF auth header threading (bd z2is)', () => {
  it('attaches Authorization: Bearer <token> when getToken is provided', async () => {
    const calls = mockFetchCapture();

    await fillPDF('i-90', '/form-kits/i-90/form.pdf', {}, SCHEMA, async () => 'tok-123');

    expect(calls).toHaveLength(1);
    expect(calls[0].url).toContain('/api/fill-pdf');
    const headers = calls[0].init.headers as Record<string, string>;
    expect(headers['Authorization']).toBe('Bearer tok-123');
    expect(headers['Content-Type']).toBe('application/json');
  });

  it('sends no Authorization header when getToken is absent or returns undefined', async () => {
    const calls = mockFetchCapture();

    await fillPDF('i-90', '/form-kits/i-90/form.pdf', {}, SCHEMA);
    await fillPDF('i-90', '/form-kits/i-90/form.pdf', {}, SCHEMA, async () => undefined);

    expect(calls).toHaveLength(2);
    for (const call of calls) {
      const headers = call.init.headers as Record<string, string>;
      expect(headers['Authorization']).toBeUndefined();
      expect(headers['Content-Type']).toBe('application/json');
    }
  });
});
