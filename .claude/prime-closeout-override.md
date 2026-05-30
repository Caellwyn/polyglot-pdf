
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
- **`dev → main`** — maintainer-driven promotion; `dev` auto-deploys to staging,
  `main` to prod. You do **not** push to `main`.

**Before saying "done":**

```
[ ] 1. bd dolt pull && bd close <id...>        close the bead(s) this PR resolves
[ ] 2. git status                              confirm a clean tree
[ ] 3. git add <files> && git commit -m "..."  commit code (worktree: git -C <path>)
[ ] 4. /closeout                               opens the PR into dev + dual review
[ ] 5. bd dolt push                            push the beads store
```

`/closeout` owns PR creation and the review loop; it pings the maintainer to
merge and never merges itself. Work is **not** done at `git push` — it is done
when closeout has run the PR to clean and the bead(s) are closed. See
`docs/doctrine/promotion-tiers.md`, `docs/doctrine/review-flow.md`, and the
`closeout` skill (`.claude/skills/closeout/SKILL.md`).
