---
date: 2026-06-05
bead: polyglot-pdf-ajx
title: "Vite 5->6 + Vitest 1->3 to clear the esbuild dev-server advisory"
tags: [security, conventions, testing]
---

## Trigger

`npm audit` on `frontend/` flagged a dev-tooling vulnerability chain. The root
advisory is GHSA-67mh-4wv8-2f99: `vite@5` pins a nested `esbuild@0.21.5` whose dev
server sets `Access-Control-Allow-Origin: *`, letting any website the developer
visits read the compiled bundle off `localhost`. Moderate (CVSS 5.3), and
**dev-server only -- no production-app exposure** (the shipped Firebase Hosting
bundle is unaffected). The chain also carried a `vite` path-traversal and the
`vite-node` transitive. `npm audit fix --force` wanted `vite@8` -- a three-major
jump (5 -> 6 -> 7 -> 8) that would break the four Vite config files + two react
plugins. The maintainer explicitly asked to avoid that sledgehammer.

## What shipped

Minimal remediation, two `devDependencies` bumps (+ regenerated lockfile):
- `vite ^5.4.0 -> ^6.4.3` -- pulls patched `esbuild ^0.25.0`.
- `vitest ^1.6.0 -> ^3.2.6` -- **required, not optional**: `vitest@2.1.x` still
  bundles its OWN nested `vite@5` / `esbuild@0.21.5`, so bumping only Vite to 6
  leaves the advisory alive via the test runner. `vitest@3` dedupes onto the
  top-level `vite@6`, collapsing the duplicate tree (lockfile nets -731 lines).

`@vitejs/plugin-react ^4.3` / `plugin-react-swc ^4.2` already support Vite 6;
`@types/node ^20` + `jsdom ^27` satisfy Vitest 3's peers -- no other dep moved.

**Verification (this is a build-tool change, so the proof is that builds + tests
still work):**
- `npm run build` (main app, `plugin-react`) -- OK on vite 6.4.3.
- `npm run build:schema` (`plugin-react-swc`) -- OK.
- `vitest run --environment jsdom` -- 83 pass / 3 fail. The 3 failures are
  **pre-existing**, verified by running the same file on the `dev` baseline
  (vite 5 / vitest 1.6.1): identical 3-fail/83-pass. The upgrade introduced ZERO
  new failures.

### Decisions made autonomously (defended)

- **Stop at Vitest 3, not 4 (maintainer-approved).** `npm audit` still flags
  `vitest <4.1.0` critical (GHSA-5xrq-8626-4rwp, "Vitest UI server arbitrary file
  read"). That advisory requires the `@vitest/ui` package (NOT installed) and a
  `vitest --ui` invocation (in NO package.json script), so it is **unreachable**
  in this repo. npm audit flags it by version range, not reachability. Vitest 4 is
  another major bump purely to silence a flag for an unused code path -- declined.
  (Surfaced to the maintainer as the one genuine cost/risk tradeoff; they chose
  stop-at-3.)
- **Filed, did not fix, the 3 pre-existing test failures.** `DisclaimerModal.test.tsx`
  lines 21/28/35 use regex `getByText` for the disclaimer BODY substring, which
  `@testing-library` cannot match inside a longer `<p>` node. Out of scope for a
  security dep-bump -> filed `polyglot-pdf-pwt` (P3 bug) rather than expanding this
  PR. Fixing it here would have coupled a test rewrite to a dependency change.
- **Own bead + PR, not bundled into the firestore-rules PR (#86).** Unrelated
  change; #86 had already merged, so this branched fresh off updated `dev`.

## Doc freshness

- `docs/standards/testing.md` (Tracks `frontend/package.json`): updated the
  frontend stack line from `vitest ^1.6.0` to `vitest ^3.2.6` (on `vite ^6.4.3`);
  bumped both `Last updated:` lines to 2026-06-05 pointing here. (Its line about
  the disclaimer-modal test "running" is pre-existingly inaccurate given the 3
  failures; left as-is because the accuracy fix is coupled to the test fix in
  `polyglot-pdf-pwt`.)
- All other STALE entries from `check_doc_freshness.py` track backend/frontend
  source files this branch does not touch (config.py, live_ai_gemini.py,
  websocket_routes.py, etc.) -- pre-existing mtime noise, not introduced here.

## Files touched

- `frontend/package.json` -- vite `^5.4.0`->`^6.4.3`, vitest `^1.6.0`->`^3.2.6`.
- `frontend/package-lock.json` -- regenerated (net -731 lines from dedup).
- `docs/standards/testing.md` -- frontend stack version + `Last updated`.
