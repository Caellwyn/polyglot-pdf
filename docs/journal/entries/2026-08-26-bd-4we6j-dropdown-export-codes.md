---
date: 2026-08-26
bead: polyglot-pdf-4we6j
title: "fix(schema-lint): the option-slug rule and the PDF disagreed about dropdown values -- and the lint's own remedy would have silently mis-printed the form"
tags: [schema-editor, testing, extractor]
---

## Trigger

Authoring the new gold I-90 (`form-kits/i-90_v2`) hit a hard 409 at the
publish gate: 124 `option-value-slug` ERRORs, one per state code, because
`WY` is not lowercase. The maintainer's read was that the validator was
wrong, and separately doubted that a dropdown would really write the
2-letter code given the option's on-screen text is longer.

Both halves of that were right, and the second one is why this is not
just a lint-tuning bead.

## What was actually wrong

The rule and the PDF genuinely disagree, and the disagreement is load-bearing.

The v2 contract (`conditional_vocabulary.py`) says `option.value` is a
SEMANTIC SLUG minted from the label, and widget identity lives ONLY in
`option.pdf_field_name` / `pdf_on_value`. Radios honour it: `value: "male"`
with `pdf_on_value: "Y"`.

**The select path never implemented its half.** `pdf_on_value` is read only on
the radio and checkbox branches of `pdf_fill_routes`; a select has no branch of
its own and falls to the scalar path, which does
`fresh_widget.field_value = str(value)`. So for a dropdown `option.value` IS
the PDF export value -- there is no second channel to put the code in.

Measured against the real `form-kits/i-90_v2/form.pdf`, widget
`P1_Line6e_State[0]` (36x18pt), driving the production write exactly:

    'WY'           -> stored 'WY'           -> renders "WY"
    'wyoming'      -> stored 'wyoming'      -> renders "wyomin"
    'Wyoming (WY)' -> stored 'Wyoming (WY)' -> renders clipped

PyMuPDF does **not** validate the write against the widget's `/Opt` choice
list. Any string is accepted silently and then clipped by the box at render
time -- the same shape as the COMB gotcha (bd `br7t`): the stored value
round-trips perfectly while the printed page is wrong.

So the lint's own remedy ("regenerate it from the label") and
`schema_repair`'s mint would have converted a loud, correct 409 into a
**silent mis-print**: `Alabama (AL)` -> `alabama_al` -> printed clipped, with
no error anywhere in the system. The blocking error was the safe state.

Worth recording: the stale `form-kits/i-90` (no longer gold) already has full
lowercase names in these same fields against the same 2-letter-only PDF, so
those state fields presumably print clipped today. The current gold, W-7, has
**no select fields at all** -- which is exactly why the hole survived
undetected: W-7 set the `pdf_on_value` precedent for radios and never
exercised the dropdown path.

## What shipped

An **evidence-based** carve-out, deliberately not a type-wide one: a select
option value is exempt from `option-value-slug` only when the acroform dump
proves the widget declares that exact value in `/Opt`. No dump, no matching
widget, or a value the PDF does not sanction -> still an ERROR, because those
are precisely the values that print wrong. Radios are untouched.

`schema_repair` got the matching guard, or "repair" would re-break a valid
schema on the next run. Shared helper `schema_repair.pdf_choice_values` is the
single source of truth for "what the PDF sanctions", so lint and repair can
never disagree (same reasoning as the shared `is_fillable_widget`).

Result: `i-90_v2` lints with ZERO ERRORs (was 124) and passes the publish
gate; repair leaves all 6 select fields byte-identical.

## Lessons

**Implementing the guard surfaced two defects the original report did not
contain, both in the repair path.** (a) Minting is triggered per-FIELD and
rewrote EVERY option, so one duplicate anywhere in a 62-option dropdown would
have clobbered all 62 codes -- the guard has to be per-option, not per-field.
(b) The fix for (a) then introduced a collision: a preserved lowercase code is
itself slug-legal, so a slug minted from a sibling's label could equal it and
manufacture the very duplicate the branch exists to repair. The minter now
reserves preserved codes before minting.

**(b) was caught only because the first check was suspected of passing for the
wrong reason.** The initial collision probe used uppercase codes (`WY`) against
lowercase slugs, which can never collide -- it reported "unique" by luck, not by
design. Re-running with a lowercase PDF code (`wy`) turned it red immediately.
A negative result from a fixture that *cannot* exhibit the failure is not
evidence; pick the fixture where the failure is possible.

**A doc gap was part of the bug's cover.** `docs/components/pdf-filling.md`
lists the fill behaviour per field type and had no `select` entry at all -- the
one type whose behaviour is "falls through to the scalar path, so value IS the
export value" was the one type nobody had written down. Added the missing
bullet plus a gotcha entry beside the COMB one.

**Mutation-verified the wrong fix, not just the absent one.** Beyond reverting
the carve-out (2 tests redden), the more valuable mutation was *widening* it to
a blanket `type != "select"` exemption -- the plausible shortcut fix -- which
reddens 7, including all four parametrizations of the absent-from-`/Opt` case
and both evidence guards. The parametrized test pins the whole property (every
`/Opt` value accepted), so a future carve-out that special-cases a subset fails
CI rather than a review round.

## Follow-up filed

`polyglot-pdf-g2fpr` (P1, blocked on this): give selects the same
`pdf_on_value` channel radios have, so `option.value` can go back to a pure
slug on every field type and this carve-out can be retired. Cross-surface:
filler, lint, repair, schema-editor, plus a kit migration.

## Files touched

- `backend/services/schema_lint.py` -- evidence-scoped exemption in
  `_check_options`; `dump` threaded through
- `backend/services/schema_repair.py` -- new shared `pdf_choice_values`;
  per-option keep-guard and reserved-seed in `_mint_slugs`
- `backend/tests/test_schema_lint.py` -- 6 tests (incl. a 4-way parametrization)
- `tests/test_schema_repair.py` -- 4 tests
- `docs/components/pdf-filling.md` -- select fill path + dropdown gotcha
