---
name: closeout
description: Run the project's sprint-closeout checklist autonomously -- beads housekeeping, doc-freshness, journal scaffold, test suite, then the SPEAR pre-PR Assess (rubric scorecard + a recursive adversarial fresh-eyes loop scored against the bead's exit criteria, looped to no-gap), then open a NORMAL (non-draft) PR and loop the Opus-4.8 outer review (two independent clearing passes) until clean, then close the bead and either auto-merge (routine low-risk PR that reviewed CLEAN) or ping the maintainer (consequence-bearing PR). Review is entirely Claude-based -- NO external reviewer. NO draft PRs. It never force-pushes or force-pushes dolt. Use at the end of every sprint/bead once the code is committed and the working tree is clean. Optional argument: the bead id (e.g. /closeout myproject-ab12).
---

# Sprint closeout

You are running the closeout for this repo. This skill encodes the closeout checklist so the **deterministic** prep runs without you re-deriving it, and you spend model tokens only on the **judgment** parts (journal prose, fresh-eyes triage).

**The bead(s) for this closeout** (if the user passed one): `$1`. If `$1` is empty, infer the primary bead from the branch name (`<type>/<id-suffix>-<slug>`) or ask. A PR may resolve **more than one** bead (small beads are often bundled to avoid a full PR cycle each) -- if so, note every bead this PR closes; you'll close them **all** in Step 6. A PR must close **at least one** bead, and no bead may span multiple PRs (split it first if it would).

