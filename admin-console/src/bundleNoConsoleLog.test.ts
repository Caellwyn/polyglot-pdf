/**
 * Guard: the PRODUCTION build of THIS app (admin-console, hosted mode)
 * contains no `console.log(` (bd polyglot-pdf-8v8i7). This is the build-time
 * backstop for console-PII sites: even a value-carrying call a source scan
 * missed is stripped from what actually ships, because the production vite
 * config sets `esbuild: { pure: ['console.log', 'console.debug'] }` --
 * deliberately NOT `drop: ['console']`, which would also remove
 * `console.warn`/`console.error` that staff read on staging.
 *
 * ONE APP PER FILE, deliberately (Opus cross-surface round 5): this test
 * used to live only in frontend/src/shared/bundleNoConsoleLog.test.ts and
 * built all three apps from inside frontend's own vitest run. That worked
 * locally because a worktree here carries a node_modules JUNCTION into all
 * three apps, but CI's frontend job (.github/workflows/ci.yml) runs
 * `npm ci` only in frontend/ -- this app has no node_modules there at all,
 * so building it from frontend's job failed with "tsc: not found" and made
 * the frontend CI job permanently red. This app now owns its own copy,
 * building only itself, run by ITS OWN CI job -- which already `npm ci`s
 * its own deps. See frontend/src/shared/bundleNoConsoleLog.test.ts for the
 * sibling copies (frontend itself, schema-editor).
 *
 * This test actually RUNS the production build (the same command
 * `npm run build:hosted` uses) and greps the emitted JS for the literal
 * property access `console.log(` -- the PROPERTY, not a particular call
 * shape, so a differently-argued console.log site still fails this test.
 *
 * COST: one real production build, roughly 5-10 seconds on a normal dev
 * machine. Keep it anyway: the bead's exit criterion is a property of the
 * SHIPPED BUNDLE, and nothing short of building it actually verifies that.
 * Do not exclude it from a routine run to save time.
 *
 * FAILS CLOSED, deliberately, on every silent-skip shape:
 *  - A failing build: `execFileSync` throws on a non-zero exit code, which
 *    fails the `it()` -- there is no try/catch here to swallow that.
 *  - A build that "succeeds" but emits no dist/assets directory, or an
 *    empty one: `bundledJsFiles` throws on a missing directory (propagating
 *    out of the `it()`), and an explicit assertion rejects an empty file
 *    list even if the directory does exist but is empty.
 */
import { describe, expect, it } from "vitest";
import { execFileSync } from "node:child_process";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const APP_ROOT = join(__dirname, "..");
const BUILD_TIMEOUT_MS = 120_000;
const DIST_DIR = join(APP_ROOT, "dist");

/** All .js files directly inside dist/assets/ (where vite emits bundled JS). */
function bundledJsFiles(distDir: string): string[] {
  const assetsDir = join(distDir, "assets");
  return readdirSync(assetsDir)
    .filter((f) => f.endsWith(".js"))
    .map((f) => join(assetsDir, f));
}

describe("production bundle: admin-console (hosted mode)", () => {
  it(
    "contains no console.log( in the built JS",
    () => {
      execFileSync("npm", ["run", "build:hosted"], {
        cwd: APP_ROOT,
        stdio: "pipe",
        shell: true,
      });

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
