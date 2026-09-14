/**
 * Guard: the PRODUCTION build of all three apps contains no `console.log(`
 * (bd polyglot-pdf-8v8i7). This is the build-time backstop for the
 * console-PII sites deleted in the source: even a value-carrying call this
 * scan missed is stripped from what actually ships, because each app's
 * production vite config sets `esbuild: { pure: ['console.log',
 * 'console.debug'] }` -- deliberately NOT `drop: ['console']`, which would
 * also remove `console.warn`/`console.error` that staff read on staging.
 *
 * This test actually RUNS each app's production build (the same command
 * `npm run build:schema:demo` / `build:hosted` uses) and grep the emitted
 * JS for the literal property access `console.log(` -- the PROPERTY, not a
 * particular call shape, so a differently-argued console.log site still
 * fails this test. It does not assert `console.debug(` is absent from the
 * bundle text because no source in this repo calls it today; `pure` still
 * covers it if one is added later (a separate config test pins the `pure`
 * list itself).
 *
 * COST: this runs three real production builds -- roughly 45-50 seconds
 * total on a normal dev machine. Keep it anyway: the bead's exit criterion
 * is a property of the SHIPPED BUNDLE, and nothing short of building it
 * actually verifies that. Do not exclude it from a routine run to save time.
 *
 * FAILS CLOSED, deliberately, on every silent-skip shape:
 *  - A failing build: `execFileSync` throws on a non-zero exit code, which
 *    fails the `it()` -- there is no try/catch here to swallow that.
 *  - The frontend app's demo build needs `.env.demo` (git-committed) for
 *    Vite's `--mode demo` env loading; a MISSING file does not fail the
 *    build (Vite just falls back to code defaults), so it is checked to
 *    exist explicitly before the build runs, with its own assertion.
 *  - A build that "succeeds" but emits no dist/assets directory, or an
 *    empty one: `bundledJsFiles` throws on a missing directory (propagating
 *    out of the `it()`), and an explicit assertion rejects an empty file
 *    list even if the directory does exist but is empty.
 */
import { describe, expect, it } from "vitest";
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const REPO_ROOT = join(__dirname, "..", "..", "..");
const BUILD_TIMEOUT_MS = 120_000;

interface AppBuild {
  name: string;
  cwd: string;
  buildArgs: string[];
  distDir: string;
  // Files that must exist before the build runs, or the build would
  // silently skip real config (e.g. a missing `.env.<mode>` -- Vite does
  // not error on that, it just falls back to code defaults).
  requiredFiles?: string[];
}

const APPS: AppBuild[] = [
  {
    name: "frontend (schema form, demo mode)",
    cwd: join(REPO_ROOT, "frontend"),
    buildArgs: ["run", "build:schema:demo"],
    distDir: join(REPO_ROOT, "frontend", "dist"),
    requiredFiles: [join(REPO_ROOT, "frontend", ".env.demo")],
  },
  {
    name: "schema-editor (hosted mode)",
    cwd: join(REPO_ROOT, "schema-editor"),
    buildArgs: ["run", "build:hosted"],
    distDir: join(REPO_ROOT, "schema-editor", "dist"),
  },
  {
    name: "admin-console (hosted mode)",
    cwd: join(REPO_ROOT, "admin-console"),
    buildArgs: ["run", "build:hosted"],
    distDir: join(REPO_ROOT, "admin-console", "dist"),
  },
];

/** All .js files directly inside dist/assets/ (where vite emits bundled JS). */
function bundledJsFiles(distDir: string): string[] {
  const assetsDir = join(distDir, "assets");
  return readdirSync(assetsDir)
    .filter((f) => f.endsWith(".js"))
    .map((f) => join(assetsDir, f));
}

describe.each(APPS)("production bundle: $name", (app) => {
  it(
    "contains no console.log( in the built JS",
    () => {
      for (const requiredFile of app.requiredFiles ?? []) {
        expect(
          existsSync(requiredFile),
          `Required file missing -- the build would silently skip this config: ${requiredFile}`
        ).toBe(true);
      }

      execFileSync("npm", app.buildArgs, {
        cwd: app.cwd,
        stdio: "pipe",
        shell: true,
      });

      const jsFiles = bundledJsFiles(app.distDir);
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
