
---

# 🚨 SESSION CLOSE PROTOCOL — polyglot-pdf override 🚨

> **This block CORRECTS the generic "git push = done" protocol that `bd prime`
> prints above.** It is project-specific and authoritative for this repo. The
> generic checklist above is stale: a bare `git push` is **not** "done" here, and
> nothing is "merged to main locally."

This repo ships through **reviewed PRs into `dev`**, never a local merge to
`main`. Promotion is `feature → dev → main`:

- **feature branch** — one bead's work; where you commit. Branch off freshly-
  pulled `dev`.
- **PR into `dev`** — opened and driven by the `/closeout` skill (NOT
  `gh pr create` by hand). Reviewed in two serial layers, both Claude, BOTH PRE-PR
  (on the local branch), with DIFFERENT jobs — a fresh-eyes assess loop
  (Sonnet/Haiku: score the exit criteria, get the local diff right, enumerate every
  changed contract), then ONE looped outer adversarial pass — a **three-way fork by
  diff type**: an Opus-5 `cross-surface-reviewer` for a SOURCE diff (follow those
  contracts out into untouched consumers), a Haiku `docs-reviewer` for a DOCS-ONLY
  diff (adversarial prose review — nothing to trace), and none at all for a
  genuinely trivial one — each looped to clean. Only after both clear does the PR open (and close the bead(s),
  one run). There is NO external reviewer (the maintainer's Codex subscription ended
  2026-07-08). On CLEAN,
  closeout **auto-merges a routine low-risk PR** (`gh pr merge`) or **pings the
  maintainer** for a consequence-bearing one (autonomy increase 2026-07-04;
  CLAUDE.md "Auto-merge vs. maintainer merge").
- **Demo deploy** — there is NO `main`/prod tier; the demo remote is the live
  target. Deploys are manual (`deploy-demo.sh`, not branch-triggered). The agent
  MAY run the demo deploy, but only after a local test of the change, with
  explicit per-instance maintainer permission, and a post-deploy test-drive (the
  three-part gate in [`docs/doctrine/promotion-tiers.md`](../docs/doctrine/promotion-tiers.md)).
  Syncing the local root to `dev` is autonomous; merging a PR into `dev` is
  autonomous for a routine low-risk PR under the auto-merge rule, the maintainer's
  for a consequence-bearing one.

**Before saying "done":**

```
[ ] 1. git status                              confirm what changed
[ ] 2. git add <files> && git commit -m "..."  commit code (worktree: git -C <path>)
[ ] 3. /closeout                               pre-PR assess, opens the PR into dev,
                                               loops review to clean, THEN closes the bead(s)
                                               and pushes the beads store
```

`/closeout` owns PR creation and the review loop, and it is the step that closes
the bead(s) — **at PR handoff, after the review loop is clean**, never before the PR
exists (a bead closed against work that hasn't landed corrupts the tracker).
Closeout also runs the final `bd dolt push`; do not pre-close or pre-push the
bead yourself. On CLEAN it auto-merges a routine low-risk PR or pings the
maintainer for a consequence-bearing one (see the merge line above). Work is
**not** done at `git push` — it is done when closeout has run the PR to clean and
either merged it or handed it to the maintainer, and closed the bead(s). See `docs/doctrine/promotion-tiers.md`,
`docs/doctrine/review-flow.md`, and the `closeout` skill
(`.claude/skills/closeout/SKILL.md`).
