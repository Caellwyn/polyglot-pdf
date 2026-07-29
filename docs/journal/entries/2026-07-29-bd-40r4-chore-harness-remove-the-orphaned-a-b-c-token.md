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
experiment closed** (`recorded_at > 2026-07-05`), the arm values are incoherent:
**115 `A`, 24 `C`, 20 `BC`, 1 `B`, and 20 unset**. Sessions were labeling themselves
with a baseline arm for a trial that had already concluded, and a ninth of them did
not bother at all.

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
`tests/test_doc_freshness.py`, which still exists.

**Full stack (both testpaths, `pytest -q -m "not external"` from the worktree):
2235 passed, 2 skipped, 3 deselected** -- that is 1323 from `backend/tests` plus
912 from `tests/`. The root `tests/` half is the one this change touches, and its
count **goes DOWN, 979 -> 912**, which reconciles exactly:
`979 - 65 (the whole test_harness_ledger.py file) - 31 + 29 (test_closeout_finish.py,
which loses the two obsolete telemetry classes but gains the 8 new guards) = 912`.
A shrinking suite is the expected shape when the thing under test is being removed;
the guards are what keep the removal from silently regressing.

**The review loop ran TEN rounds and caught 20 gaps** (1+1+3+4+1+3+3+1+2+1) --
**not one of them a functional code defect.** Every single finding was a dangling *instruction*, a stale
*comment*, a drifted *test fixture*, or a wrong *number in this entry*. That is the
characteristic failure mode of a removal like this: deleted code fails loudly and
immediately, but the prose that described it just quietly misleads the next reader,
and no test can see it. The rounds also show a clean severity gradient -- code and
config first, then comments, then documentation accuracy:

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
4. **Round 4 (Opus, re-clear):** four more --
   (a) a present-tense `.gitattributes` comment still claiming rows "are now
   written" per closeout;
   (b) the subprocess-seam banner in `closeout_finish.py` still reading
   "git/gh/bd/ledger" while its test-file counterpart had already been corrected;
   (c) this entry claimed the deleted test file had 49 tests -- it has **65**; the
   49 was carried over from hrn.17's entry, not counted from this file;
   (d) the R3(b) retention rationale said "any existing checkout" where the real,
   **measured** exposure is **18 worktrees** under `.claude/worktrees/` that still
   hold their own copy of the cache -- so the retained ignore rule protects 18
   future closeouts, not one.
5. **Round 5 (Opus, the clearing round):** all three exit criteria PASS, one
   finding -- **the arm-distribution figures in this entry were wrong and did not
   even sum to their own stated total** (100+20+15+1+20 = 156, against a claimed
   N=180). Recomputed from the rows: at the `recorded_at > 2026-07-05` cutoff that
   actually yields N=180, the distribution is **115 A / 24 C / 20 BC / 1 B / 20
   unset**. The qualitative dead-signal finding is unchanged; only the counts were
   wrong. Corrected above.
6. **Round 6 (Opus, the clearing round):** all three criteria PASS again, three
   findings -- (a) R5's figure correction had been applied to two places but
   **missed the Lessons bullet**, leaving the entry stating two different
   distributions for the same dataset; (b) the "Full stack: 1323 passed" claim was
   **the backend suite alone**, excluding `tests/` -- the only suite this change
   touches and where every new guard lives. Real full-stack figure: **2235 passed,
   2 skipped, 3 deselected** (1323 backend + 912 root); (c) `pick_review_model.py`
   -- a script closeout runs on every PR -- still said its threshold was "tunable
   later from the ledger's Haiku-escalation rate," pointing a future tuner at a
   deleted data source. All three fixed.
7. **Round 7 (Opus, the clearing round):** three findings, one of them the only
   remaining *criterion-2 failure* --
   (a) **`docs/doctrine/review-flow.md:119` still carried the A/B cost-accounting
   clause** that the diff had already scrubbed from its mirror at `SKILL.md:350`.
   That doctrine doc is the authority SKILL.md and CLAUDE.md both cite, so the two
   contradicted each other on the identical rule. Same R6c class: prose naming the
   retired subsystem with no removed identifier in it;
   (b) the "912 is up from 904 pre-change" claim was wrong in **both** the baseline
   and the direction -- measured on a clean `origin/dev` worktree, the pre-change
   root suite is **979**, and this PR makes it **shrink** to 912. Replaced with the
   exact reconciliation (`979 - 65 - 31 + 29 = 912`);
   (c) the "17 worktrees" figure printed next to its own reproduction command
   returns **18** when that command is run. Corrected in both places.
8. **Round 8 (Opus, the clearing round):** one finding, and the sharpest lesson of
   the loop -- **`pick_review_model.py`'s module docstring still called
   `CLAUDE_CODE_SUBAGENT_MODEL` "the A/B control arm (B-off)"** and pointed readers
   at the sprint plan's A/B toggling section, describing a counter this PR deletes.
   R6 had *already edited this very file* (line 79) but stopped at the one
   occurrence containing the word "ledger" -- so a second stale passage sat four
   lines from a line I had just rewritten. Fixed, along with a present-tense "the
   cost arm B exists to avoid" on line 24, after re-grepping the whole file for
   *every* experiment word (`arm`, `A/B`, `experiment`, `sprint plan`, `counter`)
   rather than the one term that first matched.
