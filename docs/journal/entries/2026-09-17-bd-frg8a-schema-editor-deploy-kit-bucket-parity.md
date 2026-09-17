---
date: 2026-09-17
bead: polyglot-pdf-frg8a
title: "Fix the CI-red FORM_KITS_BUCKET parity test after the bash deploy engine's removal"
tags: [testing, review]
---

## Trigger

The maintainer asked me to look into a `schema-editor vitest` CI failure
that had "been coming up" -- it had just failed on batch 6's bug-hunt PR
(#840), a PR that touched neither of the files involved, so it was
diagnosed as a genuine pre-existing break and filed as `polyglot-pdf-frg8a`
before this fix.

## What shipped

`schema-editor/vite-plugins/deployKitEndpoint.test.ts`'s "default bucket
parity across every `FORM_KITS_BUCKET` default" test (bd `d7hy`, `n2awd`)
enumerated three scripts (`deploy-form-kit.sh`, `pull-form-kits.sh`,
`deploy-all.sh`) that must each carry a bare `${FORM_KITS_BUCKET:-...}`
default matching the plugin's own `DEFAULT_BUCKET`. `deploy-all.sh` no
longer has ANY such default -- confirmed via `git show
origin/dev:deploy-all.sh | grep FORM_KITS_BUCKET` returning zero matches --
because bd `polyglot-pdf-oqtm7` (E4.6) moved its deploy logic entirely to
Cloud Build. `deploy-all.sh` today is a thin trigger (`run_build_targets`)
with no local bucket-resolution code at all.

Traced where the REAL bucket now comes from for a Cloud-Build form-kits
upload: `cloudbuild.yaml`'s `form-kits-upload` step computes
`BUCKET="$PROJECT_ID-form-kits"` directly -- a completely different
mechanism (no env var, no bare-default convention) than the
`${FORM_KITS_BUCKET:-...}` pattern the two remaining local scripts still
use. There is no longer a parity concern between `deploy-all.sh` and the
plugin's default, because `deploy-all.sh` doesn't consume that env var at
all anymore.

**Fix:** removed `deploy-all.sh` from the test's
`SCRIPTS_WITH_BARE_DEFAULTS` enumeration and rewrote the surrounding
comment to explain why (the old comment claimed `deploy-demo.sh` /
`deploy-production.sh` "export it explicitly before delegating to
deploy-all.sh" -- also stale, since neither delegates to it that way
anymore; corrected to describe `deploy-production.sh`'s own explicit
export as unreachable dead code, coming AFTER its unconditional
dead-script `exit 1`, not before it -- fresh-eyes caught a first attempt
at this correction that stated the ordering backwards). This was a
mechanical, one-file, test-and-comment-only change -- no production
script logic touched.

Considered and rejected: restoring a bare `FORM_KITS_BUCKET` default
inside `deploy-all.sh` to keep the enumeration unchanged. Rejected because
`deploy-all.sh` genuinely has no bucket-consuming code path anymore to
attach a meaningful default to -- adding one back would be dead code
solely to satisfy a test, the inverse of what a regression test should
protect.

Verified via `git show origin/dev:deploy-all.sh` and
`origin/dev:deploy-demo.sh`/`deploy-staging.sh` that none of them reference
`FORM_KITS_BUCKET`, confirming this is a repo-wide architectural shift (all
of `deploy-all.sh`'s deploy targets now delegate to Cloud Build), not
something specific to one script that could instead be patched locally.

## Lessons

- A parity/enumeration test (CLAUDE.md scar #8's "enumerate the set"
  pattern) needs re-validation whenever ANY enumerated member's underlying
  mechanism changes architecturally, not just when its literal value
  drifts -- this test correctly caught that `deploy-all.sh` disagreed with
  the plugin's default, but the disagreement was because `deploy-all.sh`
  had stopped being a bucket-consuming script at all, not because its
  default value had drifted. The fix is removing the member, not chasing
  its value.
- When a test names a CI job as "flaky" or "been coming up" without a
  clear owner, checking whether the failure reproduces unchanged on
  `origin/dev` (and confirming the reporting PR doesn't touch the involved
  files) settles pre-existing-vs-regression in under a minute and prevents
  wasted effort debugging the wrong PR.

## Doc freshness

No tier-1/2 docs touched. This is a test-file-only fix.

## Files touched

- `schema-editor/vite-plugins/deployKitEndpoint.test.ts` -- removed
  `deploy-all.sh` from the bucket-default parity enumeration; corrected
  the surrounding comment
