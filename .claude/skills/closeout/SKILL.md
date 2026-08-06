---
name: closeout
description: Run the project's sprint-closeout checklist autonomously -- beads housekeeping, doc-freshness, journal scaffold, test suite, then the SPEAR pre-PR Assess (rubric scorecard + a recursive adversarial fresh-eyes loop scored against the bead's exit criteria, looped to no-gap), then ONE looped Opus-5 outer cross-surface review until clean, then open a NORMAL (non-draft) PR, close the bead and either auto-merge (routine low-risk PR that reviewed CLEAN) or ping the maintainer (consequence-bearing PR). Review is entirely Claude-based -- NO external reviewer. NO draft PRs. It never force-pushes or force-pushes dolt. Use at the end of every sprint/bead once the code is committed and the working tree is clean. Optional argument: the bead id (e.g. /closeout myproject-ab12).
---

# Sprint closeout

You are running the closeout for this repo. This skill encodes the closeout checklist so the **deterministic** prep runs without you re-deriving it, and you spend model tokens only on the **judgment** parts (journal prose, fresh-eyes triage).

**The bead(s) for this closeout** (if the user passed one): `$1`. If `$1` is empty, infer the primary bead from the branch name (`<type>/<id-suffix>-<slug>`) or ask. A PR may resolve **more than one** bead (small beads are often bundled to avoid a full PR cycle each) -- if so, note every bead this PR closes; you'll close them **all** in Step 6. A PR must close **at least one** bead, and no bead may span multiple PRs (split it first if it would).

