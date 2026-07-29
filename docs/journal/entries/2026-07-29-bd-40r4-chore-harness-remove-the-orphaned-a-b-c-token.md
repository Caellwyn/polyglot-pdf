---
date: 2026-07-29
bead: polyglot-pdf-40r4
title: "chore(harness): remove the orphaned A/B/C token-cost ledger from the closeout path"
sprint: 1
tags: [harness, refactor, testing]
---

## Trigger

The maintainer asked whether the token-counting harness, the A/B/C trials, and the
ledger updates were still running on every session -- believing the epic that spawned
them had completed -- and, if they were orphaned, to remove them to save the token
overhead.

The belief was correct. Epic `polyglot-pdf-hrn` (sprint-1 harness tuning, plan of
record `docs/sprint_1_harness-tuning_plan.md` Change #1) closed 2026-07-05 at 19/19,
with an explicit closing comment: "The sprint-1 harness-tuning experiment is
concluded." Its final child (hrn.17) wrote `docs/journal/telemetry/FINAL_REPORT.md`
and committed a `REPORT_DONE` sentinel to switch off the per-closeout "write the
report" nag.

But only the *nag* was switched off. The **row-writing itself kept running on every
closeout**: `closeout_finish.py` invoked `harness_ledger.py`, then committed and
pushed a telemetry row, while closeout `SKILL.md` Step 7 (plus the arm notes in
Steps 5.5.b / 5.6) cost orchestrator tokens on every PR to supply counters -- chief
among them an `--arm` label that **nothing read**.

## What shipped

**The dead-signal finding.** A repo-wide grep confirmed the `arm` field had no
consumer: outside `harness_ledger.py` writing it, no script read it. The one thing
that had acted on it -- `phase_directive()` -- was permanently short-circuited by the
committed `REPORT_DONE` sentinel (running `--print-directive` returns "experiment
CLOSED").

The labels had also decayed into noise. Across the **180 rows written after the
experiment closed**, the arm values are incoherent: 100 `A`, 20 `BC`, 15 `C`, 1 `B`,
and 20 unset. Sessions were labeling themselves with a baseline arm for a trial that
had already concluded, and a ninth of them did not bother at all.

**Removed:**
- `scripts/harness_ledger.py` (972 lines) and `tests/test_harness_ledger.py`
  (983 lines, 65 test functions).
- `closeout_finish.py`: the `telemetry()` and `commit_push_telemetry()` steps, the
  seven counter flags (`--arm`, `--cost-category`, `--copilot-rounds`,
  `--maintainer-touchpoints`, `--deferred-nits`, `--haiku-escalations`,
  `--errors-shipped`), the `telemetry` output key, and the dry-run ledger preview.
- closeout `SKILL.md`: Step 7 in full, plus the A/B arm scaffolding threaded through
  Steps 5.5.b / 5.6 and the `CLOSEOUT_LOOP_MODE` control-arm block (**73 lines /
  ~1000 words off the per-closeout read** -- 611 -> 538 lines).
- `.claude/agents/closeout-runner.md`: the counter contract in the brief, the
  invocation flags, the `telemetry: GAP` warn-only clause, and the frontmatter
  description (which loads into every session's agent roster).
- `.claude/settings.json`: the three `harness_ledger.py` permission entries.
- `.beads/experiment_state.json` (the derived cache), deleted from the main
  checkout as well as the worktree. Its `.gitignore` rule was **deliberately kept**
  -- see the review-loop note below.
- `scripts/closeout_finish.py`'s `_utcnow()` helper and its `datetime`/`timezone`
  imports: its only call site was the deleted `--recorded-at` ledger argument.

**Kept, as a read-only archive** (maintainer's explicit call): all **376** telemetry
row files, `harness_ledger.jsonl` (the pre-2026-06-10 archive), `FINAL_REPORT.md`,
and the `REPORT_DONE` sentinel. Both telemetry READMEs were rewritten to say the
system is a **closed archive** rather than "live" -- the previous wording would have
misled the next reader into thinking rows were still accruing.

**Deliberately NOT removed: the adopted behaviors.** Arm B (the `pick_review_model.py`
diff-size router) and arm C (the nit-deferral rule) were the experiment's *winners* --
`FINAL_REPORT.md`'s verdict was to adopt BC as the standing default. They are
load-bearing review behavior now, not scaffolding. Only their experiment labelling
and counting was stripped. Removing them would have silently changed how every future
review runs, far beyond "delete the dead experiment."

**A safety property got stronger.** `closeout_finish.py --dry-run` now makes **ZERO**
subprocess calls. The only call it ever made was the ledger's own `--dry-run`
preview; with the ledger gone, the plan is printed entirely from in-memory labels.
`TestDryRun::test_no_mutating_calls` was rewritten from "the only allowed subprocess
is the ledger's" to the strictly stronger `assert rec.calls == []`.

**Tests:** two obsolete classes (`TestTelemetryWarnOnly`, `TestTelemetryCommitPush`)
deleted; the two surviving `--close-only` tests renamed and re-commented off the
now-gone double-count rationale onto what they actually pin (close-only closes the
bead and does nothing else). Two unrelated test files referenced
`tests/test_harness_ledger.py` as the module-loading idiom example -- repointed at
`tests/test_doc_freshness.py`, which still exists. Full stack: **1323 passed, 1
skipped, 3 deselected**.

**The review loop caught three real gaps across three rounds** -- all of them
dangling *instructions or fixtures* rather than broken code, which is the
characteristic failure mode of a removal like this (the code stops working loudly;
the stale instruction just quietly misleads the next reader):

1. **Round 1 (Sonnet):** the `_args()` test fixture still fabricated the seven
   removed counter fields, asserting a shape `build_parser()` could no longer
   produce. Fixed, plus two new guards -- `test_retired_telemetry_flags_rejected`
   (all seven flags must now fail to parse) and
   `test_args_fixture_matches_real_cli_shape` (the fixture may only invent
   attributes the real CLI produces). The latter was **mutation-tested** by
   reintroducing `arm="A"` and confirming it fails.
2. **Round 2 (Sonnet):** a surviving "count it for `--haiku-escalations`" in
   SKILL.md Step 5.5's `BLOCKED` branch. Four sibling mentions had been scrubbed;
   this one survived because the sweep grepped `--arm`/`telemetry` but not each
   removed flag *by name*. Re-swept all seven names across every live surface.
3. **Round 3 (Opus, the clearing round):** three more --
   (a) `CLAUDE.md` still named "telemetry setup" (above);
   (b) **deleting the `.beads/experiment_state.json` ignore rule would have wedged
   the next closeout.** The cache file still existed on disk, so un-ignoring it
   would surface it as untracked, and `closeout_prep.py` turns any
   `git status --short` output into `working tree is DIRTY (commit or stash before
   closeout)` -- blocking Step 0 on a phantom file, and inviting a `git add -A`
   reflex to commit the dead cache. Resolved by deleting the stale file *and*
   **keeping the ignore rule**;
   (c) the now-dead `_utcnow()` helper.
4. **Round 4 (Opus, re-clear):** four more -- a present-tense `.gitattributes`
   comment still claiming rows "are now written" per closeout; the
   subprocess-seam banner in `closeout_finish.py` still reading "git/gh/bd/ledger"
   while its test-file counterpart had already been corrected; and two journal
   inaccuracies (this entry claimed the deleted test file had 49 tests -- it has
   **65**; the 49 was carried over from hrn.17's entry, not counted from this
   file). Round 4 also **measured the real blast radius of (b)**: not just the main
   checkout but **17 worktrees** under `.claude/worktrees/` still hold their own
   copy of the cache, so the retained ignore rule protects 17 future closeouts,
   not one.

## Lessons

- **Switching off an experiment's *output* is not the same as retiring the
  experiment.** hrn.17 correctly killed the "write the report" directive with a
  sentinel, and everyone (including the epic's closing comment) read that as the
  experiment being closed. But the data-collection limb kept running for three more
  weeks and 180 rows. When concluding a measurement epic, the exit criteria should
  cover *stopping collection*, not just *stopping the prompt* -- otherwise the harness
  keeps paying for a signal with no consumer.
- **An orphaned field announces itself in the data.** The tell was not the code, it
  was the label distribution: once a counter has no consumer, nothing corrects
  mislabeling, so the values drift incoherent (100/20/15/1/20-unset). A quick
  distribution check over recent rows is a cheap way to test whether a telemetry
  field is still real.
- **When deleting experiment scaffolding, separate the scaffolding from what the
  experiment adopted.** "Remove the A/B/C trials" could have been read as removing
  arms B and C themselves; the report's verdict is what disambiguates it. Read the
  experiment's conclusion before deleting its apparatus.
- **Do NOT remove a `.gitignore` rule for a derived cache just because the writer
  is gone.** The rule is what keeps an already-existing copy invisible on every
  checkout that has one. Deleting it converts a harmless leftover file into an
  untracked entry, which `closeout_prep.py` reports as a DIRTY working tree --
  blocking the next closeout on a phantom, and inviting a `git add -A` reflex to
  commit the dead cache. **Measured exposure here: 17 worktrees under
  `.claude/worktrees/` still hold a copy** (`find .claude/worktrees -maxdepth 3
  -name experiment_state.json | wc -l`), so the rule guards 17 future closeouts --
  do not delete it just because the main checkout looks clean. Delete the file;
  keep the ignore line. Generalizes to any gitignored derived artifact whose
  producer is being retired.
- **A grep-based removal sweep must enumerate every removed NAME, and every file
  TYPE.** Gaps survived a sweep that searched `--arm`/`telemetry` but not
  `--haiku-escalations`; a claim about CLAUDE.md was written from a sweep that never
  covered CLAUDE.md; and `.gitattributes` (a dotfile matched by no `--include=*.ext`
  filter) kept describing the deleted system in the present tense. Enumerate the
  identifiers, include dotfiles, and state which paths the sweep actually ran over.
- **Numbers copied from a neighbouring doc are not verified numbers.** This entry's
  "49 tests" was carried over from the prior epic's journal entry rather than
  counted from the file being deleted (the real count is 65). If a figure appears in
  a journal entry, it should come from a command run against the artifact.

## Doc freshness

`closeout_prep.py` flagged **20** stale `docs/components/` and `docs/standards/` docs.
**All are unrelated to this PR** -- each is stale against `backend/` / `frontend/`
files modified by other work between 2026-07-12 and 2026-07-27, none of which this
change touches (this diff is harness scripts, the closeout skill/agent, settings,
`.gitignore`, and two journal READMEs). Reviewed and left as-is; reconciling them is
not this bead's scope.

The docs this change *does* affect were updated in this PR: `docs/journal/README.md`
and `docs/journal/telemetry/README.md` now describe the telemetry as a closed
archive, and **`CLAUDE.md`** had one surviving mention -- the `/closeout` OWNS PR
creation bullet warned that a hand-opened PR "breaks the skill's review + telemetry
setup," which named a subsystem that no longer exists. Struck to "review setup."
(An earlier draft of this entry claimed CLAUDE.md never referenced the ledger; that
was wrong -- the sweep behind it had not covered CLAUDE.md, and the Opus clearing
round caught it.) No tier-2 component or standard doc changed.
`docs/sprint_1_harness-tuning_plan.md` was deliberately left untouched: it is the
plan of record for roadmap epic `polyglot-pdf-h2r`, which is still open, and it is a
historical planning document rather than per-session overhead.

## Files touched

- `scripts/harness_ledger.py` -- DELETED (972 lines).
- `tests/test_harness_ledger.py` -- DELETED (983 lines, 65 test functions).
- `scripts/closeout_finish.py` -- removed both telemetry steps, the seven counter
  flags, the `telemetry` output key, the dry-run ledger preview, and the dead
  `_utcnow()` helper + its `datetime`/`timezone` imports; docstring rewritten
  (Steps 5-7 -> Steps 5-6).
- `CLAUDE.md` -- struck "+ telemetry" from the `/closeout` OWNS PR creation bullet.
- `.gitattributes` -- comment rewritten from the present tense ("rows are now
  written per closeout") to describe a retired system. The
  `docs/journal/harness_ledger.jsonl merge=union` driver line is KEPT: it still
  governs merges of the retained archive.
- `.claude/skills/closeout/SKILL.md` -- Step 7 removed in full; A/B arm scaffolding
  stripped from Steps 5.5.b / 5.6 and the merge-conflict + nit-rule headings.
- `.claude/agents/closeout-runner.md` -- counter contract, invocation flags,
  `telemetry: GAP` clause, and frontmatter description updated.
- `.claude/settings.json` -- three `harness_ledger.py` permission entries removed.
- `.gitignore` -- `.beads/experiment_state.json` rule KEPT (comment rewritten to
  explain why it outlives the ledger); the cache file itself deleted from both the
  worktree and the main checkout.
- `docs/journal/README.md`, `docs/journal/telemetry/README.md` -- rewritten as a
  closed archive.
- `tests/test_closeout_finish.py` -- two obsolete classes removed; dry-run test
  strengthened to zero-subprocess-calls; `--close-only` tests renamed.
- `tests/test_pick_review_model.py`, `tests/test_schema_score_section_grouping.py` --
  idiom comment repointed off the deleted test file.
- `docs/journal/entries/2026-07-29-bd-40r4-...md` -- this entry.
