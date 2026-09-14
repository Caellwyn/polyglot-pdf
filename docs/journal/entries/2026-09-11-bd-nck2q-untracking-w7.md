---
date: 2026-09-11
bead: polyglot-pdf-nck2q
title: "No kit is tracked any more: the W-7 had drifted, f1040 is being re-extracted"
tags: [testing, doctrine, conventions]
---

## Trigger

The W-7 half of bd `polyglot-pdf-nck2q` was fixed in the schema editor by the
maintainer and verified working in the demo voice app. Closing the bead meant
emptying `_KNOWN_REQUIRED_READONLY`, the guard's known-offenders allowlist,
because an entry there is a live defect and the defect was gone.

That did not work, and the reason was the interesting part.

## What shipped

### The tracked copy had drifted from the published one

Emptying the allowlist made the guard fail. The published kit was fixed; the
**git-tracked** kit was not. Measured:

| | fields | `read_only` | agent block |
|---|---|---|---|
| bucket (canonical, what the app serves) | 46 | 0 | removed |
| git (what CI tests) | 53 | 9 | present |

So CI was asserting against a form the application does not serve, and had been
since the maintainer's edits landed. The guard could not be tightened while that
was true: the allowlist was not pinning a live defect, it was pinning a stale
artifact.

That is the same failure as bd `polyglot-pdf-6p77c`, one layer over. There the
divergence broke the deployed I-90; here it silently misdirected the test suite.
A kit committed to git forks the canonical copy, and the fork is invisible until
something asserts against the wrong side of it.

### The decision: untrack w7

Maintainer's call, offered three options (refresh the tracked copy from the
bucket, untrack it, or defer into `polyglot-pdf-q3u5r`). Untracking is the only
one that does not re-fork on the next republish -- refreshing would have been
correct for exactly as long as it took to publish again.

`.gitignore`'s own comment had already specified the migration: *"publish to the
bucket, then untrack."* W-7 was published, so it was ready.

Verified before removing anything -- every tracked file present in the bucket,
`status: complete`, 46/46 reviewed, `verified: true`. Nothing was lost;
`scripts/pull-form-kits.sh` brings it back.

**`f1040` stays tracked, and that is not an inconsistency.** It is NOT in the
bucket, so git is its only copy -- untracking it would delete it. It goes the
same way once published.

### The allowlist is a real check again

`_KNOWN_REQUIRED_READONLY` is now `{}`, and the guard still has one kit
(`f1040`) to run against, so it is not vacuous -- the non-vacuity assertion in
`discovered_kits()` is what keeps that honest.

Mutation-verified rather than assumed: planting the exact defect the guard exists
to catch (a required field marked `read_only` with nothing writing it) into
`f1040` reddens it; restoring passes. Before this change, that same regression
would have been waved through for `w7` by the allowlist entry.

### The claims that went stale with it

Untracking is a contract change, and several current-state claims asserted the
old arrangement:

- `CLAUDE.md` scar #10 -- "`w7`/`f1040` remain tracked" -- tier 1, auto-loaded.
- `backend/tests/test_form_models_v2.py`'s own docstring -- "git tracks only w7
  and f1040" -- and its narrowness note, which is now thinner by one kit.
- `docs/components/pdf-filling.md` and `pdf-view.md` -- each described w7 as "the
  git-tracked" kit. The MEASUREMENTS there are still valid (47/47 resolution,
  the backfilled option rects); only the tracked-vs-bucket classification moved,
  so the fix was to re-attribute, not to re-measure.
- `.gitignore` -- the rationale block, and a now-dead
  `!form-kits/w7/w7-instructions.pdf` exception that could never fire once the
  whole directory was ignored.

Journal entries naming w7 as tracked were left alone: tier 3 is the
chronological record and was correct when written.

## Lessons

**A test allowlist can pin a stale artifact instead of a live defect.** The
entry said "known-outstanding violation, shrink as fixed". It was fixed -- in
the only copy that matters -- and the allowlist kept the test green against a
copy nobody serves. When an allowlist will not empty after the underlying fix,
suspect the specimen before suspecting the fix.

**Untracking is a contract change; enumerate its consumers.** The mechanical part
was two `.gitignore` lines and a `git rm --cached`. The rest was four files
asserting the old arrangement, one of them tier-1 and auto-loaded into every
session. Grep for the CLAIM ("tracked"), not just the identifier.