> **Portability note.** This skill assumes the claude-swarm-kit stack: beads (`bd`) for issues, GitHub PRs, and git worktrees. **Review is entirely Claude-based** -- ONE looped Opus-5 outer cross-surface review (Step 5.6, PRE-PR), NOT an external bot. (The repo previously used OpenAI Codex, and Copilot before it; both are retired -- the maintainer's Codex subscription ended 2026-07-08.) The integration config (repo slug, bead prefix) lives in `swarm.config.json` -- the scripts read it automatically.

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

- **Review is entirely Claude-based -- there is NO external reviewer, and BOTH layers run PRE-PR.** The outer review (Step 5.6) is an Opus-5 adversarial cross-surface review: the `cross-surface-reviewer` agent (`model: opus`) on the LOCAL diff (`git diff origin/dev...HEAD`), looped to a SINGLE clearing `NO-GAPS`, BEFORE the PR opens. There is **no `@codex review` trigger comment, no `pr_review_watcher.py` bot watcher, and no `requested_reviewers` API** -- all dead path (the maintainer's OpenAI Codex subscription ended 2026-07-08; Codex had succeeded Copilot at the earlier credit-exhaustion cutover, bd hrn.8/hrn.9 -- both retired). **The Step 5.6 gate is a THREE-way fork** (bd polyglot-pdf-saxh): source diffs get that Opus cross-surface review; **docs-only diffs get ONE adversarial Haiku review** (the `docs-reviewer` agent, looped to `NO-GAPS` -- prose review, not a contract trace); only a genuinely TRIVIAL diff skips adversarial review entirely (its fresh-eyes `NO-GAPS` from Step 5.5 is the record).
- **Open a NORMAL (non-draft) PR, never stop before it.** Do NOT use `--draft`. BOTH review layers run PRE-PR: the fresh-eyes inner loop (Step 5.5) and the Opus-5 outer review (Step 5.6, review-worthy PRs only), both looped to clean on the LOCAL branch. Only then does Step 6 open the PR, close the bead(s), and make the merge decision (Step 6.2): a routine low-risk PR that reviewed CLEAN auto-merges; a consequence-bearing one is pinged to the maintainer. Do NOT idle waiting for a "go" to open the PR.
- **NEVER use a draft PR + ready-flip.** A draft adds a state flip for no benefit. Always open normal.
- **Merge is autonomous for routine low-risk PRs; the maintainer's for consequence-bearing ones (autonomy increase 2026-07-04).** Once the review is CLEAN and CI is green, apply the auto-merge rule (CLAUDE.md "Auto-merge vs. maintainer merge"): if the PR is NOT consequence-bearing, **run `gh pr merge` yourself** (Step 6.2). If it IS consequence-bearing -- proves the bead direction impossible / substantially changes an approved plan / affects operational cost / affects user-facing features / risks downstream disruption / needs substantial multi-surface rework -- do NOT merge; **ping the maintainer** that the PR is clean and ready for their merge. When unsure which side of the line, treat it as consequence-bearing and ping. Force-push and `bd dolt push --force` stay barred regardless.
- **Loop the ONE Opus-5 outer review until it clears (PRE-PR, only if review-worthy).** This runs on the LOCAL branch BEFORE the PR opens (Step 5.6). After a **behavioral** fix, re-spawn the Opus reviewer on the updated local diff. The review is CLEAN when a single Opus pass returns `NO-GAPS`. **A NON-BEHAVIORAL fix does NOT invalidate that clear** -- filing a bead, editing a comment or docstring, `docs/`-only prose, a journal entry, or a `.beads/` sync leaves the clear standing; do not re-spawn for it (full rule + tie-breaker in Step 5.6). The reviewer is a **subagent whose STATUS line you read directly** -- there is no bot watcher. **Never treat a subagent TIMEOUT/ERROR (no verdict returned) as clean** -- surface it (a failure of the last-resort reviewer is a genuine stop). **One exception:** an effort-unsupported `400` on the spawn ITSELF is a transport failure, not a missing verdict -- take the effort-400 Workflow fallback in Step 5.6 (it applies to EVERY subagent spawn in closeout, at any model and any step, including the Step 6 `closeout-runner`) and do NOT surface it, unless the wrapped retry also fails. A change that skipped review per the Step 5.6 gate has no outer loop at all.
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
  and closes the bead(s) -- ALL in one run, because both reviews already cleared
  before it runs. It resolves the `$R`/`$WT`/`$PY` worktree
  traps **internally**, so neither you nor the subagent re-derives them.

**The flow:** you make ALL the judgments FIRST -- prep is READY, the journal prose
is written, **and BOTH reviews have cleared on the local branch: Step 5.5's
fresh-eyes loop to `NO-GAPS`, then Step 5.6's ONE Opus outer cross-surface review
to `NO-GAPS`** (or the outer review was skipped per the Step 5.6
gate), with all fixes committed. THEN you hand the `closeout-runner` a structured
brief (bead id(s) + close reason; the **complete filled journal text**; PR title +
body, including the Step-5.5 scorecard; branch + base). It
runs the glue -- open PR, close bead(s) -- and **stops back at every
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
- File a NEW bead (via `bd_safe.py` or bracketed `bd create`) for EVERY deferred / out-of-scope finding surfaced this sprint. Commit-message notes are not tracker entries. If the sprint identified ordered next steps, wire them with `bd dep add <later> <earlier>` (the FIRST arg is what gets blocked) so `bd ready` surfaces only the unblocked step. Epic wiring is a parent-child edge, not a blocks edge (bd rejects task-blocks-epic): `bd dep add <child> <epic> -t parent-child`. `bd_safe.py dep-add --epic/--child` (or `--blocked/--prereq`) makes the edge un-invertible.

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
TRIVIAL PR (no adversarial review at all) the fresh-eyes gap-free verdict IS the review
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
on the updated diff -> ... until the routed reviewer returns **`NO-GAPS`**. **That
verdict IS terminal** -- there is no Opus round here; the single Opus pass is the
Step 5.6 outer cross-surface review, which runs next.

1. **Pick the fresh-eyes model from diff size.** Zero-token router --
   size in, model name out, NO risk judgment (the risk call happens inside the
   fresh-eyes turn, by the cheap model):
   `R="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"; WT="$(git rev-parse --show-toplevel)"; PY="$R/backend/.venv/Scripts/python.exe"; (cd "$WT" && "$PY" "$WT/scripts/pick_review_model.py" --base origin/dev)`
   It prints `haiku` (<= ~80 changed lines) or `sonnet`. **Run the worktree's OWN
   copy (`$WT/scripts/...`), and `cd "$WT"` first** (same discipline as Steps
   2/3/4): the script only exists on THIS branch until merge, and it runs
   `git diff` in its own cwd -- without `cd "$WT"` it would measure the MAIN repo's
   `origin/dev...HEAD` (~0 lines) and route every review to `haiku`. On a
   measurement failure it prints `sonnet` and exits 1 (fail toward the capable
   model). If `CLAUDE_CODE_SUBAGENT_MODEL` is set, that session-wide override
   wins, so the picker is moot -- skip it and use Sonnet.
2. **Spawn the reviewer, passing it the bead's EXIT CRITERIA.** Prefer the standing
   agent `.claude/agents/fresh-eyes-reviewer.md` (spawn by type) with a `model`
   override of the picked value; otherwise use its prompt via a one-off
   `Agent({ subagent_type: "general-purpose", model: "<picked>", ... })`. The prompt
   MUST (a) include the bead's `## Exit criteria` verbatim so the assessor scores
   the rubric, not just style; (b) name the branch; (c) tell it to read the REAL
   diff (`git diff origin/dev...HEAD`), never a summary; (d) tell it to **ENUMERATE
   every changed value/format/contract into its `## Changed contracts` block** --
   NOT to trace them into consumers. Tracing is the Step 5.6 outer reviewer's job,
   and duplicating it here is the cost the inner/outer split exists to remove; the
   enumeration is what the outer reviewer starts from, so an omission there becomes
   an untraced contract downstream. **If you picked `haiku`,
   the prompt MUST tell the reviewer it is running as Haiku** -- that sentence arms
   the self-escalation clause (a Haiku run that finds the change risky stops and
   recommends a Sonnet re-review). Without it the clause is dormant.
3. **Read its STATUS line gap verdict and act:**
   - **`NO-GAPS`** -> the inner loop is **done** (this verdict is terminal at
     whatever model produced it -- there is no Opus round here). Collect any
     out-of-scope bead IDs it filed (it files genuine out-of-scope bugs itself -- it
     has Bash) for the journal + merge ping, **carry its `## Changed contracts`
     block forward into the Step 5.6 spawn**, then proceed to Step 5.6.
   - **`GAPS-FOUND (n)`** -> **fix the gaps before the PR opens.** A rubric-criterion
     FAIL is a criterion failure, not a deferrable nit -- fix it inline (Step 5.5.a's
     "any FAIL -> fix before opening the PR" governs here too). For every OTHER
     finding, apply **the same triage rule as Step 5.6** (the pre-existing test, the
     narrowed blocker test, and the never-swept-under-the-rug rule -- stated once
     there, and governing here too): fix the blockers inline, and **file
     pre-existing and non-blocking findings as beads rather than chasing them here.**
     Chasing a pre-existing finding in this loop expands the diff before the Opus
     pass ever runs -- the same churn one layer down. A genuinely out-of-scope bug is
     fresh-eyes' own to file (it has Bash). A rubric gap is never a "true nit" -- fix
     it inline, do not defer it. Commit the fixes, then **re-spawn fresh-eyes** on
     the updated diff. This is the recursion.
   - **`BLOCKED`** (Haiku self-escalation) -> re-spawn the SAME reviewer with
     `model: sonnet`.
   - **A subagent TIMEOUT/ERROR** (no verdict returned) -> **surface to the
     maintainer; NEVER silently skip the assess.** Silence is not `NO-GAPS`.
     **Exception -- the effort-400:** if the spawn itself failed with an
     effort-unsupported `400` (see the effort-400 fallback in Step 5.6, which
     applies to these Step 5.5 spawns too, at haiku/sonnet/opus alike), that is a
     transport failure -- retry it wrapped in a one-agent Workflow with
     `effort: 'high'` and carry on; surface only if the wrapped retry also fails.
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
5. **This loop stays on the routed model -- there is NO Opus round here.** The
   diff-size router (step 1) picks haiku or sonnet and that model's `NO-GAPS` is
   terminal for the inner loop. The strongest reviewer still gets the last look
   before the PR opens, but it gets it **once**, in Step 5.6, doing the
   cross-surface job the cheap tiers genuinely cannot do -- not by re-running this
   same rubric-and-local-bugs pass at a higher price.

Commit any gap fixes (and fold the assess outcome -- the rubric scorecard, the
fresh-eyes round count, the adopt/reject/defer breakdown, and any filed bead IDs --
into the journal entry's "What shipped" section) so the tree is clean before
Step 5.6. **Step 5.6's adversarial review runs next, BEFORE the PR opens** -- the
Opus cross-surface review for a source diff (carry the inner reviewer's `## Changed
contracts` block into its prompt), or the Haiku `docs-reviewer` for a docs-only
diff. For a genuinely TRIVIAL PR (no adversarial review at all) the last fresh-eyes
`NO-GAPS` verdict here is the review record -- note that in the PR body.

## Step 5.6 -- Adversarial review (PRE-PR): ONE looped clearing pass, model by diff type

**Both review layers run BEFORE the PR opens (2026-07-08 flow).** The inner
fresh-eyes loop (Step 5.5) cleared to `NO-GAPS`; the Opus-5 outer cross-surface
review runs now, on the LOCAL branch, and must clear to `NO-GAPS` BEFORE Step 6 opens
the PR. Nothing is pushed and no PR exists yet -- the outer review reads the local
diff (`git diff origin/dev...HEAD`).

**The two layers have DIFFERENT jobs -- that is the point of the split.** The inner
loop got the local diff right (rubric + in-diff correctness) and **enumerated** every
changed contract. The outer pass does **not** re-hunt local bugs; it takes that
enumeration and follows each contract OUT of the diff into consumers in files the
diff never touched. Finding no local bug is not a failure of the outer pass -- that
work is already done.

**First, judge whether this PR warrants an outer review at all** (the orchestrator
makes this call -- there is no script gate). A review of a change that can't contain
a code regression is wasted effort. Decision rule:

**This is a THREE-way fork, not a skip/run binary** (maintainer directive
2026-08-05, bd polyglot-pdf-saxh). Every PR gets SOME adversarial review; only the
model and mandate change:

- **Run the Opus outer cross-surface review** when the diff touches executable source
  (`backend/`, `frontend/src/`, scripts, CI, config that changes runtime behavior)
  in any non-trivial way. This is Step 5.6 proper (`cross-surface-reviewer`,
  `model: opus`).
- **Run the HAIKU docs review** when the diff is docs-only -- `docs/`, `*.md`,
  `.beads/`, journal entries, or other non-executed prose. Spawn the
  **`docs-reviewer`** agent (`.claude/agents/docs-reviewer.md`, already
  `model: haiku`) on the same local diff, looped to `NO-GAPS` exactly like the Opus
  loop. Its mandate is **adversarial prose review, NOT a contract trace** -- prose
  that contradicts the code it documents, stale cross-references, doc-vs-doc
  conflicts, a `*Last updated:*` bump with no real prose review. Its prompt MUST
  (a) include the bead's `## Exit criteria` verbatim; (b) name the branch; (c) tell
  it to read the REAL LOCAL diff (`git diff origin/dev...HEAD`), never a summary.
  The Opus spawn's (d) and (e) do NOT apply here: (d) is about the dormant
  self-escalation clause, which this agent does not have, and (e)'s `## Changed
  contracts` paste is meaningless when the diff changes no runtime contract.
  *Why this exists:* before bd saxh a docs-only PR got NO adversarial model review
  at all (the retired guaranteed-Opus inner round had been its only one), so a doc
  asserting something the code contradicts could ship unchallenged.
- **Skip adversarial review entirely** only for a genuinely TRIVIAL diff -- a typo
  fix, a whitespace change, a `.beads/` sync with no prose. Its fresh-eyes `NO-GAPS`
  from Step 5.5 is the record. When in doubt between trivial and docs-only, run the
  Haiku review: it is cheap and fast, and that is the whole point of having it.
- **When genuinely ambiguous between docs-only and source, run the OPUS review** --
  a wasted review is cheaper than a shipped regression. "Ambiguous" means a real
  judgment call, not "I'd rather not wait"; do not use the gate to dodge review of
  actual code. **A diff that touches even one executable file is a source diff**, no
  matter how much docs prose rides along with it.

**Auto-merge is UNCHANGED by this fork** (bd saxh deliberately did not widen it): a
docs PR that a Haiku review cleared still **pings** the maintainer rather than
auto-merging. Whether a Haiku-cleared docs PR should become auto-merge-eligible is a
product/autonomy call for the maintainer, not this skill's to assume. See Step 6.2.

**Fresh-eyes is NOT re-run here** -- it ran (and looped to `NO-GAPS`) in Step 5.5;
its triage breakdown and any filed out-of-scope beads are already recorded. Step 5.6
is the Opus-5 OUTER review: an independent adversarial look at the
same local diff by a fresh subagent with no shared context. There is **no external reviewer, no bot watcher, no trigger
comment** -- you spawn the reviewer subagents and read their STATUS lines directly
(the maintainer's Codex subscription ended 2026-07-08; the Opus review that was
formerly the "fallback for when Codex was unavailable" is now the always-on
primary). Do NOT put an `@codex review` line anywhere, do NOT use the
`requested_reviewers` reviewer API, and do NOT launch `pr_review_watcher.py` -- all
retired dead path.

**ONE looped Opus pass is the gate (2026-08-05).** A single `cross-surface-reviewer`
spawn at `model: opus`, looped fix -> re-spawn until `NO-GAPS`. The duplicate
confirming pass is **retired**: it doubled the most expensive step and re-ran on every fix, for a
marginal catch rate that did not justify the bill. Independence -- the property that
actually mattered -- is preserved: a fresh subagent, no shared context, reading the
real diff.

**Only a BEHAVIORAL fix invalidates a clear.** After an Opus `NO-GAPS`, if you then
make a fix, ask: **does it change what the program does?**

- **Behavioral -> the clear is void.** Re-spawn. No exceptions; this is the whole gate.
- **Non-behavioral -> the clear STANDS.** Do NOT re-spawn. Covers: deferral
  bookkeeping (filing a bead, adding a bead ID to the journal or PR body), comment and
  docstring edits, `docs/`-only prose, journal entries, `.beads/` sync. Re-running a
  heavy Opus pass because you wrote a journal sentence is pure waste -- and the fear of
  it is what pushed reviewers to fix nits inline instead of filing them.
- **The tie-breaker is "does the program do anything different?"** -- not "did I touch
  a source file." A comment edit inside a `.py` file is non-behavioral. Changing a
  string another module parses is behavioral even if it looks like prose. When you
  genuinely cannot tell, treat it as behavioral -- but that is rare, and this carve-out
  is defeated if you claim it often.

**Spawn the `cross-surface-reviewer` agent** (`.claude/agents/cross-surface-reviewer.md`; it is already `model: opus`, so no override is needed). Its mandate is the blast radius, not the local diff. The prompt MUST (a) include the bead's `## Exit criteria` verbatim; (b) name the branch; (c) tell it to read the REAL LOCAL diff (`git diff origin/dev...HEAD`), never a summary; (d) NOT mention Haiku (it is the strong model -- there is no self-escalation clause in this agent); (e) **paste the inner reviewer's `## Changed contracts` block verbatim** -- that list is where it starts, so omitting it forces the expensive model to re-derive what the cheap one already produced. Read its STATUS line:

> **Spawn-failure fallback -- the effort-400 (added 2026-07-27). This applies to
> EVERY Agent-tool subagent spawn in closeout, at ANY model, at ANY step** -- the
> Step 5.5 fresh-eyes rounds (haiku/sonnet/opus alike), the Step 5.6 outer review,
> and the Step 6 `closeout-runner` handoff. If a spawn fails with
> `400 output_config.effort 'xhigh' is not supported
> when thinking is disabled on this model. Use effort 'high' or below, or enable
> thinking.` (or a functionally similar effort-unsupported 400), the spawn was
> killed by the SESSION's effort setting, which subagents inherit and which you
> cannot read.
>
> **This is a TRANSPORT failure, not a review failure.** It is NOT a `BLOCKED`
> verdict, it is NOT the "subagent ERROR / no verdict" case that escalates, and it
> does NOT justify downgrading the reviewer to a cheaper model. Do not surface it
> to the maintainer.
>
> Retry the SAME single spawn -- same agent, same prompt, same model -- wrapped in
> a **one-agent Workflow** whose `agent()` call passes `effort: 'high'` explicitly
> (the Workflow tool exposes an `effort` option the Agent tool lacks; verified
> working 2026-07-27). Read the returned verdict exactly as you would an inline
> STATUS line. **This authorizes a SINGLE-agent wrapper only** -- a transport
> workaround for one blocked spawn, not an opt-in to multi-agent orchestration,
> which still requires the maintainer's explicit go-ahead.
>
> **If the Workflow-wrapped retry ALSO fails, that IS a genuine stop** -- surface it
> to the maintainer. Never proceed to Step 6 without the outer review on a
> review-worthy change. Delete this whole fallback once the underlying bug is fixed
> upstream.

- **`NO-GAPS`** -> the outer review is CLEAN and **the gate is met** (the **adversarial clear**). **Go to Step 6** to open the PR + close the bead(s) + make the merge decision. If you make any further fix before Step 6, apply the behavioral test above: a behavioral fix voids this clear and re-spawns; a non-behavioral one does not.
- **`GAPS-FOUND (n)`** -> triage each finding by the rule below (pre-existing -> bead; blocker -> fix; true nit -> bead), commit, then **re-spawn the Opus review** on the updated local diff. This is the loop. Re-run the test suite (Step 4) after any code fix. (No push -- pre-PR.)
- **`BLOCKED` / a subagent TIMEOUT or ERROR (no verdict)** -> surface to the maintainer. A failure of the last-resort reviewer is a genuine stop (no further fallback, EXCEPT the effort-400 Workflow retry above -- take that first when the failure is an effort-unsupported 400, and surface only if it too fails), so this is the one branch that escalates. **Never** interpret a missing verdict as CLEAN.

### The nit-vs-blocker decision rule (bd polyglot-pdf-hrn.5)

The reviewer returns findings, but a subagent cannot reliably tell a nit from a blocker, so **the orchestrator makes that call.** For EACH finding, classify and act:

**This rule is stated ONCE, here, and governs Step 5.5's triage too** -- the inner
loop chasing a pre-existing finding expands the diff before the Opus pass ever runs,
which is the same churn one layer down.

- **PRE-EXISTING -> always a bead, never fixed here.** Clean checkable test first:
  does the finding reproduce **UNCHANGED on `origin/dev`**? Check it (`git show
  origin/dev:<path>`, or run the reproducing case against the base). If the defect is
  present at the base with no contribution from this diff, **file it as a bead** and
  move on -- regardless of severity. Fixing it here expands the diff, invalidates the
  review that just cleared, and buries the actual change. Do NOT ignore it either; an
  unfiled pre-existing finding is the thing this rule exists to stop. If the diff
  *worsens* a pre-existing defect, it is **not** pre-existing -- it is a finding.
- **Blocker -- fix now, then loop.** A finding that is, or might be, a correctness /
  security / data-loss / regression issue **in the behavior THIS DIFF introduces or
  changes**. **Ambiguity about the diff's own behavior counts as a blocker.** But
  scope the ambiguity test correctly: it asks *"am I unsure whether this diff behaves
  correctly?"* -- **not** *"can I imagine any edge case anywhere?"* Almost every
  finding has a conceivable edge; treating that as ambiguity swallows the entire nit
  category and is a leading cause of round count.
- **Non-blocking -- file a bead, do NOT fix inline.** A finding that **does not change
  behavior AND does not indicate the behavior is wrong.** Both halves required.
  Journal nits, doc nits, naming preferences, formatting: file them. **But a comment
  that contradicts its code is NOT a nit** -- it is evidence the CODE is wrong. Same
  for a name that contradicts what a function does, a docstring describing different
  behavior than the body, or a test whose name asserts something it does not check.
  The question is never "is it just a comment?" -- it is **"does this signal the
  behavior is wrong?"**
- **Never swept under the rug.** Every non-blocking and pre-existing finding gets
  **filed**. "Not a blocker" is a routing decision, not a dismissal. A finding you
  neither fixed nor filed is the one failure mode this rule does not tolerate.

**Deferred-nit bead convention.** File **one** bead per closeout collecting that change's true nits (not one bead per nit): title `chore(nits): deferred review nits from <bead-id>` (the review runs PRE-PR, so key the title on the bead being closed, not a PR number that does not exist yet), body listing each nit with its source (the review pass) + file:line. Create it with a pull/push-bracketed `bd create` (the same way Step 1 files deferred findings -- `bd_safe.py` has no `create` subcommand, so bracket the `bd create` directly). These deferred-nit beads are **prime candidates for a later multi-bead cleanup PR** (several tiny nit beads bundled into one closeout, per the bead/PR contract in CLAUDE.md).

**Loop-stop rule -- OUTCOME-based, no round cap (maintainer directive 2026-07-04).**
There is **no hard round ceiling** on the adopt-and-loop cycle. Because closeout can
now merge routine PRs autonomously, the bar is code quality, not iteration budget:
**keep looping as long as each round's findings are correct and are blockers.** A
lengthy back-and-forth to get the code right is expected and fine. You **STOP the
loop (it is CLEAN)** on a round when EVERY remaining finding is one of:
  - **incorrect** -- the finding is wrong, refuted, or a false positive (you verified
    it against the code; record the refutation so the maintainer can audit it);
  - **pre-existing** -- reproduces unchanged on `origin/dev`, so it is filed as a
    bead, not fixed here (per the rule above); or
  - **a true nit, not a blocker** -- real but non-blocking, better filed as a
    deferred-nit bead than fixed in this PR (per the nit-vs-blocker rule + the
    deferred-nit bead convention above).
If any finding is a correct blocker, **fix it and loop again** -- however many
rounds that takes. Do NOT stop because "it's been N rounds"; the only stop is "no
correct blocker remains." **One Opus review reaching CLEAN IS the gate** (the second
confirming pass is retired). (Ambiguous-about-this-diff's-behavior still counts as a
blocker -- keep looping. The escalation branch is a `BLOCKED`/TIMEOUT/ERROR from a
reviewer, or a gap you can neither fix nor honestly classify -- never a round count.)

**Escape hatch.** Setting `CLOSEOUT_LOOP_MODE=zero` disables nit-deferral for a run: do NOT defer nits to a bead; fix or explicitly reject every finding inline before looping. Same outcome-based loop-stop. Unset (the default) applies the nit-deferral rule above.

### Merge-conflict resolution (bd polyglot-pdf-hrn.6)

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

Keep the working tree clean between rounds (`git status --short`). Both loops run PRE-PR: fresh-eyes (Step 5.5, to `NO-GAPS`), then the ONE Opus outer cross-surface review (Step 5.6, to `NO-GAPS`). They do not interleave. The reviewers are subagents you read directly -- there is no bot watcher.

## Step 6 -- Open the PR, close the bead(s), and auto-merge or ping

Both reviews have now cleared on the LOCAL branch (Step 5.5 `NO-GAPS`, Step 5.6 `NO-GAPS`), or the review was skipped per the Step 5.6 gate. So the PR opens with review already done: **one `closeout_finish.py` run opens the PR AND closes the bead(s)** (the two-call watcher pattern is gone -- there was no bot to wait on). Then make the merge decision.

**There is NO trigger comment and NO watcher.** Do NOT put an `@codex review` line in the PR body, do NOT use the `requested_reviewers` reviewer API, and do NOT launch `pr_review_watcher.py` -- all retired dead path.

1. **Open the PR + close the bead(s) in one `closeout_finish.py` run** (or the raw commands if not delegating). The one run does everything mechanical: rebase, push, open the PR, and close the bead(s). The PR body is a **brief what-shipped summary + bead id(s)** plus the **`## Exit criteria` scorecard from Step 5.5.a** (each criterion PASS/FAIL with one-line evidence; note the review record matching the Step 5.6 fork -- "review record: Opus outer cross-surface review, NO-GAPS" for a source change, "review record: Haiku docs review, NO-GAPS" for a docs-only change, or "review record: fresh-eyes NO-GAPS, round <n>" for a trivial change with no adversarial review). Write the body ONCE -- Step 6.3 records the review outcome in the journal + merge ping, not the PR body, so do NOT add an empty placeholder section. The pre-push `git pull --rebase origin dev` may hit a conflict -- resolve it per "Merge-conflict resolution" above. The equivalent raw commands, if opening BY HAND:
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
2. **Decide the merge: auto-merge or ping** (autonomy increase 2026-07-04; CLAUDE.md "Auto-merge vs. maintainer merge"). Auto-merge requires ALL of: (a) an **adversarial reviewer cleared the diff** -- the Opus-5 outer cross-surface review gate (`NO-GAPS` on the final diff, Step 5.6); (b) CI / required checks green; (c) the PR is **not consequence-bearing**. Judge (c): does it prove the bead direction impossible / substantially change an approved plan / affect operational cost / affect user-facing features / risk downstream disruption / need substantial multi-surface rework? (Same line as the step-2 escalation triggers; when unsure, treat as consequence-bearing.)
   - **All three hold -> AUTO-MERGE.** Capture the exact head SHA the review + CI cleared (`HEAD_SHA="$(gh pr view <pr#> --json headRefOid -q .headRefOid)"`), confirm CI/required checks are green (`gh pr checks <pr#>`), then merge **pinned to that SHA**: `gh pr merge <pr#> --squash --match-head-commit "$HEAD_SHA"` (match the repo's merge style). The `--match-head-commit` guard makes the merge FAIL rather than silently merge an unreviewed head if anything pushed to the branch between the clear and the merge (the review-race). NEVER pass `--admin` (it bypasses the very checks gate condition (b) relies on; it is also settings-denied). Then post a SHORT plain-language note to the maintainer: what shipped + bead id(s), and the defended-decision list (below). This is a notification, not a request -- the merge is done. If the merge fails on the SHA match, a new commit landed -> re-review that commit before retrying, do NOT drop the guard.
   - **Any of the three fails -> PING, do not merge.** That includes: consequence-bearing; review NOT clean; checks red; **or a PR whose adversarial review was not the Opus cross-surface one** -- that is, a docs-only PR cleared by the Haiku `docs-reviewer`, or a trivial PR with no adversarial review at all. **Condition (a) currently means the OPUS gate specifically**, so neither is auto-merge-eligible even though both are low-risk; hand them to the maintainer. (Whether a Haiku-cleared docs PR *should* satisfy (a) is an open product/autonomy question for the maintainer -- bd polyglot-pdf-saxh deliberately did not decide it. Do not widen this on your own.) Also ping when you're simply unsure which side of the line the PR is on. Hand the maintainer a "clean and ready for your merge" summary and stop.
3. **Write the merge ping / notification.** Either way the summary is **for the product owner in plain language -- no jargon, no acronyms** (the maintainer's standing checkpoint AND the escalation-rule audit surface; see CLAUDE.md "Escalation vs. autonomy"). Include: what shipped + bead id(s), housekeeping result, doc/journal status, test result, fresh-eyes breakdown, the review outcome (**name the arm that actually ran** -- the Opus cross-surface review, the Haiku docs review, or none for a trivial change -- plus its round count and final `NO-GAPS`), the PR URL, and **whether you auto-merged or are handing it back**. **Then LIST each judgment call you made autonomously this PR -- INCLUDING the merge decision itself -- and briefly DEFEND it.** Make these easy to scan; this defended decision list is where the maintainer catches anything that was decided (or merged) but should have been escalated.

**Do NOT go back and rewrite the PR body after opening it.** The fresh-eyes triage breakdown and the outer-review round count already live in the **journal entry** (Step 3, the canonical chronological record) and the **merge ping** (Step 6.3, what the maintainer actually reads). Re-editing the PR description with `gh pr edit` is a **wasted model turn** generating prose for a surface nobody reads -- the initial `gh pr create --body` is the only body write. The durable record is the journal.

The PR is a normal, mergeable PR the moment it opens -- there is no flip step and no post-PR review wait. For a routine low-risk PR that reviewed CLEAN, **you merge it** (`gh pr merge`) and notify; for a consequence-bearing PR, pinging the maintainer is the autonomous endpoint. Force-push and `bd dolt push --force` are never yours regardless.
