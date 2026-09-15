/**
 * Guard: the PRODUCTION build of THIS app (frontend, schema form / demo mode)
 * contains no `console.log(` (bd polyglot-pdf-8v8i7). This is the build-time
 * backstop for the console-PII sites deleted in the source: even a value-
 * carrying call this scan missed is stripped from what actually ships,
 * because the production vite config sets `esbuild: { pure: ['console.log',
 * 'console.debug'] }` -- deliberately NOT `drop: ['console']`, which would
 * also remove `console.warn`/`console.error` that staff read on staging.
 *
 * ONE APP PER FILE, deliberately (Opus cross-surface round 5): an earlier
 * version of this test built all three apps (frontend, schema-editor,
 * admin-console) from inside frontend's own vitest run. That works locally
 * because a worktree here carries a node_modules JUNCTION into all three
 * apps, but CI's frontend job (.github/workflows/ci.yml) runs `npm ci` only
 * in frontend/ -- schema-editor and admin-console have no node_modules
 * there at all, so those two builds fail with "tsc: not found" and the
 * frontend CI job goes permanently red. Each app now owns its OWN copy of
 * this test (schema-editor/src/bundleNoConsoleLog.test.ts,
 * admin-console/src/bundleNoConsoleLog.test.ts), building only itself, run
 * by that app's own CI job -- which already `npm ci`s its own deps.
 *
 * This test actually RUNS the production build (the same command
 * `npm run build:schema:demo` uses) and greps the emitted JS for the
 * literal property access `console.log(` -- the PROPERTY, not a particular
 * call shape, so a differently-argued console.log site still fails this
 * test. It does not assert `console.debug(` is absent from the bundle text
 * because no source in this repo calls it today; `pure` still covers it if
 * one is added later (a separate config test pins the `pure` list itself).
 *
 * COST: one real production build, roughly 10-15 seconds on a normal dev
 * machine. Keep it anyway: the bead's exit criterion is a property of the
 * SHIPPED BUNDLE, and nothing short of building it actually verifies that.
 * Do not exclude it from a routine run to save time.
 *
 * FAILS CLOSED, deliberately, on every silent-skip shape:
 *  - A failing build: `execFileSync` throws on a non-zero exit code, which
 *    fails the `it()` -- there is no try/catch here to swallow that.
 *  - This app's demo build needs `.env.demo` (git-committed) for Vite's
 *    `--mode demo` env loading; a MISSING file does not fail the build
 *    (Vite just falls back to code defaults), so it is checked to exist
 *    explicitly before the build runs, with its own assertion.
 *  - A build that "succeeds" but emits no dist/assets directory, or an
 *    empty one: `bundledJsFiles` throws on a missing directory (propagating
 *    out of the `it()`), and an explicit assertion rejects an empty file
 *    list even if the directory does exist but is empty.
 */
import { describe, expect, it } from "vitest";
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { withBuildLock } from "./testBuildLock";

const APP_ROOT = join(__dirname, "..", "..");
// Two build-running test files serialize on withBuildLock, so the waiting
// file's budget must cover BOTH builds on a cold CI runner.
const BUILD_TIMEOUT_MS = 300_000;
const DIST_DIR = join(APP_ROOT, "dist");
const REQUIRED_FILE = join(APP_ROOT, ".env.demo");

/** All .js files directly inside dist/assets/ (where vite emits bundled JS). */
function bundledJsFiles(distDir: string): string[] {
  const assetsDir = join(distDir, "assets");
  return readdirSync(assetsDir)
    .filter((f) => f.endsWith(".js"))
    .map((f) => join(assetsDir, f));
}

describe("production bundle: frontend (schema form, demo mode)", () => {
  it(
    "contains no console.log( in the built JS",
    () => {
      expect(
        existsSync(REQUIRED_FILE),
        `Required file missing -- the build would silently skip this config: ${REQUIRED_FILE}`
      ).toBe(true);

      withBuildLock(() =>
        execFileSync("npm", ["run", "build:schema:demo"], {
          cwd: APP_ROOT,
          stdio: "pipe",
          shell: true,
        })
      );

      const jsFiles = bundledJsFiles(DIST_DIR);
      expect(jsFiles.length).toBeGreaterThan(0);

      const offenders: string[] = [];
      for (const file of jsFiles) {
        const content = readFileSync(file, "utf8");
        if (content.includes("console.log(")) {
          offenders.push(file);
        }
      }

      expect(offenders).toEqual([]);
    },
    BUILD_TIMEOUT_MS
  );
});
