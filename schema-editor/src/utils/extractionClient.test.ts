/**
 * Tests for the dev-only extraction client (bd 7a9.17). The client is the browser
 * side of POST /api/extract; these pin its fetch contract and -- critically --
 * that EVERY failure mode degrades to a benign result rather than throwing, so a
 * static build (no endpoint) simply hides the button instead of erroring.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import {
  isExtractionAvailable, runExtraction, verifyExtractorFolder,
} from './extractionClient';

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

// --- same-folder handshake asker (bd polyglot-pdf-ball) --------------------- //
//
// The extractor writes schema.json under the VITE HOST's own form-kits root, so
// running it against a picked folder that is a copy elsewhere silently
// overwrites a DIFFERENT kit. This asker is what proves the two are one
// directory. Every failure mode must resolve sameFolder=FALSE: unproven can
// never read as proven, because the action it gates is destructive.
describe('verifyExtractorFolder', () => {
  it('reports agreement and the host root when the nonce is read back', async () => {
    mockFetch(async () => jsonResponse({ sameFolder: true, extractorRoot: '/repo/form-kits' }));
    const res = await verifyExtractorFolder('n1');
    expect(res.sameFolder).toBe(true);
    // Surfaced as backendRoot: verifySameFolder's asker contract speaks of "the
    // root the server uses" -- here that server is the extractor host.
    expect(res.backendRoot).toBe('/repo/form-kits');
  });

  it('POSTs the nonce to the handshake sub-route', async () => {
    let url = '';
    let body: unknown = null;
    mockFetch(async (u, init) => {
      url = u;
      body = JSON.parse(init?.body as string);
      return jsonResponse({ sameFolder: true });
    });
    await verifyExtractorFolder('abc123');
    expect(url).toBe('/api/extract/handshake');
    expect(body).toEqual({ nonce: 'abc123' });
  });

  it('reports a MISMATCH as sameFolder:false', async () => {
    mockFetch(async () => jsonResponse(
      { sameFolder: false, reason: 'mismatch', extractorRoot: '/repo/form-kits' }));
    const res = await verifyExtractorFolder('n1');
    expect(res.sameFolder).toBe(false);
    expect(res.backendRoot).toBe('/repo/form-kits');
  });

  it('does NOT read a rejected fetch as agreement', async () => {
    mockFetch(async () => { throw new Error('network down'); });
    expect((await verifyExtractorFolder('n1')).sameFolder).toBe(false);
  });

  it('does NOT read a non-OK response as agreement', async () => {
    mockFetch(async () => jsonResponse({ sameFolder: true }, false, 500));
    expect((await verifyExtractorFolder('n1')).sameFolder).toBe(false);
  });

  it('reports 5xx and transport failure as UNREACHABLE, but 4xx as answered', async () => {
    // Both refuse -- only the explanation differs. A 4xx means the host replied
    // and rejected the request, so telling the user "check the dev server is
    // running" would be wrong advice about a server that just answered.
    const seen: string[] = [];
    const probe = async (impl: () => Promise<Response>) => {
      let reached = true;
      mockFetch(impl);
      const res = await verifyExtractorFolder('n1', () => { reached = false; });
      expect(res.sameFolder).toBe(false); // every case still refuses
      seen.push(reached ? 'answered' : 'unreachable');
    };

    await probe(async () => jsonResponse({ detail: 'missing nonce' }, false, 400));
    await probe(async () => jsonResponse({ detail: 'boom' }, false, 500));
    await probe(async () => { throw new Error('network down'); });

    expect(seen).toEqual(['answered', 'unreachable', 'unreachable']);
  });

  it('does NOT read a non-JSON response as agreement', async () => {
    mockFetch(async () => ({
      ok: true, status: 200, json: async () => { throw new Error('not json'); },
    } as unknown as Response));
    expect((await verifyExtractorFolder('n1')).sameFolder).toBe(false);
  });

  it('requires sameFolder to be exactly true, not merely truthy', async () => {
    // A static build's 404 HTML, or an older host that does not know this route,
    // must not squeak through on a coerced value.
    mockFetch(async () => jsonResponse({ sameFolder: 'yes' }));
    expect((await verifyExtractorFolder('n1')).sameFolder).toBe(false);
  });
});
