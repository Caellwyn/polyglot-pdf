/**
 * Same-folder handshake (bd polyglot-pdf-s2bf).
 *
 * The editor reads and writes the folder the human PICKED; the backend
 * resolves the same kit id against its OWN FORM_KITS_LOCAL_ROOT. When those
 * differ, every server-side action (repair, regenerate divisions, regenerate
 * guidance) rewrites the OTHER copy while the editor re-reads the picked one --
 * destructive, and invisible to the human.
 *
 * A path comparison is impossible (the browser cannot read a filesystem path
 * out of a directory handle, by design), so agreement is proved by SHARED
 * OBSERVATION: write a nonce here, have the backend read it back from its own
 * root, require a match.
 */
import { describe, it, expect, vi } from 'vitest';
import { verifySameFolder } from './formKitDirectory';
import type { FsDirectoryHandle } from './fileSystemAccess';

/** A directory handle that records what was written and removed. */
function mockDir(opts: { writable?: boolean; canRemove?: boolean } = {}) {
  const { writable = true, canRemove = true } = opts;
  const state: { written: Record<string, string>; removed: string[] } = {
    written: {}, removed: [],
  };
  const dir = {
    getFileHandle: async (name: string) => {
      if (!writable) throw new DOMException('read-only', 'NotAllowedError');
      return {
        createWritable: async () => ({
          write: async (d: string | ArrayBuffer) => {
            state.written[name] = typeof d === 'string' ? d : '';
          },
          close: async () => {},
        }),
      };
    },
    removeEntry: canRemove
      ? async (name: string) => { state.removed.push(name); }
      : undefined,
  } as unknown as FsDirectoryHandle;
  return { dir, state };
}

/** The nonce the editor wrote, read back out of the mock's captured file. */
function writtenNonce(state: { written: Record<string, string> }): string {
  const raw = state.written['.editor-store-check.json'];
  return raw ? (JSON.parse(raw) as { nonce: string }).nonce : '';
}

describe('verifySameFolder', () => {
  it('passes when the backend sees the SAME nonce', async () => {
    const { dir, state } = mockDir();
    const ask = vi.fn(async (nonce: string) => {
      // The backend read the marker out of its own root and it matched.
      expect(nonce).toBe(writtenNonce(state));
      return { sameFolder: true, backendRoot: '/repo/form-kits' };
    });
    await expect(verifySameFolder(dir, ask)).resolves.toEqual({ ok: true });
    expect(ask).toHaveBeenCalledOnce();
  });

  it('fails with the backend root when the folders DIFFER', async () => {
    const { dir } = mockDir();
    const ask = async () => ({ sameFolder: false, backendRoot: '/repo/form-kits' });
    await expect(verifySameFolder(dir, ask)).resolves.toEqual({
      ok: false, reason: 'mismatch', backendRoot: '/repo/form-kits',
    });
  });

  it('reports unwritable WITHOUT calling the backend', async () => {
    // A read-only source folder cannot be the write target either way, so the
    // write failure is its own answer -- and asking the backend would be
    // pointless (there is no marker for it to find).
    const { dir } = mockDir({ writable: false });
    const ask = vi.fn();
    await expect(verifySameFolder(dir, ask)).resolves.toEqual({
      ok: false, reason: 'unwritable',
    });
    expect(ask).not.toHaveBeenCalled();
  });

  it('cleans the marker up afterwards, on success AND on mismatch', async () => {
    const a = mockDir();
    await verifySameFolder(a.dir, async () => ({ sameFolder: true }));
    expect(a.state.removed).toEqual(['.editor-store-check.json']);

    const b = mockDir();
    await verifySameFolder(b.dir, async () => ({ sameFolder: false }));
    expect(b.state.removed).toEqual(['.editor-store-check.json']);
  });

  it('still answers when the marker cannot be deleted', async () => {
    // A leftover marker can never cause a FALSE match -- the next check mints a
    // fresh nonce, so a stale file reads as a mismatch. Not worth failing over.
    const { dir } = mockDir({ canRemove: false });
    await expect(verifySameFolder(dir, async () => ({ sameFolder: true })))
      .resolves.toEqual({ ok: true });
  });

  it('mints a FRESH nonce each time', async () => {
    // A reused nonce would let a stale marker in a DIFFERENT folder read as a
    // match -- the exact false pass this guard exists to prevent.
    const seen: string[] = [];
    for (let i = 0; i < 3; i++) {
      const { dir, state } = mockDir();
      // eslint-disable-next-line no-await-in-loop
      await verifySameFolder(dir, async () => {
        seen.push(writtenNonce(state));
        return { sameFolder: true };
      });
    }
    expect(new Set(seen).size).toBe(3);
  });

  it('propagates a backend failure instead of reporting a false pass', async () => {
    // If the backend cannot answer, "same folder" is UNPROVEN. The caller
    // treats a throw as unproven and leaves the server actions off.
    const { dir } = mockDir();
    await expect(
      verifySameFolder(dir, async () => { throw new Error('backend down'); }),
    ).rejects.toThrow('backend down');
  });
});
