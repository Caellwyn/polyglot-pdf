---
date: 2026-09-14
bead: polyglot-pdf-f3svv
title: "fix(closeout): defend the suite-gate ceiling by measurement, not a frozen literal (with bd polyglot-pdf-i1hej)"
tags: [testing, harness, review]
---

## Trigger

Two beads filed by the Opus cross-surface reviewer during bd polyglot-pdf-u98r1's
closeout, both about the same constants in the same three files:

- **f3svv** -- the suite-gate ceiling was justified by a hardcoded "measured
  runtime" (706s at 4494 collected tests, recorded 2026-09-03), and both guards
  asserted the ceiling against that literal. Neither side of either comparison
  observes anything, so the suite could grow until the real gate timed out again
  while both guards stayed green.
- **i1hej** -- the same ceiling and the same TimeoutExpired-arm ordering were
  pinned TWICE, in two files, by two techniques, with two different numeric
  thresholds (>= 1200 and >= 2*706).

Bundled into one PR deliberately. f3svv's body says "treat them as ONE set
(CLAUDE.md scar #8)" and i1hej's says "Coordinate with bd polyglot-pdf-f3svv,
which may change what the threshold should be derived from." Doing i1hej alone
would have consolidated the duplicate thresholds and then immediately re-edited
the same lines to change what they derive from.

The staleness was not theoretical. The baseline said 4494 tests; the suite
collected 6017 on 2026-09-12 and 6127 two days later -- 1.36x growth in eleven
days, with every guard green throughout.

## What shipped

**The ceiling is now defended by measurement.** `check_tests` times its own run
(`time.monotonic` around `subprocess.run`) and appends a margin note to the
summary when a run consumes more than `_TESTS_MARGIN_WARN_FRACTION` (0.5) of
`_TESTS_TIMEOUT_S`. That signal moves with the suite: a slower machine or a few
hundred new tests shift it, where a literal stays put. It rides the existing
summary line rather than a new result field no consumer knows to read.

Worth noting how portable the old literal was NOT: the same suite measured 597s
on one machine and 399s on another, against a "706s" baseline. Any assertion
built on that number was machine-specific from birth.

**The duplicate pins were consolidated.** The two files now own distinct
concerns, each stated in its own docstring:

- `test_closeout_prep.py` owns the ceiling and its margin, behaviourally,
  against the imported module.
- `test_every_suite_root_is_gated.py` keeps only what a source read uniquely
  covers -- that the ceiling is a named constant actually passed to
  `subprocess.run`. A behavioural test stubs `subprocess.run` and so can never
  see which timeout the real call was handed.

Zero numeric threshold assertions remain in `tests/`. The surviving 706/4494
mentions are prose explaining why the literal approach failed.

**Verified end-to-end, not just by unit test:** a real `closeout_prep` run went
green through the modified gate (6017 passed, 0 failed, 399.73s) and the margin
note correctly stayed silent, 399s being well under the 900s budget.

**Review: four inner rounds, one outer.** Every inner round found a real defect
in code I had added in the previous round -- see Lessons. The outer Opus pass
returned NO-GAPS and filed one finding of its own,
`polyglot-pdf-xkfy6`: the margin note is invisible on the DELEGATED closeout
path, because `.claude/agents/closeout-runner.md` relays the prep TODO only on
ATTENTION and proceeds silently on READY. A warning riding an OK verdict is
therefore swallowed whenever prep is delegated -- which SKILL.md explicitly
sanctions. Correctly filed rather than fixed here: the defect is in a `.claude/`
file this diff does not touch and reproduces on `dev`. But it caps the
mechanism's reach today, and that belongs in the honest record.

## Lessons

**Three consecutive review rounds found the same defect class in my own new
code: an assertion that cannot distinguish fixed from broken.**

1. Round 1 flagged that the note quoted the warn THRESHOLD, so a 51%-of-ceiling
   run and a 99% one both read "over 50%" -- the text never intensified as the
   run approached the cliff it exists to warn about.
2. My fix used `{:.0%}`, which rounds to NEAREST, so every run from 900s to 909s
   printed "50% of the ceiling" while the warning only exists because the run
   passed 50%. The message contradicted its own trigger at exactly the moment a
   reader first sees it.
3. The boundary test I then wrote asserted `"50.0%" not in note` -- vacuous,
   because the regression renders "50%" with no decimal point. It passed on the
   exact bug its own docstring named. It only looked covered because a sibling
   test, probing values outside the dead zone, incidentally failed too.

The third is the instructive one. **Banning a string is one spelling away from
defeat.** The fix was to assert positively: parse the percentage actually
printed and require it to exceed the threshold that triggered the warning. That
states the property, so no re-spelling of the wrong answer evades it --
mutation-verified in isolation with `-k boundary` so no sibling test could
assist.

The generalizable check, before trusting any assertion: **name the concrete
input on which fixed and broken outputs DIFFER, and confirm the assertion sees
that difference.** All three defects fail it in one sentence.

**`git checkout <file>` restores from the INDEX, so it discards uncommitted
work.** Mid-mutation-run it reverted every uncommitted production edit -- the
helper, the constant, the docstring -- back to `dev`. My test edits survived
(different files), so the suite still ran and the next three mutations reported
"anchor not found" rather than a false pass. The harness asserting its anchors
is what turned a silent wrong answer into a loud one. Commit before mutating, or
restore from a copy outside the tree; this repo's `mutation-restore-can-revert-real-edits`
memory says exactly that and I re-learned it anyway.

**A guard deletion needs its replacement proved, not assumed.** Removing the
source-text arm-ordering pin was correct only because the behavioural test
covers it -- and the round-1 reviewer verified that by constructing the
arm-swap mutation itself rather than taking my word. That is the check worth
copying whenever a consolidation deletes a guard.

## Doc freshness

`check_doc_freshness.py` flagged 25 tier-2 docs STALE. **None tracks any file
this branch touches** -- every one is driven by `backend/`, `frontend/`, or
`deploy-*.sh` changes from other PRs, and all reproduce on `origin/dev`.
Reviewed and left; no stamps bumped.

Checked specifically for claims this diff could falsify: no doc anywhere states
the ceiling, the measured runtime, or the removed test names (the only repo-wide
`1800` hit is an unrelated birthdate example in an archived doc), and
`docs/standards/testing.md:66`'s claim that `check_tests` runs a bare `pytest`
remains true. No tier-1/2 doc carries a `**Tracks:**` glob covering
`scripts/closeout_prep.py`.

## Files touched

- `scripts/closeout_prep.py` -- `_timeout_margin_note` helper, the
  `_TESTS_MARGIN_WARN_FRACTION` constant, wall-clock timing around the suite
  run, and a rewritten constant block/docstring replacing the stale-literal
  rationale. New `import math`, `import time`.
- `tests/test_closeout_prep.py` -- five behavioural margin tests replacing the
  frozen-literal headroom assertion, plus a `_run_at` helper that advances a
  fake clock so a simulated 900s run costs no wall time.
- `tests/test_every_suite_root_is_gated.py` -- two source-text guards reduced to
  one, scoped to the concern only a source read covers; the import orphaned by
  that deletion removed.