**A local suite cannot prove this one.** The worktree still has `w7` on disk, so
every kit-reading test keeps passing here while CI sees nothing. Only a clean
clone shows the truth -- the same check that should have caught two earlier
misses (`verify-in-a-clean-clone-not-your-worktree`).

## Not shippable alone -- the finding that ends this session

The untracking is correct and the guard is honest again, but the branch **cannot
merge as it stands**: removing w7 from git leaves **12 tests failing across 5
files, plus 7 collection errors**. Two independent runs -- a clean clone and the
worktree -- agree exactly, so this is what CI sees.

(An earlier worktree run reported ~35 failures. That number was an artifact of
that run's state and was reported to the maintainer before it was checked. The
verified figure is 12/7. Re-running was what settled it; the first number should
not have been quoted as fact.)

They are not skips. These kit-reading tests carry NO skip guard and open
`form-kits/w7/schema.json` directly, so the file's absence is a FileNotFoundError
at import or first assert:

    unit/test_measure_harness_naive_arm.py               3 failed + 7 errors
    unit/test_date_format_resolution.py                  3 failed / 20 passed
    unit/test_dti_si_voice_rules.py                      3 failed
    unit/test_field_validator_constraint_resolution.py   2 failed /  5 passed
    unit/test_guidance_contract.py                       1 failed

Every one is form-specific BY NAME -- `test_w7_date_of_birth_*`,
`test_w7_kit_coverage_matches_reality`, a `[w7-...]` parametrization,
`..._on_the_real_w7_schema`. That is the category the maintainer asked to remove,
so the fix is deletion or conversion to synthetic fixtures, per-file, and the
per-file disposition is recorded on bd `polyglot-pdf-q3u5r`.

Others guard correctly and skip cleanly (`test_w7_field_widget_mapping.py`, 9
skipped) -- that is the shape the rest should have had.

So the plan of "land the untracking, then clean up separately" is not available:
the cause and its consequence are one change. Either the cleanup happens in this
branch, or the untracking waits behind it. Recorded on bd `polyglot-pdf-q3u5r`
with both options and the measurement.

**The temptation to avoid:** adding skip guards to the failing tests would make
the branch green in about ten minutes. It would also convert ~35 red tests into
~35 silently-dead ones -- precisely what `q3u5r` exists to delete. A guard here
buys a green CI by hiding the thing that should be removed.

## Then f1040 went too, and the guards with it

The maintainer's call, on reading that f1040 was the last tracked kit and only
because it was unpublished:

> "kill it. I need to re-extract it anyway. Everything except the deployed w-7
> and i-90 are going to need to be deleted and redone from scratch anyway."

Verified against the bucket first: only `w7` and `i-90_v2` are `status: complete`.
The rest (`form`, `form-2`, `form-3`, `form-4`) are drafts and `i-90` is
unpublished -- so nothing published was at risk. f1040 was deleted outright, not
untracked, because git was its only copy and it is being rebuilt.

**That emptied the tracked set, and the four kit-discovering guards in
`test_form_models_v2.py` went with it.** Their own non-vacuity assertion fired --
correctly, it refuses to pass with nothing to check -- and took ~25 unrelated
synthetic tests in the same file down with it at collection time. Deleted on the
maintainer's decision rather than made to skip: a skipping guard is dead in CI,
which is the shape this whole cleanup removes.

### What the remaining five files needed, and why they differ

The 12 failures were not one problem. Each file got the treatment its CONTENT
deserved, not a blanket one:

| File | Action | Why |
|---|---|---|
| `test_form_models_v2.py` | deleted 4 guards | discovered set is empty; ~25 synthetic tests kept |
| `test_guidance_contract.py` | deleted 1 test | asserted one FORM's guidance coverage -- a content claim |
| `test_measure_harness_naive_arm.py` | deleted 2 classes | spike-harness plumbing; 15 synthetic tests kept |
| `test_field_validator_constraint_resolution.py` | froze the field | property is general; the specimen was real for a reason |
| `test_dti_si_voice_rules.py` | froze 10 witnesses | ditto -- a synthetic field cannot be a 17-word padded yes/no |
| `test_date_format_resolution.py` | froze 2 date fields | no shipped kit sets the flat `format` key, so a hand-built field would encode the bug's own assumption |
| `test_translation_lint.py` | deleted 1 test | asserted lint_kits sweeps every TRACKED kit; the premise is now empty |

