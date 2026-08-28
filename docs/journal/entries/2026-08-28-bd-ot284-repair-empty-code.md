---
date: 2026-08-28
bead: polyglot-pdf-ot284
title: "fix(schema-repair): Repair erased the guard it was meant to preserve -- and each of my four fixes introduced the next defect"
tags: [schema-editor, testing, review, postmortem]
---

## Trigger

bd `polyglot-pdf-alzbr` (PR #664) has the schema editor create a select option
with an EMPTY value on purpose, relying on `schema_lint`'s
`option-value-missing` ERROR as the "the author must supply the PDF export
code" publish gate. The cross-surface review of that PR found the gate was
erasable: a Repair run minted a slug over the blank.

## What was wrong

`'option'` is a valid v2 slug, so after Repair the lint reported NOTHING --
while a dropdown's value goes verbatim into the combobox (`fill_widget` never
reads `pdf_on_value`, and PyMuPDF does not validate against `/Opt`). So the form
printed "option" in the state box, silently. Measured:

    before repair: [WY, AL, ''] -> ERROR option-value-missing
    after  repair: [WY, AL, 'option'] -> NO findings at all

The trigger was the natural authoring flow: add option -> save -> see the error
-> click Repair -> error gone, corruption invisible.

## What shipped

The blank is held aside in `_mint_slugs` instead of minted, exactly as
PDF-sanctioned codes already are. Scoped to `select` only: radio and
checkbox_group carry widget identity in `pdf_on_value`, so a minted slug is the
correct repair for them.

## Lessons

**Four review rounds, four defects -- every one in the HARDENING, none in the
core guard.** The guard itself (hold the blank aside, select-only) was correct
from the first commit and never changed. Each fix I layered on top introduced
the next bug:

1. Holding blanks aside made a keyless option "kept", but the reserved-list
   builder still subscripted `o["value"]` -- a `KeyError` that aborted
   `repair()` for the ENTIRE schema, not just that option.
2. The guard tested `v == ""` while `schema_lint` defines missing as
   `value is None or value.strip() == ""`. So `'   '` was still minted over,
   clearing the exact gate this bead exists to keep standing. **A guard that
   defines its condition differently from the rule it protects is only ever a
   partial guard.**
3. Fixing (1) with `str(o.get("value") or "")` used truthiness where the rest of
   the function uses `is not None`. A dump can declare the code `"0"`, so a
   numeric `0` is kept like any other code -- and `0 or ""` dropped it from the
   dedupe seed, manufacturing the very `option-value-duplicate` the branch
   exists to prevent. **When a function already has a consistent convention,
   deviating from it IS the bug**; I reasoned "that case can't happen" instead
   of measuring, and the measurement disagreed.
4. A condition can name an option by LABEL. When that option was the held-aside
   blank, `_resolve_value` returned `""` with `ok=True`, so the condition was
   rewritten to `equals ""` and logged as a SUCCESSFUL repair -- and lint
   deliberately skips `""` (the v1 emptiness idiom), so once the author supplied
   the code the kit published CLEAN carrying a permanently dead condition. Now
   dropped with `error=True`, matching the `option_id` path's "never guess".

**The recurring failure mode is mine, not the code's: reasoning about
reachability instead of measuring it.** Defect 3 was found by a reviewer
refuting the exact self-check I had asked them to confirm. Every round, the
measurement contradicted my argument. What actually worked was the review loop
plus mutation testing -- not my judgment about what could happen.

**Drop beats a dangling rewrite when lint cannot see the dangle.** The reviewer
made the case better than I had: a dropped `show_if` leaves the field ALWAYS
VISIBLE, and on a legal intake form an extra visible question is recoverable
while a silently-never-shown one is not. A `""` rewrite fails in the hidden
direction AND is invisible to lint, the publish gate, and the editor's finding
list -- "visible" only in the sense that the JSON still has a key.

**A stale `.pyc` newer than its source made a correct fix look like a no-op.**
Python served cached bytecode; clearing `__pycache__` and running with `-B` was
what actually exercised the edit. Cost me and both reviewers real time. When a
change appears to do nothing in this worktree, suspect the cache before
concluding the fix is wrong.

**An unpinned scoping clause is how the next person deletes it.** The reviewer
filed the guard's `and str(v).strip() != ""` as non-blocking -- deleting it left
all 91 tests green. Fixed anyway: the distinguishing input is whitespace on
BOTH sides, and it is a two-minute test.

## Follow-ups

- `polyglot-pdf-9g698` (P2): the editor's "Repair all (N)" button is now a
  permanent no-op for this defect, since repair deliberately cannot fix it.
  UX gap, not correctness -- the finding list still carries the right remedy.
- `polyglot-pdf-dr43j`: annotated and RE-SCOPED. The half that motivated it is
  fixed here; the remainder (lint structurally cannot see any condition
  comparing a choice trigger against `""`) is pre-existing and is a DESIGN call
  about condition vocabulary, not a mechanical fix -- `equals ""` IS the
  documented v1 emptiness idiom the i-90 gold relies on.
- `polyglot-pdf-xydxm`: closed by the scoping test above.

## Files touched

- `backend/services/schema_repair.py` -- the hold-aside in `_mint_slugs`, the
  `is not None` dedupe seed, the `_register` None-guard, and the
  blank-resolution drop in `_rewrite_atom`
- `tests/test_schema_repair.py` -- 8 tests, each mutation-verified
