---
date: 2026-06-01
bead: polyglot-pdf-9pe
title: "Closeout audits the worktree branch + collision guard stops false-positives"
tags: [conventions, testing, review]
---

## Trigger

`polyglot-pdf-9pe`, filed during the rt4/sprint-1 closeout (PR #46) after two
closeout-tooling sharp edges bit in the same session: Step 2's freshness check
kept reporting stale docs that were already fixed on the branch, and claiming
this very bead via `bd_safe.py` was aborted by a "collision" with the merged PR
that had only *mentioned* it. Both trace to scripts operating on the wrong
target. Scope was folded to cover both (maintainer call).

## What shipped

- **Closeout reads the worktree branch, not main.** `check_doc_freshness.py` and
  `journal_scaffold.py` derive their repo root from their own file location and
  read from cwd, so invoking the MAIN-repo copy (`$R` = git-common-dir parent)
  audited/wrote against main — not the branch under review. `SKILL.md` Step 2 now
  resolves `WT="$(git rev-parse --show-toplevel)"` and runs `$WT/scripts/...`
  with cwd=`$WT`; Step 3's scaffold likewise runs the worktree copy and writes
  straight into the branch (the old "move it by hand" note is gone). `$R` still
  supplies the venv interpreter and the content-agnostic scripts
  (`closeout_housekeeping.py` reads only `bd`; `copilot_watch.py` only the GitHub
  API), with an explicit note that `$WT == $R` in a main checkout.

- **Collision guard no longer false-blocks.** `bd_safe.py`'s `_pr_collision`
  used `gh pr list --search <id> --state all`, which matched CLOSED/MERGED PRs
  and matched the id anywhere via full-text — so a PR whose *body* mentioned the
  bead blocked the claim forever. Now `--state open --json number,title`, and the
  id must appear in the PR **title** (the `(bd <id>)` convention) to count as a
  live claim. Added `json` import + docstring update.

- **This closeout dogfooded both fixes:** Step 2 audited the branch (clean) via
  the new `$WT` form, and Step 3's scaffold landed directly in the worktree.

Fresh-eyes triage: see the PR body.

## Lessons

- **A script's "repo root" is wherever its *copy* lives, not where `git` points.**
  Anything resolving `Path(__file__).parent` and reading from cwd audits the
  checkout it's run from. In a worktree, run the worktree's own copy; reserve the
  git-common-dir (`$R`) for things that genuinely live only in the main repo (the
  venv) or are checkout-agnostic (bd, GitHub API). Generalized into agent scar
  tissue ([[closeout-scripts-run-against-main-not-worktree]]).
- **A collision/dedup search scoped too broadly is worse than none — it blocks
  valid work.** `--state all` + full-text turned "is anyone working on this?" into
  "has this id ever appeared in any PR?". Scope liveness checks to *open* state and
  match the field that carries the *claim* (the title), not incidental mentions.

## Doc freshness

- No tier-1/tier-2 doc tracked the changed files (`SKILL.md`, `bd_safe.py`,
  `tests/`), so none needed a bump. Freshness check: clean on the branch.
- No CLAUDE.md change (the closeout section already points at SKILL.md as source
  of truth; the `$WT` mechanics live in the skill).

## Files touched

- `.claude/skills/closeout/SKILL.md` — Step 2 + Step 3 run the worktree's script copy (`$WT`) with cwd=`$WT`; rationale notes citing 9pe.
- `scripts/bd_safe.py` — `_pr_collision`: `--state open` + `--json`, title-match filter; `json` import; docstring update.
- `tests/test_bd_safe.py` — updated PR-collision tests to JSON; added body-mention-ignored, empty-JSON, and open-scoping regression tests.
- `docs/journal/entries/2026-06-01-bd-9pe-closeout-freshness-scripts-audit-main-repo-not.md` — this entry.
