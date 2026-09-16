---
date: 2026-09-15
bead: polyglot-pdf-3bsyv
title: "fix(frontend): relative asset base breaks every deep link on Hosting (MIME text/html for chunks under /console/*)"
sprint: 22
tags: [hotfix, testing]
---

## Trigger

The maintainer opened `https://polyglot-app-staging.web.app/console/links`
directly on 2026-09-15 and got a browser error: "Failed to load module
script: Expected a JavaScript-or-Wasm module script but the server
responded with a MIME type of text/html" for `vendor-react-*.js`. Root
cause: `frontend/vite.config.schema.ts` set `base: './'`, so the built
`index.html` referenced `./assets/...` -- a path the browser resolves
against the CURRENT URL, not the site root. At any path carrying a segment
(`/console/links`, `/console/employees`, a client magic link with a path)
the browser instead asked for `/console/assets/...`, which does not exist;
`firebase.json`'s catch-all `"**" -> /index.html` rewrite answered with
HTML, and the browser refused to execute it as a module script. Only a
cold load of the bare site root ever worked; client-side navigation FROM
the root never re-fetches hashed assets, which is exactly why the bug
shipped and stayed invisible through every normal manual test.

## What shipped

- `frontend/vite.config.schema.ts`: `base` changed from `'./'` to `'/'`.
  Absolute is correct here because this app is always served from a
  Hosting site root (the `app`/`app-staging` targets) or dev-local's own
  root, never from a subdirectory -- there is no legitimate consumer of the
  relative form in this repo.
- New test, `frontend/src/shared/buildAbsoluteAssetBase.test.ts`, mirroring
  the existing `bundleNoConsoleLog.test.ts` pattern in the same directory:
  1. A static read of `vite.config.schema.ts`'s `base:` assignment,
     asserting the literal value is exactly `'/'`.
  2. A real production build (`npm run build:schema:demo`) whose emitted
     `frontend/dist/index.html` is asserted to reference every `/assets/`
     path with a leading slash -- the property that actually matters for
     the SHIPPED bundle, not just the source config.
  Mutation-verified (CLAUDE.md scar #9): reverted `base` back to `'./'`,
  reran both assertions -- both failed on the exact real regression (the
  static check on the literal, the build check on the emitted
  `./assets/main-*.js` / `./assets/vendor-react-*.js` / `./assets/main-*.css`
  markup) -- then restored and reconfirmed green.
- Checked `schema-editor/vite.config.ts` and `admin-console/vite.config.ts`
  per the bead's instruction: neither sets a `base` override at all, so
  both already default to Vite's own absolute `/` -- this bug was unique
  to `frontend/vite.config.schema.ts`. No change needed in either sibling
  app, and no separate consumer anywhere in the repo needs the relative
  form (`'./'` had no legitimate use here to preserve).
- Local verification of the fix's actual effect (short of a staging
  deploy): built the fixed config, then served `frontend/dist` from a
  throwaway local static server (bound to 127.0.0.1 only, no network
  calls) that reproduces `firebase.json`'s exact rewrite rule -- serve the
  requested file if it exists, else fall back to `/index.html`. Curl
  checks against it:
  - `GET /` -> `200 text/html` (site root, as before)
  - `GET /console/links` -> `200 text/html` (the SPA shell, correctly
    served by the catch-all rewrite for a deep-link path)
  - `GET /assets/main-C7RHmdVB.js` -> `200 text/javascript` (the hashed
    asset itself, requested at its ABSOLUTE path regardless of the
    referring page's path -- this is the check that would have failed
    under the old relative base, where the same asset would have been
    requested as `/console/assets/main-*.js` and received the `index.html`
    fallback body with a `text/html` content type instead)
  This is a local proxy for the real staging cold-load check named in the
  bead's exit criterion 2, not a substitute for it -- a live curl against
  `polyglot-app-staging.web.app/console/links` still needs to run after
  the next staging deploy, which is a maintainer-gated action this build
  session does not perform. Recorded here so the post-deploy check has a
  concrete "what to expect" baseline.

## Lessons

The doc-freshness convention (`docs/doc-architecture.md`: prune-on-bump,
replace the old stamp paragraph rather than appending a new one) applied
directly here -- `docs/components/config-deployment.md`'s existing stamp
was fully replaced rather than growing another parenthetical, keeping the
file current-state-only.

No new cross-cutting lesson beyond what `bundleNoConsoleLog.test.ts`
already established: a config-shape bug in a build tool is only really
pinned by building the artifact and inspecting it, not by reading the
config file alone (a static-only test could not distinguish "the value is
right" from "the value is right but something else overrides it").

## Doc freshness

- `docs/components/config-deployment.md`: bumped. Added
  `frontend/vite.config.schema.ts` to the `Tracks:` line and a new bullet
  under the Frontend deploy section explaining the former relative-base
  bug, why it was invisible to client-side navigation, and that
  schema-editor/admin-console were never affected. Stamp replaced (not
  appended) per the prune-on-bump rule.
- Every other doc `closeout_prep.py`'s doc-freshness pass flagged as STALE
  (`auth.md`, `context-compression.md`, `jit-schema.md`, `schema-forms.md`,
  `tool-call-flow.md`, `voice-ai.md`, `websocket-routing.md`,
  `ai-models.md`, `bead-tiers.md`, `logging-and-cost.md`, `risk-rating.md`,
  `schema-key-visibility.md`, `section-reset-deprecation.md`,
  `si-reduction.md`, `stateless-architecture.md`, `terminology.md`,
  `testing.md`, `validation-delegation.md`, `voice-and-vad.md`,
  `ws-protocol.md`, `technical_guide.md`) was reviewed against this
  branch's two-file diff (`frontend/vite.config.schema.ts` +
  `frontend/src/shared/buildAbsoluteAssetBase.test.ts`) and left as-is:
  every flagged staleness traces to files this bead did not touch (other
  concurrent work on `backend/config.py`, `live_ai_gemini.py`,
  `websocket_routes.py`, etc.), confirmed via a pre-existing-failure check
  against the unmodified tree.
- Review outcomes recorded in the closeout ping.

## Files touched

- `frontend/vite.config.schema.ts` -- `base: './'` -> `base: '/'`, with an
  explanatory comment.
- `frontend/src/shared/buildAbsoluteAssetBase.test.ts` -- new test file
  (static config check + real-build check).
- `docs/components/config-deployment.md` -- `Tracks:` line + new Frontend
  deploy bullet + bumped stamp.
- `docs/journal/entries/2026-09-15-bd-3bsyv-absolute-asset-base.md` -- this
  entry.

Also filed, out of scope for this bead: `polyglot-pdf-sw5vl` (P3) for a
pre-existing flaky test, `frontend/src/shared/sessionCredential.test.ts`,
observed timing out at the 5000ms default under a full unfiltered
`npx vitest run` but passing cleanly in isolation on the unmodified tree
(confirmed pre-existing via a tagged `git stash` round-trip before this
bead's changes were applied).
