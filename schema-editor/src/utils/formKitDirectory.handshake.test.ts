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
import { verifySameFolder, verifySameFolderForExtractor } from './formKitDirectory';
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

// --- cross-channel independence (bd polyglot-pdf-bagn) ---------------------- //
//
// TWO channels now run this handshake against the SAME picked folder: the
// backend store check (App.handleRootChange, bd s2bf) and the Vite extractor
// check (FormCatalogue.handleRunExtraction, bd ball). They are not serialized
// against each other -- handlePickFolder bars a folder SWITCH during extraction,
// but the App handshake is already in flight from the folder pick.
//
// While they shared one fixed marker filename, either channel's cleanup deleted
// the other's in-flight marker, so a folder that genuinely agrees was refused
// with "not the one the extractor uses". Fail-closed, but actively misleading.
// Each channel now writes its OWN marker name, which makes the interference
// structurally impossible rather than merely unlikely.

/** A directory shared by both channels, so a cross-channel delete is visible. */
function sharedDir() {
  const files = new Map<string, string>();
  const dir = {
    getFileHandle: async (name: string) => ({
      createWritable: async () => ({
        write: async (d: string | ArrayBuffer) => {
          files.set(name, typeof d === 'string' ? d : '');
        },
        close: async () => {},
      }),
    }),
    removeEntry: async (name: string) => { files.delete(name); },
  } as unknown as FsDirectoryHandle;
  return { dir, files };
}

describe('two channels on one folder (bd polyglot-pdf-bagn)', () => {
  it('a concurrently-finishing backend check does not void an extraction check', async () => {
    const { dir, files } = sharedDir();

    // Channel A (backend) is mid-flight; we hold it open, then let it finish
    // WHILE channel B (extractor) is waiting on its own answer.
    let releaseA: () => void = () => {};
    const aHeld = new Promise<void>((r) => { releaseA = r; });

    const aDone = verifySameFolder(dir, async () => {
      await aHeld;
      return { sameFolder: true };
    });

    // Channel B is the EXTRACTOR check -- the pairing that actually occurs, and
    // the one that used to break. It writes its marker, then asks; its asker
    // reads what is ON DISK at ask time, exactly as the real Vite host does. If
    // A's cleanup removed B's marker, B sees nothing and refuses a folder that
    // agrees.
    let bSaw: string | null = null;
    const bDone = verifySameFolderForExtractor(dir, async (nonce) => {
      releaseA();          // A now completes, running its finally-cleanup
      await aDone;         // ...and is fully done before B looks
      // Emulate the host reading the marker back out of the shared folder.
      const marker = [...files.values()]
        .map((raw) => { try { return JSON.parse(raw).nonce; } catch { return null; } })
        .find((n) => n === nonce) ?? null;
      bSaw = marker;
      return { sameFolder: marker === nonce };
    });

    const b = await bDone;
    expect(bSaw).not.toBeNull();   // B's marker survived A's cleanup
    expect(b).toEqual({ ok: true }); // and the agreeing folder is NOT refused
  });

  it('both markers coexist while BOTH checks are in flight', async () => {
    // Genuinely concurrent, which is the property the name claims. An earlier
    // version awaited the two calls in sequence, so only one marker ever existed
    // at a time -- it proved the constants differ (already covered by
    // markerNames.contract.test.ts) but not that the files coexist.
    const { dir, files } = sharedDir();
    let releaseA: () => void = () => {};
    let releaseB: () => void = () => {};
    const aHeld = new Promise<void>((r) => { releaseA = r; });
    const bHeld = new Promise<void>((r) => { releaseB = r; });
    let bothInFlight: string[] = [];

    const a = verifySameFolder(dir, async () => { await aHeld; return { sameFolder: true }; });
    const b = verifySameFolderForExtractor(dir, async () => {
      // Both markers are now written and neither check has cleaned up.
      bothInFlight = [...files.keys()].sort();
      await bHeld;
      return { sameFolder: true };
    });
    // Let B reach its asker, snapshot, then unwind both.
    await Promise.resolve();
    releaseB(); releaseA();
    await Promise.all([a, b]);

    expect(bothInFlight).toHaveLength(2);            // two distinct files on disk
    expect(bothInFlight[0]).not.toBe(bothInFlight[1]);
    expect(files.size).toBe(0);                      // both cleaned up after
  });

  it('the reverse direction too: an extraction check cannot void a backend check', async () => {
    // The bagn fix is symmetric, but this direction has the LARGER blast radius:
    // a voided backend check sets folderCheck={ok:false}, which opens the s2bf
    // mismatch modal and drives serverActionsOk false -- disabling Repair all,
    // Regenerate divisions, Rewrite guidance and the widget picker. Pin it too,
    // so a refactor that re-shares the backend marker cannot pass on the
    // extractor-direction test alone.
    const { dir, files } = sharedDir();
    let releaseExtractor: () => void = () => {};
    const held = new Promise<void>((r) => { releaseExtractor = r; });

    const extractorDone = verifySameFolderForExtractor(dir, async () => {
      await held;
      return { sameFolder: true };
    });

    let backendSaw: string | null = null;
    const backendDone = verifySameFolder(dir, async (nonce) => {
      releaseExtractor();      // the extractor check completes, running cleanup
      await extractorDone;
      backendSaw = [...files.values()]
        .map((raw) => { try { return JSON.parse(raw).nonce; } catch { return null; } })
        .find((n) => n === nonce) ?? null;
      return { sameFolder: backendSaw === nonce };
    });

    expect(await backendDone).toEqual({ ok: true });
    expect(backendSaw).not.toBeNull();
  });

  it('STILL fail-closed: a distinct marker cannot satisfy the other channel', async () => {
    // The whole point of the gate. A per-check nonce plus a per-channel filename
    // must not open any path to a false PASS on a folder that disagrees.
    const { dir } = sharedDir();
    const res = await verifySameFolderForExtractor(dir, async () => (
      { sameFolder: false, backendRoot: '/elsewhere' }
    ));
    expect(res.ok).toBe(false);
  });

  it('STILL fail-closed: an unwritable folder refuses on the extractor channel too', async () => {
    const dir = {
      getFileHandle: async () => { throw new DOMException('ro', 'NotAllowedError'); },
    } as unknown as FsDirectoryHandle;
    const res = await verifySameFolderForExtractor(dir, async () => ({ sameFolder: true }));
    expect(res).toEqual({ ok: false, reason: 'unwritable' });
  });
});
