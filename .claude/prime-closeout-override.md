
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
  `gh pr create` by hand). Reviewed by Copilot + fresh-eyes in parallel, looped
  to clean. The maintainer clicks merge (auto-merge is disabled).
- **Demo deploy** — there is NO `main`/prod tier; the demo remote is the live
  target. Deploys are manual (`deploy-demo.sh`, not branch-triggered). The agent
  MAY run the demo deploy, but only after a local test of the change, with
  explicit per-instance maintainer permission, and a post-deploy test-drive (the
  three-part gate in [`docs/doctrine/promotion-tiers.md`](../docs/doctrine/promotion-tiers.md)).
  Syncing the local root to `dev` is autonomous; merging a PR into `dev` is the
  maintainer's.

**Before saying "done":**

```
[ ] 1. git status                              confirm what changed
[ ] 2. git add <files> && git commit -m "..."  commit code (worktree: git -C <path>)
[ ] 3. /closeout                               opens the PR into dev, runs dual review,
                                               loops to clean, THEN closes the bead(s)
                                               and pushes the beads store
```

`/closeout` owns PR creation and the review loop, and it is the step that closes
the bead(s) — **at PR handoff, after Copilot is clean**, never before the PR
exists (a bead closed against work that hasn't landed corrupts the tracker).
Closeout also runs the final `bd dolt push`; do not pre-close or pre-push the
bead yourself. It pings the maintainer to merge and never merges itself. Work is
**not** done at `git push` — it is done when closeout has run the PR to clean and
closed the bead(s). See `docs/doctrine/promotion-tiers.md`,
`docs/doctrine/review-flow.md`, and the `closeout` skill
(`.claude/skills/closeout/SKILL.md`).
