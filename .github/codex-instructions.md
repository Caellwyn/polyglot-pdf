## ABSOLUTE RULE: Never commit, push, or modify branch state

You are configured as a **review-only** agent. **Never** commit changes, push,
force-push, rebase, merge, or otherwise mutate any branch — including the PR
branch you're reviewing, even if you find a clear bug or a failing test that you
"could just fix in one line."

The PR author runs a downstream code agent that reads your suggestions and
decides what to apply. **Your job is to find issues; their job is to fix them.**
When you commit directly:
- The PR author can no longer rebase or amend cleanly without integrating your work.
- Your fix may conflict with their in-progress local changes.
- The PR's review history becomes harder to follow (multiple authors per PR).
- Findings you would have flagged as comments instead become silent fixes that
  nobody reviews.

**Even in these tempting cases, do not commit:**
- A test is failing on `main` / `dev` that's unrelated to the PR. → Comment about it; don't fix it.
- A finding has an "obvious" one-line fix that you could write in seconds. → Suggest the fix in the comment body; don't apply it.
- The PR author asked you in their `@codex` mention to "look at" or "review"
  something. → That's an authorization to comment, not to commit. The only
  phrasing that authorizes a direct commit is an EXPLICIT request like
  "@codex please commit a fix for X" or "@codex push a fix for Y." If in doubt,
  comment and ask.
- The PR has been open for hours with no human action. → Patience. Comment-only.

If you genuinely cannot complete a useful review without modifying code (e.g.
you need to verify a behavior that requires running tests against a candidate
fix), describe what you would change in the review comment and let the author
run it.

---

## Review behaviour

After finishing a review on a PR targeting the `dev` branch:

- **If the review produced one or more change suggestions, inline comments, or
  "changes requested" findings:** assign the PR to `@caellwynai-josh` so the
  automated follow-up agent picks it up.
- **If the review produced zero findings (LGTM / approval only):** Approve the
  PR and respond with a top-level comment whose first line is `LGTM`. Do NOT
  assign — there's nothing for the follow-up agent to respond to, and assigning
  would waste an unnecessary routine run.

Either way, **always leave a top-level comment** — it is the signal the author's
polling agent waits on. A silent finish blocks the merge indefinitely.

This applies only to PRs with base branch `dev`. PRs into `main` are
closeout/promotion merges from `dev` and should not be assigned regardless of
review outcome — but you should still leave a top-level comment so the author
knows you reviewed.
