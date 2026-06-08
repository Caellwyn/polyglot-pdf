---
name: closeout
description: Run the project's sprint-closeout checklist autonomously -- beads housekeeping, doc-freshness, journal scaffold, test suite, then open a NORMAL (non-draft) PR and run Codex round 1 in parallel with fresh-eyes, fix the combined issues, loop Codex until clean, then close the bead + ping the maintainer to merge. NO draft PRs. The only thing it never does autonomously is the final merge (that is the maintainer's). Use at the end of every sprint/bead once the code is committed and the working tree is clean. Optional argument: the bead id (e.g. /closeout myproject-ab12).
---

# Sprint closeout

You are running the closeout for this repo. This skill encodes the closeout checklist so the **deterministic** prep runs without you re-deriving it, and you spend model tokens only on the **judgment** parts (journal prose, fresh-eyes triage).

**The bead(s) for this closeout** (if the user passed one): `$1`. If `$1` is empty, infer the primary bead from the branch name (`<type>/<id-suffix>-<slug>`) or ask. A PR may resolve **more than one** bead (small beads are often bundled to avoid a full PR cycle each) -- if so, note every bead this PR closes; you'll close them **all** in Step 8. A PR must close **at least one** bead, and no bead may span multiple PRs (split it first if it would).

> **Portability note.** This skill assumes the claude-swarm-kit stack: beads (`bd`) for issues, GitHub PRs with OpenAI Codex code review (triggered by an `@codex review` comment; bd hrn.9), and git worktrees. The integration config (repo slug, bead prefix) lives in `swarm.config.json` -- the scripts read it automatically.

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

