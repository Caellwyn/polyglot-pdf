/**
 * Unit tests for the remote kit store (bd polyglot-pdf-92qe.2): the fetch-backed
 * mirror of formKitDirectory over the token-gated /api/editor routes.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { FormSchema } from '../types/schema';
import {
  AuthError,
  apiBaseUrl,
  clearAccessCode,
  extractRemoteKit,
  getAccessCode,
  isHostedMode,
  listRemoteKits,
  loadRemotePdfBlobUrl,
  loadRemoteSchema,
  probeSession,
  saveRemoteSchema,
  setAccessCode,
  setRemoteStatus,
} from './remoteKitStore';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
  window.localStorage.clear();
  clearAccessCode(); // drops the module-level in-memory fallback copy too
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  window.localStorage.clear();
});

describe('mode + access-code plumbing', () => {
  it('isHostedMode reflects VITE_DELIVERY_MODE at call time', () => {
    expect(isHostedMode()).toBe(false);
    vi.stubEnv('VITE_DELIVERY_MODE', 'hosted');
    expect(isHostedMode()).toBe(true);
  });

  it('apiBaseUrl comes from VITE_API_BASE_URL (empty default)', () => {
    expect(apiBaseUrl()).toBe('');
    vi.stubEnv('VITE_API_BASE_URL', 'https://backend.example');
    expect(apiBaseUrl()).toBe('https://backend.example');
  });

  it('stored access code wins over a baked token; clear falls back', () => {
    vi.stubEnv('VITE_EDITOR_TOKEN', 'baked-tok');
    expect(getAccessCode()).toBe('baked-tok');
    setAccessCode('typed-tok');
    expect(getAccessCode()).toBe('typed-tok');
    clearAccessCode();
    expect(getAccessCode()).toBe('baked-tok');
  });
});

describe('request shape', () => {
  it('sends the access code as X-Editor-Token and prefixes the base URL', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://backend.example');
    setAccessCode('sekret');
    fetchMock.mockResolvedValue(jsonResponse({ kits: [] }));

    await listRemoteKits();

    expect(fetchMock).toHaveBeenCalledWith(
      'https://backend.example/api/editor/kits',
      expect.objectContaining({
        headers: expect.objectContaining({ 'X-Editor-Token': 'sekret' }),
      }),
    );
  });

  it('omits the header when no code exists (server answers 401/503)', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ kits: [] }));
    await listRemoteKits();
    const headers = (fetchMock.mock.calls[0][1] as RequestInit).headers as Record<string, string>;
    expect(headers['X-Editor-Token']).toBeUndefined();
  });

  it('a 401 raises AuthError from any call', async () => {
    setAccessCode('stale');
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'nope' }, 401));
    await expect(listRemoteKits()).rejects.toBeInstanceOf(AuthError);
    await expect(probeSession()).rejects.toBeInstanceOf(AuthError);
    await expect(saveRemoteSchema('i-90', { fields: [] } as unknown as FormSchema))
      .rejects.toBeInstanceOf(AuthError);
  });

  it('a non-401 error surfaces the server detail', async () => {
    setAccessCode('ok');
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'editor surface is not configured' }, 503));
    await expect(probeSession()).rejects.toThrow('editor surface is not configured');
  });
});

describe('endpoints', () => {
  beforeEach(() => setAccessCode('tok'));

  it('probeSession returns the role', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ role: 'author' }));
    await expect(probeSession()).resolves.toEqual({ role: 'author' });
  });

  it('listRemoteKits unwraps the kits array (and tolerates junk)', async () => {
    const kit = {
      id: 'i-90', label: 'I-90', status: 'draft', hasSchema: true, hasPdf: true,
      schemaFile: 'schema.json', pdfFile: 'form.pdf',
    };
    fetchMock.mockResolvedValueOnce(jsonResponse({ kits: [kit] }));
    await expect(listRemoteKits()).resolves.toEqual([kit]);
    fetchMock.mockResolvedValueOnce(jsonResponse({}));
    await expect(listRemoteKits()).resolves.toEqual([]);
  });

  it('loadRemoteSchema returns the schema, and null on 404 (no schema yet)', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ fields: [{ id: 'a' }] }));
    await expect(loadRemoteSchema('i-90')).resolves.toEqual({ fields: [{ id: 'a' }] });
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'no schema' }, 404));
    await expect(loadRemoteSchema('fresh')).resolves.toBeNull();
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/editor/kits/i-90/schema', expect.anything(),
    );
  });

  it('loadRemotePdfBlobUrl returns an object URL, null on 404', async () => {
    const createObjectURL = vi.fn(() => 'blob:fake');
    vi.stubGlobal('URL', { ...URL, createObjectURL });
    fetchMock.mockResolvedValueOnce(new Response(new Blob([new Uint8Array([1])]), { status: 200 }));
    await expect(loadRemotePdfBlobUrl('i-90')).resolves.toBe('blob:fake');
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'no pdf' }, 404));
    await expect(loadRemotePdfBlobUrl('fresh')).resolves.toBeNull();
  });

  it('saveRemoteSchema PUTs the schema JSON with editor state stripped', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));
    // `_ungroup` is the STASH_KEY stripEditorState removes (the merge/group
    // scratch state that must never reach persisted schemas).
    const schema = {
      fields: [{ id: 'a', _ungroup: { anything: 1 } }],
    } as unknown as FormSchema;

    await saveRemoteSchema('i-90', schema);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/editor/kits/i-90/schema');
    expect((init as RequestInit).method).toBe('PUT');
    const sent = JSON.parse((init as RequestInit).body as string);
    expect(sent.fields[0].id).toBe('a');
    expect(sent.fields[0]._ungroup).toBeUndefined();
  });

  it('setRemoteStatus POSTs the status and surfaces the promote-gate detail', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true }));
    await setRemoteStatus('i-90', 'complete');
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/editor/kits/i-90/status');
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({ status: 'complete' });

    fetchMock.mockResolvedValueOnce(
      jsonResponse({ detail: 'Schema does not validate against the form contract' }, 422),
    );
    await expect(setRemoteStatus('broken', 'complete'))
      .rejects.toThrow('does not validate');
  });

  it('extractRemoteKit NEVER sends an empty multipart body (bd 1ysc)', async () => {
    // A zero-part FormData body is rejected by python-multipart with a parse
    // error starlette does not catch -> FastAPI 400 "There was an error parsing
    // the body" BEFORE the route runs. The client must always append `force`.
    // (A fresh Response per call: a Response body is single-read.)
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({ ok: true })));

    // Bare Run-extraction click: no force, no instructions PDF.
    await extractRemoteKit('form-2');
    let [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/editor/kits/form-2/extract');
    let body = (init as RequestInit).body as FormData;
    expect(body.get('force')).toBe('false');       // present, never empty
    expect(body.get('instructions_pdf')).toBeNull();

    // force path still sends true.
    await extractRemoteKit('form-2', { force: true });
    body = (fetchMock.mock.calls[1][1] as RequestInit).body as FormData;
    expect(body.get('force')).toBe('true');

    // instructions PDF still attaches alongside force.
    const pdf = new File([new Uint8Array([1])], 'instr.pdf', { type: 'application/pdf' });
    await extractRemoteKit('form-2', { instructionsPdf: pdf });
    body = (fetchMock.mock.calls[2][1] as RequestInit).body as FormData;
    expect(body.get('force')).toBe('false');
    expect((body.get('instructions_pdf') as File).name).toBe('instr.pdf');
  });
});

describe('storage-less browsers (Codex r2, PR #280)', () => {
  it('keeps the entered code in memory when localStorage.setItem throws', () => {
    const original = window.localStorage.setItem.bind(window.localStorage);
    // Simulate Safari private browsing: writes throw, reads return null.
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('QuotaExceededError');
    });
    try {
      setAccessCode('memory-only-code');
      expect(getAccessCode()).toBe('memory-only-code');
      clearAccessCode();
      expect(getAccessCode()).toBeNull();
    } finally {
      vi.mocked(Storage.prototype.setItem).mockRestore();
      original('noop', 'noop');
      window.localStorage.removeItem('noop');
    }
  });

  it('localStorage still wins over the memory copy when available', () => {
    setAccessCode('persisted');
    expect(window.localStorage.getItem('schema-editor.accessCode')).toBe('persisted');
    expect(getAccessCode()).toBe('persisted');
    clearAccessCode();
  });
});
