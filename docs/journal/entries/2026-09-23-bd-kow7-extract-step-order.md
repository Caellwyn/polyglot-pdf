---
date: 2026-09-23
bead: polyglot-pdf-kow7
title: "Verifying a bead's recipe found a bigger problem than the bead"
tags: [testing, extractor, conventions]
---

## Trigger

Bug-hunt continuation. bd `polyglot-pdf-kow7`: two tests in
`tests/test_extract_form_sections.py` opened their docstrings by claiming to
pin the "step-3e-BEFORE-repair ordering contract" of `extract_form`'s
pipeline, and neither invoked `extract_form` at all.

## What shipped

**The bead was already half-closed, and reading before acting is what showed
it.** `kow7` offered two exits: (a) actually pin the ordering, or (b) reword
the docstrings to claim only what they assert. Option (b) was **already
done** -- the docstrings now say plainly "it does NOT detect a future
refactor that REORDERS the pipeline", and the 2026-07-31 journal entry
records that narrowing and files this bead as the follow-up for (a). Had I
taken the bead's description at face value I would have "fixed" prose that
was already correct.

**Verifying the bead's own recipe found something worse than the bead.** Its
verification step is: swap the two calls, run
`tests/test_extract_form_sections.py`, confirm the tests stay GREEN. They do
not stay green -- **all 11 cases SKIP**:

```
6  "w7 kit not present"
2  "form-kits/i-90/form.pdf not present (kit deprecated)"
1  "f1040 kit not present"
(11 skipped, 0 run)
```

No kit is tracked in git by design (scar #10). So that file is **inert in
CI**: the ordering is unguarded, and so are the composition properties it
does assert -- they are only ever checked on a machine that happens to have
an untracked kit lying around. Filed as bd `polyglot-pdf-yrhyx` with the
measurements rather than widening this diff.

**The fix had to be static, and that was forced rather than chosen.**
`derive_and_apply` needs a real PDF on disk, so a runtime ordering test needs
exactly the fixture dependency that makes the existing file dead. The
property is genuinely syntactic -- which call comes first inside `extract()`
-- so `tests/test_extract_form_step_order.py` parses the source instead.
Precedent: `tests/test_llm_providers.py`,
`backend/tests/unit/test_bootstrap_editor_message.py`.

## Lessons

**Run the bead's own verification recipe before trusting its premise.** This
bead's description was written by someone who reasonably assumed those tests
executed. The description is internally coherent, cites real line numbers,
and names a real gap -- and its central empirical claim ("the tests stay
green under the swap") is false in a way that changes the fix. The tests do
not stay green; they never run. Reading the bead and reading the code would
both have left that invisible. Only running it surfaced it.

This is the second time in this session that a bead's *noun* was wrong while
its *concern* was right (bd `kk74` said a panel was "removed" when only its
contents were). The pattern: a bead is a snapshot of one person's
understanding at filing time, and the part most likely to have drifted is the
part they did not execute.

**A skipped test is not a passing test, and the two are easy to confuse at a
glance.** `11 skipped` and `11 passed` occupy the same line of pytest output
and both read as "fine". The distinction matters most exactly where these
tests sit: kit-coupled integration tests that a maintainer sees run locally
and CI never runs at all. Worth reading the skip count, not just the failure
count -- and `-rs` to see the reasons.

**When a guard cannot be dynamic, check whether the property is syntactic.**
I nearly concluded the ordering was unpinnable without a fixture kit. It is
not: "which of two calls comes first in this function" is a fact about the
source text, and an AST parse answers it with no kit, no PDF and no network.
The runtime test would have been *better* -- it would catch a reorder that
preserved call order but changed behaviour -- but a static pin that runs
beats a dynamic one that skips.

## Doc freshness

No tier-1/tier-2 docs affected: this diff adds one test file and touches no
production source, so nothing tracked by `check_doc_freshness.py` moved. (It
also adds this tier-3 journal entry.)

The claims corrected by the earlier half of `kow7` -- the docstrings in
`tests/test_extract_form_sections.py` -- were verified accurate as they now
stand and left alone.

No CLAUDE.md changes.

## Files touched

- `tests/test_extract_form_step_order.py` -- NEW. Two guards: the ordering
  itself, and a non-vacuity pair (each step called exactly once; a renamed
  call fails loudly rather than passing on an empty comparison).
