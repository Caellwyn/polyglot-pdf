---
date: 2026-08-27
bead: polyglot-pdf-nukx2
title: "fix(scripts): run-schema-editor.sh backend reloads on unrelated worktree file changes"
tags: [hotfix, harness, schema-editor]
---

## Trigger

The maintainer reported that `scripts/run-schema-editor.sh`'s backend
(uvicorn `--reload`) kept reloading mid-session with log lines like
`WatchFiles detected changes in '.claude\worktrees\polyglot-pdf-5tuas\backend\...'`
-- a completely unrelated agent session editing its own worktree's copy of
`backend/` was restarting a server that wasn't even running off that
worktree. This repo's root holds `.claude/worktrees/` with ~100+ sibling
worktrees, each a full checkout, so the annoyance recurs constantly. No
existing bead covered it; filed polyglot-pdf-nukx2 ad hoc and closed it in
the same PR (small, self-contained fix, per the bead/PR bundling allowance
in CLAUDE.md).

## What shipped

`scripts/run-schema-editor.sh` passed `--reload-dir backend` as a path
**relative** to `$ROOT_DIR` (the cwd at uvicorn invocation time). That did
not fully scope the watcher: cross-worktree file changes still triggered a
reload. Fix: pass an **absolute** `--reload-dir "$ROOT_DIR/backend"` instead
-- an absolute path structurally cannot resolve into any other worktree's
`backend/`, so the watch is provably scoped to this checkout.

A first attempt also added `--reload-exclude "$ROOT_DIR/.claude/worktrees/*"`
as a belt-and-suspenders exclude. Fresh-eyes review caught that this crashes
`uvicorn.Config()` outright: uvicorn's exclude-pattern resolver only accepts
**relative** glob patterns and raises `NotImplementedError: Non-relative
patterns are unsupported` on an absolute one -- so the "fix" would have
failed to launch the backend at all, a strictly worse outcome than the
original bug. The exclude flag was dropped entirely: it was also redundant,
since `--reload-dir` scoped to an absolute path already excludes everything
outside it.

Fresh-eyes assess: 1 round, `GAPS-FOUND (2)` -> fixed the crash (dropped
`--reload-exclude`, kept only the absolute `--reload-dir`) and clarified the
comment -> re-spawned -> `NO-GAPS`. No Opus outer cross-surface review was
run: this is a genuinely trivial diff (a dev-only launch script, no shipped
runtime behavior, no contract with any consumer -- confirmed by fresh-eyes'
own `## Changed contracts: none`), so per the Step 5.6 three-way fork its
fresh-eyes `NO-GAPS` is the review record.

Manually verified end-to-end (not just structurally): started a real backend
instance from this worktree, touched a file under a sibling worktree's
`backend/` (no reload fired), then touched a file under this worktree's own
`backend/` (reload fired as expected). Both directions confirmed working.

## Lessons

A relative `uvicorn --reload-dir` value does not scope the watcher as
tightly as it looks like it should when worktrees are nested inside the
repo root -- always pass an absolute path for reload-dir/reload-exclude
targets in a repo layout with nested worktrees. Separately: `uvicorn`'s
`--reload-exclude` only accepts relative glob patterns; passing an absolute
one is a silent-at-review-time, loud-at-runtime crash (`NotImplementedError`
on `Config()` construction, before the server binds) -- caught here only by
a fresh-eyes reviewer actually reproducing it against the installed
package, not by reading the flag names. No standards doc update: this is
narrow to one dev-launch script, not a generalizable rule.

## Doc freshness

`scripts/closeout_prep.py`'s doc-freshness check flagged the usual broad set
of tier-2 docs as stale against unrelated recent commits (auth.md,
config-deployment.md, context-compression.md, jit-schema.md, pdf-filling.md,
pdf-view.md, schema-forms.md, tool-call-flow.md, voice-ai.md,
websocket-routing.md, ai-models.md, bead-tiers.md, confirmation-and-audit.md,
hipaa-pii-policy.md, logging-and-cost.md, risk-rating.md,
schema-key-visibility.md, section-reset-deprecation.md, si-reduction.md,
stateless-architecture.md, terminology.md, testing.md,
validation-delegation.md, voice-and-vad.md, ws-protocol.md,
technical_guide.md). None of these track `scripts/run-schema-editor.sh` or
this PR's change; reviewed and left as-is per the freshness check's own
guidance (pre-existing staleness this branch didn't touch).

## Files touched

- `scripts/run-schema-editor.sh` -- absolute `--reload-dir`, dropped the
  crashing `--reload-exclude`, rewrote the surrounding comment.
