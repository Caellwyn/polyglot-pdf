/**
 * Tests for the dev-only extraction client (bd 7a9.17). The client is the browser
 * side of POST /api/extract; these pin its fetch contract and -- critically --
 * that EVERY failure mode degrades to a benign result rather than throwing, so a
 * static build (no endpoint) simply hides the button instead of erroring.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { isExtractionAvailable, runExtraction } from './extractionClient';

afterEach(() => { vi.restoreAllMocks(); });

function mockFetch(impl: (url: string, init?: RequestInit) => Promise<Response>) {
  global.fetch = vi.fn(impl as unknown as typeof fetch);
}
function jsonResponse(body: unknown, ok = true, status = 200): Response {
  return { ok, status, json: async () => body } as unknown as Response;
}

describe('isExtractionAvailable', () => {
  it('is true when GET /api/extract returns ok:true', async () => {
    mockFetch(async () => jsonResponse({ ok: true, detail: 'available' }));
    expect(await isExtractionAvailable()).toBe(true);
  });

  it('is false on a non-OK HTTP status (no endpoint -> 404)', async () => {
    mockFetch(async () => jsonResponse({}, false, 404));
    expect(await isExtractionAvailable()).toBe(false);
  });

  it('is false when fetch rejects (network error / static build)', async () => {
    mockFetch(async () => { throw new Error('connection refused'); });
    expect(await isExtractionAvailable()).toBe(false);
  });

  it('is false when the body is ok:false', async () => {
    mockFetch(async () => jsonResponse({ ok: false }));
    expect(await isExtractionAvailable()).toBe(false);
  });
});

describe('runExtraction', () => {
  it('POSTs the kit id (+ filename overrides) as JSON and returns the result', async () => {
    const seen: { url?: string; init?: RequestInit } = {};
    mockFetch(async (url, init) => {
      seen.url = url; seen.init = init;
      return jsonResponse({ ok: true, detail: 'wrote schema.json', schemaFile: 'schema.json' });
    });

    const result = await runExtraction('w7', { pdfFile: 'form.pdf', schemaFile: 'schema.json' });

    expect(seen.url).toBe('/api/extract');
    expect(seen.init?.method).toBe('POST');
    expect(JSON.parse(seen.init?.body as string)).toEqual({
      id: 'w7', pdfFile: 'form.pdf', schemaFile: 'schema.json',
    });
    expect(result.ok).toBe(true);
    expect(result.schemaFile).toBe('schema.json');
  });

  it('returns ok:false with the server detail on a failed extraction', async () => {
    mockFetch(async () => jsonResponse(
      { ok: false, detail: 'extraction failed (exit 1): boom' }, false, 500));
    const result = await runExtraction('w7');
    expect(result.ok).toBe(false);
    expect(result.detail).toContain('boom');
  });

  it('returns ok:false (not throw) when fetch rejects', async () => {
    mockFetch(async () => { throw new Error('network down'); });
    const result = await runExtraction('w7');
    expect(result.ok).toBe(false);
    expect(result.detail).toContain('network down');
  });

  it('returns ok:false when the response is not JSON', async () => {
    mockFetch(async () => ({
      ok: true, status: 200, json: async () => { throw new Error('not json'); },
    } as unknown as Response));
    const result = await runExtraction('w7');
    expect(result.ok).toBe(false);
    expect(result.detail).toMatch(/non-JSON/i);
  });
});
