---
date: 2026-08-28
bead: polyglot-pdf-alzbr
title: "fix(schema-editor): the editor re-slugged a dropdown's PDF export codes -- and four of the tests I wrote to pin the fix were vacuous"
tags: [schema-editor, testing, review]
---

## Trigger

bd `polyglot-pdf-4we6j` (PR #651) made lint, repair and the model gate accept a
dropdown's PDF export codes as legal `option.value`s. The cross-surface review
of that PR then found the editor itself still destroying them: editing a select
option's LABEL re-minted its value, and `+ Add Option` could only ever mint a
slug. Pre-existing on `dev`, but newly a correctness bug once codes became the
sanctioned state -- and the maintainer was about to spend a session in the
editor on exactly those six I-90 dropdown fields.

## What was wrong

A select has no fill branch of its own: `pdf_fill_routes.fill_widget` writes
`str(option.value)` verbatim into the combobox and never consults
`pdf_on_value`, and PyMuPDF does not validate the write against the widget's
`/Opt` list. So a dropdown's value IS the PDF export code, and a label-derived
slug prints clipped -- `'WY'` renders "WY", `'wyoming'` renders "wyomin" in the
36x18pt box, with no error anywhere.

THREE mint sites could reach a select, not the two the bead named: the
label-edit `onBlur`, and BOTH "+ Add Option" buttons (the populated-options one
and a structurally separate zero-options one). Found by grepping the set rather
than trusting the bead.

## What shipped

- Label edits leave a select's value alone entirely.
- Both Add-Option buttons give a select an EMPTY value for the author to supply;
  a minted slug there looks valid and prints wrong, while empty trips the
  existing `option-value-missing` ERROR -- an honest "you must supply this".
- The value became EDITABLE for selects (a "PDF export code" input). It had to:
  once it cannot be derived from the label, there must be somewhere to type it.
  It was previously a read-only chip labelled "not editable".
- Editing a code RETARGETS dependent `show_if`/`require_if` references, via the
  same `retargetOptionValueReferences` path the radio label-rename uses. The
  pre-edit code is captured in a ref on focus AND on the first keystroke,
  because this input's `onChange` writes `.value` itself -- unlike the label
  path, whose `.value` stays genuinely stale.
- BLANKING a code deliberately does NOT retarget (see Lessons).
- The Advanced block opens to the editor tier for selects, since "+ Add Option"
  already was and an editor could otherwise create an option they cannot
  complete.
- `ConditionBuilder` never seeds a condition from an unfilled export code.

## Lessons

**Retargeting a dangling reference to `""` is worse than leaving it dangling.**
I chose to point a dependent at `""` when its option's code was cleared,
reasoning the reference should track the option. The reviewer pushed back and
was right: `schema_lint` SKIPS its `ref-option-value` check for `""` on purpose
-- that is the v1 "field is empty" idiom, used for real on the i-90's unit-type
radios. Measured: leaving the old code reports `ref-option-value`; rewriting to
`""` reports NOTHING. The tidier-looking option was the one that hid the
breakage, and it also matches an unanswered dropdown live. Follow-up
`polyglot-pdf-ed630` blocks the blank-out the way Remove already does.

**FOUR of my tests were vacuous, every one green against broken code**, plus a
fifth deleted as unverifiable. The shared root cause: **asserting on HOW the
component called back instead of WHAT THE DATA BECAME.** When the correct
behaviour is "commit nothing", a callback-shaped assertion can only ever pass.
The individual failures:
  - assumed `authorTier` defaults false (it defaults TRUE), so the fixture
    could not exhibit the failure;
  - used a `vi.fn()` parent that never re-renders, PLUS an `e.target.value`
    override at blur, manufacturing a mismatch unreachable in the app;
  - looped over zero callback invocations, asserting nothing;
  - asserted on committed calls when correct behaviour is to commit nothing.
The deleted one: jsdom cannot express cross-row focus transfer (native
`.focus()`/`.blur()` do not reach React's synthetic handlers), so the guard
could not be made to fail and was removed rather than kept as decoration.

**A mutation that spans two sites proves ONE of them.** My "add" mutation
flipped both Add-Option branches at once; one test reddened and I read that as
covering the pair. The zero-options site was in fact untested. Same shape one
round later: `defaultAtom` and `coerceAtom` are separate paths, and reverting
`coerceAtom` alone left 1250 tests green. **Mutate each layer alone.**

**Chasing that per-layer pin found a LIVE bug the previous commit claimed to
have fixed.** Switching a row's trigger from a text field onto a half-authored
select still produced `value: ''` -- the seed fallback never ran, because the
`options.some(...)` guard matched first (`''` genuinely IS in the option set of
a select whose code is unfilled). Traced live rather than reasoned:
`AFTER SWITCH: {"field":"state","value":""}`. A commit message that claims a
mutation reddens a test is worth re-running, not trusting.

**Confirm the mutation APPLIED, and that the run produced counts.** Several
attempts this bead silently no-opped -- on CRLF anchors, on heredoc
indentation, and once because a reviewer had removed the `node_modules`
junction so vitest never started and printed nothing. Every one of those would
have read as a pass.

**The repo's own guard test caught two of my edits.**
`optionsConsumerSet.test.ts` (bd `8bjdx`) flagged an unguarded `options.find`,
and later flagged that moving a read into a `keep` const invalidated its
registered exemption text. Both were fair; the second needed the exemption
updated, not waived.

## Follow-ups filed

- `polyglot-pdf-ot284` (P2): a Repair run mints a slug over the empty code,
  erasing the `option-value-missing` guard this bead relies on -- `'option'` is
  a valid slug, so lint then reports nothing while the form prints "option".
  Verified against the real modules. Deliberately deferred: the corrupt end
  state is pre-existing on `dev` and this branch is frontend-only.
- `polyglot-pdf-ed630` (P2): blanking a REFERENCED code should be blocked the
  way Remove is.
- `polyglot-pdf-jbek5` (P2): the voice path's fuzzy select fallback matches by
  bare substring, which collides on two-letter codes ('al' hits alabama,
  alaska, california). Pre-existing, surfaced by the cross-surface trace.

## Files touched

- `schema-editor/src/components/FieldEditor.tsx` -- three mint sites made
  select-aware; the export-code input, its focus/blur ref and retarget; the
  editor-tier gate
- `schema-editor/src/components/ConditionBuilder.tsx` -- neither seed path
  takes an unfilled export code
- `schema-editor/src/components/FieldEditor.selectexportcode.test.tsx` -- new
- `schema-editor/src/components/ConditionBuilder.test.tsx` -- per-layer pins
- `schema-editor/src/components/FieldEditor.optionwidget.test.tsx` -- one
  assertion updated (the value is an input now, not a chip)
- `schema-editor/src/utils/optionsConsumerSet.test.ts` -- exemption fragment
