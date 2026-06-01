---
date: 2026-06-01
bead: polyglot-pdf-n4k
title: "Stale Gemini model name 'gemini-live-2.5-flash-native-audio' in README.md + PROJECT_CONTEXT.md"
tags: [conventions, hotfix]
---

## Trigger

Two unrelated small changes bundled into one PR to avoid a full review cycle each:

1. **Maintainer request (no bead):** agents were leaving the `copilot_watch.py`
   background process running after a PR merged, burning tokens. Asked to add a
   kill instruction to the `/closeout` skill.
2. **`bd polyglot-pdf-n4k`:** fresh-eyes on PR #29 (bd 4cm) found retired
   native-audio model aliases still named in `README.md` and the still-live
   `planning_documents/PROJECT_CONTEXT.md`. Out of scope for 4cm (untouched
   files), deferred as n4k.

## What shipped

**Closeout skill (`.claude/skills/closeout/SKILL.md`):** added a `copilot_watch.py`
kill rule in three reinforcing places -- the hard-rules block, the Step 7
Copilot loop (kill the moment Copilot reports CLEAN), and a Step 8 backstop
(kill if still alive at handoff or once the branch is merged). Condition is
"CLEAN received **OR** branch merged," whichever fires first.

**n4k doc fix:** corrected the stale model names. The active standard
native-audio default is `gemini-2.5-flash-native-audio-preview-12-2025`
(`backend/config.py` `MODEL_NATIVE_STANDARD`, resolved via `USE_PREMIUM_MODEL`).
- `README.md:62` ("Working Features") -> explicit current default.
- `README.md:358` + `PROJECT_CONTEXT.md:19,144` ("Always Do") -> rephrased to
  point at the `MODEL_NATIVE` knob (current default named) so they don't drift
  on the next model bump.
- Left the archived copy (`planning_documents/archived/PROJECT_CONTEXT.md`) and
  the journal entries untouched -- those are the historical record.
  `PROJECT_CONTEXT.md` itself is slated for archival under epic `gfb`.

**Verification subtlety worth recording:** the worktree was cut before PR #29
landed on `dev`, so its `backend/config.py` still showed the *old* model name --
which made the README look correct and the bead look wrong. Verifying against
`origin/dev` (not the local checkout) confirmed the bead was right and the
worktree was stale; rebased onto `origin/dev` first, then fixed the docs against
current code.

Fresh-eyes triage: _(filled at closeout)_.

Nothing deferred.

## Lessons

The "verify claims against code, not the brief" rule has a worktree-staleness
corollary: when a doc claim and the local code disagree, the local checkout may
simply be behind the integration branch. Check `origin/dev` before concluding
the bead (or the code) is wrong. Two prior standing notes converged here:
worktrees lag `dev`, and claims must be verified against the *current* code path.

## Doc freshness

`check_doc_freshness.py`: "No docs to check" -- `docs/components/` and
`docs/standards/` are still the empty starter skeleton, so nothing to bump.
The 4 stale `in_progress` beads surfaced by `closeout_housekeeping.py`
(gfb.2, m3f, pki, hjo) are all other workers' active work, unrelated to this
PR -- left untouched. No CLAUDE.md change needed.

## Files touched

- `.claude/skills/closeout/SKILL.md` -- added the `copilot_watch.py` kill rule (hard rules + Step 7 + Step 8).
- `README.md` -- fixed stale native-audio model names on lines 62 and 358.
- `planning_documents/PROJECT_CONTEXT.md` -- fixed stale native-audio model name on lines 19 and 144.
- `docs/journal/entries/2026-06-01-bd-n4k-stale-gemini-model-name-gemini-live-2-5-flash.md` -- this entry.
