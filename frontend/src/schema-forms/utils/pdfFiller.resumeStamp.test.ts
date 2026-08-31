// @vitest-environment jsdom
//
// The resume stamp's CLIENT half (bd polyglot-pdf-dft1).
//
// The backend stamps form_session_id into the saved PDF so a client who closes
// the tab -- or steps away past the 60-minute state expiry -- can reopen their
// own file and resume. It can only stamp what the client SENDS, so this pins
// that fillPDF actually puts it on the wire.
//
// Written because the backend half is fully tested and would stay green while
// this end of the contract was silently dropped: the stamp would simply never
// appear, and a client's saved PDF would be unresumable with no error anywhere.
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

function bodyOf(calls: { init: RequestInit }[]): Record<string, unknown> {
  return JSON.parse(String(calls[0].init.body));
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('fillPDF sends the resume stamp (bd dft1)', () => {
  it('puts form_session_id in the request body when one is given', async () => {
    const calls = mockFetchCapture();

    await fillPDF(
      'i-90', '/form-kits/i-90/form.pdf', {}, SCHEMA,
      undefined, 'form.pdf', 'fss_1756000000_abc',
    );

    expect(bodyOf(calls).form_session_id).toBe('fss_1756000000_abc');
  });

  it('OMITS the key entirely for a staff download', async () => {
    // Absence is how the backend distinguishes a staff download from a
    // client's, and it must not arrive as the string "undefined" -- which
    // would stamp a session id of literally that into the PDF.
    const calls = mockFetchCapture();

    await fillPDF('i-90', '/form-kits/i-90/form.pdf', {}, SCHEMA);

    const body = bodyOf(calls);
    expect('form_session_id' in body).toBe(false);
  });

  it('omits the key rather than sending an empty string', async () => {
    const calls = mockFetchCapture();

    await fillPDF(
      'i-90', '/form-kits/i-90/form.pdf', {}, SCHEMA,
      undefined, 'form.pdf', '',
    );

    expect('form_session_id' in bodyOf(calls)).toBe(false);
  });

  it('still sends the rest of the payload unchanged', async () => {
    // The stamp is additive: adding it must not disturb the fields the fill
    // has always depended on.
    const calls = mockFetchCapture();

    await fillPDF(
      'i-90', '/form-kits/i-90/form.pdf', { a: '1' }, SCHEMA,
      undefined, 'form.pdf', 'fss_1_abc',
    );

    const body = bodyOf(calls);
    expect(body.kit_id).toBe('i-90');
    expect(body.pdf_filename).toBe('form.pdf');
    expect(body.field_values).toEqual({ a: '1' });
    expect(body.form_schema).toBeDefined();
  });
});
