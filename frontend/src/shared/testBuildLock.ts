/**
 * Cross-PROCESS mutex for tests that run a real production build (bd
 * polyglot-pdf-3bsyv, Opus cross-surface finding 1).
 *
 * WHY A FILE LOCK, NOT AN IN-MEMORY ONE. vitest's default forks pool runs
 * every test FILE in its own Node process, so two build-running test files
 * (bundleNoConsoleLog.test.ts and buildAbsoluteAssetBase.test.ts) start
 * `npm run build:schema:demo` at the same time. That script's prebuild step
 * `rm -rf`s the shared `frontend/public/form-kits`, and the build itself
 * empties the shared `frontend/dist`, so the two builds trample each other
 * (EPERM on the rmdir, or one build's index.html read while the other is
 * mid-write). An in-memory mutex cannot be shared across processes; an
 * atomic `mkdirSync` on a directory under the OS temp dir can.
 *
 * Only the build-running tests take this lock, so the rest of the suite
 * stays parallel. Any future test that runs a real build must wrap its
 * build call in `withBuildLock` too.
 */
import { mkdirSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const LOCK_DIR = join(tmpdir(), "polyglot-frontend-build.lock");
/** A holder that died without releasing (a killed test run) must not block
 *  every later run forever: a lock older than this is treated as abandoned. */
const STALE_LOCK_MS = 10 * 60 * 1000;
const POLL_MS = 250;
const WAIT_TIMEOUT_MS = 10 * 60 * 1000;

function sleepSync(ms: number): void {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

function tryAcquire(): boolean {
  try {
    mkdirSync(LOCK_DIR);
    return true;
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code !== "EEXIST") throw err;
    try {
      const age = Date.now() - statSync(LOCK_DIR).mtimeMs;
      if (age > STALE_LOCK_MS) rmSync(LOCK_DIR, { recursive: true, force: true });
    } catch {
      // Raced with the holder releasing it; the next attempt sees the truth.
    }
    return false;
  }
}

/** Run `fn` while holding the build lock; released in `finally`. Throws if
 *  the lock cannot be acquired within WAIT_TIMEOUT_MS (a wedged holder). */
export function withBuildLock<T>(fn: () => T): T {
  const deadline = Date.now() + WAIT_TIMEOUT_MS;
  while (!tryAcquire()) {
    if (Date.now() > deadline) {
      throw new Error(`timed out waiting for the frontend build lock at ${LOCK_DIR}`);
    }
    sleepSync(POLL_MS);
  }
  try {
    return fn();
  } finally {
    rmSync(LOCK_DIR, { recursive: true, force: true });
  }
}
