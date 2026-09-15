/**
 * Guard: THIS app's (frontend, schema form / demo mode) Vite config always
 * serves assets from an ABSOLUTE base path, and a real production build's
 * emitted `index.html` actually references them that way (bd
 * polyglot-pdf-3bsyv).
 *
 * BACKGROUND. `frontend/vite.config.schema.ts` used to set `base: './'`
 * (relative). This app is always served from a Hosting site ROOT
 * (`polyglot-app-staging.web.app`, `polyglot-demo-aa709.web.app`) or from
 * dev-local's root -- never from a subdirectory -- so a relative base was
 * never correct: `index.html` referenced `./assets/vendor-react-*.js`, which
 * the browser resolves relative to the CURRENT PATH, not the site root. A
 * cold load at any path with a segment (`/console/links`,
 * `/console/employees`, `/console/links/history`) then
 * requested `/console/assets/...`, which does not exist, and
 * `firebase.json`'s catch-all `"**" -> /index.html` rewrite answered with
 * HTML instead of JS -- the browser then refuses the module script with
 * "Expected a JavaScript-or-Wasm module script but the server responded
 * with a MIME type of text/html". Only the site root ever worked on a cold
 * load; client-side navigation FROM the root hid the bug (no re-fetch of
 * hashed assets), which is why it survived undetected.
 *
 * TWO LAYERS, deliberately:
 *  1. A STATIC read of `vite.config.schema.ts`'s source text for the `base:`
 *     value. Fast (no build), and it is what a reviewer or future editor
 *     will grep for first; it also fails immediately (not after a 10-20s
 *     build) if someone reverts the literal.
 *  2. A REAL production build (mirrors `bundleNoConsoleLog.test.ts`'s
 *     pattern in this same directory) whose emitted `frontend/dist/index.html`
 *     is asserted to reference `/assets/` absolutely, not `./assets/` or a
 *     bare `assets/`. This is the layer that actually verifies the SHIPPED
 *     artifact, not just the config source -- a static-only check could not
 *     tell you whether some other build setting silently overrides `base`.
 *
 * MUTATION-VERIFIED (CLAUDE.md scar #9): temporarily flipping the config's
 * `base` back to `'./'` fails BOTH layers -- the static assertion on the
 * literal, and the build assertion on the emitted `href="./assets/...`/
 * `src="./assets/...` markup -- then restored; see the journal entry for
 * bd polyglot-pdf-3bsyv for the transcript.
 *
 * ONE APP PER FILE (same reasoning as bundleNoConsoleLog.test.ts): this test
 * builds only the `frontend` app the way `bundleNoConsoleLog.test.ts` does,
 * for the same CI-isolation reason (schema-editor and admin-console have no
 * node_modules in the frontend-only CI job). schema-editor and admin-console
 * already default `base` to `/` (no override in either app's vite config --
 * admin-console's absolute-asset behavior is confirmed live) so they need no
 * sibling copy of this test; this file only pins the app that regressed.
 *
 * COST: one real production build, roughly 10-15 seconds on a normal dev
 * machine (build test only -- the static test is instant). Keep it anyway:
 * exit criterion 1 for bd polyglot-pdf-3bsyv is a property of the SHIPPED
 * bundle, and nothing short of building it actually verifies that.
 */
import { describe, expect, it } from "vitest";
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { withBuildLock } from "./testBuildLock";

const APP_ROOT = join(__dirname, "..", "..");
const VITE_CONFIG_PATH = join(APP_ROOT, "vite.config.schema.ts");
// Two build-running test files serialize on withBuildLock, so the waiting
// file's budget must cover BOTH builds on a cold CI runner.
const BUILD_TIMEOUT_MS = 300_000;
const DIST_DIR = join(APP_ROOT, "dist");
const DIST_INDEX_HTML = join(DIST_DIR, "index.html");
const REQUIRED_FILE = join(APP_ROOT, ".env.demo");

describe("frontend/vite.config.schema.ts: base is absolute", () => {
  it("sets base: '/' (not a relative path)", () => {
    const source = readFileSync(VITE_CONFIG_PATH, "utf8");
    // Match the exact `base:` assignment line so a reviewer changing quote
    // style or adding a trailing comment does not silently defeat this
    // (unlike a bare `includes("base: '/'")`, which a `base: '/console/'`
    // typo would still satisfy -- so also assert the relative form is gone).
    // Anchored to the START of a line so a `base: './'` mention inside the
    // config's own comment block can never satisfy (or spuriously fail) this.
    const baseLineMatch = source.match(/^\s*base:\s*(['"])(.*?)/m);
    expect(
      baseLineMatch,
      `Could not find a base: '...' assignment in ${VITE_CONFIG_PATH}`
    ).not.toBeNull();
    const baseValue = baseLineMatch![2];
    expect(baseValue).toBe("/");
  });
});

describe("production bundle: frontend (schema form, demo mode) references assets absolutely", () => {
  it(
    "built index.html references /assets/ with a leading slash, not ./assets/",
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

      expect(
        existsSync(DIST_INDEX_HTML),
        `Build did not emit ${DIST_INDEX_HTML}`
      ).toBe(true);

      const html = readFileSync(DIST_INDEX_HTML, "utf8");

      // Every asset reference (script src, stylesheet href, modulepreload)
      // Vite emits for a hashed build asset must start with /assets/, never
      // a relative ./assets/ or a bare assets/ (both resolve against the
      // CURRENT PATH in the browser, not the site root, which is exactly
      // the bug this test pins). Collect every quoted assets-directory
      // reference and check ALL of them, not just the first.
      const assetRefs = [...html.matchAll(/["'](\.?\/?assets\/[^"']+)["']/g)].map(
        (m) => m[1]
      );
      expect(
        assetRefs.length,
        `No /assets/ references found in ${DIST_INDEX_HTML} -- did the build output change shape?`
      ).toBeGreaterThan(0);

      const nonAbsolute = assetRefs.filter((ref) => !ref.startsWith("/assets/"));
      expect(nonAbsolute).toEqual([]);
    },
    BUILD_TIMEOUT_MS
  );
});
