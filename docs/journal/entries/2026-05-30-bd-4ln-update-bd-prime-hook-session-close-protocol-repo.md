---
date: 2026-05-30
bead: polyglot-pdf-4ln
title: "Update bd-prime hook SESSION CLOSE PROTOCOL: repo now uses PRs into dev, not local merge"
tags: [conventions]
---

## Trigger

The `bd prime` SessionStart/PreCompact hook ended with a generic "SESSION CLOSE
PROTOCOL" whose checklist was `git status` → `git add` → `git commit` →
`git push`, declaring "Work is not done until pushed"; the legacy phrasing also
spoke of code being "merged to main locally." As of bd polyglot-pdf-xmf that is
stale and actively misleading: the repo ships through reviewed PRs into `dev`
driven by `/closeout`, with maintainer-driven `dev → main` promotion. A bare
`git push` is *not* the finish line here, and nothing merges to `main` locally.

## What shipped

A wrapper around `bd prime` plus a project-specific close-protocol override:

- **`scripts/bd_prime.py`** — runs `bd prime` unchanged and appends the override
  text only when prime emits the generic protocol block. Forces UTF-8 stdout
  (Windows cp1252 chokes on the 🚨 heading emoji — same class of bug as the
  copilot_watch UTF-8 fix), resolves the override path relative to `__file__`
  (worktree-safe), passes through flags, and preserves prime's exit code. Skips
  the append on `--memories-only` output (PreCompact MCP mode), which omits the
  protocol block.
- **`.claude/prime-closeout-override.md`** — the corrected, authoritative close
  protocol: feature → PR-into-`dev` via `/closeout` (dual review, looped to
  clean) → maintainer-driven `dev → main`. Cites the promotion-tiers and
  review-flow doctrine and the closeout skill.
- **`.claude/settings.json`** — repointed both the `SessionStart` and
  `PreCompact` hooks from `bd prime` to `python scripts/bd_prime.py`.

**Why not the obvious knob:** `bd`'s only override mechanism, `.beads/PRIME.md`,
replaces the *entire* prime output — verified that this silently drops the
`bd remember` persistent-memories block (8 memories) that prime injects at
session start. The wrapper keeps memories + the full command reference intact
and only *adds* the correction, which is exactly the bead's intent (fix the
text, don't take over the output). `bd config set no-git-ops true` was the other
candidate but it only *deletes* the git lines rather than *correcting* them to
the PR workflow.

## Lessons

- **`bd prime`'s `.beads/PRIME.md` override is all-or-nothing** — it nukes the
  persistent-memories block too. To augment prime without losing memories, wrap
  the command in a hook script and append; don't override.
- **Worktree hazard, again (scar tissue #3).** First pass wrote all three files
  to absolute paths under the *main* repo (cwd resets between tool calls), not
  the worktree; caught by an empty `git status` in the worktree. Moved the files
  in and reverted the main checkout. Absolute paths into the main repo bite the
  same way a chained `cd <main> && git …` does.

## Doc freshness

No `docs/components/` or `docs/standards/` docs exist yet (docs-reorg epic
`polyglot-pdf-gfb` still populating), so none to bump. The override file
intentionally points at `docs/doctrine/promotion-tiers.md`,
`docs/doctrine/review-flow.md`, and the closeout skill as the sources of truth
rather than duplicating them. No CLAUDE.md change needed.

## Files touched

- `scripts/bd_prime.py` (new) — prime wrapper + UTF-8/worktree handling.
- `.claude/prime-closeout-override.md` (new) — corrected close protocol.
- `.claude/settings.json` (edit) — both hooks now call the wrapper.
