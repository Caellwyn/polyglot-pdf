---
date: 2026-08-26
bead: polyglot-pdf-82rzp
title: "docs(check_doc_freshness): stale check-COUNT prose -- 'two halves/both' paragraph and 'other two checks' docstring now disagree with four checks"
tags: [doctrine, testing]
---

## Trigger

`scripts/check_doc_freshness.py`'s module docstring correctly said "four
warn-only checks," but a paragraph immediately below it still said "Why
both checks live in one script: they're two halves..." -- stale prose
that desynced when `check_doc_conventions` (check #3) was added and was
never updated then either; the fourth check (bd `polyglot-pdf-3pii5`'s
`check_code_citations`) widened the drift from 2-vs-3 to 2-vs-4.
`report_code_citations()`'s own docstring had the same problem in
miniature: "the other two checks" when there are three others.

## What shipped

Enumerated the complete set of check-count mentions mechanically before
fixing anything -- confirmed every other hit in the file besides the
bead's two named sites is either accurate or refers to an unrelated
two-valued dimension (`--all`/`--staged` modes), not check count.
Rewrote both stale sites to be count-free. Added a CI-gate test
(`TestModuleDocstringCheckCountMatchesMain`) pinning the actual
property: the module docstring's numbered-list length must equal the
number of distinct checks `main()` dispatches to, counted via
`inspect.getsource` rather than hand-maintained.

## Lessons

**Fixing the property surfaced a false-positive in the property-checker
itself, mid-review.** Fresh-eyes adversarially probed the new counting
heuristic beyond the bead's own two mutations and found that a
`report_*(`-shaped substring inside a whole-line comment in `main()`
(an ordinary "someday also call X" TODO) would inflate the count with no
real behavior change. Fixed by stripping whole-line comments before
matching, then re-verified both of the bead's original mutations still
redden correctly -- narrowing a false-positive must never accidentally
weaken the property being pinned, so both directions need re-checking
after any change to the checker itself, not just the one direction that
motivated the change.

**Fixing a set can surface an adjacent, larger set one level out.** The
outer Opus review found that this fix's own module docstring LEAD
SENTENCE ("This script does four warn-only checks...") still carries a
bare count word, uncovered by the new test (which only counts the
numbered list, not the sentence above it) -- and that an EXISTING,
unrelated test (`_SITE_ANCHORS`) hard-anchors on that exact sentence
text, so a future correct fifth-check addition would both (a) leave the
sentence silently wrong and (b) hard-fail a different test with a
misleading "the site may have been reworded" message. Both defects
predate this branch (reproduce unchanged on `origin/dev`), so correctly
filed separately as `polyglot-pdf-nlbck` rather than folded in --
exactly the CLAUDE.md scar #7 pattern recurring one level in from where
this bead started.

## Files touched

- `scripts/check_doc_freshness.py` -- two count-bearing sites rewritten
  count-free
- `tests/test_doc_freshness.py` -- new `TestModuleDocstringCheckCountMatchesMain`
