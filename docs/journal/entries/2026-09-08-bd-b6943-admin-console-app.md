---
date: 2026-09-08
bead: polyglot-pdf-b6943
title: "feat(console): 1.7 admin-console app skeleton, sign-in gate, live + candidate Hosting sites, deploy script"
sprint: 22
tags: [conventions, testing]
---

## Trigger

Epic 1 child 1.7 of the admin-console program (plan:
`docs/sprint_22_admin-console_plan.md`, "Console app" section). Beads 1.1-1.6
had already shipped the admin service itself -- `require_app_admin`, `GET
/admin/whoami`, the audit log, the runtime-config routes, `/version` -- but
nothing could call any of it except curl and a bearer token from
`scripts/bootstrap_admin_user.py`. This bead builds the actual console: a
separate Vite app, its sign-in gate, and the deploy plane to ship it.

## What shipped

`admin-console/`, a new Vite + React + Tailwind app mirroring
`schema-editor/`'s shape closely: `vite.config.ts` carries the same worktree
`fsAllowList` fix and `.claude/worktrees` watch exclusion, and adds a
build-time git-SHA `define` (`__ADMIN_CONSOLE_GIT_SHA__`) so the who-am-i
page can answer "what build is this" for the console itself, distinct from
`GET /version`'s SHA (a different deployed service).

`SignInGate.tsx` and `utils/adminAuth.ts` duplicate `schema-editor`'s
sign-in gate SHAPE almost verbatim (Firebase sign-in, then a server-side
role probe -- here `GET /admin/whoami` instead of `/api/editor/session`) --
duplicated rather than imported, for the same maintainer constraint that
keeps `schema-editor/` from importing `frontend/` (no new cross-surface
dependency to unravel later). `utils/adminApi.ts` is the admin-service
client: `probeWhoAmI`, `listAuditRows`, `getChannelConfig`,
`setChannelConfigKey`, with `AuthError`/`ForbiddenError` classified by the
`NO_ADMIN_ACCESS:` wire marker the same way the editor classifies
`NO_EDITOR_ACCESS:`.