9. **Round 9 (Opus, the clearing round):** two findings, the first of which is this
   entry's own lesson biting back --
   (a) **`docs/doctrine/review-flow.md:224` still listed "ledger rows" as a live
   append-only merge-conflict class**, diverging from its mirror at `SKILL.md:483`,
   which lists journal entries / CHANGELOG / "Related" lists and no ledger. That is
   the *same defect class* as R7a, in the *same file*, one section below the clause
   R7 fixed -- caught by neither because each fix targeted the matched line rather
   than re-reading the file;
   (b) the tally in this very section said "16 gaps" while the rounds it enumerates
   summed to 17 -- failing the "make any multi-part count sum to its stated total"
   rule this entry prescribes two sections later. Now stated with the addends shown
   so the arithmetic is checkable at a glance.
10. **Round 10 (Opus, the clearing round):** all three exit criteria PASS. One
    finding, and it is the same bookkeeping defect one level deeper: **Round 4's
    bullet said "four more" but its prose enumerated only three**, because the
    fourth (the measured 18-worktree exposure) had been written as a trailing
    sentence reading like supplementary confirmation of R3(b) rather than as a
    counted finding. Re-labelled R4 as explicit (a)-(d). The lesson is that a
    stated-total-vs-enumerated-parts check has to run at **every** level of a
    nested list, not just the top: R9 fixed the outer tally, and the same defect
    was still sitting inside one of its addends.

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
  mislabeling, so the values drift incoherent (115/24/20/1/20-unset). A quick
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
  commit the dead cache. **Measured exposure here: 18 worktrees under
  `.claude/worktrees/` still hold a copy** (`find .claude/worktrees -maxdepth 3
  -name experiment_state.json | wc -l`), so the rule guards 18 future closeouts --
  do not delete it just because the main checkout looks clean. Delete the file;
  keep the ignore line. Generalizes to any gitignored derived artifact whose
  producer is being retired.
- **A grep-based removal sweep must cover every removed NAME, every file TYPE, and
  the PROSE that names the thing without using its identifier.** Four separate gaps
  came from one sweep being too narrow: `--haiku-escalations` (searched `--arm` and
  `telemetry`, not each flag by name); CLAUDE.md (never in the swept paths);
  `.gitattributes` (a dotfile matched by no `--include=*.ext` filter); and
  `pick_review_model.py`'s "the ledger's Haiku-escalation rate" (prose naming the
  subsystem without using any removed identifier -- invisible to an
  identifier-only grep). Sweep identifiers AND the plain-English name of what you
  deleted, include dotfiles, and state which paths the sweep actually ran over.
- **When a rule is DUPLICATED in a skill and its doctrine doc, fixing one is half a
  fix.** `SKILL.md` and `docs/doctrine/review-flow.md` deliberately mirror each
  other, and CLAUDE.md cites the doctrine doc as the authority -- so scrubbing the
  A/B clause from the skill while leaving it in the doctrine left the two
  contradicting each other on the identical rule, with the *authoritative* copy
  holding the stale text. After editing a rule in a skill, grep the doctrine docs
  for the same sentence (and vice versa).
- **Once a file is open for a stale-reference fix, re-sweep the WHOLE file.** This
  cost TWO separate rounds. R8 found a second stale passage in
  `pick_review_model.py` four lines from one already rewritten; R9 then found a
  second stale passage in `docs/doctrine/review-flow.md` one section below the
  clause R7 had fixed. Both were missed the same way: the fix targeted the line that
  matched the search term instead of re-reading the file for every way the retired
  thing gets named. **Fixing the grep hit is not the same as fixing the file** --
  after the first hit lands, re-grep that file for the full vocabulary (`arm`,
  `A/B`, `experiment`, `counter`, `ledger`, the plan it cites) before moving on.
- **Every figure in a journal entry must come from a command run against the
  artifact -- and the review loop should check the arithmetic.** THREE separate
  numeric/factual claims in this one entry were wrong on first writing: "49 tests"
  (carried over from the prior epic's entry; really 65), "CLAUDE.md never referenced
  the ledger" (written from a sweep that never covered CLAUDE.md), and the
  arm-distribution counts (which did not sum to their own stated total -- 156 vs a
  claimed 180). The prose was written from memory of the investigation rather than
  re-derived, and *supporting evidence for the change's core justification* is
  exactly where that is least acceptable. Cheapest guard: make any multi-part count
  sum to its stated total before writing it down -- **and run that check at every
  level of a nested list.** Round 9 fixed the outer tally (16 vs 17); round 10 then
  found the identical defect *inside* one of its addends (R4 said "four" and
  enumerated three). Fixing the total does not validate the parts.

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
- `docs/doctrine/review-flow.md` -- two fixes, both restoring parity with the
  `SKILL.md` mirror: struck the "or the A/B cost accounting" clause (line 119), and
  dropped "or ledger rows" from the append-only merge-conflict class (line 224),
  which now matches the skill's list of journal entries / CHANGELOG / "Related".
- `scripts/pick_review_model.py` -- COMMENT ONLY (arm B behavior untouched, verified
  by `git diff | grep -v '^[+-]#'` returning nothing): the threshold note no longer
  points a future tuner at the deleted ledger; the module docstring no longer frames
  `CLAUDE_CODE_SUBAGENT_MODEL` as "the A/B control arm (B-off)" of a running trial
  (now stated as the plain operational rule) and no longer cites the sprint plan's
  A/B toggling section, which describes a counter this PR deleted. The past-tense
  provenance lines ("bd polyglot-pdf-hrn.4 -- A/B arm B") are deliberately KEPT:
  they record which bead produced the script, and erasing lineage would be
  over-removal.
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
