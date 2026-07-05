---
date: 2026-07-05
bead: polyglot-pdf-8jf1
title: "docs(branch-protection): reconcile Copilot-era + 'single human merge gate' staleness with auto-merge policy"
tags: [doctrine]
---

## Trigger

`docs/branch-protection-setup.md` was stale on three axes, all filed as bd 8jf1
(spawned by the Opus-4.8 fallback review during bd 16pj, which found the doc
outside 16pj's own reconciliation surfaces). The three stale claims: (1) the
maintainer is "the single human merge gate" / must "click merge"; (2) the "To Dev"
ruleset "makes Copilot review on PR-open"; (3) the whole doc treats defending an
active `main` as required setup.

## What shipped

Reconciled the doc to current state:

- **Merge gate:** removed "single human merge gate" / "click merge". Now describes
  `allow_auto_merge=false` as disabling only GitHub's merge-on-green *feature* (not
  the orchestrator's explicit `gh pr merge`), and points at the auto-merge-vs-ping
  rule (bd `polyglot-pdf-16pj`) as the actual merge policy.
- **Copilot -> Codex:** removed the `copilot_code_review` ruleset rule from the "To
  Dev" JSON and all "Copilot reviews on PR-open" language. Codex is a repo-level
  GitHub app that auto-reviews on PR-open -- NOT a branch-ruleset rule -- so the doc
  now says code review is not configured via ruleset and points at review-flow.md;
  it explicitly says do NOT add a `copilot_code_review` rule (Copilot retired at bd
  `hrn.8`/`hrn.9`).
- **No active prod:** marked the "Defend Production" ruleset OPTIONAL and
  skip-for-this-repo -- there is no active production `main` (maintainer, 2026-07-05:
  this is a demo for future investor demonstration, not a production app), so
  protecting `main` is not load-bearing. Kept for reference / a future prod tier.

## Lessons

- **A cross-cutting policy change should sweep setup/runbook docs, not just the
  doctrine docs.** bd 16pj reconciled the doctrine surfaces (CLAUDE.md, SKILL.md,
  review-flow, promotion-tiers, planning) but this one-time-setup runbook carried
  the same stale merge-gate + Copilot claims and was missed until a reviewer caught
  it. Setup docs describe current-state behavior too.

## Doc freshness

- `docs/branch-protection-setup.md`: rewritten to current state; `Last updated:`
  bumped to 2026-07-05.
- No tier-1/tier-2 doc changes; no code changes.

## Files touched

- `docs/branch-protection-setup.md` -- merge-gate + Copilot->Codex + optional-prod
  reconciliation.
- `docs/journal/entries/2026-07-05-bd-8jf1-...md` -- this entry.