Three skeleton pages behind a simple tabbed shell (no router -- three tabs
is not enough surface to justify one yet): `WhoAmIPage` (renders what the
gate already fetched), `AuditLogPage` (`GET /admin/audit`, filters matching
the route's own vocabulary, cursor-based "load more"), and
`ConfigEditorPage` (`GET`+`PUT /admin/config/{channel}`, ONE KEY AT A TIME
matching the route's `ConfigPutRequest` contract, with a post-save re-read
so the screen reflects the server's own coercion).

Deploy plane: two new `firebase.json` Hosting targets (`admin` ->
`polyglot-admin-demo`, `admin-candidate` -> `polyglot-admin-candidate`),
neither carrying an `/api` rewrite (the console calls the admin service
directly, same reasoning as the editor's rewrite-free target). Matching
`.firebaserc` entries. `deploy-admin-console.sh` mirrors
`deploy-editor.sh`'s live-URL-resolution + reachability-gate pattern, but
ships to the CANDIDATE site by default and only promotes the same build to
LIVE on a second explicit `--live` run -- the admin service has no channel
of its own (it serves both staging's and the demo's data), so there is no
cheap staging tier to catch a bad console build the way `deploy-staging.sh`
protects the voice app; the candidate site is the substitute. A preview
channel was deliberately rejected (random-hash URLs would need
re-authorizing in Firebase Auth and the admin service's
`CORS_EXTRA_ORIGINS` on every single deploy).

The reachability-gate function is copied byte-identical from
`deploy-editor.sh` (the fourth copy now), and
`tests/test_deploy_reachability_gate.py` is extended to keep pinning that:
`deploy-admin-console.sh` added to `URL_BAKING_SCRIPTS` with its (1 warn, 0
fatal) severity signature, a new
`test_gate_copies_are_identical_across_all_four_scripts`, and
`ADMIN_SERVICE_NAME` bound in the call-site execution driver so the
existing argument-binding assertions still exercise the real call.

### Fresh-eyes fixup round (2026-09-08)

Two GAPS-FOUND findings, both fixed inline in this diff's own new code:

- **Adopted -- wired the dead `refusedReason` mid-session-revocation path.**
  `SignInGate`'s `refusedReason` prop and its own pinning test existed from
  the first pass, but nothing in the app ever constructed the prop: a 401 or
  403 from `AuditLogPage`/`ConfigEditorPage` (an operator's `app_admin`
  claim revoked mid-session, or a token that simply expired) surfaced as
  each page's own generic red error string, with no path back to the gate's
  explicit "ask an operator to grant access" / "sign in again" screens this
  bead built specifically for that case. Fixed by mirroring
  `schema-editor/src/App.tsx`'s `handleAuthExpired` pattern: `App.tsx` now
  owns a `refusedMidSession` state and a `handleAuthExpired` callback passed
  to both pages as `onAuthExpired`; each page's catch blocks call it FIRST
  and skip their own generic banner when it reports the failure as handled.
  Simpler than the editor's version -- every admin route gates on the SAME
  single `require_app_admin` check (no "author-only" partial-permission 403
  to carve out), so any `AuthError`/`ForbiddenError` here means a full
  eviction. Pinned with two new tests in `ConfigEditorPage.test.tsx`
  (a 403 on load and a 401 on save both route to `onAuthExpired` instead of
  the page's own error banner) and mutation-verified: reverting the load
  path's `onAuthExpired` guard reproduced the failure in exactly the test
  written to catch it.
- **Adopted -- `deploy-admin-console.sh`'s `--live` flag now rejects an
  unrecognized argument.** The flag was matched by a single `if [ "$1" =
  "--live" ]` with no catch-all, so a typo (`--Live`, `-live`) silently fell
  through to the CANDIDATE deploy while still printing a normal success
  banner -- the same operational risk `tests/test_deploy_reachability_gate.py`
  already documents for `deploy-demo.sh`/`deploy-staging.sh` (bd
  `polyglot-pdf-7aez9`), just never extended to this new script. Fixed by
  switching to the same `for arg in "$@"; do case "$arg" in ... *) ... exit
  1 ;; esac; done` shape those two scripts use, with an `Unknown argument`
  message and `exit 1` on anything but `--live`. Verified behaviorally (not
  just `bash -n`): an isolated copy of the parser exits 0/`DEPLOY_LIVE=true`
  on `--live`, exits 0/`false` with no args, and now exits 1 with an error
  on a typo`'d flag (previously exit 0, silently deploying to candidate).
  Not added to `test_channel_wrapper_rejects_an_unknown_argument`'s
  parametrize list -- that test's `for arg in ... esac` slice-matching
  assumes the two-arg (`--backend`/`--frontend`/`--form-kits`) wrapper shape;
  extending it to a single-flag script is a decidable follow-up, not a
  behavioral gap, so it is left as a defer rather than bundled into this
  fixup.

Both findings were fixed inside this diff's own newly-added code (not
pre-existing, not out of scope), so neither needed a separate bead -- both
are closed out by this same bead/PR per CLAUDE.md's escalation rules.

## Lessons

`ConfigEditorPage`'s round-trip test caught a real bug during development:
the post-save re-read (`load(channel)`) unconditionally cleared the "Saved
..." confirmation message, so an operator who successfully saved a value
would see the message flash and vanish before the re-read even resolved.
Fixed with an explicit `clearSavedMessage` option so the confirmation
survives the very re-read that proves the save round-tripped. Mutation-
verified: reverting the fix reproduced the failure in exactly the test
written to catch it (CLAUDE.md scar #9, "test the tests").

Enumerating the reachability-gate's pinned set (CLAUDE.md scar #8) mattered
here: `deploy-admin-console.sh` resolves a Cloud Run URL and bakes it into a
`VITE_*` build var, which is exactly the pattern
`tests/test_deploy_reachability_gate.py`'s `test_url_baking_set_is_complete`
derives mechanically from source (`services describe` + `export VITE_`) --
so the new script would have failed CI on its own existing set-completeness
check had the test file not been updated in the same commit.

## Doc freshness

`docs/technical_guide.md`: new Surface contract 16 (admin console -> admin
service: sign-in gate + page reads/writes).

`docs/components/config-deployment.md`: Tracks line extended with
`admin-console/`, `deploy-admin-console.sh`, and `deploy-editor.sh` (the
last was covered in prose already but missing from the Tracks line itself);
the "Hosted schema editor" section updated for the now-five Hosting
targets, and a new "Admin console" subsection added.

`docs/doctrine/promotion-tiers.md` and `docs/components/auth.md` were
deliberately left untouched -- the plan assigns their admin-tier sections to
bead 1.8 (`polyglot-pdf-2cwja`), which blocks on this bead and documents the
admin tier as a whole once the console exists to describe.

## Files touched

- `admin-console/` (new): `vite.config.ts`, `tsconfig.json`,
  `tsconfig.node.json`, `tailwind.config.js`, `postcss.config.js`,
  `index.html`, `.env.hosted`, `.gitignore`, `package.json`,
  `package-lock.json`
- `admin-console/src/main.tsx`, `App.tsx`, `styles/index.css`,
  `vite-env.d.ts`, `test/setup.ts`
- `admin-console/src/utils/adminAuth.ts`, `adminApi.ts`
- `admin-console/src/components/SignInGate.tsx` (+ `.test.tsx`),
  `WhoAmIPage.tsx`, `AuditLogPage.tsx`, `ConfigEditorPage.tsx` (+
  `.test.tsx`)
- `firebase.json`, `.firebaserc` (two new `admin`/`admin-candidate` Hosting
  targets)
- `deploy-admin-console.sh` (new)
- `.gitignore` (the `!admin-console/.env.hosted` negation)
- `tests/test_deploy_reachability_gate.py` (extended set + severity maps)
- `docs/technical_guide.md`, `docs/components/config-deployment.md`

Review outcomes recorded in the closeout ping.
