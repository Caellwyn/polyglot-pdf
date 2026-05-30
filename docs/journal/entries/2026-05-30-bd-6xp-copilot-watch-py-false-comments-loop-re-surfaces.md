---
date: 2026-05-30
bead: polyglot-pdf-6xp
title: "copilot_watch.py: false-COMMENTS loop — re-surfaces stale round-1 inline comment after Copilot resolves via issue-comment"
tags: [hotfix, review, testing]
---

## Trigger

`bd polyglot-pdf-6xp`. Discovered live during the `qbm` closeout (PR #21): the
GitHub thread showed Copilot explicitly approving ("no further changes were
needed", twice), yet `copilot_watch.py` reported `RESULT: COMMENTS` on every
re-watch — an infinite false-positive that can never reach the loop's `CLEAN`
exit. The maintainer's instinct ("check how the script pulls the conversation —
it may not be comparing diffs properly") was correct. Root-caused via a
multi-agent diagnostic workflow against the live PR #21 API data.

## What shipped

Three compounding bugs, fixed together (the workflow proved any one alone is
insufficient — fixing only the obvious `--since` gap turns a false-COMMENTS into
a false-TIMEOUT).

**`scripts/copilot_watch.py`:**

- **Bug A (primary) — surface mismatch.** Copilot's *re-review* verdict (after
  `@copilot please review`) lands as an **issue comment** — no `state`, no
  `pull_request_review_id`, absent from `/pulls/{n}/reviews`. The watcher read
  `/reviews` only, so it could never see the resolution and kept re-selecting the
  frozen round-1 review. Added `_classify_issue_comment_round()`: when no
  in-window review exists (or the timeline is `finished`), classify the latest
  in-window Copilot **issue comment** — an explicit approval phrase
  (`_is_approval_comment`, e.g. "no further changes…") → `CLEAN`, otherwise
  `COMMENTS`. Wired into **both** the `reviewed` (review-None) and `finished`
  branches of `watch()`. Defaults to `COMMENTS` on ambiguity — never reads
  silence/ambiguity as `CLEAN`.
- **Bug B — outdated inline comments never expire.** `_collect_findings` matched
  inline comments by `review_id`, so a resolved round-1 comment re-matched its
  frozen review forever. Now drops a comment whose `position` is
  **present-and-null** (GitHub's canonical "outdated" = anchor fell out of the
  current diff). A *missing* `position` key is NOT treated as outdated (robust to
  partial payloads). State still wins: a `CHANGES_REQUESTED` verdict stays
  `COMMENTS` even if its only comment is outdated.

**`.claude/skills/closeout/SKILL.md` (Bug C):** the re-watch in Step 7 invoked
`copilot_watch.py <pr#>` with **no `--since`**, so each re-watch re-detected the
prior round. Step 7 now captures the re-trigger comment's **server** `created_at`
(`TS=$(gh api …/issues/<pr>/comments -f body=… --jq .created_at)`) and passes
`--since "$TS"`, scoping each re-watch to its own round. (Round-1 watch in Step 6
stays bare — no prior round to exclude.)

### Verification

Reproduced against PR #21's **real** API shape (not just synthetic fixtures):
**without `--since` → `COMMENTS`** (still broken, proving the SKILL change is
load-bearing); **with `--since` at the re-trigger → `CLEAN`** via the
issue-comment-approval path. A nuance the workflow's spec got slightly wrong and
the live data corrected: the round-1 inline comment had `position: 1` (not
`null`), so Bug B's drop does **not** fire here — Fix A (issue-comment verdict)
is what actually clears PR #21. Both real approval comment bodies match
`_is_approval_comment`.

`tests/test_copilot_watch.py` (+14 cases, 31 total): the real-shape `--since`
repro; issue-comment approval → CLEAN and non-approval → COMMENTS; outdated-drop
→ CLEAN; and the anti-false-negative guards (non-null `position` still COMMENTS;
`CHANGES_REQUESTED` state wins over an outdated comment; `finished`+approval →
CLEAN). Fixed one pre-existing test whose fixture omitted `position` (made the
drop present-and-null so the missing-key case is unaffected). Full suite: 144
pass.

## Review hardening (fresh-eyes + a live crash)

Fresh-eyes round 1 (and the round-1 Copilot watch itself **crashing** on the 💡
emoji in this PR's own description) caught a serious regression and several
correctness gaps:

- **Reverted a named bug.** My `Edit`s landed in the MAIN repo on a stale branch
  (`pitch/working-draft`, predating bead `polyglot-pdf-39a`'s Windows UTF-8 fix),
  then a `cp` clobbered the worktree — silently **deleting `_setup_utf8_stdio` /
  `_safe_print`** and re-introducing the cp1252 `print()` crash. Rebuilt the
  branch from `origin/dev`'s `copilot_watch.py` and re-applied the three logical
  changes on top, so the guard is intact. (The deleted emoji/safe-print tests are
  back too.)
- **Tightened `_is_approval_comment` (finding #1/#7).** A plain substring match
  would read "no changes needed in section 3, **but** please fix section 4" as an
  approval → false CLEAN. Now requires an approval phrase AND **no change-ask
  signal** (`but`/`however`/`please`/`fix`/…) in the same comment; mixed comments
  stay COMMENTS. Added the mixed-comment guard test.
- **`_latest_by_created` (finding #3).** Pick the latest issue comment by max
  `created_at`, not list `[-1]` — don't trust API ordering.
- **Approval not counted as a finding (finding #4).** `_collect_findings`
  Surface-3 now skips approval issue comments, so a clean review + a same-round
  "no further changes" comment stays CLEAN instead of flipping to COMMENTS.

## Lessons

- **Verify a workflow/spec's concrete claims against live data before coding to
  them.** The diagnosis assumed the stale comment had `position: null`; the real
  value was `1`. The spec's *structure* (three bugs, fix-together) held, but the
  primary mechanism for *this* PR was Fix A, not Fix B. Pulling the actual
  `gh api …/comments` payload caught it and reshaped which fix is load-bearing.
- **Edit IN the worktree; never `cp` from another checkout as a shortcut.** The
  stale-base clobber that reverted bug `39a` happened because edits went to the
  main repo and got copied over. Branch from `dev` and edit the worktree files
  directly. (CLAUDE.md scar tissue #3, again — the cost here was a reverted fix
  that only the review caught.)
- **A reviewer's verdict and its resolution can live on different API surfaces.**
  Copilot posts a formal *review* the first time and an *issue comment* on
  re-review. Any "did the reviewer approve?" check must reconcile reviews **and**
  issue comments, or it watches the wrong surface forever. (Generalizes — noted
  for any future review-automation.)
- **`run_in_background` + absolute paths re-triggered the worktree write trap.**
  Several `Edit`s to `scripts/`+`tests/` landed in the MAIN repo (on an unrelated
  branch) instead of the worktree, because the path resolved to the main checkout;
  pytest ran the worktree copy and "saw" no changes. Had to consolidate. Reinforces
  CLAUDE.md scar tissue #3 (the file-write half).

## Doc freshness

`check_doc_freshness.py`: clean (no `**Tracks:**`-bearing component/standards doc
covers `scripts/` or `tests/`, so nothing went stale). No tier-1/2 doc changed
besides the `/closeout` SKILL (which is not a freshness-tracked doc). The
"reviewer verdict can span surfaces" lesson is review-automation-specific, not a
code standard, so it stays here rather than in `docs/standards/`.

## Files touched

- `scripts/copilot_watch.py` — `_classify_issue_comment_round` + `_is_approval_comment`; issue-comment path in `watch()`'s reviewed/finished branches; outdated-inline drop (present-and-null); docstring "two staleness traps".
- `.claude/skills/closeout/SKILL.md` — Step 7 captures re-trigger `created_at` and passes `--since "$TS"` on the re-watch.
- `tests/test_copilot_watch.py` — +14 cases (real-shape repro, issue-comment paths, outdated-drop, anti-false-negative guards); fixed one fixture missing `position`.
- `docs/journal/entries/2026-05-30-bd-6xp-…md` — this entry.