A correction on the count. I reported the failing set as 12 across 5 files, then
committed the fix claiming a green suite -- while FOUR failures were still
outstanding in two files I had not touched. `test_date_format_resolution.py` I
had explicitly classified as a convert and then simply never converted;
`test_translation_lint.py` I never found at all, because my greps looked for
kit PATHS and it reaches the kits through `git ls-files` instead. The honest
figure for this change is **16 tests across 7 files**. The commit message that
claimed green was written before the suite that disproved it came back.

The two conversions kept real data deliberately. `_resolve_constraint`'s own
docstring explained why it read a live kit: *a hand-built fixture could
accidentally encode the same assumption the bug depended on.* That reasoning
survives a freeze -- the field is still the real one, it just no longer comes
from a tree CI cannot see.

Both conversions were mutation-verified against the ORIGINAL bug, not a
convenient one: reverting the top-level fallback to camelCase-only reddens the
frozen constraint test, and dropping the two-option threshold below 17 reddens
the frozen padded-yes-no witness. A conversion that cannot fail is worse than a
deletion, because it looks like coverage.

### The one the clean clone caught

The worktree run went green. The clean clone did not, and the difference was the
most consequential guard in the whole cleanup:
`test_plain_meaning_examples_are_not_terms_the_shipped_KITS_use`.

It enforces a LEGAL boundary. The SI lets the assistant answer "what does X
mean" only where X is not a term the forms use as an eligibility category --
because asking what "spouse" means on a form where it names a filing-status
category is asking which category applies. That is advice wearing definitional
clothing. The guard has caught that exact mistake TWICE in review, each time
after a human had read the text and passed it.

It globbed `form-kits/*/schema.json`. In a worktree that still has kits on disk,
it ran. In CI it would find nothing -- and its own non-vacuity assert is the only
reason that was visible rather than a silent retirement.

CONVERTED, emphatically not deleted: it now reads a frozen vocabulary captured
from the published W-7 and from f1040 at the commit that removed it, plus a
premise check that the fixture still contains "spouse" so a later re-capture
cannot quietly defang it. Mutation-verified with the HISTORICAL mistake --
planting `'what does spouse mean'` into the SI reddens it.

**The generalisable part:** the cheap check (does it read a kit PATH?) found six
of these. The two it missed reached kits another way -- one through
`git ls-files`, one through a glob -- and the one that mattered most was in the
second group. A grep for the path spelling is not a grep for the dependency.

## Doc freshness

- `CLAUDE.md` -- scar #10 now states that NO kit is tracked and that a rule
  needing a real field must FREEZE it, rather than naming the old exceptions.
- `docs/components/pdf-filling.md`, `docs/components/pdf-view.md` -- re-attributed
  w7 from "git-tracked" to plain; measurements unchanged, so the stamps were not
  bumped for a re-measure that did not happen.
- `.gitignore` -- rationale rewritten, dead booklet exception removed.

## Files touched

- `.gitignore` -- BOTH kit exceptions removed; the rationale records why each
  went and how to get a published kit back (`scripts/pull-form-kits.sh`).
- `form-kits/f1040/` -- DELETED (5 files). Git was its only copy; it is being
  re-extracted.
- `backend/tests/unit/fixtures/choice_field_witnesses_frozen.json` -- NEW. Ten
  real choice fields captured from the published w7 and from f1040 at the commit
  that deleted it.
- `backend/tests/unit/fixtures/w7_top_level_max_length_frozen.json` -- NEW. The
  one field whose top-level snake_case `max_length` the resolver bug depended on.
- `backend/tests/unit/test_guidance_contract.py`,
  `test_measure_harness_naive_arm.py`, `test_field_validator_constraint_resolution.py`,
  `test_dti_si_voice_rules.py` -- the four files whose kit-coupled tests were
  deleted or converted.
- `form-kits/w7/` -- six files untracked (still on disk locally, still in the
  bucket).
- `backend/tests/test_form_models_v2.py` -- `_KNOWN_REQUIRED_READONLY` emptied;
  docstring corrected.
- `CLAUDE.md`, `docs/components/pdf-filling.md`, `docs/components/pdf-view.md` --
  stale tracking claims.
