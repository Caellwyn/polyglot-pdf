---
name: closeout
description: Run the project's sprint-closeout checklist autonomously -- beads housekeeping, doc-freshness, journal scaffold, test suite, then open a NORMAL (non-draft) PR and run Copilot round 1 in parallel with fresh-eyes, fix the combined issues, loop Copilot until clean, then close the bead + ping the maintainer to merge. NO draft PRs (the draft->ready flip wastes a Copilot review). The only thing it never does autonomously is the final merge (that is the maintainer's). Use at the end of every sprint/bead once the code is committed and the working tree is clean. Optional argument: the bead id (e.g. /closeout myproject-ab12).
---

# Sprint closeout

You are running the closeout for this repo. This skill encodes the closeout checklist so the **deterministic** prep runs without you re-deriving it, and you spend model tokens only on the **judgment** parts (journal prose, fresh-eyes triage).

**The bead for this closeout** (if the user passed one): `$1`. If `$1` is empty, infer it from the branch name (`<type>/<id-suffix>-<slug>`) or ask.

> **Portability note.** This skill assumes the claude-swarm-kit stack: beads (`bd`) for issues, GitHub PRs with Copilot code review, and git worktrees. The integration config (repo slug, bead prefix) lives in `swarm.config.json` -- the scripts read it automatically.

