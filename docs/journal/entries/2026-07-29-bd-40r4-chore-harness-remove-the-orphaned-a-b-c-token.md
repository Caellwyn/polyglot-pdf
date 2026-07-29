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
- `scripts/harness_ledger.py` (972 lines) and `tests/test_harness_ledger.py` (49 tests).
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
- `.beads/experiment_state.json` (the derived cache) and its `.gitignore` entry.

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

## Doc freshness

`closeout_prep.py` flagged **20** stale `docs/components/` and `docs/standards/` docs.
**All are unrelated to this PR** -- each is stale against `backend/` / `frontend/`
files modified by other work between 2026-07-12 and 2026-07-27, none of which this
change touches (this diff is harness scripts, the closeout skill/agent, settings,
`.gitignore`, and two journal READMEs). Reviewed and left as-is; reconciling them is
not this bead's scope.

The two docs this change *does* affect -- `docs/journal/README.md` and
`docs/journal/telemetry/README.md` -- were updated in this PR to describe the
telemetry as a closed archive. No tier-1/tier-2 component or standard doc changed,
and no CLAUDE.md change was needed (CLAUDE.md never referenced the ledger).
`docs/sprint_1_harness-tuning_plan.md` was deliberately left untouched: it is the
plan of record for roadmap epic `polyglot-pdf-h2r`, which is still open, and it is a
historical planning document rather than per-session overhead.

## Files touched

- `scripts/harness_ledger.py` -- DELETED (972 lines).
- `tests/test_harness_ledger.py` -- DELETED (983 lines, 49 tests).
- `scripts/closeout_finish.py` -- removed both telemetry steps, the seven counter
  flags, the `telemetry` output key, and the dry-run ledger preview; docstring
  rewritten (Steps 5-7 -> Steps 5-6).
- `.claude/skills/closeout/SKILL.md` -- Step 7 removed in full; A/B arm scaffolding
  stripped from Steps 5.5.b / 5.6 and the merge-conflict + nit-rule headings.
- `.claude/agents/closeout-runner.md` -- counter contract, invocation flags,
  `telemetry: GAP` clause, and frontmatter description updated.
- `.claude/settings.json` -- three `harness_ledger.py` permission entries removed.
- `.gitignore` -- `.beads/experiment_state.json` entry + its comment removed.
- `docs/journal/README.md`, `docs/journal/telemetry/README.md` -- rewritten as a
  closed archive.
- `tests/test_closeout_finish.py` -- two obsolete classes removed; dry-run test
  strengthened to zero-subprocess-calls; `--close-only` tests renamed.
- `tests/test_pick_review_model.py`, `tests/test_schema_score_section_grouping.py` --
  idiom comment repointed off the deleted test file.
- `docs/journal/entries/2026-07-29-bd-40r4-...md` -- this entry.