> **Portability note.** This skill assumes the claude-swarm-kit stack: beads (`bd`) for issues, GitHub PRs, and git worktrees. **Review is entirely Claude-based** -- an Opus-4.8 outer review (two independent clearing passes; Step 5.6, PRE-PR), NOT an external bot. (The repo previously used OpenAI Codex, and Copilot before it; both are retired -- the maintainer's Codex subscription ended 2026-07-08.) The integration config (repo slug, bead prefix) lives in `swarm.config.json` -- the scripts read it automatically.

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
> `REPO=...; PY=...; PYTHONPATH="$REPO" "$PY" -m pytest backend/tests/ -q`.
> Target `backend/tests/` EXPLICITLY: since the root `pytest.ini` landed
> (bd polyglot-pdf-uov.1) a bare `pytest` runs BOTH suites (`backend/tests/`
> plus the top-level `tests/` harness suite); the closeout step names
> `backend/tests/` for speed, not to exclude the harness suite. The `!`...``
> lines that auto-run at skill-load (Step 1, Step 2) already inline the
> resolution this way.

## Hard rules (read before doing anything)

- **Review is entirely Claude-based -- there is NO external reviewer, and BOTH layers run PRE-PR.** The outer review (Step 5.6) is an Opus-4.8 adversarial review: the `fresh-eyes-reviewer` agent spawned at `model: opus` on the LOCAL diff (`git diff origin/dev...HEAD`), requiring **two independent clearing passes** on the identical diff, BEFORE the PR opens. There is **no `@codex review` trigger comment, no `pr_review_watcher.py` bot watcher, and no `requested_reviewers` API** -- all dead path (the maintainer's OpenAI Codex subscription ended 2026-07-08; Codex had succeeded Copilot at the earlier credit-exhaustion cutover, bd hrn.8/hrn.9 -- both retired). **For a change that does not warrant a review** (see the Step 5.6 review-worthiness gate), skip the outer review entirely; a docs-only / beads-only / journal-only / trivial change gets no outer review (its fresh-eyes `NO-GAPS` from Step 5.5 is the record).
- **Open a NORMAL (non-draft) PR, never stop before it.** Do NOT use `--draft`. BOTH review layers run PRE-PR: the fresh-eyes inner loop (Step 5.5) and the Opus-4.8 outer review (Step 5.6, review-worthy PRs only), both looped to clean on the LOCAL branch. Only then does Step 6 open the PR, close the bead(s), and make the merge decision (Step 6.2): a routine low-risk PR that reviewed CLEAN auto-merges; a consequence-bearing one is pinged to the maintainer. Do NOT idle waiting for a "go" to open the PR.
- **NEVER use a draft PR + ready-flip.** A draft adds a state flip for no benefit. Always open normal.
- **Merge is autonomous for routine low-risk PRs; the maintainer's for consequence-bearing ones (autonomy increase 2026-07-04).** Once the review is CLEAN and CI is green, apply the auto-merge rule (CLAUDE.md "Auto-merge vs. maintainer merge"): if the PR is NOT consequence-bearing, **run `gh pr merge` yourself** (Step 6.2). If it IS consequence-bearing -- proves the bead direction impossible / substantially changes an approved plan / affects operational cost / affects user-facing features / risks downstream disruption / needs substantial multi-surface rework -- do NOT merge; **ping the maintainer** that the PR is clean and ready for their merge. When unsure which side of the line, treat it as consequence-bearing and ping. Force-push and `bd dolt push --force` stay barred regardless.
- **Loop the Opus-4.8 outer review until two independent passes both clear (PRE-PR, only if review-worthy).** This runs on the LOCAL branch BEFORE the PR opens (Step 5.6). After a fix, re-spawn the Opus reviewer on the updated local diff; a fix found by EITHER of the two independent reviews invalidates both clears and re-runs both. The review is CLEAN only when two independent Opus passes (the primary looped review + a second independent confirming review -- fresh Opus, or Sonnet if a 2nd Opus is unavailable) both return `NO-GAPS` on the identical final diff. The reviewers are **subagents whose STATUS lines you read directly** -- there is no bot watcher. **Never treat a subagent TIMEOUT/ERROR (no verdict returned) as clean** -- surface it (a failure of the last-resort reviewer is a genuine stop). A change that skipped review per the Step 5.6 gate has no outer loop at all.
- **The outer review is read directly, not watched by a script.** `pr_review_watcher.py` was the GitHub-bot (Codex) path and is retired -- do NOT launch it for the outer review. There is no background watch to leave running, no `--since` floor, no ack window.
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
  5.6); spawning + triaging **fresh-eyes** (Step 5.5) and the **Opus outer review**
  (Step 5.6); the **nit-vs-blocker** calls; resolving a merge conflict; **naming
  which beads close**; the merge ping; any escalation.
- **DELEGABLE (mechanics):** running `closeout_prep.py`; writing the
  already-composed journal entry to disk; and running **`scripts/closeout_finish.py`**
  -- the one-shot glue that commits the staged work, rebases, pushes, opens the PR,
  records the telemetry row, and closes the bead(s) -- ALL in one run, because both
  reviews already cleared before it runs. It resolves the `$R`/`$WT`/`$PY` worktree
  traps **internally**, so neither you nor the subagent re-derives them.

**The flow:** you make ALL the judgments FIRST -- prep is READY, the journal prose
is written, **and BOTH reviews have cleared on the local branch: Step 5.5's
fresh-eyes loop to `NO-GAPS`, then Step 5.6's Opus outer review to
two-independent-`NO-GAPS`** (or the outer review was skipped per the Step 5.6
gate), with all fixes committed. THEN you hand the `closeout-runner` a structured
brief (bead id(s) + close reason; the **complete filled journal text**; PR title +
body, including the Step-5.5 scorecard; the telemetry counters; branch + base). It
runs the glue -- open PR, telemetry, close bead(s) -- and **stops back at every
judgment point** (prep ATTENTION, a rebase conflict, any tooling error, a missing
brief input). Fresh-eyes and the Opus outer review are NOT spawned by the runner --
they already ran pre-PR (Steps 5.5 + 5.6).

**Bead close (one run, review already done).** Because both reviews cleared BEFORE
`closeout_finish.py` runs, the single run opens the PR AND closes the bead(s)
together -- `--close-beads` is the script's default now, and there is no two-call
watcher pattern (no bot to wait on). `--close-only` remains only as a recovery tool
for the rare case where a PR was opened but its bead close failed or was deferred.

**When you run `--close-only`**, it runs the slow `bd dolt push`, so **the harness
backgrounds it and notifies you on completion.** Fire it and **END YOUR TURN; do
not `sleep`/`cat`/poll its output file.** The bead-close is committed locally before
the push finishes (a `bd show <id>` will already read CLOSED if you must check), so
there is nothing to wait on -- the `RESULT: CLOSED-ONLY` line arrives via the task
notification. This is the "a `run_in_background` / auto-backgrounded task is a hard
STOP" rule; it applies to every backgrounded step here.

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
(`closeout_housekeeping.py` reads only `bd`). If `$WT` and `$R` are the same path,
you're in the main checkout and both forms behave identically.

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
during triage** (a fresh-eyes gap fix in Step 5.5, an outer-review fix in Step 5.6, or a
Step-1 fix that touched source), re-run the suite so the PR ships a green run:

`R="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"; WT="$(git rev-parse --show-toplevel)"; PY="$R/backend/.venv/Scripts/python.exe"; PYTHONPATH="$WT" "$PY" -m pytest "$WT/backend/tests/" -q -m "not external"`  -- `$WT` (the worktree root) MUST be set in the SAME command (shell state does not persist between tool calls), or `PYTHONPATH`/the test path expand empty and you silently test the wrong checkout (fresh-eyes finding on PR #47). Point `PYTHONPATH` and the test path at the WORKTREE so you test THIS branch's code, not the main checkout; `$R` supplies only the venv interpreter. Watch the COLLECTED count, not just pass/fail -- a broken import silently drops tests from collection. (If slow, run it in the background and wait for the notification rather than polling.)

If anything FAILS, stop and fix it before continuing -- a red suite is not eligible for a PR. If the project defines extra verification harnesses for the area you touched, run those too.

## Step 5 -- Commit any closeout doc/journal work

The journal entry and any doc bumps must ship in THIS PR, on THIS branch. Stage and commit them now, then re-run `git status --short` to confirm the tree is clean again.

## Step 5.5 -- Pre-PR Assess: rubric scorecard + recursive adversarial fresh-eyes

This is the SPEAR **Assess** gate, and it runs BEFORE the PR opens (doctrine:
[`docs/doctrine/planning.md`](../../../docs/doctrine/planning.md) +
[`review-flow.md`](../../../docs/doctrine/review-flow.md)). Two parts: you score the
rubric yourself, then a recursive adversarial fresh-eyes loop hunts the gaps you
cannot see. **Fresh-eyes ALWAYS runs here -- review-worthy or not** -- so for a
review-skipped PR (no outer review) the fresh-eyes gap-free verdict IS the review
record.

### Step 5.5.a -- Score the exit-criteria rubric (orchestrator judgment)

Read the `## Exit criteria` of each bead this PR closes and score EACH criterion
`PASS` / `FAIL` with one line of evidence (the file:line or behavior that settles
it):

- **Any FAIL -> fix it before opening the PR.** A FAIL means the work does not meet
  its own contract; opening the PR anyway ships a known gap. Fix, re-test, re-score.
- **Missing criteria** (a legacy bead with no rubric) -> write a RETROSPECTIVE
  rubric now (1-3 binary criteria the work should have met), score against it, and
  note in the journal that the rubric was reconstructed at closeout (a
  creation-time-norm slip the claim-time gate should have caught).
- The final scorecard goes in the **PR body under an `## Exit criteria` section**
  (Step 6 writes the body; carry the scorecard there). This is the
  self-demonstrating record the maintainer scans.

### Step 5.5.b -- Recursive adversarial fresh-eyes loop (the inner Assess cycle)

Fresh-eyes is the **Assessor**; its mandate is gap-exhaustion against the rubric
("find every place the changes do NOT meet the criteria"), never approval. The
cycle is: spawn fresh-eyes (criteria passed in) -> fix the gaps it finds -> re-spawn
on the updated diff -> ... until an **Opus** pass returns **`NO-GAPS`** (clause 5:
a haiku/sonnet `NO-GAPS` is not terminal -- the final clearing round must be Opus),
THEN proceed to Step 6 (open the PR).

1. **Pick the fresh-eyes model from diff size (A/B arm B).** Zero-token router --
   size in, model name out, NO risk judgment (the risk call happens inside the
   fresh-eyes turn, by the cheap model):
   `R="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"; WT="$(git rev-parse --show-toplevel)"; PY="$R/backend/.venv/Scripts/python.exe"; (cd "$WT" && "$PY" "$WT/scripts/pick_review_model.py" --base origin/dev)`
   It prints `haiku` (<= ~80 changed lines) or `sonnet`. **Run the worktree's OWN
   copy (`$WT/scripts/...`), and `cd "$WT"` first** (same discipline as Steps
   2/3/4): the script only exists on THIS branch until merge, and it runs
   `git diff` in its own cwd -- without `cd "$WT"` it would measure the MAIN repo's
   `origin/dev...HEAD` (~0 lines) and route every review to `haiku`. On a
   measurement failure it prints `sonnet` and exits 1 (fail toward the capable
   model). **A/B control (arm B OFF):** if `CLAUDE_CODE_SUBAGENT_MODEL` is set, that
   session-wide override wins, so the picker is moot -- skip it and use Sonnet. Note
   whether arm B was active (picker ran AND the env var was unset); count Haiku
   self-escalations for Step 7's `--haiku-escalations`.
2. **Spawn the reviewer, passing it the bead's EXIT CRITERIA.** Prefer the standing
   agent `.claude/agents/fresh-eyes-reviewer.md` (spawn by type) with a `model`
   override of the picked value; otherwise use its prompt via a one-off
   `Agent({ subagent_type: "general-purpose", model: "<picked>", ... })`. The prompt
   MUST (a) include the bead's `## Exit criteria` verbatim so the assessor scores
   the rubric, not just style; (b) name the branch; (c) tell it to read the REAL
   diff (`git diff origin/dev...HEAD`), never a summary; (d) tell it to TRACE every
   changed value/format/contract into its consumers in untouched files before
   clearing (bd dgoa -- the standing agent file already embeds this mandate; state
   it in a one-off prompt too, and it is worth naming explicitly for a diff whose
   changed strings/formats are parsed elsewhere). **If you picked `haiku`,
   the prompt MUST tell the reviewer it is running as Haiku** -- that sentence arms
   the self-escalation clause (a Haiku run that finds the change risky stops and
   recommends a Sonnet re-review). Without it the clause is dormant.
3. **Read its STATUS line gap verdict and act:**
   - **`NO-GAPS`** -> **check clause 5 FIRST: if this clearing round ran on
     haiku/sonnet, it is NOT terminal** -- do the Opus final round (re-spawn the
     same reviewer at `model: opus` on the unchanged diff) and require ITS `NO-GAPS`
     before proceeding. Once an Opus round returns `NO-GAPS` (or this one already
     ran on Opus / a forced-Opus session), the inner loop is done: collect any
     out-of-scope bead IDs it filed (it files genuine out-of-scope bugs itself -- it
     has Bash) for the journal + merge ping, then proceed to Step 6.
   - **`GAPS-FOUND (n)`** -> **fix the gaps before the PR opens.** A rubric-criterion
     FAIL is a criterion failure, not a deferrable nit -- fix it inline (Step 5.5.a's
     "any FAIL -> fix before opening the PR" governs here too); fix other
     high-confidence findings inline as well. A genuinely out-of-scope bug is fresh-eyes'
     own to file as a separate bead (it has Bash). A rubric gap is never a "true
     nit" -- fix it inline, do not defer it. Commit the fixes, then **re-spawn
     fresh-eyes** on the updated diff. This is the recursion.
   - **`BLOCKED`** (Haiku self-escalation) -> re-spawn the SAME reviewer with
     `model: sonnet`; count it for `--haiku-escalations`.
   - **A subagent TIMEOUT/ERROR** (no verdict returned) -> **surface to the
     maintainer; NEVER silently skip the assess.** Silence is not `NO-GAPS`.
4. **Loop-stop rule -- OUTCOME-based, no round cap** (maintainer directive
   2026-07-04; the former `MAX_FRESH_EYES_ROUNDS = 3` is retired). Keep spawning
   fresh-eyes and fixing as long as each round's gaps are **correct and blocking.**
   STOP (the assess is `NO-GAPS`) when every remaining gap is either **incorrect**
   (refuted against the code -- record why) or a **true nit** better filed as a bead
   than fixed here. Fix every correct blocker and re-spawn, however many rounds it
   takes -- do NOT stop on round count. A gap you can neither fix nor honestly
   classify as incorrect/nit is the signal to escalate (normal step-2), not a round
   ceiling. (A subagent TIMEOUT/ERROR is still surfaced per the bullet above --
   silence is never `NO-GAPS`.)
5. **The FINAL confirming round MUST run on Opus** (maintainer directive
   2026-07-05, bd polyglot-pdf-dgoa). The diff-size router (step 1) routes the
   EARLIER rounds cheaply (haiku/sonnet) -- that stays. But a `NO-GAPS` is only
   terminal when the round that produced it ran on **Opus**: before you treat the
   inner loop as done, if the clearing round ran on haiku or sonnet, **re-spawn the
   SAME reviewer with `model: opus` on the unchanged diff** and require ITS verdict
   to be `NO-GAPS` too. If that Opus round finds gaps, they are real -- fix and
   continue the loop (the next clearing round again ends on Opus). Rationale: the
   strongest reviewer always gets the last look before the PR opens, because the
   cheaper tiers miss cross-file interaction bugs (a Sonnet `NO-GAPS` shipped the
   bd bo4m regression; only the stronger tier's trace caught it). This does NOT
   change the merge decision or the A/B cost accounting for the earlier rounds --
   it is one guaranteed Opus pass at the end. (When the diff is already routed to
   Opus, or `CLAUDE_CODE_SUBAGENT_MODEL` forces Opus, the clearing round already
   satisfies this -- no extra pass.)

Commit any gap fixes (and fold the assess outcome -- the rubric scorecard, the
fresh-eyes round count, the adopt/reject/defer breakdown, and any filed bead IDs --
into the journal entry's "What shipped" section) so the tree is clean before
Step 5.6. **The Opus-4.8 outer review (Step 5.6) runs next, BEFORE the PR opens.**
For a review-SKIPPED PR (no outer review) the last fresh-eyes `NO-GAPS` verdict
here is the review record -- note that in the PR body.

## Step 5.6 -- Opus-4.8 outer review (PRE-PR): two independent clearing passes, looped to clean

**Both review layers run BEFORE the PR opens (2026-07-08 flow).** The inner
fresh-eyes loop (Step 5.5) cleared to `NO-GAPS`; the Opus-4.8 outer review runs now,
on the LOCAL branch, and must clear to two-independent-`NO-GAPS` BEFORE Step 6 opens
the PR. Nothing is pushed and no PR exists yet -- the outer review reads the local
diff (`git diff origin/dev...HEAD`).

**First, judge whether this PR warrants an outer review at all** (the orchestrator
makes this call -- there is no script gate). A review of a change that can't contain
a code regression is wasted effort. Decision rule:

- **Skip the outer review** when the diff cannot introduce a runtime/logic
  regression -- e.g. it touches ONLY docs (`docs/`, `*.md`), `.beads/`, journal
  entries, or other non-executed prose/config. A pure doc bump, a beads sync, or a
  journal-only PR is in this bucket; go straight to Step 6 (its fresh-eyes `NO-GAPS`
  from Step 5.5 is the review record).
- **Run the Opus outer review** when the diff touches executable source
  (`backend/`, `frontend/src/`, scripts, CI, config that changes runtime behavior)
  in any non-trivial way.
- **When genuinely ambiguous, run the review** -- a wasted review is cheaper than
  a shipped regression. "Ambiguous" means a real judgment call, not "I'd rather not
  wait"; do not use the gate to dodge review of actual code.

**Fresh-eyes is NOT re-run here** -- it ran (and looped to `NO-GAPS`) in Step 5.5;
its triage breakdown and any filed out-of-scope beads are already recorded. Step 5.6
is the Opus-4.8 OUTER review: an independent, stronger-tier adversarial look at the
same local diff. There is **no external reviewer, no bot watcher, no trigger
comment** -- you spawn the reviewer subagents and read their STATUS lines directly
(the maintainer's Codex subscription ended 2026-07-08; the Opus review that was
formerly the "fallback for when Codex was unavailable" is now the always-on
primary). Do NOT put an `@codex review` line anywhere, do NOT use the
`requested_reviewers` reviewer API, and do NOT launch `pr_review_watcher.py` -- all
retired dead path.

**Two independent clearing reviews are required, not one** (maintainer directive 2026-07-05, bd polyglot-pdf-dgoa). The Opus outer review is the ONLY independent adversarial gate, so a single pass is a single point of failure -- the exact path PR #312 relied on when its regression could have slipped had that one pass missed it. The gate is met only when **TWO independent reviews BOTH return `NO-GAPS` on the same final diff**: the primary looped Opus review below, plus a **second independent confirming review** on the settled diff (a fresh Opus spawn -- a new subagent with no shared context -- OR a fresh Sonnet spawn; use Sonnet only when a second Opus is unavailable, and note which in the merge ping). The second reviewer reviews the SAME final commit the first one cleared; if it finds a correct blocker, that gap is real -- fix it, then BOTH reviews must clear again on the new diff (a fix invalidates a prior clear). Only when two independent passes agree `NO-GAPS` on the identical final diff is the gate satisfied.

**The primary review: spawn the `fresh-eyes-reviewer` agent with `model: opus`** (its adversarial gap-exhaustion SI is exactly the outer-review mandate). The prompt MUST (a) include the bead's `## Exit criteria` verbatim; (b) name the branch; (c) tell it to read the REAL LOCAL diff (`git diff origin/dev...HEAD`), never a summary; (d) NOT mention Haiku (it is the strong model -- the self-escalation clause stays dormant). Read its STATUS line:

- **`NO-GAPS`** -> the PRIMARY review is CLEAN, but that is only ONE of the two required passes. **Now run the second independent confirming review** (fresh Opus spawn, or fresh Sonnet if a second Opus is unavailable) on the SAME final commit, with the same prompt requirements (a)-(d):
  - **Second review `NO-GAPS`** -> the two-reviewer gate is met (the **adversarial clear**). The review is done; **go to Step 6** to open the PR + close the bead(s) + make the merge decision. The merge ping (Step 6) MUST note that TWO independent reviews cleared it (naming the second reviewer's model).
  - **Second review `GAPS-FOUND`** -> its correct blockers are real (the first reviewer missed them -- exactly why two are required). Fix inline / defer true nits, commit, then **BOTH reviews must clear again on the new diff** (a fix invalidates the prior clear): re-spawn the primary Opus loop to `NO-GAPS`, then the second confirming review, until two independent passes agree on the identical final diff. (No push -- the PR does not exist yet; this all happens on the local branch.)
- **`GAPS-FOUND (n)`** -> fix blockers inline / defer true nits (the nit-vs-blocker rule below), commit, then **re-spawn the Opus review** on the updated local diff. This is the loop. Re-run the test suite (Step 4) after any code fix. (No push -- pre-PR.)
- **`BLOCKED` / a subagent TIMEOUT or ERROR (no verdict)** -> surface to the maintainer. A failure of the last-resort reviewer is a genuine stop (there is no further fallback), so this is the one branch that escalates. **Never** interpret a missing verdict as CLEAN.

### The nit-vs-blocker decision rule (A/B arm C -- bd polyglot-pdf-hrn.5)

The reviewer returns findings, but a subagent cannot reliably tell a nit from a blocker, so **the orchestrator makes that call.** For EACH finding, classify and act:

- **Blocker -- address now, then loop.** Anything that *is*, or *might be*, a correctness / security / data-loss / regression issue. **Ambiguous counts as a blocker** (safe default): if you cannot confidently say "this is purely cosmetic and changes no behavior," treat it as a blocker and fix it. A wasted fix is cheap; a shipped regression is not.
- **True nit -- defer, don't fix inline.** A finding that is unambiguously cosmetic / stylistic / non-behavioral (naming preference, a comment-wording tweak, an optional micro-refactor with no functional effect). Do **not** fix these inline (that just spawns another review round for no behavior change). Instead **file them as ONE follow-up bead** (see the convention below) and proceed.
- **When in doubt, it's a blocker.** Do not use "nit" as an excuse to skip a fix you're unsure about -- the whole point of "ambiguous = blocker" is that the cheap mistake (an extra fix) is the one we choose.

**Deferred-nit bead convention.** File **one** bead per closeout collecting that change's true nits (not one bead per nit): title `chore(nits): deferred review nits from <bead-id>` (the review runs PRE-PR, so key the title on the bead being closed, not a PR number that does not exist yet), body listing each nit with its source (the review pass) + file:line, and tag it with the arm that deferred it via `bd create ... --metadata '{"arm":"C"}'` (the JSON-string form `bd` expects -- see hrn.4/hrn.5's own `arm` metadata) so the telemetry audit can later check whether any deferred "nit" turned out to be a real bug (the nit-turned-blocker rate, charged to the deferring arm -- see Step 7). Create it with a pull/push-bracketed `bd create` (the same way Step 1 files deferred findings -- `bd_safe.py` has no `create` subcommand, so bracket the `bd create` directly). These deferred-nit beads are **prime candidates for a later multi-bead cleanup PR** (several tiny nit beads bundled into one closeout, per the bead/PR contract in CLAUDE.md). Count them for Step 7's `--deferred-nits`.

**Loop-stop rule -- OUTCOME-based, no round cap (maintainer directive 2026-07-04).**
There is **no hard round ceiling** on the adopt-and-loop cycle. This governs EACH
review's own loop (the primary Opus loop, and -- if it finds blockers -- the second
confirming review's). Because closeout can now merge routine PRs autonomously, the
bar is code quality, not iteration budget: **keep looping as long as each round's
findings are correct and are blockers.** A lengthy back-and-forth to get the code
right is expected and fine. You **STOP that review's loop (it is CLEAN)** on a round
when EVERY remaining finding is one of:
  - **incorrect** -- the finding is wrong, refuted, or a false positive (you verified
    it against the code; record the refutation so the maintainer can audit it); or
  - **a true nit, not a blocker** -- real but non-blocking, better filed as a
    deferred-nit bead than fixed in this PR (per the nit-vs-blocker rule + the
    deferred-nit bead convention above).
If any finding is a correct blocker, **fix it and loop again** -- however many
rounds that takes. Do NOT stop because "it's been N rounds"; the only stop is "no
correct blocker remains." **A single review reaching CLEAN is not the GATE** -- the
gate still requires BOTH independent reviews CLEAN on the identical final diff
(above); a fix in either loop invalidates both clears. (Ambiguous still counts as a
blocker -- keep looping. The escalation branch is a `BLOCKED`/TIMEOUT/ERROR from a
reviewer, or a gap you can neither fix nor honestly classify -- never a round count.)

**A/B control (arm C OFF).** The `CLOSEOUT_LOOP_MODE` env var forces the control arm:
- unset / `blockers` (the default, **arm C ON**) -> the rule above: defer true nits, loop on blockers, ambiguous=blocker (under the outcome-based loop-stop -- no round cap).
- `zero` (**arm C OFF / control**) -> the old behavior: do NOT defer nits to a bead; fix or explicitly reject every finding inline before looping (no deferral, so `--deferred-nits 0`). Same outcome-based loop-stop (the arm distinction is nit-deferral vs. no-deferral, not a round count).
**Note whether arm C was active** (it was, if `CLOSEOUT_LOOP_MODE` is unset/`blockers`); Step 7 (telemetry) combines the active arms into the single `--arm` value and applies the Phase-A default.

### Merge-conflict resolution (A/B arm-agnostic -- bd polyglot-pdf-hrn.6)

The Step-6 pre-push `git pull --rebase origin dev` can hit a **merge conflict**
when the feature branch and the integration branch touched the same lines. When
that happens, **the orchestrator resolves it; it is not an automatic escalation.**
Most closeout conflicts are mechanical (two PRs each appended a journal entry, a
changelog line, or a bead row), and stopping to ask the maintainer to hand-merge a
journal ordering is exactly the kind of trivial, no-consequence ask the escalation
doctrine says to decide yourself (see CLAUDE.md "Escalation vs. autonomy").

**Resolve inline (decide it yourself)** when the conflict is **mechanical /
ordering** -- both sides are independently correct and the only question is how to
arrange them. This is the common case:

- **append-only ordering** -- journal entries, a CHANGELOG, a doc's "Related"
  list: **keep BOTH sides**, ordered the natural way (chronological for journal,
  then re-stamp if a date/sequence collides);
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

Keep the working tree clean between rounds (`git status --short`). Both loops run PRE-PR: fresh-eyes (Step 5.5, to `NO-GAPS`), then the Opus outer review (Step 5.6, to two-independent-`NO-GAPS`). They do not interleave. The reviewers are subagents you read directly -- there is no bot watcher.

## Step 6 -- Open the PR, close the bead(s), and auto-merge or ping

Both reviews have now cleared on the LOCAL branch (Step 5.5 `NO-GAPS`, Step 5.6 two-independent-`NO-GAPS`), or the review was skipped per the Step 5.6 gate. So the PR opens with review already done: **one `closeout_finish.py` run opens the PR AND closes the bead(s)** (the two-call watcher pattern is gone -- there was no bot to wait on). Then make the merge decision.

**There is NO trigger comment and NO watcher.** Do NOT put an `@codex review` line in the PR body, do NOT use the `requested_reviewers` reviewer API, and do NOT launch `pr_review_watcher.py` -- all retired dead path. If `closeout_finish.py` prints a `WATCH_CMD`, ignore it.

1. **Open the PR + close the bead(s) in one `closeout_finish.py` run** (or the raw commands if not delegating). The one run does everything mechanical: rebase, push, open the PR, **write + commit + push the telemetry row** (from the counters you pass it -- see Step 7 for what they mean), and close the bead(s). Pass the telemetry counters ON THIS run (`--arm`, `--cost-category`, `--copilot-rounds`, `--maintainer-touchpoints`, `--deferred-nits`, `--haiku-escalations`, `--errors-shipped`); do NOT re-run `harness_ledger.py` in Step 7 (that duplicates the row). The PR body is a **brief what-shipped summary + bead id(s)** plus the **`## Exit criteria` scorecard from Step 5.5.a** (each criterion PASS/FAIL with one-line evidence; for a review-SKIPPED change, also note "review record: fresh-eyes NO-GAPS, round <n>"; for a reviewed change, note "review record: Opus outer review, two independent NO-GAPS"). Write the body ONCE -- Step 6.3 records the review outcome in the journal + merge ping, not the PR body, so do NOT add an empty placeholder section. The pre-push `git pull --rebase origin dev` may hit a conflict -- resolve it per "Merge-conflict resolution" above. If opening BY HAND (not via `closeout_finish.py`), you must also run the Step-7 `harness_ledger.py` command yourself (that is its fallback role):
   ```bash
   git -C "<WT>" fetch origin && git -C "<WT>" pull --rebase origin dev
   git -C "<WT>" push -u origin <branch>
   PR=$(gh pr create --base dev \
        --title "<scope>(<context>): <summary> (bd <full-id>)" \
        --body "<brief what-shipped summary + bead id(s) + scorecard>" \
        | grep -oE '[0-9]+$')
   echo "PR=$PR"
   ```
   Do NOT pass `--draft`. The PR can't merge itself (`allow_auto_merge=false`), so opening it normally is safe. The bead(s) close in the same `closeout_finish.py` run (`--close-beads` is default-on now); if opening by hand, close them with one `scripts/bd_safe.py close <full-id> --reason "..."` per bead.
2. **Decide the merge: auto-merge or ping** (autonomy increase 2026-07-04; CLAUDE.md "Auto-merge vs. maintainer merge"). Auto-merge requires ALL of: (a) an **adversarial reviewer cleared the diff** -- the Opus-4.8 outer review gate (TWO independent `NO-GAPS` on the identical final diff, Step 5.6); (b) CI / required checks green; (c) the PR is **not consequence-bearing**. Judge (c): does it prove the bead direction impossible / substantially change an approved plan / affect operational cost / affect user-facing features / risk downstream disruption / need substantial multi-surface rework? (Same line as the step-2 escalation triggers; when unsure, treat as consequence-bearing.)
   - **All three hold -> AUTO-MERGE.** Capture the exact head SHA the review + CI cleared (`HEAD_SHA="$(gh pr view <pr#> --json headRefOid -q .headRefOid)"`), confirm CI/required checks are green (`gh pr checks <pr#>`), then merge **pinned to that SHA**: `gh pr merge <pr#> --squash --match-head-commit "$HEAD_SHA"` (match the repo's merge style). The `--match-head-commit` guard makes the merge FAIL rather than silently merge an unreviewed head if anything pushed to the branch between the clear and the merge (the review-race). NEVER pass `--admin` (it bypasses the very checks gate condition (b) relies on; it is also settings-denied). Then post a SHORT plain-language note to the maintainer: what shipped + bead id(s), and the defended-decision list (below). This is a notification, not a request -- the merge is done. If the merge fails on the SHA match, a new commit landed -> re-review that commit before retrying, do NOT drop the guard.
   - **Any of the three fails -> PING, do not merge.** That includes: consequence-bearing; review NOT clean; checks red; **or a review-SKIPPED PR** (docs-only / beads-only / trivial per the Step 5.6 gate) -- a skipped PR had no adversarial review, so condition (a) is unmet and it is NOT auto-merge-eligible even though it's low-risk; hand it to the maintainer. Also ping when you're simply unsure which side of the line the PR is on. Hand the maintainer a "clean and ready for your merge" summary and stop.
3. **Write the merge ping / notification.** Either way the summary is **for the product owner in plain language -- no jargon, no acronyms** (the maintainer's standing checkpoint AND the escalation-rule audit surface; see CLAUDE.md "Escalation vs. autonomy"). Include: what shipped + bead id(s), housekeeping result, doc/journal status, test result, fresh-eyes breakdown, the review outcome (the Opus outer review's round count, final = two independent `NO-GAPS`, and the second reviewer's model), the PR URL, and **whether you auto-merged or are handing it back**. **Then LIST each judgment call you made autonomously this PR -- INCLUDING the merge decision itself -- and briefly DEFEND it.** Make these easy to scan; this defended decision list is where the maintainer catches anything that was decided (or merged) but should have been escalated.

**Do NOT go back and rewrite the PR body after opening it.** The fresh-eyes triage breakdown and the outer-review round count already live in the **journal entry** (Step 3, the canonical chronological record) and the **merge ping** (Step 6.3, what the maintainer actually reads). Re-editing the PR description with `gh pr edit` is a **wasted model turn** generating prose for a surface nobody reads -- the initial `gh pr create --body` is the only body write. The durable record is the journal.

The PR is a normal, mergeable PR the moment it opens -- there is no flip step and no post-PR review wait. For a routine low-risk PR that reviewed CLEAN, **you merge it** (`gh pr merge`) and notify; for a consequence-bearing PR, pinging the maintainer is the autonomous endpoint. Force-push and `bd dolt push --force` are never yours regardless.

## Step 7 -- The harness telemetry row (deterministic)

The telemetry row is written by **`closeout_finish.py` itself in Step 6** -- you
pass it the counters (`--arm`, `--cost-category`, `--copilot-rounds`,
`--maintainer-touchpoints`, `--deferred-nits`, `--haiku-escalations`,
`--errors-shipped`) and it runs `harness_ledger.py` and commits+pushes the row
internally as part of the same run. **Do NOT run `harness_ledger.py` a second time
here** -- that would write a DUPLICATE row and contaminate the A/B cost-arm
counters (the exact double-count the hrn.15 discipline exists to prevent). This
step is the REFERENCE for what those counters mean (below), plus the **hand-run
fallback** for when you did NOT open the PR via `closeout_finish.py` (e.g. a manual
`gh pr create`): only then do you run the ledger yourself.

Write one JSON file to `docs/journal/telemetry/` capturing this closeout's
cost (bd polyglot-pdf-hrn.1). Each closeout writes its own file (named by
timestamp + session prefix), so parallel PRs never touch the same path and
GitHub merges them without conflict -- no custom merge driver needed. The script
is **zero-model-token**: it parses the session transcript JSONL for the token
split (orchestrator-vs-subagent, by model) and wall-clock; you only pass the
handful of numbers a script can't read off the transcript. **Fallback only**
(when the PR was NOT opened via `closeout_finish.py`) -- run the **worktree's copy**
so the file path resolves into THIS checkout (same `$WT` rule as Steps 3/4):

`R="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"; WT="$(git rev-parse --show-toplevel)"; PY="$R/backend/.venv/Scripts/python.exe"; "$PY" "$WT/scripts/harness_ledger.py" --bead <bead-id> --arm <A|B|C|BC> --cost-category <production|audit> --recorded-at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --copilot-rounds <n> --maintainer-touchpoints <n> --deferred-nits <n> --haiku-escalations <n> --errors-shipped <n>`

(The explicit `%Y-%m-%dT%H:%M:%SZ` form is used instead of `%FT%TZ` because `%F`
/`%T` are GNU `date` extensions -- BSD/macOS `date` would emit the literal format
string and land junk in `--recorded-at`. The script also has a UTC fallback if
`--recorded-at` is omitted entirely.)

Pass **one `--bead` per bead this PR closed** (repeat the flag for a bundled
PR). Fill the counters from what actually happened this session:
- `--arm` -- the experiment arm you ran, as a SINGLE value derived from which
  arms were active (Steps 5.5.b / 7 told you to note each -- arm B is the
  fresh-eyes model-picker in Step 5.5.b, arm C is the outer-review nit-loop in Step 5.6):
  - **Phase A (the default, until the counter says otherwise): pass `A`** --
    regardless of what Steps 5.5.b/7 noted. In Phase A you are measuring the
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
- `--copilot-rounds` -- how many outer-review rounds this PR took (final = CLEAN). The flag name is retained from the Copilot era to avoid churning the ledger schema + historical rows; it now counts Opus-4.8 outer-review rounds (the external reviewers -- Copilot, then Codex -- are retired).
- `--maintainer-touchpoints` -- times you had to ping/ask the maintainer.
- `--deferred-nits` -- nit beads you filed instead of fixing inline (the
  denominator for the nit-turned-blocker rate).
- `--haiku-escalations` -- times a Haiku fresh-eyes pass self-escalated to Sonnet
  (0 until arm B ships; diagnostic, not a failure).
- `--errors-shipped` -- known bugs shipped in this PR (usually 0; a later
  nit-turned-blocker audit may revise this retroactively against the deferring arm).

This is **warn-only**: a missing/failed telemetry file must never block the merge.
If the script exits non-zero (e.g. it can't locate the transcript), note the
telemetry gap in the journal entry and continue -- do NOT loop on it. The
experiment counter is **derived by scanning `docs/journal/telemetry/`** (plus the
legacy `harness_ledger.jsonl` for pre-migration rows), counted by `arm`; the
script refreshes a gitignored local cache (`.beads/experiment_state.json`)
that is never committed and can't collide on a parallel merge. `--no-counter`
only skips that cache refresh (cosmetic; the counts are always re-derivable).