> **This repo's layout (polyglot-pdf).** The Python interpreter is the backend
> venv, which lives ONLY in the main repo at `backend/.venv` -- worktrees do NOT
> have their own venv. Resolve it from anywhere (main checkout or a worktree)
> via the git common dir, and run pytest against `backend/tests/` with
> `PYTHONPATH` set to the repo root. The resolution is these two lines:
>
> ```bash
> REPO="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"
> PY="$REPO/backend/.venv/Scripts/python.exe"   # Windows; on macOS/Linux: $REPO/backend/.venv/bin/python
> ```
>
> **Shell state does NOT persist between tool calls** (the cwd and any vars
> reset each call -- see CLAUDE.md scar tissue #3), so you CANNOT set these once
> and reuse them in a later call. **Prepend both lines to every command** that
> needs them, in the SAME Bash call. So a hand-run script step is
> `REPO=...; PY=...; "$PY" "$REPO/scripts/X.py"` and the test step is
> `REPO=...; PY=...; PYTHONPATH="$REPO" "$PY" -m pytest backend/tests/ -q`
> (NOT `pytest tests/`). The `!`...`` lines that auto-run at skill-load (Step 1,
> Step 2) already inline the resolution this way.

## Hard rules (read before doing anything)

- **Open a NORMAL (non-draft) PR, never stop before it.** Do NOT use `--draft`. A normal PR triggers Copilot's round-1 review on OPEN, so Copilot runs in parallel with fresh-eyes -- you keep the parallelism with no draft. The human gate is NOT the PR-open -- it is the maintainer's final **manual merge** (`allow_auto_merge=false`, so the PR can't merge itself). Do NOT idle waiting for a "go" to open the PR.
- **NEVER use a draft PR + ready-flip.** The draft->ready flip is ITSELF a Copilot trigger (GitHub re-reviews when a PR is marked ready -- there is no ruleset toggle for it), so a draft costs TWO Copilot reviews of the same final content. Copilot review tokens are SCARCE; never trigger a redundant review of content Copilot already approved. A normal PR has no flip event, so this waste is structurally impossible.
- **The one thing you must NOT do autonomously: merge.** Never run `gh pr merge`. Everything up to and including pinging the maintainer that the PR is clean is autonomous; the merge is the maintainer's alone.
- **Loop Copilot until it has NO comments.** After a fix-push, Copilot re-reviews (`review_on_push`, ~4 min); ALSO post `@copilot please review` as a backstop. Adopt -> push -> re-watch -> repeat until clean; only then is Copilot done. Handle all four `copilot_watch` states (CLEAN/COMMENTS exit 0, ERROR exit 1, TIMEOUT exit 2 -- never treat ERROR/TIMEOUT as clean).
- **All beads writes go through `scripts/bd_safe.py`** (or direct `bd` with pull/push bracketing). Beads writes are main-thread only -- that's you, the orchestrator, not a subagent.
- **Run every git command with `git -C "<worktree-abs-path>"`** if you're in a worktree -- a bare `cd` can land you in the main repo's checkout (the shell cwd resets between tool calls).

## State injected at load time

These run from the session's working directory, which is normally the
worktree root. If any look wrong (empty branch, unexpected status), you may
be in the main repo's checkout -- re-run them with an explicit
`git -C "<worktree-abs-path>"` before trusting the values.

Current branch:
!`git rev-parse --abbrev-ref HEAD`

Working-tree status (MUST be clean before closeout):
!`git status --short`

Commits on this branch vs the integration branch:
!`git log --oneline origin/dev..HEAD`

## Step 0 -- Preconditions

1. Confirm the working tree is clean (the `git status --short` above is empty). If it is NOT, stop and tell the user: closeout assumes committed work. Do not proceed.
2. Confirm there is at least one commit ahead of the integration branch (`origin/dev` above; rename if your integration branch differs). If empty, there's nothing to close out.

## Step 1 -- Beads housekeeping (deterministic)

Run the housekeeping audit (pull + orphans + stale + push):

!`R="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"; "$R/backend/.venv/Scripts/python.exe" "$R/scripts/closeout_housekeeping.py"`

- **CLEAN** -> nothing to triage; continue.
- **SLIP-FOUND** -> triage what it surfaced:
  - An orphan (closed-in-commits but still open) -> close it with `scripts/bd_safe.py close <id> --reason "..."`.
  - A stale IN_PROGRESS bead -> decide its real state (close / defer / drop) and transition it.
- File a NEW bead (via `bd_safe.py` or bracketed `bd create`) for EVERY deferred / out-of-scope finding surfaced this sprint. Commit-message notes are not tracker entries. If the sprint identified ordered next steps, wire them with `bd dep add <later> <earlier>` (the FIRST arg is what gets blocked; for an epic, the epic is blocked BY its children, so `bd dep add <epic> <child>`) so `bd ready` surfaces only the unblocked step. `bd_safe.py dep-add --epic/--child` (or `--blocked/--prereq`) makes the direction un-invertible.

## Step 2 -- Doc freshness (deterministic)

Run the freshness checker (see `docs/doc-architecture.md` for the system it enforces):

!`R="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"; "$R/backend/.venv/Scripts/python.exe" "$R/scripts/check_doc_freshness.py"`

For each STALE doc whose `**Tracks:**` globs cover a file THIS branch changed: update the doc's CURRENT-STATE prose and bump its `*Last updated:*` line to **today's UTC date** (`date -u +%F`), swapping any obsolete journal pointer for this sprint's per-file entry. If a stale doc tracks files your branch did NOT touch, leave it -- it was already stale before you; note that in the journal entry.

Use the per-file-entry stamp shape:
`*Last updated: YYYY-MM-DD. See [path/to/journal/entry.md](...) for closeout details.*`

Do NOT chain a `Previously:` entry or add a "Recent sprint history" section -- the journal entry IS the chronological record (see the doc-maintenance rules in `docs/doc-architecture.md`).

If `check_doc_freshness.py` warns about an orphaned/missing sprint plan, resolve it -- archive a completed plan and fix the index reference.

## Step 3 -- Journal entry (scaffold deterministic, prose generative)

Scaffold the entry for this bead. Use the bead id resolved in Step 0 (NOT a
literal `$1` -- if the skill was invoked without an argument, `$1` is empty
and you must pass the id you inferred from the branch or were given):

`REPO="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"; PY="$REPO/backend/.venv/Scripts/python.exe"; "$PY" "$REPO/scripts/journal_scaffold.py" <bead-id> [--sprint N] [--pr STR]`

NOTE: this script writes into `$REPO` (the MAIN repo), not the worktree. If
you're in a worktree, MOVE the generated `docs/journal/entries/...md` into the
worktree so it ships on THIS branch, and delete the stray main-repo copy.

(Pass `--sprint`/`--pr` only if this is a numbered sprint / multi-PR sprint; omit for hotfixes.) The script writes `docs/journal/entries/YYYY-MM-DD-bd-<suffix>-<slug>.md` with the frontmatter and the 5 empty sections.

Then YOU fill it in (this is judgment, not mechanics):
- **tags:** replace the `tags: []` placeholder with 1-5 tags **verbatim from `docs/journal/TAGS.md`** -- never invent a tag. Most-specific first. (If the project hasn't set up a tag vocabulary, the scaffolded placeholder can stay or you can add `docs/journal/TAGS.md`.)
- **Trigger / What shipped / Lessons / Doc freshness / Files touched:** write the prose. In "What shipped" include the fresh-eyes triage breakdown (adopt/reject/defer + the bead ids for deferrals). In "Doc freshness" record which docs were bumped or reviewed-and-left.
- If a lesson **generalizes** (applies anywhere in the codebase), also add a one-liner to the relevant `docs/standards/*.md` citing this entry.

## Step 4 -- Run the test suite (deterministic)

Run the full suite (if slow, run it in the background and wait for the notification rather than polling):

`REPO="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"; PY="$REPO/backend/.venv/Scripts/python.exe"; PYTHONPATH="$WT" "$PY" -m pytest "$WT/backend/tests/" -q`  -- where `$WT` is the worktree root (the dir you're working in). Point `PYTHONPATH` and the test path at the WORKTREE so you test THIS branch's code, not the main checkout. Watch the COLLECTED count, not just pass/fail -- a broken import silently drops tests from collection.

If anything FAILS, stop and fix it before continuing -- a red suite is not eligible for a PR. If the project defines extra verification harnesses for the area you touched, run those too.

## Step 5 -- Commit any closeout doc/journal work

The journal entry and any doc bumps must ship in THIS PR, on THIS branch. Stage and commit them now, then re-run `git status --short` to confirm the tree is clean again.

## Step 6 -- Open a NORMAL PR and start BOTH reviews in parallel

Push the branch (`git push -u origin <branch>` after `git fetch origin && git pull --rebase origin dev`), then -- in the SAME step -- open the PR and start fresh-eyes. Copilot's round-1 review fires automatically on PR open, so the two run concurrently.

1. **Open a NORMAL (NOT draft) PR** into the integration branch:
   `gh pr create --base dev --title "<scope>(<context>): <summary> (bd <full-id>)" --body "<summary + a 'Fresh-eyes review' section you'll fill after triage>"`
   Do NOT pass `--draft`. The PR can't merge itself (`allow_auto_merge=false`), so opening it normally is safe AND avoids the draft->ready flip that would cost a second redundant Copilot review.
2. **Start Copilot-watch** (round 1) via `run_in_background` so you're woken once with the verdict, no polling turns:
   `REPO="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"; PY="$REPO/backend/.venv/Scripts/python.exe"; "$PY" "$REPO/scripts/copilot_watch.py" <pr#>`  (same invocation for the re-watch loop in Step 7)
3. **Spawn the fresh-eyes reviewer** concurrently. Prefer the standing agent `.claude/agents/fresh-eyes-reviewer.md` (spawn by type); otherwise use that file's prompt via a one-off `Agent({ subagent_type: "general-purpose", model: "sonnet", ... })`. Substitute the branch name. It MUST read the REAL diff (`git diff origin/dev...HEAD`), never a summary.

Both run simultaneously -- total round-1 wait is `max(copilot, fresh-eyes)`, not the sum.

## Step 7 -- Fix the COMBINED round-1 issues, then loop Copilot until clean

**Wait for BOTH round-1 reviewers, then fix their findings together in one batch** (so the next push carries all of them and Copilot re-reviews once, not once per reviewer):

- **Fresh-eyes (one pass):** triage -- high-confidence findings fixed inline; the rest filed as a bead BEFORE moving on (the PR body is an audit log, not a tracker); record the adopt/reject/defer breakdown for the PR body + journal.
- **Copilot round 1:** `copilot_watch.py` reports one of FOUR terminal states (exit codes: CLEAN/COMMENTS=0, ERROR=1, TIMEOUT=2) -- handle ALL four:
  - **CLEAN** (no comments) -> Copilot already happy; if fresh-eyes also produced no on-branch fixes, skip straight to Step 8.
  - **COMMENTS** -> triage like fresh-eyes (adopt inline / defer to beads).
  - **ERROR** (quota/failure) -> surface to the maintainer; NO auto-retry (a quota error won't clear for hours). NOT a clean state.
  - **TIMEOUT** (no completed review in the window) -> treat like ERROR: surface to the maintainer, never interpret silence as CLEAN. You may re-run the watch once with a longer `--timeout-min`, but never auto-clear on a timeout.

Commit the combined fixes, then **push once and loop Copilot to clean:**
1. Rebase on the FEATURE branch (NOT the integration branch): `git pull --rebase origin <branch>` -- picks up anything pushed to the branch. (Step 6's one-time pre-push rebase was against the integration branch; the loop rebases against the feature branch.)
2. Push the fix commit. The push auto-re-triggers Copilot (`review_on_push`, ~4 min).
3. **Also post `@copilot please review`** as a belt-and-suspenders re-trigger -- push-triggering has been reliable, but the mention guarantees it.
4. Re-run `copilot_watch.py <pr#>` (`run_in_background`) and repeat the COMMENTS -> fix -> push -> re-watch loop **until Copilot reports CLEAN with no comments**.

Keep the working tree clean between rounds (`git status --short`). Fresh-eyes is one pass (round 1 only); only Copilot loops.

## Step 8 -- Close the bead + ping the maintainer to merge

Once Copilot is CLEAN (no comments) and fresh-eyes is triaged, finish autonomously:

1. **Update the PR body** so the "Fresh-eyes review" section records the final adopt/reject/defer breakdown (and the Copilot rounds, if notable).
2. **Close the bead** at PR handoff via `scripts/bd_safe.py close <full-id> --reason "..."`.
3. **Ping the maintainer to merge** with a tight summary: what shipped + bead id, housekeeping result, doc/journal status, test result, fresh-eyes breakdown, Copilot rounds (final = CLEAN), and the PR URL.

The PR is already a normal, mergeable PR -- there is no flip step. The merge is the maintainer's: **never run `gh pr merge` yourself.** Pinging the maintainer is the autonomous endpoint.