- **Codex AUTO-REVIEWS on PR open; round 2+ re-reviews need an `@codex review` COMMENT (opt-in per PR).** Round 1 fires automatically when the PR opens -- no trigger call; include an `@codex review` line in the PR BODY as a belt-and-suspenders nudge. Round 2+ (after a fix-push) need an explicit `@codex review` issue comment (`gh api repos/<owner>/<repo>/issues/$PR/comments -f 'body=@codex review'`, as the gh-authenticated user), capturing its `created_at` as that round's `--since` floor. **The trigger string is EXACTLY `@codex review`** -- `@codex please commit ...` would instead invoke Codex's commit path (see AGENTS.md "If you are reviewing a PR"). **For a PR that does not warrant a review** (see the Step 6 review-worthiness gate), omit the `@codex review` line from the body and skip the whole watch loop; a docs-only / beads-only / journal-only / trivial PR gets no review. (Codex's prepaid-Copilot predecessor was retired at bd hrn.8/hrn.9 -- never use the `requested_reviewers` reviewer API; that fires Copilot, whose credits are exhausted.)
- **Open a NORMAL (non-draft) PR, never stop before it.** Do NOT use `--draft`. Fresh-eyes runs regardless; Codex runs in parallel with it ONLY when the PR is review-worthy (it auto-reviews on open; the body carries an `@codex review` nudge). The human gate is NOT the PR-open -- it is the maintainer's final **manual merge** (`allow_auto_merge=false`, so the PR can't merge itself). Do NOT idle waiting for a "go" to open the PR.
- **NEVER use a draft PR + ready-flip.** A draft adds a state flip for no benefit. Always open normal; never trigger a redundant review of content Codex already approved.
- **The one thing you must NOT do autonomously: merge.** Never run `gh pr merge`. Everything up to and including pinging the maintainer that the PR is clean is autonomous; the merge is the maintainer's alone.
- **Loop Codex until it reports CLEAN (only if the PR is review-worthy).** A fix-push does NOT re-trigger Codex on its own -- you MUST post a fresh `@codex review` comment to request each re-review. Adopt -> push -> re-comment `@codex review` (capture the new comment's `created_at` as the floor) -> re-watch -> repeat until clean; only then is Codex done. Codex signals CLEAN with a 👍 (`+1`) reaction on its summary comment (canonical), with "Didn't find any major issues" / exact `LGTM` as fallbacks. Handle all four `pr_review_watcher.py` states (CLEAN/COMMENTS exit 0, ERROR exit 1, TIMEOUT exit 2 -- never treat ERROR/TIMEOUT as clean). A PR that skipped review per the Step 6 gate has no loop at all.
- **Never leave a `pr_review_watcher.py` background process running once it is no longer needed** -- i.e. once Codex reports CLEAN OR the branch is merged. The watcher self-exits at every terminal state (CLEAN/COMMENTS/ERROR/TIMEOUT), so a watch you READ is already gone; the hazard is an orphaned watch you launched and walked away from. It runs as a `run_in_background` **Bash** task (no `TaskStop` handle) -- if one is still alive at CLEAN or merge, kill it by PID. ERROR/TIMEOUT do NOT mean "keep watching": that watch has already exited; surface the state to the maintainer (per the loop rule above) rather than spawning a fresh watcher that would then linger.
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

## Step 0 -- Prep: preconditions + beads + docs + tests in ONE run (deterministic)

Steps 0/1/2/4 (preconditions, beads housekeeping, doc-freshness, tests) are four
deterministic checks. `scripts/closeout_prep.py` runs **all four in one call** and
prints a single structured TODO, so you read ONE verdict instead of four
skill-load echoes (bd polyglot-pdf-hrn.2). Run the **worktree's copy** so it
audits THIS branch (same `$WT` rule as the steps it wraps; the venv still comes
from `$R`):

!`R="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"; WT="$(git rev-parse --show-toplevel)"; PY="$R/backend/.venv/Scripts/python.exe"; (cd "$WT" && "$PY" "$WT/scripts/closeout_prep.py")`

Read the `RESULT:` line:
- **READY** (exit 0) -- all four checks clean; skip the per-step detail below and
  go straight to Step 3 (journal). Steps 1/2/4 are already satisfied.
- **ATTENTION** (exit 3) -- one or more checks need triage. The TODO lists exactly
  which (`preconditions` / `beads` / `docs` / `tests`) with the detail inline.
  Triage each per the matching step below, then re-run prep (or just the one
  check) until READY.
- **PREP-ERROR** (exit 1) -- a check could not RUN (e.g. venv/script not found);
  this is a tooling failure, not a closeout verdict. Fix the tooling, or fall back
  to the individual hand-run commands in the steps below, before continuing.

The prep script **only reports** -- every fix below (commit a dirty tree, close an
orphan, bump a stale doc, fix a red test) is still your judgment. Steps 0--2 and 4
below are the triage reference the prep output points into; you do NOT separately
re-run their commands when prep already reported READY.

## Mechanical handoff -- you do the judgment, a cheap subagent does the glue (bd polyglot-pdf-hrn.13)

Closeout splits into **judgment** (yours, the orchestrator's) and **mechanics**
(deterministic glue). To stop spending the expensive model on git plumbing, the
mechanics can be delegated to the cheap `closeout-runner` subagent
(`.claude/agents/closeout-runner.md`, Haiku). The split:

- **YOURS (judgment, never delegate):** triaging any prep `ATTENTION`; bumping
  stale docs; **writing the journal prose**; the **review-worthiness gate** (Step
  6); spawning + triaging **fresh-eyes**; the **nit-vs-blocker** calls and the
  Codex loop (Step 7); resolving a merge conflict; **naming which beads close**;
  the merge ping; any escalation.
- **DELEGABLE (mechanics):** running `closeout_prep.py`; writing the
  already-composed journal entry to disk; and running **`scripts/closeout_finish.py`**
  -- the one-shot glue that commits the staged work, rebases, pushes, opens the PR
  (the orchestrator puts the `@codex review` nudge in the PR body; Codex
  auto-reviews on open, so for a review-worthy PR the glue captures the PR-open
  time as the watch floor + PRINTS the watch command, already carrying
  `--reviewer codex`), records the telemetry row,
  and (when told) closes the bead(s). It resolves the `$R`/`$WT`/`$PY` worktree
  traps **internally**, so neither you nor the subagent re-derives them.

**The flow:** you make the judgments (prep is READY, the journal prose is written,
the review verdict is decided), then hand the `closeout-runner` a structured brief
(bead id(s) + close reason; the review verdict; the **complete filled journal
text**; PR title + body; the telemetry counters; branch + base; whether to pass
`--close-beads`). It runs the glue and **stops back at every judgment point**
(prep ATTENTION, a rebase conflict, any tooling error, a missing brief input). You
then resume: launch the watcher from the `WATCH_CMD` it returns (adding
`--close-on-clean <bead-id>` -- see below), spawn fresh-eyes, and run the Step-7
loop. For a review-worthy PR you no longer make a separate post-CLEAN close call:
the watcher does it.

**CLEAN-trigger bead close (the second "call" is now the watcher -- bd hrn.14).**
A **review-skipped** PR (docs/beads/journal-only) has no review loop, so the single
`closeout_finish.py` run carries `--close-beads` and closes immediately (one call,
one telemetry row). A **review-worthy** PR opens WITHOUT `--close-beads`; the
bead-close happens DETERMINISTICALLY when the review terminates CLEAN, driven by
`pr_review_watcher.py --close-on-clean <bead-id>` (one `--close-on-clean` per bead,
on the round-1 watch AND every re-watch). On a CLEAN terminal state -- and ONLY
CLEAN, never COMMENTS/ERROR/TIMEOUT -- the watcher runs `closeout_finish.py
--close-only` itself (which is `bd_safe close` -> `bd dolt push`), closing the
bead(s) and **waking you only for the merge ping**, not for the close. This removes
the orchestrator turn the old manual second call cost. **Why `--close-only` and not
a commit/push:** bead state syncs via `bd dolt push` to the bead remote,
independent of the PR/git -- so there is nothing to commit or push and no
merge-race (the re-exported `.beads/*.jsonl` mirror is left dirty for the next
manual `bd` sync). **Telemetry stays clean:** `--close-only` writes NO ledger row,
so the first call's row is not duplicated (the hrn.15 A/B discipline). If the close
itself fails the watcher exits **CLOSE-FAILED (3)** so you triage it instead of
pinging merge. `closeout_finish.py` never blocks on the watcher.

**When YOU run `--close-only` by hand** (the fresh-eyes-race path: round 1 watched
WITHOUT `--close-on-clean`, then you close after CLEAN -- see Step 7), it runs the
slow `bd dolt push`, so **the harness backgrounds it and notifies you on
completion -- exactly like the watcher.** Fire it and **END YOUR TURN; do not
`sleep`/`cat`/poll its output file.** The bead-close is committed locally before
the push finishes (a `bd show <id>` will already read CLOSED if you must check), so
there is nothing to wait on -- the `RESULT: CLOSED-ONLY` line arrives via the task
notification. This is the same "a `run_in_background` / auto-backgrounded task is a
hard STOP" rule the round-1 watch states at Step 6.2 ("no polling turns"); it
applies to **every** backgrounded step here, not just the watcher.

**Preview first:** `closeout_finish.py ... --dry-run` prints the fully-resolved
plan (every command with `$R`/`$WT`/`$PY` substituted) and performs **zero** side
effects -- run it once to confirm before the real call, and as the way to rehearse
this skill without opening junk PRs.

**Delegation is optional.** Every mechanical step below also documents its raw
hand-run form; if you are not delegating, run `closeout_finish.py` yourself (it is
the same turn savings minus the subagent). The judgment steps are identical either
way. See `closeout_finish.py --help` for the full flag list.

### Step 0 detail -- Preconditions (triage if prep flagged `preconditions`)

1. Working tree must be clean. If `preconditions` is flagged DIRTY, stop and tell the user: closeout assumes committed work. Do not proceed until it's committed/stashed.
2. There must be at least one commit ahead of the integration branch (`origin/dev`; rename if yours differs). If prep reports "no commits ahead," there's nothing to close out.

### Step 1 detail -- Beads housekeeping (triage if prep flagged `beads`)

Prep runs the housekeeping audit (pull + orphans + stale + push) for you. To
re-run it standalone after a fix: `R="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"; "$R/backend/.venv/Scripts/python.exe" "$R/scripts/closeout_housekeeping.py"`

- **CLEAN** -> nothing to triage; continue.
- **SLIP-FOUND** -> triage what it surfaced:
  - An orphan (closed-in-commits but still open) -> close it with `scripts/bd_safe.py close <id> --reason "..."`.
  - A stale IN_PROGRESS bead -> decide its real state (close / defer / drop) and transition it.
- File a NEW bead (via `bd_safe.py` or bracketed `bd create`) for EVERY deferred / out-of-scope finding surfaced this sprint. Commit-message notes are not tracker entries. If the sprint identified ordered next steps, wire them with `bd dep add <later> <earlier>` (the FIRST arg is what gets blocked; for an epic, the epic is blocked BY its children, so `bd dep add <epic> <child>`) so `bd ready` surfaces only the unblocked step. `bd_safe.py dep-add --epic/--child` (or `--blocked/--prereq`) makes the direction un-invertible.

## Step 2 detail -- Doc freshness (triage if prep flagged `docs`)

Prep runs the freshness checker for you (see `docs/doc-architecture.md` for the
system it enforces). To re-run it standalone after a doc fix:

`R="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"; WT="$(git rev-parse --show-toplevel)"; test -n "$WT" && cd "$WT" || { echo "ERROR: could not resolve worktree root (git rev-parse --show-toplevel failed)"; exit 1; }; "$R/backend/.venv/Scripts/python.exe" "$WT/scripts/check_doc_freshness.py"`

**Why `$WT`, not `$R`, for this script** (`bd polyglot-pdf-9pe`): the freshness
checker sets `REPO_ROOT` to its own location's parent and reads docs + `git`
commit times from the cwd, so it audits whichever checkout it RUNS from. `$R`
(the git common-dir parent) is the MAIN repo, so an `$R/scripts/...` invocation
audits main's docs -- NOT this branch -- and silently misses stale docs the
branch introduced (and false-flags ones the branch already fixed). Run the
**worktree's own copy** (`$WT/scripts/...`) with cwd at `$WT` so the gate checks
the code under review. `$R` is still correct for the venv interpreter (the venv
lives only in the main repo) and for repo-content-agnostic scripts
(`closeout_housekeeping.py` reads only `bd`; `pr_review_watcher.py` reads only the
GitHub API). If `$WT` and `$R` are the same path, you're in the main checkout
and both forms behave identically.

For each STALE doc whose `**Tracks:**` globs cover a file THIS branch changed: update the doc's CURRENT-STATE prose and bump its `*Last updated:*` line to **today's UTC date** (`date -u +%F`), swapping any obsolete journal pointer for this sprint's per-file entry. If a stale doc tracks files your branch did NOT touch, leave it -- it was already stale before you; note that in the journal entry.

Use the per-file-entry stamp shape:
`*Last updated: YYYY-MM-DD. See [path/to/journal/entry.md](...) for closeout details.*`

Do NOT chain a `Previously:` entry or add a "Recent sprint history" section -- the journal entry IS the chronological record (see the doc-maintenance rules in `docs/doc-architecture.md`).

If `check_doc_freshness.py` warns about an orphaned/missing sprint plan, resolve it -- archive a completed plan and fix the index reference.

## Step 3 -- Journal entry (scaffold deterministic, prose generative)

Scaffold the entry for this bead. Use the bead id resolved in Step 0 (NOT a
literal `$1` -- if the skill was invoked without an argument, `$1` is empty
and you must pass the id you inferred from the branch or were given):

`R="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"; WT="$(git rev-parse --show-toplevel)"; PY="$R/backend/.venv/Scripts/python.exe"; "$PY" "$WT/scripts/journal_scaffold.py" <bead-id> [--sprint N] [--pr STR]`

The script derives its write path (`docs/journal/entries/`) from its OWN
location, so running the **worktree's copy** (`$WT/scripts/...`) writes the entry
straight into THIS branch -- no manual move (`bd polyglot-pdf-9pe`; the venv
interpreter still comes from `$R`, the main repo). If you instead run the
main-repo copy (`$R/scripts/...`) the entry lands in the main checkout and you
must move it into the worktree by hand -- prefer the `$WT` form above.

(Pass `--sprint`/`--pr` only if this is a numbered sprint / multi-PR sprint; omit for hotfixes.) The script writes `docs/journal/entries/YYYY-MM-DD-bd-<suffix>-<slug>.md` with the frontmatter and the 5 empty sections.

**Write the entry ONCE -- do not use the empty-file-then-Edit dance.** The
default file-write mode above writes an empty skeleton, which then forces a
Read-before-Edit to fill it (3 wasted turns -- see bd polyglot-pdf-hrn.13). Prefer
ONE of these single-write paths instead:
- run `journal_scaffold.py <bead-id> --print [--sprint N]` (it writes NOTHING,
  emits the skeleton to stdout), read the path it WOULD use from the naming rule
  (`docs/journal/entries/<date>-bd-<suffix>-<slug>.md`), and `Write` the FILLED
  entry (prose already composed) to that path in one shot; or
- if you delegate the mechanical tail to the `closeout-runner` subagent (see the
  Mechanical handoff note at the top), hand it the complete filled prose and it
  writes the entry once.
The `--print` flag exists precisely so the structure never has to be written
twice.

Then YOU fill it in (this is judgment, not mechanics) -- compose this prose BEFORE
the single write above:
- **tags:** replace the `tags: []` placeholder with 1-5 tags **verbatim from `docs/journal/TAGS.md`** -- never invent a tag. Most-specific first. (If the project hasn't set up a tag vocabulary, the scaffolded placeholder can stay or you can add `docs/journal/TAGS.md`.)
- **Trigger / What shipped / Lessons / Doc freshness / Files touched:** write the prose. In "What shipped" include the fresh-eyes triage breakdown (adopt/reject/defer + the bead ids for deferrals). In "Doc freshness" record which docs were bumped or reviewed-and-left.
- If a lesson **generalizes** (applies anywhere in the codebase), also add a one-liner to the relevant `docs/standards/*.md` citing this entry.

## Step 4 detail -- Test suite (triage if prep flagged `tests`; re-run after a code fix)

Prep already ran the suite in Step 0 (`backend/tests/`, excluding the flaky
`external` live-Gemini test). That result stands through Steps 3/5 as long as you
do NOT change code after it -- journal/doc work doesn't. **If you DO change code
during triage** (a fresh-eyes/Codex fix in Step 7, or a Step-1 fix that touched
source), re-run the suite so the PR ships a green run:

`R="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"; WT="$(git rev-parse --show-toplevel)"; PY="$R/backend/.venv/Scripts/python.exe"; PYTHONPATH="$WT" "$PY" -m pytest "$WT/backend/tests/" -q -m "not external"`  -- `$WT` (the worktree root) MUST be set in the SAME command (shell state does not persist between tool calls), or `PYTHONPATH`/the test path expand empty and you silently test the wrong checkout (fresh-eyes finding on PR #47). Point `PYTHONPATH` and the test path at the WORKTREE so you test THIS branch's code, not the main checkout; `$R` supplies only the venv interpreter. Watch the COLLECTED count, not just pass/fail -- a broken import silently drops tests from collection. (If slow, run it in the background and wait for the notification rather than polling.)

If anything FAILS, stop and fix it before continuing -- a red suite is not eligible for a PR. If the project defines extra verification harnesses for the area you touched, run those too.

## Step 5 -- Commit any closeout doc/journal work

The journal entry and any doc bumps must ship in THIS PR, on THIS branch. Stage and commit them now, then re-run `git status --short` to confirm the tree is clean again.

## Step 6 -- Decide review-worthiness, then open a NORMAL PR and start reviews

**First, judge whether this PR warrants a Codex review at all** (the orchestrator
makes this call -- there is no script gate). A review of a PR that can't contain a
code regression is wasted effort. Decision rule:

- **Skip Codex** (omit the `@codex review` line from the PR body; do NOT start `pr_review_watcher.py`) when the
  diff cannot introduce a runtime/logic regression -- e.g. it touches ONLY docs
  (`docs/`, `*.md`), `.beads/`, journal entries, or other non-executed prose/config.
  A pure doc bump, a beads sync, or a journal-only PR is in this bucket.
- **Review with Codex** (include the `@codex review` line in the PR body so the auto-review fires; run
  the watch loop) when the diff touches executable source (`backend/`,
  `frontend/src/`, scripts, CI, config that changes runtime behavior) in any
  non-trivial way.
- **When genuinely ambiguous, trigger the review** -- a wasted review is cheaper than
  a shipped regression. "Ambiguous" means a real judgment call, not "I'd rather not
  wait"; do not use the gate to dodge review of actual code.

Fresh-eyes ALWAYS runs regardless of this gate.

Push the branch (`git push -u origin <branch>` after `git fetch origin && git pull --rebase origin dev`), then -- in the SAME step -- open the PR and start fresh-eyes. For a review-worthy PR, **Codex auto-reviews on open** (see below), so the watch runs concurrently with fresh-eyes. (**If this pre-push `git pull --rebase origin dev` hits a merge conflict, resolve it per Step 7's "Merge-conflict resolution in the loop"** -- mechanical/ordering conflicts inline, structural ones escalate; the same boundary applies to both rebases.)

**ROUND 1: Codex AUTO-REVIEWS a review-worthy PR on open -- no trigger comment needed.** Codex (chatgpt-codex-connector[bot]) automatically reviews a PR when it opens, so round 1 needs no explicit trigger. Include an **`@codex review` line in the PR BODY** as a belt-and-suspenders nudge (it costs nothing and guarantees the review fires). **The trigger string is EXACTLY `@codex review`** -- `@codex please commit ...` would instead invoke Codex's commit path (see AGENTS.md "If you are reviewing a PR"). Do NOT use the `requested_reviewers` reviewer API -- that fires Copilot, whose prepaid credits are exhausted (bd hrn.8/hrn.9). The round-1 watch floor is the PR-open time, captured BEFORE `gh pr create` (the auto-review can land inside the create round-trip -- a floor stamped after could miss it; see the bash block above). **Round 2+ re-reviews DO need an explicit `@codex review` COMMENT** -- that's the Step-7 loop, below. (Auto-review is scoped maintainer-side, so a review-SKIPPED PR per the gate above genuinely gets no Codex review and correctly skips the watch loop -- there is no unhandled auto-review feedback to triage.)

1. **Open a NORMAL (NOT draft) PR with `@codex review` in the body, then (if review-worthy) capture the watch floor -- all in ONE Bash call.** The body is a **brief what-shipped summary + bead id(s)**, plus an `@codex review` line for review-worthy PRs. Keep it short and write it ONCE -- you will NOT come back to edit it after review (Step 8 records the fresh-eyes/Codex outcome in the journal + merge ping, not here), so do NOT add an empty 'Fresh-eyes review' placeholder section to fill in later. If you're skipping review per the gate above, omit the `@codex review` line and the `TS`:
   ```bash
   # review-worthy ONLY -- capture the floor BEFORE `gh pr create`. Codex
   # auto-reviews the instant the PR opens, so a verdict can land inside the
   # create round-trip; a floor stamped AFTER create could exclude it and TIMEOUT
   # the watch (Codex review, PR #118). Skip this line for a review-skipped PR.
   TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
   PR=$(gh pr create --base dev \
        --title "<scope>(<context>): <summary> (bd <full-id>)" \
        --body "<brief what-shipped summary + bead id(s)>

   @codex review" \
        | grep -oE '[0-9]+$')
   echo "PR=$PR TS=$TS"
   ```
   (For a review-SKIPPED PR, drop the `@codex review` line from the body and skip the `TS`.) Do NOT pass `--draft`. The PR can't merge itself (`allow_auto_merge=false`), so opening it normally is safe. (`<owner>/<repo>` comes from `swarm.config.json` / `gh repo view --json nameWithOwner`.)
2. **(Review-worthy PRs only) Start the round-1 watch with `--reviewer codex --since "$TS"`** via `run_in_background` so you're woken once with the verdict, no polling turns. `--reviewer codex` is the watcher default (bd hrn.9), so it is optional but passed explicitly for clarity. Passing `--since` scopes detection to the auto-review that fires on open. **Do NOT pass `--close-on-clean` on this round-1 watch** -- fresh-eyes is spawned in the very next sub-step and runs concurrently, so a fast clean Codex verdict here would close the bead before fresh-eyes' findings are triaged (the fresh-eyes race -- see Step 7 and the watcher's own `--close-on-clean` help). You carry `--close-on-clean <bead-id>` (one per bead) on the RE-WATCH in Step 7 instead, after all round-1 fixes are pushed -- so the deterministic close (bd hrn.14) fires on a genuinely terminal CLEAN:
   `REPO="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"; PY="$REPO/backend/.venv/Scripts/python.exe"; "$PY" "$REPO/scripts/pr_review_watcher.py" <pr#> --reviewer codex --since "$TS"`  (the Step-7 re-watch adds `--close-on-clean`; same `--since` discipline). **Skip this entirely for a review-skipped PR** -- there is no Codex round to watch (a review-skipped PR closes its bead in the single `closeout_finish.py` run, not via the watcher). (Edge case: if fresh-eyes turns out to produce NO on-branch fixes, you MAY add `--close-on-clean` to a re-watch even if Codex round 1 was already clean.)
3. **Pick the fresh-eyes model from diff size (A/B arm B), then spawn the reviewer** concurrently.

   **First run the deterministic router** so the cheap model handles small diffs (bd polyglot-pdf-hrn.4). It is zero-token -- size in, model name out, NO risk judgment (the risk call happens inside the fresh-eyes turn, by the cheap model):
   `R="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"; WT="$(git rev-parse --show-toplevel)"; PY="$R/backend/.venv/Scripts/python.exe"; (cd "$WT" && "$PY" "$WT/scripts/pick_review_model.py" --base origin/dev)`
   It prints `haiku` (≤ ~80 changed lines) or `sonnet`. **Run the worktree's OWN copy (`$WT/scripts/...`), and `cd "$WT"` first** -- two distinct worktree-safety reasons (same discipline as Steps 2/3/4): (a) the script file itself only exists in THIS branch until merge, so `$R/scripts/...` (the main checkout) would be a "file not found" pre-merge; and (b) the script runs `git diff` in its own cwd, so without `cd "$WT"` -- if the shell cwd has drifted to the main checkout -- it would measure the MAIN repo's `origin/dev...HEAD` (typically ~0 lines) and silently route every review to `haiku`. `$R` supplies only the venv interpreter. On a measurement failure it prints `sonnet` and exits 1 (fail toward the capable model); use whatever it printed.

   **A/B control (arm B OFF):** if `CLAUDE_CODE_SUBAGENT_MODEL` is set in the env, that session-wide override wins over any per-agent `model:`, so the picker is moot -- **skip it and use Sonnet** (the control arm). Run the picker only when that env var is unset. **Note whether arm B was active this session** (it was, if you let the picker route AND `CLAUDE_CODE_SUBAGENT_MODEL` was unset) -- Step 8.5 turns the active arms into the single `--arm` value (and honors the Phase-A baseline default). Count any Haiku self-escalations for `--haiku-escalations`.

   **Then spawn the reviewer** with the chosen model. Prefer the standing agent `.claude/agents/fresh-eyes-reviewer.md` (spawn by type) with a `model` override of the picked value; otherwise use that file's prompt via a one-off `Agent({ subagent_type: "general-purpose", model: "<picked>", ... })`. Substitute the branch name. **If you picked `haiku`, your prompt MUST tell the reviewer it is running as Haiku** -- that one sentence is what arms the agent's self-escalation clause (a Haiku run that finds the change risky -- a cross-file symbol, multiple surfaces, or `google-genai` wiring -- stops and recommends a Sonnet re-review instead of rendering a verdict). Without that sentence the clause is dormant and you lose the safety net. It MUST read the REAL diff (`git diff origin/dev...HEAD`), never a summary.

   **If the Haiku reviewer self-escalates** (its STATUS line is `BLOCKED` + "escalating to Sonnet re-review"), re-spawn the SAME fresh-eyes reviewer with `model: sonnet` and use that verdict; count the escalation for Step 8.5's `--haiku-escalations`.

For a review-worthy PR both reviewers run simultaneously -- total round-1 wait is `max(codex, fresh-eyes)`, not the sum. For a review-skipped PR, only fresh-eyes runs. (A Haiku self-escalation adds a short Sonnet re-run after the cheap pass; that is the expected, diagnostic cost of arm B, not a failure.)

## Step 7 -- Fix the COMBINED round-1 issues, then loop Codex until clean

**If you skipped Codex per the Step 6 gate, there is no Codex round here** -- triage fresh-eyes only (below), then go straight to Step 8. The rest of this step applies only to review-worthy PRs.

**Wait for BOTH round-1 reviewers, then fix their findings together in one batch** (so the next push carries all of them and you trigger ONE Codex re-review, not one per reviewer):

- **Fresh-eyes (one pass):** triage -- high-confidence findings fixed inline; the rest filed as a bead BEFORE moving on (the PR body is an audit log, not a tracker); record the adopt/reject/defer breakdown for the PR body + journal.
- **Codex round 1:** `pr_review_watcher.py` reports one of FOUR terminal states (exit codes: CLEAN/COMMENTS=0, ERROR=1, TIMEOUT=2; plus **CLOSE-FAILED=3** when `--close-on-clean` was passed and the deterministic close itself failed) -- handle ALL of them:
  - **CLEAN** (👍 reaction / no findings) -> Codex already happy. **If `--close-on-clean` was passed, the watcher has ALREADY closed the bead(s)** -- do NOT make a separate `--close-only` call (that would be the removed second turn). If fresh-eyes also produced no on-branch fixes, go to Step 8 (the bead is already closed; Step 8 just does telemetry + the merge ping). **One caveat -- the fresh-eyes race:** pass `--close-on-clean` on the round-1 watch ONLY once fresh-eyes is known to have produced no on-branch fixes; if fresh-eyes fixes are still pending, a round-1 CLEAN would close the bead before those fixes are reviewed. In that case launch round 1 WITHOUT `--close-on-clean`, push the fresh-eyes fixes, and carry `--close-on-clean` on the re-watch instead (every re-watch follows you having addressed everything, so its CLEAN is genuinely terminal).
  - **CLOSE-FAILED** (exit 3) -> the review WAS clean but the mechanical bead-close failed (the watcher prints the `closeout_finish.py` error). Do NOT ping "ready to merge"; triage the close (re-run `closeout_finish.py --bead <id> --close-only` by hand, or surface to the maintainer if it's a `bd`/network failure). The review verdict still stands -- only the close needs fixing.
  - **COMMENTS** -> the watcher already printed the comment bodies; **you** (the orchestrator) judge each one nit-vs-blocker per the decision rule below, then adopt blockers inline / defer true nits to a bead.
  - **ERROR** (quota/failure) -> surface to the maintainer; NO auto-retry (a quota error won't clear for hours). NOT a clean state.
  - **TIMEOUT** (no completed review in the window) -> treat like ERROR: surface to the maintainer, never interpret silence as CLEAN. You may re-run the watch once with a longer `--timeout-min`, but never auto-clear on a timeout.

### The nit-vs-blocker decision rule (A/B arm C -- bd polyglot-pdf-hrn.5)

`pr_review_watcher.py` only detects the terminal state and **extracts the comment bodies** -- a script cannot reliably tell a nit from a blocker, so **the orchestrator makes that call.** For EACH Codex finding (and each deferred fresh-eyes finding), classify and act:

- **Blocker -- address now, then loop.** Anything that *is*, or *might be*, a correctness / security / data-loss / regression issue. **Ambiguous counts as a blocker** (safe default): if you cannot confidently say "this is purely cosmetic and changes no behavior," treat it as a blocker and fix it. A wasted fix is cheap; a shipped regression is not.
- **True nit -- defer, don't fix inline.** A finding that is unambiguously cosmetic / stylistic / non-behavioral (naming preference, a comment-wording tweak, an optional micro-refactor with no functional effect). Do **not** fix these inline (that just spawns another review round for no behavior change). Instead **file them as ONE follow-up bead** (see the convention below) and proceed.
- **When in doubt, it's a blocker.** Do not use "nit" as an excuse to skip a fix you're unsure about -- the whole point of "ambiguous = blocker" is that the cheap mistake (an extra fix) is the one we choose.

**Deferred-nit bead convention.** File **one** bead per closeout collecting that PR's true nits (not one bead per nit): title `chore(nits): deferred review nits from PR #<n>`, body listing each nit with its source (`codex`/`fresh-eyes`) + file:line, and tag it with the arm that deferred it via `bd create ... --metadata '{"arm":"C"}'` (the JSON-string form `bd` expects -- see hrn.4/hrn.5's own `arm` metadata) so the telemetry audit can later check whether any deferred "nit" turned out to be a real bug (the nit-turned-blocker rate, charged to the deferring arm -- see Step 8.5). Create it with a pull/push-bracketed `bd create` (the same way Step 1 files deferred findings -- `bd_safe.py` has no `create` subcommand, so bracket the `bd create` directly). These deferred-nit beads are **prime candidates for a later multi-bead cleanup PR** (several tiny nit beads bundled into one closeout, per the bead/PR contract in CLAUDE.md). Count them for Step 8.5's `--deferred-nits`.

**Hard loop ceiling.** The Codex adopt-and-loop cycle is bounded at **`MAX_REVIEW_ROUNDS = 3`** rounds (formerly `MAX_COPILOT_ROUNDS`; renamed reviewer-neutral at the Codex cutover, bd hrn.9). If Codex still reports COMMENTS after 3 rounds of you addressing blockers, **stop looping and escalate to the maintainer** (do not loop forever): summarize the still-open findings, what you changed each round, and why they persist, and let the maintainer decide. Reaching the ceiling is an escalation, never an auto-clear -- never treat "I'm tired of looping" as CLEAN. (Round 1 from Step 6 counts as round 1; the re-watch loop below is rounds 2 and 3.)

**A/B control (arm C OFF).** The `CLOSEOUT_LOOP_MODE` env var forces the control arm:
- unset / `blockers` (the default, **arm C ON**) -> the rule above: defer true nits, loop on blockers, ambiguous=blocker, ceiling 3.
- `zero` (**arm C OFF / control**) -> the old behavior: do NOT defer nits to a bead; fix or explicitly reject every Codex finding inline before looping (no deferral, so `--deferred-nits 0`). Same ceiling.
**Note whether arm C was active** (it was, if `CLOSEOUT_LOOP_MODE` is unset/`blockers`); Step 8.5 combines the active arms into the single `--arm` value and applies the Phase-A default.

Commit the combined fixes, then **push once and loop Codex to clean:**
1. Rebase on the FEATURE branch (NOT the integration branch): `git pull --rebase origin <branch>` -- picks up anything pushed to the branch. (Step 6's one-time pre-push rebase was against the integration branch; the loop rebases against the feature branch.)
2. Push the fix commit. The push does NOT re-trigger Codex by itself -- the re-trigger comment in the next sub-step is what requests the re-review.
3. **Post a fresh `@codex review` comment, capturing its `created_at` as the floor** -- the new comment requests the re-review, and the floor is the round boundary the re-watch needs (without it, the watcher re-detects the PREVIOUS round's verdict and loops forever; see `bd polyglot-pdf-6xp`). The comments API returns the created comment's JSON, so read the floor from its `created_at`:
   `TS=$(gh api repos/<owner>/<repo>/issues/<pr#>/comments -f 'body=@codex review' --jq '.created_at')`
4. **Re-watch with `--reviewer codex --since "$TS"`** (`run_in_background`), scoping detection to THIS round. Carry `--close-on-clean <bead-id>` (one per bead) on the re-watch too, so whichever round reaches CLEAN closes the bead(s) deterministically:
   `REPO="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"; PY="$REPO/backend/.venv/Scripts/python.exe"; "$PY" "$REPO/scripts/pr_review_watcher.py" <pr#> --reviewer codex --since "$TS" --close-on-clean <bead-id> [...]`
   Repeat the COMMENTS -> (judge nit-vs-blocker) -> fix blockers / defer nits -> push -> re-comment `@codex review`(capture TS) -> re-watch loop **until Codex reports CLEAN or you hit `MAX_REVIEW_ROUNDS` (3)**, whichever comes first. At the ceiling, escalate to the maintainer (per the decision rule above) rather than looping again. (Round 1 in Step 6 takes no `--since` -- it has no prior round to exclude. The re-watch ALWAYS does.)

### Merge-conflict resolution in the loop (A/B arm-agnostic -- bd polyglot-pdf-hrn.6)

The rebase in sub-step 1 (`git pull --rebase origin <branch>`) -- and the Step-6
pre-push `git pull --rebase origin dev` -- can hit a **merge conflict** when the
feature branch and the integration branch touched the same lines. When that
happens, **the orchestrator resolves it; it is not an automatic escalation.** Most
closeout conflicts are mechanical (two PRs each appended a journal entry, a
changelog line, or a bead row), and stopping to ask the maintainer to hand-merge a
journal ordering is exactly the kind of trivial, no-consequence ask the escalation
doctrine says to decide yourself (see CLAUDE.md "Escalation vs. autonomy").

**Resolve inline (decide it yourself)** when the conflict is **mechanical /
ordering** -- both sides are independently correct and the only question is how to
arrange them. This is the common case:

- **append-only ordering** -- journal entries, `harness_ledger.jsonl` rows, a
  CHANGELOG, a doc's "Related" list: **keep BOTH sides**, ordered the natural way
  (chronological for journal/ledger, then re-stamp if a date/sequence collides);
- **independent additions to the same list/table** -- two new rows in a doc table,
  two new entries in `MEMORY.md` or an index: keep both, in a sensible order;
- **a pure interleave** where neither side changed the other's lines, git just
  couldn't pick an order.

After an inline resolution, **re-read the merged region** to confirm both sides'
intent survived (an append-both that accidentally drops one side is the failure
mode), then `git add` + `git rebase --continue` and proceed with the push.

**Escalate (STOP and ask the maintainer)** ONLY on a **genuine structural
incompatibility** -- where keeping both sides is *not* correct and choosing
between them is a real decision:

- the two sides change the **same logic / contract** in incompatible ways (both
  edited the same function body, the same wire-format key, the same config value)
  and reconciling them requires a **design call**, not an ordering call;
- resolving it would **silently drop or override** the other PR's behavior change;
- you **cannot tell** whether both intents survive a merge -- ambiguous counts as
  structural (same safe-default spirit as "ambiguous = blocker" above).

When you escalate a structural conflict, **abort the rebase** (`git rebase --abort`)
so the branch is left clean, not half-merged, then ping the maintainer with the
conflicting hunks and what each side was trying to do. Per the hard-stop rule,
first finish anything that does *not* depend on the resolution. (Verification of
this boundary -- synthetic mechanical conflict resolves inline, synthetic
structural conflict escalates -- is recorded in this bead's journal entry.)

**As soon as Codex reports CLEAN, make sure no `pr_review_watcher.py` is still running** (a lingering watcher wastes tokens). `pr_review_watcher.py` exits on its own at every terminal state (CLEAN/COMMENTS/ERROR/TIMEOUT), so the one you just read is already gone -- the real hazard is an EARLIER watch you launched and never read, or a re-watch you started and then abandoned. The watcher runs as a `run_in_background` **Bash** task (not an agent task, so there is no `TaskStop` handle) -- if one is still alive, kill it by its background task / PID (e.g. `Stop-Process`). Do this before moving to Step 8 -- do not leave a watcher running into the merge wait.

Keep the working tree clean between rounds (`git status --short`). Fresh-eyes is one pass (round 1 only); only Codex loops.

## Step 8 -- Close the bead + ping the maintainer to merge

Once Codex is CLEAN (👍 / no findings) and fresh-eyes is triaged, finish autonomously:

0. **Confirm no `pr_review_watcher.py` is still running.** It should already have been killed when Codex went CLEAN (Step 7); if any watcher is still alive here -- or later, once you observe the branch has been merged -- kill it now. Never leave a `pr_review_watcher` process running past CLEAN or past merge.
1. **Close the bead(s)** this PR resolves at PR handoff -- **but only if they are not already closed.** For a **review-worthy** PR the watcher's `--close-on-clean` already closed them when the review went CLEAN (Step 7); do NOT re-close (a redundant `bd close` is a no-op but a wasted turn). Close here ONLY when the watcher did NOT (a **review-skipped** PR -- where `closeout_finish.py --close-beads` already closed in the single run, so nothing to do here either; or a recovery after a **CLOSE-FAILED** that you then fixed). When you do close by hand: one `scripts/bd_safe.py close <full-id> --reason "..."` per bead (at least one; all of them if the PR bundled several). If you're unsure, `bd show <id>` -- a re-close of an already-closed bead is harmless but skip it.
2. **Ping the maintainer to merge** with a summary written **for the product owner in plain language -- no jargon, no acronyms** (this is the maintainer's standing checkpoint AND the audit surface for the escalation rule; see CLAUDE.md "Escalation vs. autonomy"). Include: what shipped + bead id(s), housekeeping result, doc/journal status, test result, fresh-eyes breakdown, Codex rounds (final = CLEAN), and the PR URL. **Then LIST each judgment call you made autonomously this PR and briefly DEFEND it** -- what you chose, and why it was yours to decide rather than escalate. Make these easy to scan; this defended decision list is where the maintainer catches anything that was decided but should have been escalated.

**Do NOT go back and rewrite the PR body after review.** The fresh-eyes triage breakdown and the Codex-round count already live in the **journal entry** (Step 3, the canonical chronological record) and the **merge ping** (Step 8.2, what the maintainer actually reads). Re-editing the PR description with `gh pr edit` after the PR is approved is a **wasted model turn** generating prose for a surface nobody reads -- the initial `gh pr create --body` (Step 6) is the only body write. Whatever you put there at open time stands; the durable record is the journal.

The PR is already a normal, mergeable PR -- there is no flip step. The merge is the maintainer's: **never run `gh pr merge` yourself.** Pinging the maintainer is the autonomous endpoint.

## Step 8.5 -- Record the harness telemetry row (deterministic)

Append one row to `docs/journal/harness_ledger.jsonl` capturing this closeout's
cost (bd polyglot-pdf-hrn.1). The script is **zero-model-token**: it parses the
session transcript JSONL for the token split (orchestrator-vs-subagent, by
model) and wall-clock; you only pass the handful of numbers a script can't read
off the transcript. Run the **worktree's copy** so the ledger path resolves into
THIS checkout (same `$WT` rule as Steps 3/4):

`R="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"; WT="$(git rev-parse --show-toplevel)"; PY="$R/backend/.venv/Scripts/python.exe"; "$PY" "$WT/scripts/harness_ledger.py" --bead <bead-id> --arm <A|B|C|BC> --cost-category <production|audit> --recorded-at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --copilot-rounds <n> --maintainer-touchpoints <n> --deferred-nits <n> --haiku-escalations <n> --errors-shipped <n>`

(The explicit `%Y-%m-%dT%H:%M:%SZ` form is used instead of `%FT%TZ` because `%F`
/`%T` are GNU `date` extensions -- BSD/macOS `date` would emit the literal format
string and land junk in `--recorded-at`. The script also has a UTC fallback if
`--recorded-at` is omitted entirely.)

Pass **one `--bead` per bead this PR closed** (repeat the flag for a bundled
PR). Fill the counters from what actually happened this session:
- `--arm` -- the experiment arm you ran, as a SINGLE value derived from which
  arms were active (Steps 6.3 / 7 told you to note each):
  - **Phase A (the default, until the counter says otherwise): pass `A`** --
    regardless of what Steps 6.3/7 noted. In Phase A you are measuring the
    baseline, so the arm is `A` even though the picker/loop ran their normal
    path; the B/C notes only become the arm value once the phase directive has
    advanced to B/C toggling. Mislabeling a baseline closeout `B`/`C` would
    prematurely advance the phase counters and invalidate the baseline.
  - **Once toggling (directive says "start B/C"):** pass `B` if only arm B was
    active, `C` if only arm C, **`BC` if BOTH were active** this session, or `A`
    if both were forced off by their control env vars. Combine -- never pass two
    `--arm` flags; the counter takes one arm label per row.
  The script prints the next-phase directive after it writes; check it any time
  with `"$PY" "$WT/scripts/harness_ledger.py" --print-directive`.
- `--cost-category` -- `production` for normal feature/bug work; **`audit`** for a
  closeout whose work was measurement / cross-arm bug-reporting (audit work is
  never charged to the arm doing it -- the plan's fairness rule).
- `--copilot-rounds` -- how many bot review rounds this PR took (final = CLEAN). The flag name is retained from the Copilot era to avoid churning the ledger schema + historical rows; under the Codex cutover (bd hrn.9) it counts Codex rounds.
- `--maintainer-touchpoints` -- times you had to ping/ask the maintainer.
- `--deferred-nits` -- nit beads you filed instead of fixing inline (the
  denominator for the nit-turned-blocker rate).
- `--haiku-escalations` -- times a Haiku fresh-eyes pass self-escalated to Sonnet
  (0 until arm B ships; diagnostic, not a failure).
- `--errors-shipped` -- known bugs shipped in this PR (usually 0; a later
  nit-turned-blocker audit may revise this retroactively against the deferring arm).

This is **warn-only**: a missing/failed ledger row must never block the merge.
If the script exits non-zero (e.g. it can't locate the transcript), note the
telemetry gap in the journal entry and continue -- do NOT loop on it. The
experiment counter is **derived from the ledger** (counted by `arm`), not bumped;
the script refreshes a gitignored local cache (`.beads/experiment_state.json`)
that is never committed and can't collide on a parallel merge (bd
polyglot-pdf-8o4). `--no-counter` only skips that cache refresh (cosmetic; the
counts live in the ledger regardless).
