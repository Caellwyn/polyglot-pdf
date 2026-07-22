---
date: 2026-07-18
bead: polyglot-pdf-1rgr
title: "ci(schema-editor): add a tsc typecheck CI step (missing, unlike frontend)"
tags: [testing, schema-editor]
---

## Trigger

The schema-editor CI job (`.github/workflows/ci.yml`, `schema-editor-tests`) ran
`vitest` only -- no typecheck step -- unlike the frontend job, which runs `npm run
typecheck` before its vitest step. This was the hole that let a
build-breaking-but-test-green change reach review in the d25e/p8sq/r8gq bundle: an
`Array.prototype.at` call that vitest's esbuild transpile tolerated but `tsc &&
vite build` (the `deploy-editor.sh` path) rejects under the package's ES2020
`lib` target. It was caught only by the fresh-eyes review, not CI. Maintainer
go-ahead recorded in-chat 2026-07-17: "if you think it's worthwhile, then let's
do it."

## What shipped

- Added a `typecheck` script to `schema-editor/package.json`: `"tsc --noEmit"`,
  mirroring the frontend package's `typecheck` script (both run against the
  package's default `tsconfig.json`, matching what `build` already does with
  bare `tsc`).
- Added a "Type-check (schema-editor)" step to the `schema-editor-tests` CI job,
  running before the existing `test:run` step, mirroring the frontend job's
  ordering and comment style.
- Pre-flight verified `npm run typecheck` exits 0 on current dev (post-#460)
  before opening the PR, per the bead's own instruction -- a red baseline would
  have bricked every future schema-editor PR.
- Nothing deferred; this was a small, fully-scoped CI change.

## Lessons

No new generalizable lesson -- this closes a known gap the bead had already
diagnosed and prescribed a fix for (mirror the frontend job).

## Doc freshness

`docs/standards/testing.md` was flagged STALE by the freshness checker (it
`Tracks:` `.github/workflows/ci.yml`, which this PR touched). Updated its CI
description to mention both vitest jobs now carry a typecheck step, and updated
the sentence pointing at "the standalone `npm run typecheck` gate in CI's
frontend job" to say "frontend and schema-editor jobs." Bumped its
`*Last updated:*` line.

The same closeout run flagged many other docs STALE (auth.md,
context-compression.md, jit-schema.md, schema-forms.md, tool-call-flow.md,
voice-ai.md, confirmation-and-audit.md, hipaa-pii-policy.md, logging-and-cost.md,
risk-rating.md, section-reset-deprecation.md, stateless-architecture.md,
terminology.md, voice-and-vad.md, ws-protocol.md) -- all against files this
branch did not touch (other in-flight work). Left as-is per the closeout
instruction to leave docs stale against files outside this branch's diff.

## Files touched

- `.github/workflows/ci.yml` -- added a typecheck step to the
  `schema-editor-tests` job.
- `schema-editor/package.json` -- added the `typecheck` npm script.
- `docs/standards/testing.md` -- updated CI description, bumped
  `*Last updated:*`.
