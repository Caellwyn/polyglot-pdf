---
date: 2026-07-06
bead: polyglot-pdf-zb55
title: "Section-grouping score: match no-PDF-name fields without section_id"
tags: [harness, testing]
---

## Trigger

`scripts/schema_score.py` (the PDF->JSON authoring bake-off scorer, bd 7a9.3)
matches truth fields to draft fields without trusting either side's extractor
`id`. Fields with no `pdf_field_name` at all (and no option-level pdf names) --
rare table/static/supplement fields, e.g. ~6 of 303 on i-589, 0 on i-90 -- could
only be paired by Pass 2's fuzzy `(section_id, name)` key, which STILL bakes in
`section_id`. So a draft that kept the field names but RENAMED the section left
those fields unmatched, and the naming-agnostic section-GROUPING metric (bd
7a9.13) then went `n/a` for exactly the fields it means to grade -- the metric's
naming-agnosticism leaked back in through the matcher. Deferred from bd 7a9.13's
PR #235 (Codex round 3) to avoid scope-creeping the metric change into the
field-matcher; this bead (zb55) picks it up.

## What shipped

A section-id-free name fallback in `match_fields`, added as **Pass 3** after the
existing exact-pfn (1a), endswith-pfn (1b), and fuzzy `(section, name)` (2)
passes:

- New `_name_key(f)` -- the normalized field name alone (no section_id).
- Pass 3 runs only on the PDF-less remainder that Passes 1-2 left unmatched, and
  is restricted to **PDF-less-vs-PDF-less**: a truth field that HAS a
  pdf_field_name is skipped (matching it on name alone would ignore the widget
  name it genuinely has -> a false pair), and only draft fields with no pfn are
  candidates. Same `SequenceMatcher >= 0.85` bar as Pass 2.
- Empty-name guard: an empty `_name_key` can't pair (`SequenceMatcher("","")`
  is 1.0, which would otherwise manufacture matches between two nameless fields).

Verification:
- 5 new tests in `tests/test_schema_score_section_grouping.py` pin the rescue,
  both pfn-guards (truth-has-pfn and draft-has-pfn, sections deliberately
  differing so Pass 2 misses and the Pass-3 guard is isolated), the empty-name
  guard, and the end-to-end path where the rescued pair makes the grouping
  metric gradable (F1 100% instead of n/a). Full file: 17/17 pass.
- i-90 self-test (`--draft schema.json --truth schema.json`) stays 100% on every
  metric -- i-90 has 0 PDF-less fields so Pass 3 never fires there; zero
  regression on the primary form.

Scope note: no i-589 kit exists locally, so the renamed-section rescue is
demonstrated by the synthetic tests rather than against a live i-589 gold. This
scorer is a manual research harness -- no CI/gate/runtime/user exposure.

Nothing deferred; no out-of-scope beads filed.

## Lessons

Process, not code: the schema_score.py edits first landed in the MAIN checkout
because the Edit calls used a `C:\...\polyglot-pdf\scripts\...` absolute path
instead of the worktree path (CLAUDE.md scar #3 / memory
`write-tool-needs-worktree-path-not-main`). Caught immediately when the
worktree's test suite imported the UNmodified worktree copy and failed;
recovered by `git diff > patch` in main, `git checkout` to revert main, `git
apply` into the worktree. The tell was tests failing on behavior the direct
in-repl debug proved correct -- i.e. the test and the code-under-test were
looking at two different files.

## Doc freshness

`check_doc_freshness.py` flagged ~25 tier-2 docs STALE, but every one tracks
`backend/*` or `frontend/*` files this branch did not touch (they were touched
2026-07-05 by unrelated work already on dev) -- pre-existing staleness, left
as-is per the closeout rule. No tier-2 doc `**Tracks:**` `scripts/schema_score.py`
(confirmed by grep), so no doc bump was owed by this change. The module
docstring's "fall back to a (section, name) fuzzy key" line was updated in-file
to mention the new name-only fallback (current-state doc discipline).

## Files touched

- `scripts/schema_score.py` -- added `_name_key`; added Pass 3 (section-id-free,
  PDF-less-only name match) to `match_fields`; updated the module docstring.
- `tests/test_schema_score_section_grouping.py` -- 5 new Pass-3 tests.
- `docs/journal/entries/2026-07-06-bd-zb55-pdfless-name-fallback.md` -- this entry.
