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
 * OWNERSHIP. The holder writes a random token into the lock directory and
 * only releases a lock that still carries ITS token, so a waiter can never
 * remove a live holder's lock. Stale-lock recovery (a killed run left a
 * lock older than STALE_LOCK_MS) is an atomic `renameSync` of the stale
 * directory to a unique name before removal: exactly one waiter wins the
 * rename, the others see ENOENT and simply retry `mkdirSync`.
 *
 * Only the build-running tests take this lock, so the rest of the suite
 * stays parallel. Any future test that runs a real build must wrap its
 * build call in `withBuildLock` too.
 */
import { randomBytes } from "node:crypto";
import { mkdirSync, readFileSync, renameSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const LOCK_DIR = join(tmpdir(), "polyglot-frontend-build.lock");
const OWNER_FILE = join(LOCK_DIR, "owner");
/** A holder that died without releasing (a killed test run) must not block
 *  every later run forever: a lock older than this is treated as abandoned. */
const STALE_LOCK_MS = 10 * 60 * 1000;
const POLL_MS = 250;
const WAIT_TIMEOUT_MS = 10 * 60 * 1000;

function sleepSync(ms: number): void {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

function evictIfStale(): void {
  let age: number;
  try {
    age = Date.now() - statSync(LOCK_DIR).mtimeMs;
  } catch {
    return; // released between our EEXIST and this stat; retry mkdir
  }
  if (age <= STALE_LOCK_MS) return;
  const graveyard = `${LOCK_DIR}.stale-${process.pid}-${randomBytes(4).toString("hex")}`;
  try {
    renameSync(LOCK_DIR, graveyard); // atomic: only one waiter wins
  } catch {
    return; // another waiter evicted it first (ENOENT); retry mkdir
  }
  rmSync(graveyard, { recursive: true, force: true });
}

function tryAcquire(token: string): boolean {
  try {
    mkdirSync(LOCK_DIR);
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code !== "EEXIST") throw err;
    evictIfStale();
    return false;
  }
  writeFileSync(OWNER_FILE, token);
  return true;
}

function releaseIfOwned(token: string): void {
  let owner = "";
  try {
    owner = readFileSync(OWNER_FILE, "utf8");
  } catch {
    return; // evicted as stale by a waiter (or never ours); nothing to release
  }
  if (owner === token) rmSync(LOCK_DIR, { recursive: true, force: true });
}

/** Run `fn` while holding the build lock; released in `finally`, and only if
 *  this process still owns it. Throws if the lock cannot be acquired within
 *  WAIT_TIMEOUT_MS (a wedged holder). */
export function withBuildLock<T>(fn: () => T): T {
  const token = `${process.pid}-${randomBytes(8).toString("hex")}`;
  const deadline = Date.now() + WAIT_TIMEOUT_MS;
  while (!tryAcquire(token)) {
    if (Date.now() > deadline) {
      throw new Error(`timed out waiting for the frontend build lock at ${LOCK_DIR}`);
    }
    sleepSync(POLL_MS);
  }
  try {
    return fn();
  } finally {
    releaseIfOwned(token);
  }
}
