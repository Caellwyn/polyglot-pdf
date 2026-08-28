/**
 * Unit tests for the remote kit store (bd polyglot-pdf-92qe.2): the fetch-backed
 * mirror of formKitDirectory over the per-user /api/editor routes.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { FormSchema } from '../types/schema';
import {
  AuthError,
  ForbiddenError,
  apiBaseUrl,
  extractRemoteKit,
  hasBackend,
  isHostedMode,
  listRemoteKits,
  loadRemotePdfBlobUrl,
  loadRemoteSchema,
  probeSession,
  saveRemoteSchema,
  setRemoteLabel,
  setRemoteStatus,
} from './remoteKitStore';
import { editorIdToken } from './editorAuth';

// The store now identifies the caller with a Firebase ID token
// (bd polyglot-pdf-yswp3). Mock the auth module rather than the SDK: these
// tests are about what the STORE sends, not about Firebase.
vi.mock('./editorAuth', () => ({ editorIdToken: vi.fn() }));
const idTokenMock = vi.mocked(editorIdToken);

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
  idTokenMock.mockReset();
  idTokenMock.mockResolvedValue('id-token');
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  window.localStorage.clear();
});

describe('mode + delivery plumbing', () => {
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

  // bd polyglot-pdf-cpiw: local dev runs the backend too, so "where do kits
  // live" and "can we call a server" are separate questions.
  it('apiBaseUrl falls back to VITE_BACKEND_URL for local dev', () => {
    expect(apiBaseUrl()).toBe('');
    vi.stubEnv('VITE_BACKEND_URL', 'http://127.0.0.1:8000');
    expect(apiBaseUrl()).toBe('http://127.0.0.1:8000');
  });

  it('the hosted URL always wins, so a hosted build never hits localhost', () => {
    vi.stubEnv('VITE_BACKEND_URL', 'http://127.0.0.1:8000');
    vi.stubEnv('VITE_API_BASE_URL', 'https://backend.example');
    expect(apiBaseUrl()).toBe('https://backend.example');
  });

  it('hasBackend is true when hosted, regardless of VITE_BACKEND_URL', () => {
    expect(hasBackend()).toBe(false);
    vi.stubEnv('VITE_DELIVERY_MODE', 'hosted');
    expect(hasBackend()).toBe(true);
  });

  it('hasBackend is true in LOCAL mode once a backend URL is set', () => {
    expect(isHostedMode()).toBe(false);
    expect(hasBackend()).toBe(false);
    vi.stubEnv('VITE_BACKEND_URL', 'http://127.0.0.1:8000');
    // Still local (kits stay on disk) but the server-side rules are reachable.
    expect(isHostedMode()).toBe(false);
    expect(hasBackend()).toBe(true);
  });

  // The shared access code is GONE (bd polyglot-pdf-yswp3): no VITE_EDITOR_TOKEN
  // baked into the bundle, and nothing read from localStorage. Identity comes
  // only from the signed-in person's ID token. Pin the absence so a re-added
  // build-baked credential fails here rather than shipping in plaintext.
  it('never reads a build-baked or stored credential', async () => {
    vi.stubEnv('VITE_DELIVERY_MODE', 'hosted');
    vi.stubEnv('VITE_EDITOR_TOKEN', 'baked-tok');
    window.localStorage.setItem('schema-editor.accessCode', 'stored-tok');
    idTokenMock.mockResolvedValue('the-id-token');
    fetchMock.mockResolvedValue(jsonResponse({ kits: [] }));

    await listRemoteKits();

    const headers = (fetchMock.mock.calls[0][1] as RequestInit).headers as Record<string, string>;
    expect(headers['X-Editor-Token']).toBeUndefined();
    expect(headers['Authorization']).toBe('Bearer the-id-token');
    expect(JSON.stringify(headers)).not.toContain('baked-tok');
    expect(JSON.stringify(headers)).not.toContain('stored-tok');
  });
});

describe('request shape', () => {
  it('sends the ID token as Authorization: Bearer and prefixes the base URL', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://backend.example');
    idTokenMock.mockResolvedValue('sekret-id-token');
    fetchMock.mockResolvedValue(jsonResponse({ kits: [] }));

    await listRemoteKits();

    expect(fetchMock).toHaveBeenCalledWith(
      'https://backend.example/api/editor/kits',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer sekret-id-token' }),
      }),
    );
  });

  it('omits the header when nobody is signed in (server answers 401)', async () => {
    idTokenMock.mockResolvedValue(null);
    fetchMock.mockResolvedValue(jsonResponse({ kits: [] }));
    await listRemoteKits();
    const headers = (fetchMock.mock.calls[0][1] as RequestInit).headers as Record<string, string>;
    expect(headers['Authorization']).toBeUndefined();
  });

  // The token is fetched PER REQUEST, not captured once: Firebase ID tokens
  // expire hourly and the SDK refreshes them, so a cached copy would 401 an
  // editor mid-kit -- the exact failure this bead removes.
  it('asks for a fresh token on every request', async () => {
    // A fresh Response per call: a body can only be read once.
    fetchMock.mockImplementation(async () => jsonResponse({ kits: [] }));
    idTokenMock.mockResolvedValueOnce('first').mockResolvedValueOnce('second');

    await listRemoteKits();
    await listRemoteKits();

    const h0 = (fetchMock.mock.calls[0][1] as RequestInit).headers as Record<string, string>;
    const h1 = (fetchMock.mock.calls[1][1] as RequestInit).headers as Record<string, string>;
    expect(h0['Authorization']).toBe('Bearer first');
    expect(h1['Authorization']).toBe('Bearer second');
    expect(idTokenMock).toHaveBeenCalledTimes(2);
  });

  it('a 401 raises AuthError from any call', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'nope' }, 401));
    await expect(listRemoteKits()).rejects.toBeInstanceOf(AuthError);
    await expect(probeSession()).rejects.toBeInstanceOf(AuthError);
    await expect(saveRemoteSchema('i-90', { fields: [] } as unknown as FormSchema))
      .rejects.toBeInstanceOf(AuthError);
  });

  // 403 is a REAL account with no editor role -- a different remedy from 401
  // (an operator must grant access; retrying never helps), so it must NOT be
  // an AuthError or the gate would loop the person through sign-in forever.
  it('a 403 raises ForbiddenError, NOT AuthError, and carries the detail', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: 'This account does not have schema editor access' }, 403));
    const err = await probeSession().catch((e) => e);
    expect(err).toBeInstanceOf(ForbiddenError);
    expect(err).not.toBeInstanceOf(AuthError);
    expect(err.message).toBe('This account does not have schema editor access');
    await expect(listRemoteKits()).rejects.toBeInstanceOf(ForbiddenError);
  });

  it('a non-401 error surfaces the server detail', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'editor surface is not configured' }, 503));
    await expect(probeSession()).rejects.toThrow('editor surface is not configured');
  });
});

describe('endpoints', () => {
  beforeEach(() => idTokenMock.mockResolvedValue('tok'));

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
    fetchMock.mockResolvedValueOnce(jsonResponse({
      ok: true, status: 'complete', retranslated: 2, translationModel: 'gemini-2.5-pro',
    }));
    // The sweep summary round-trips to the caller (bd polyglot-pdf-783r).
    const result = await setRemoteStatus('i-90', 'complete');
    expect(result.retranslated).toBe(2);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/editor/kits/i-90/status');
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({ status: 'complete' });

    fetchMock.mockResolvedValueOnce(
      jsonResponse({ detail: 'Schema does not validate against the form contract' }, 422),
    );
    await expect(setRemoteStatus('broken', 'complete'))
      .rejects.toThrow('does not validate');
  });

  it('setRemoteLabel POSTs the new label and surfaces the refusal detail', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true, label: 'W-9' }));
    await setRemoteLabel('form-2', 'W-9');
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/editor/kits/form-2/label');
    expect((init as RequestInit).method).toBe('POST');
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({ label: 'W-9' });

    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'Label must not be empty' }, 422));
    await expect(setRemoteLabel('form-2', '   ')).rejects.toThrow('must not be empty');
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
