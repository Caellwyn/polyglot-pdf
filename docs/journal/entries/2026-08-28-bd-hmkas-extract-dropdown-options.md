---
date: 2026-08-28
bead: polyglot-pdf-hmkas
title: "fix(extractor): dropdown options were never extracted -- the model was shown 12 of 63 choices and asked for the other 51"
tags: [extractor, testing, review]
---

## Trigger

The maintainer asked why the i-90_v2 extraction produced `type: "select"` fields
with no options at all, having just hand-built all 143 option values across four
state and two height dropdowns.

## What was wrong -- three compounding causes

All three were deterministic-data problems. The acroform dump already held the
exact, complete, correct answer.

**1. The choice list was truncated to 12, silently.** Both prompt builders
capped it identically (`schema_contract.py`, `structural_enrich.py`), so for
`P1_Line6e_State[0]` the model literally saw:

    choices=[ ,AA,AE,AK,AL,AP,AR,AS,AZ,CA,CO,CT]

51 of 63 dropped, with no marker -- the model could not even tell the list had
been cut. Asked to emit a complete 62-item set from a 12-item sample, emitting
nothing was arguably its best move; the alternative was inventing the rest.

**2. The contract asked for the wrong thing.** CHOICE-FIELD RULES said
`option.value` MUST be a semantic slug minted from the label. Right for
radio/checkbox_group, which carry widget identity in `pdf_field_name` /
`pdf_on_value`; wrong for a select, whose value goes VERBATIM into the combobox.
The older i-90 shows the result: 50 options valued `alabama`, `alaska`, ...
against a PDF that accepts only `AL`, `AK`. Those fields print clipped today.

**3. Nothing deterministically copied the list.** `structural_enrich` only
renders choices INTO THE PROMPT (truncated), and is not wired into
`extract_form` at all. Meanwhile `_backfill_positions` -- a few hundred lines
up, for rects -- had solved exactly this shape of problem years earlier.

## What shipped

`_backfill_dropdown_options`, mirroring `_backfill_positions`: same rationale
(the LLM is flaky, the dump is authoritative), same suffix-aware resolution via
`schema_lint._match_dump_names`, same first-match-only rule as
`schema_repair.pdf_choice_values`. Plus honest truncation ("... and N more") and
the slug rule scoped to radio/checkbox_group in all three places it is stated.

**The validation that mattered:** stripping every select's options from the real
i-90_v2 kit and re-running the backfill reproduces all 143 values BYTE-IDENTICAL
to the hand-authored gold. Re-running over the gold unchanged preserves it
exactly -- values and labels -- so it is safe over existing kits.

## Lessons

**A pattern for this already existed and I did not look for it first.**
`_backfill_positions` had the same rationale, the same dump-resolution helper,
and the same "deterministic wins over model" inversion (bd icyi). Reading it
before writing shaped the new function's shape, its return dict, and its
unconditional-overwrite rule. The half-hour spent finding the precedent was the
highest-leverage part of the work.

**I enumerated the set with a pattern too narrow to find its own set.** The
cross-surface reviewer flagged the JSON skeleton as a second unscoped statement.
Grepping the RENDERED prompt case-insensitively found a THIRD they had missed --
the condition-reference rule, which still told the model a `show_if` on a select
must name that option's slug. The reviewer had grepped `SEMANTIC SLUG`
uppercase; line 331 said `that option's SLUG` with lowercase `option's`. Both of
us hit scar #8 while citing scar #8. The method that works: render the artifact,
grep case-insensitively, read every hit.

**Four attempts at one guard, every failure caught by mutation:**
  1. Line-by-line scan -- the skeleton splits one rule across two lines, so
     neither half named both "slug" and "select" and it passed while the
     contradiction stood.
  2. Substring `select` -- the checkbox_group operator rows say "the group's
     selected set" and were flagged as false positives.
  3. Non-vacuity floor asserting "export code" appears ANYWHERE -- three
     statements contain that phrase, so deleting any one left it green.
  4. Same floor scoped to the CHOICE-FIELD block -- my block boundary spanned
     all three statements, the same hole one level in.
Final shape: one parametrized case per statement, keyed on text unique to each.
The reviewer independently confirmed each needle occurs exactly once.

**I reasoned from the wrong kit and asserted it as fact.** I declined to pin the
exit criterion's real numbers, saying the kit is gitignored and absent in CI.
True of `form-kits/i-90_v2/` -- but the criterion names `form-kits/i-90/`, which
is TRACKED, and a live precedent for exactly this test shape was sitting in the
same test file. The reviewer corrected the premise. A claim about repo state is
one `git ls-files` away from being checked; I should have checked it.

**The scan is evadable by rewording, and that is acceptable.** The reviewer
transplanted it out-of-repo and found six evasion shapes (a rule split across a
blank line, across a full stop, the plural "selects"). None is reachable by
REVERTING the fix -- both real pre-fix wordings redden it -- so it guards what it
was built to guard. Filed as `polyglot-pdf-nya53` rather than chased further.

## Follow-ups filed

- `polyglot-pdf-jpjcv` (P2): a freshly extracted state dropdown speaks bare
  two-letter codes. THIS DIFF CAUSED IT -- telling the model to omit a select's
  options makes the label-preservation path dead by construction for new kits.
  The shipped i-90 kit is hand-authored and unaffected; this bites the next kit.
- `polyglot-pdf-0ebi0` (P2): `schema_score._opts_match` matches on LABEL, so a
  backfilled state dropdown scores Jaccard 0.0 against a gold whose labels are
  state names -- a spurious regression in the scorer, not the extractor.
- `polyglot-pdf-nya53` (P3): the slug-scope scan's residual evadability.
- `polyglot-pdf-r311s` (P2, pre-existing): both prompt builders KeyError if a
  /Opt choice dict lacks "value".

## Files touched

- `scripts/authoring/extract_form.py` -- `_backfill_dropdown_options` + step 3z
- `scripts/bakeoff/schema_contract.py` -- honest truncation; slug rule scoped in
  the skeleton, CHOICE-FIELD RULES, and the condition-reference rule
- `scripts/bakeoff/structural_enrich.py` -- honest truncation (the twin)
- `tests/test_extract_form_backfill.py` -- 13 tests incl. a real-PDF regression
- `tests/test_prompt_choice_truncation.py` -- new; both builders, plus the
  slug-scope set pin
