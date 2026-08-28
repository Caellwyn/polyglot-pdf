/**
 * localStamp (sprint-18 C4b, bd polyglot-pdf-na1zy).
 *
 * Two halves:
 *  - stampKitReadinessRemote: the POST to the backend's stamp-refresh route
 *    (bearer ID token, AuthError on 401 / ForbiddenError on 403, stamp
 *    payload back).
 *  - invalidateLocalStamp: the no-backend fallback that retracts a stale
 *    stamp claim (verified: false) while preserving every other metadata key
 *    and NEVER destroying an unparseable file -- the client mirror of the
 *    backend's never-destroy rule in _stamp_readiness.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { invalidateLocalStamp, stampKitReadinessRemote } from './localStamp';
import { AuthError, ForbiddenError } from './remoteKitStore';
import { editorIdToken } from './editorAuth';

// This route is a DIRECT fetch (not editorFetch), so it carries the signed-in
// person's ID token itself (bd polyglot-pdf-yswp3). Mock the auth module: the
// test is about what this module SENDS, not about Firebase.
vi.mock('./editorAuth', () => ({ editorIdToken: vi.fn() }));
const idTokenMock = vi.mocked(editorIdToken);
import type { FsDirectoryHandle } from './fileSystemAccess';

// --- fakes ------------------------------------------------------------------

/** A fake kit directory whose metadata.json content is observable. */
function fakeDir(initial: string | null): {
  handle: FsDirectoryHandle; written: () => string | null;
} {
  let content = initial;
  let written: string | null = null;
  const handle = {
    getFileHandle: vi.fn(async (name: string) => {
      if (name !== 'metadata.json' || content === null) {
        throw new DOMException('not found', 'NotFoundError');
      }
      return {
        getFile: async () => ({ text: async () => content as string }),
        createWritable: async () => ({
          write: async (data: string) => { written = data; content = data; },
          close: async () => undefined,
        }),
      };
    }),
  } as unknown as FsDirectoryHandle;
  return { handle, written: () => written };
}

afterEach(() => {
  vi.unstubAllGlobals();
  idTokenMock.mockReset();
});

// --- invalidateLocalStamp ---------------------------------------------------

describe('invalidateLocalStamp', () => {
  it('flips verified to false and preserves every other key', async () => {
    const meta = {
      status: 'draft', label: 'Kit A', schema: 'custom.json',
      readiness: { reviewed: 3, to_review: 1, total: 4, errors: 0,
                   percent: 75, ready: false, verified: true,
                   schema_sha1: 'abc', stamped_at: '2026-08-01T00:00:00Z' },
    };
    const dir = fakeDir(JSON.stringify(meta));
    expect(await invalidateLocalStamp(dir.handle)).toBe(true);
    const after = JSON.parse(dir.written()!);
    expect(after.readiness.verified).toBe(false);
    // The retraction changes ONLY the claim, never the record around it.
    expect(after.status).toBe('draft');
    expect(after.label).toBe('Kit A');
    expect(after.schema).toBe('custom.json');
    expect(after.readiness.percent).toBe(75);
    expect(after.readiness.schema_sha1).toBe('abc');
  });

  it('no-ops when there is nothing to retract', async () => {
    // No metadata.json at all.
    const missing = fakeDir(null);
    expect(await invalidateLocalStamp(missing.handle)).toBe(false);
    expect(missing.written()).toBeNull();
    // Metadata without a readiness block.
    const bare = fakeDir(JSON.stringify({ status: 'draft' }));
    expect(await invalidateLocalStamp(bare.handle)).toBe(false);
    expect(bare.written()).toBeNull();
    // A stamp already retracted.
    const done = fakeDir(JSON.stringify({ readiness: { verified: false } }));
    expect(await invalidateLocalStamp(done.handle)).toBe(false);
    expect(done.written()).toBeNull();
  });

  it('never destroys an unparseable metadata.json', async () => {
    const dir = fakeDir('{not json');
    expect(await invalidateLocalStamp(dir.handle)).toBe(false);
    expect(dir.written()).toBeNull();
  });
});

// --- stampKitReadinessRemote ------------------------------------------------

describe('stampKitReadinessRemote', () => {
  it('POSTs the schema with the editor token and returns the stamp', async () => {
    idTokenMock.mockResolvedValue('tok-123');
    const stamp = { percent: 50, verified: true };
    const fetchMock = vi.fn(async () => ({
      ok: true, status: 200,
      json: async () => ({ readiness: stamp }),
    }));
    vi.stubGlobal('fetch', fetchMock);
    const out = await stampKitReadinessRemote('kit a', { fields: [] });
    expect(out).toEqual(stamp);
    const [url, init] = fetchMock.mock.calls[0] as unknown as
      [string, RequestInit];
    expect(url).toContain('/api/editor/kits/kit%20a/readiness');
    expect(init.method).toBe('POST');
    // Per-user identity, and NOT the retired shared-code header.
    expect((init.headers as Record<string, string>)['Authorization'])
      .toBe('Bearer tok-123');
    expect((init.headers as Record<string, string>)['X-Editor-Token'])
      .toBeUndefined();
    expect(init.body).toBe(JSON.stringify({ fields: [] }));
  });

  it('throws AuthError on 401, ForbiddenError on 403, Error on others', async () => {
    idTokenMock.mockResolvedValue('tok');
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 401 })));
    await expect(stampKitReadinessRemote('k', {})).rejects.toBeInstanceOf(AuthError);
    // A real account with no editor role: distinct from 401 here too, so a
    // caller cannot mistake "not allowed" for "sign in again".
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 403 })));
    const err = await stampKitReadinessRemote('k', {}).catch((e) => e);
    expect(err).toBeInstanceOf(ForbiddenError);
    expect(err).not.toBeInstanceOf(AuthError);
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 502 })));
    await expect(stampKitReadinessRemote('k', {})).rejects.toThrow('HTTP 502');
  });
});
