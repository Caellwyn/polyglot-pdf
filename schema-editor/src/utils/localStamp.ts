/**
 * Local-save readiness stamping (sprint-18 C4b, bd polyglot-pdf-na1zy).
 *
 * A LOCAL kit save is a File System Access write with no backend round trip,
 * so C4's stamps went stale the moment a local save landed (bd j8sr) and a
 * catalogue Refresh could move a kit's number BACKWARD (bd bqgr). This module
 * closes that with ONE writer preserved (the epic's thesis):
 *
 *   - `stampKitReadinessRemote` -- after a successful in-place kit save, POST
 *     the just-written schema to the backend, which recomputes and PERSISTS
 *     the stamp through the same `_stamp_readiness` the hosted save uses.
 *     Valid only when the same-folder handshake proved the backend serves the
 *     picked folder (App gates on `serverActionsOk`), so the file the backend
 *     writes IS the folder the catalogue reads.
 *   - `invalidateLocalStamp` -- when no backend is reachable (or the stamp
 *     call failed), mark the kit's existing stamp `verified: false` so the
 *     card degrades to the VERIFY HINT instead of rendering a confident
 *     percentage for a schema the stamp never measured. This writes no
 *     counts and computes nothing -- it only retracts a claim that is no
 *     longer true, so it is not a second stamp producer.
 *
 * Mirrors the backend's never-destroy rule: an unparseable metadata.json is
 * left untouched (replacing a corrupt-but-recoverable file would delete the
 * kit's status/label -- see `_stamp_readiness`'s docstring), and a kit with
 * no metadata.json or no stamp needs no invalidation (the card already shows
 * the hint for an absent stamp).
 */
import type { FsDirectoryHandle } from './fileSystemAccess';
import { AuthError, ForbiddenError, apiBaseUrl } from './remoteKitStore';
import { editorIdToken } from './editorAuth';

const METADATA_FILE = 'metadata.json';

/** Ask the backend to recompute + persist the kit's readiness stamp for the
 * schema that was just saved to disk. Resolves to the stamp it wrote (snake
 * case, as metadata.json carries it) or null when stamping was skipped
 * server-side. Throws on HTTP failure (AuthError on 401, ForbiddenError on
 * 403) -- the caller falls back to invalidateLocalStamp so a dead backend
 * never leaves a stale confident number. */
export async function stampKitReadinessRemote(
  kitId: string, schema: unknown,
): Promise<Record<string, unknown> | null> {
  // Same per-user identity every other editor call carries
  // (bd polyglot-pdf-yswp3). This route does NOT go through editorFetch --
  // it is one of two direct fetch sites in the editor -- so the token and the
  // 401/403 split are repeated here deliberately rather than drifting apart.
  const token = await editorIdToken();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(
    `${apiBaseUrl()}/api/editor/kits/${encodeURIComponent(kitId)}/readiness`,
    { method: 'POST', headers, body: JSON.stringify(schema) },
  );
  if (res.status === 401) throw new AuthError();
  if (res.status === 403) throw new ForbiddenError();
  if (!res.ok) throw new Error(`Could not refresh the kit's progress (HTTP ${res.status})`);
  const body = (await res.json()) as { readiness?: Record<string, unknown> | null };
  return body.readiness ?? null;
}

/** Retract a kit's stamp claim after a save the backend could not measure:
 * set `readiness.verified = false` in the kit's metadata.json, preserving
 * every other key. No-ops (returns false) when there is nothing to retract --
 * no metadata.json, no readiness block, already unverified -- or when the
 * file is unparseable (never destroy a recoverable file). Returns true when
 * it wrote. */
export async function invalidateLocalStamp(
  dirHandle: FsDirectoryHandle,
): Promise<boolean> {
  let raw: string;
  try {
    const fh = await dirHandle.getFileHandle(METADATA_FILE);
    raw = await (await fh.getFile()).text();
  } catch {
    return false; // no metadata.json -> no stamp -> the card already hints
  }
  let meta: unknown;
  try {
    meta = JSON.parse(raw);
  } catch {
    return false; // unparseable -> never destroy (mirror the backend rule)
  }
  if (!meta || typeof meta !== 'object' || Array.isArray(meta)) return false;
  const m = meta as Record<string, unknown>;
  const stamp = m.readiness;
  if (!stamp || typeof stamp !== 'object' || Array.isArray(stamp)) return false;
  if ((stamp as Record<string, unknown>).verified === false) return false;
  const next = {
    ...m,
    readiness: { ...(stamp as Record<string, unknown>), verified: false },
  };
  const fh = await dirHandle.getFileHandle(METADATA_FILE);
  const writable = await fh.createWritable();
  try {
    await writable.write(JSON.stringify(next, null, 2));
  } finally {
    await writable.close();
  }
  return true;
}
