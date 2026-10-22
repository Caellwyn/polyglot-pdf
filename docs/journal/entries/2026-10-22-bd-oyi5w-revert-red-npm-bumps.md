---
date: 2026-10-22
bead: polyglot-pdf-oyi5w
title: "fix(deps): revert the red grouped npm bumps #880/#884/#885 (frontend typecheck broken; blocks staging verify)"
tags: [hotfix, testing]
---

## Trigger

While closing out the backend pin-back (bd `polyglot-pdf-niwcu`, PR #887),
its CI showed `frontend vitest`, `admin-console vitest` and `schema-editor
vitest` failing on files that PR never touched. The cause was the three grouped
npm Dependabot PRs: #880 (frontend), #884 (admin-console) and #885
(schema-editor). All three were merged RED on 2026-10-22 between 01:35 and
01:36, the same minute as the backend #882.

Cloud Build's `verify` gate runs `npm ci && npm run typecheck && npm run
test:run` for the frontend and the admin console. So staging would have stayed
blocked even with the backend pin-back merged.

## What shipped

A `git revert` of all three PRs. It restores their exact `package.json` files
and the Linux-generated lockfiles, so nothing is regenerated on Windows (the
known lockfile-skew trap). The reverted majors are:

- React 18 -> 19 (all three apps), with the matching type and
  testing-library packages
- react-router-dom 6 -> 7 (frontend)
- pdfjs-dist 4 -> 6 (frontend and schema-editor)
- tailwindcss 3 -> 4 (admin-console and schema-editor)
- jsdom 27 -> 30 and @testing-library/jest-dom 6 -> 7

Typecheck had already caught pdfjs-dist 6's viewer-API changes and React 19's
`useRef()` signature. Tailwind 4 is an engine rewrite that changes how pages
LOOK without failing a single test.

Each upgrade is its own bead, and each exit criterion includes a browser
check: `lhrnq` React 19, `q0i7k` pdfjs 6, `umd8r` Tailwind 4, `vxssq`
react-router 7, `50zcc` jsdom/jest-dom. Holding npm majors out of the groups is
bd `fx8gg`. It follows #887, because both edit `.github/dependabot.yml`.

**Verification** (local, on the reverted lockfiles): `npm ci`, typecheck and
vitest all pass for the three apps. The frontend ran 170 files and 2,405 tests.

## Lessons

- **One bad batch can break several gates.** The backend failure stopped
  Cloud Build's verify before it reached the frontend steps, which hid a
  second break behind the first. When a gate fails early, check the REST of
  that gate's steps against the same commit before declaring the fix complete.
- **Windows MAX_PATH bites npm too.** esbuild's binary under a deep scratch
  path failed `npm ci` with ENOENT. Run installs through a short junction.

## Doc freshness

None of the tier-1/2 docs track package.json or lockfiles for version claims.
`docs/standards/testing.md` describes the npm toolchain exclusions, which are
unchanged here (bd `fx8gg` will touch them).

## Files touched

- frontend, admin-console, schema-editor: package.json and package-lock.json
  (git revert of #880, #884, #885)
