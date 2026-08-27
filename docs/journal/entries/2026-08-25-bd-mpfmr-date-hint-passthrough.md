---
date: 2026-08-25
bead: polyglot-pdf-mpfmr
title: "fix(voice-dates): help.format_hint was dropped at FormField construction, so every date fell back to ISO"
tags: [validation, voice, dates, testing]
---

## Trigger

The maintainer ran a local voice session against the W-7 and reported that the
model was still demanding dates in year-month-day order, months after the
date-layout work of the bd `polyglot-pdf-52qm` era. The W-7 kit declares
`help.format_hint = "MM/DD/YYYY"` on both date fields, so the report read as
either the model ignoring its guidance or the hint never arriving.

## What the logs showed

`backend/logs/gemini_2026-08-25.jsonl` settled it, and inverted the diagnosis.
The model was sent the CORRECT hint -- the guidance block reads
`Format: MM/DD/YYYY`, and the booklet text quoted alongside it spells out the
same layout. The model then BEHAVED CORRECTLY: it converted the spoken date and
submitted `10/12/2005`.

The backend rejected its own correct answer:

```
"value": "10/12/2005", "constraint": "format",
"message": "Invalid date (expected YYYY-MM-DD)", "constraint_value": "YYYY-MM-DD"
```

Seven such rejections in one session. The model read that error text and adapted
to it -- which is exactly the mechanism `_resolve_date_format`'s own docstring
describes as the original bug. So the year-first demands were a SYMPTOM of the
validator, not a model-compliance problem.

## Root cause

`build_fields_from_schema` (`backend/services/field_utils.py`) constructs
`FormField` from an explicit ALLOWLIST of schema keys. `help` was not in it, so
`help.format_hint` was discarded the moment the session's field list was built --
silently, with no error and no log.

Everything downstream was already correct and had been for weeks:
`validation_handler._convert_fields_to_dicts` forwards both `format` and
`help.format_hint`, and `field_validator._resolve_date_format` reads
`format -> help.format_hint -> validation.hint` with prose-hint handling. Those
layers were operating on a `FormField` that no longer carried the hint.

**This is why the 52qm-era fix did not take.** It repaired the FORWARDING and the
RESOLUTION. The CONSTRUCTION was never in scope, so the hint never reached the
code that was fixed. Every layer passed in isolation -- including its unit tests --
while the running app stayed broken. A green unit test on the resolver was
compatible with total failure end to end.

## What shipped

`help` and the flat `format` key now pass through the constructor.

The bead was an ENUMERATE-THE-SET case (CLAUDE.md scar #7), so the set was
derived mechanically rather than fixed instance-first: `FormField` declares 39
properties and the constructor passed 8. **31 were being dropped.** The blast
radius is narrower than that number suggests -- `validation` IS passed through
and carries `min`/`max`/`max_length`/`pattern`/`hint`, so kits declaring
constraints in the nested block were unaffected. The break was specific to
top-level and `help` declarations, which is exactly where the schema editor's
"Format Hint" box writes.

`test_field_utils_property_passthrough.py` pins the SET, not the instance. Its
expectations are checked against `FormField.model_fields`, so a property added to
the model without a passthrough decision fails CI by name. This constructor had
already produced three separate defects (this one; `hidden`/`read_only`, flagged
in `test_52qm7_static_field_states.py`; and dormant `min`/`max`, noted in
`form_models.py`) without anyone connecting them.

The reactive/visibility group (`hidden`, `read_only`, `show_if`, `require_if`,
`conditional_behavior`) is deliberately still excluded, with a per-key reason
recorded in `EXPECTED_DROPPED` and a follow-up bead (`polyglot-pdf-slfc5`).
Enabling those inside a date bugfix could change which fields are shown or
required in a live session -- a behavior change that deserves its own
verification rather than riding along on a fix.

## Scar tissue: the fixture that masked its own regression

The first draft of the test file was mutation-verified and looked fine -- removing
the `help` passthrough reddened 2 tests. But the three END-TO-END tests, the ones
that exist specifically to catch this regression, **stayed green under the exact
mutation they were written for.**

The fixture also set the flat `format` key. That second layout source satisfied
the resolver, so the loss of `help` was invisible. The shipped kits do not set
`format` -- w7 and i-90 carry `help.format_hint` alone.

Fixed by giving the end-to-end tests a help-only fixture that mirrors the real
kits. The same mutation now reddens 5 tests. The general lesson, which is the
reason this section exists: **a fixture richer than production can defeat a
mutation test by supplying a redundant source the real data never has.** Pick the
mutation that actually happened, and make sure the fixture is as impoverished as
reality (bd memory `mutation-verify-the-mutation-that-matters`).

Also verified: the partition guard fails by name when a new `FormField` property
is added, and each passthrough (`help`, `format`) is independently pinned.

## Scar tissue: the fix that introduced a worse bug

The fresh-eyes review caught a defect the first draft INTRODUCED. Passing the
flat `format` key straight through looked like a free ride-along -- it is the
first source in the same layout-resolution chain. But `FormField.format` is a
CLOSED `DateFormat` enum of 4 case-sensitive literals, and `build_fields_from_
schema` wraps construction in a broad `except` that DROPS THE WHOLE FIELD on any
error.

So a kit writing `"format": "MM/DD/YYYY"` -- the natural authoring casing, and
the exact string `help.format_hint` already uses on every shipped kit -- would
have made the entire field VANISH from the session. Silently, to stdout. That is
strictly worse than the bug being fixed: a field with a wrong date layout is at
least visible and fillable; a field that does not exist cannot be filled at all.

On `origin/dev` the same bad value was harmless, because `format` was never
passed. The fix created the hazard.

Resolved by coercing case-insensitively (matching how `field_validator`'s own
`_DATE_LAYOUTS` lowercases before matching) and falling back to `None`, so an
unresolvable value leaves `help.format_hint` as the layout source -- exactly the
behavior before the flat key was passed at all. Same coerce-or-fall-back shape
as the `FieldType` handling directly above it in the same function.

The general lesson: **widening an allowlist is not automatically safe when the
receiving field is strictly typed and the construction is wrapped in a
catch-all.** The blast radius of a passthrough is set by what the CONSUMER does
with a bad value, not by how innocuous the key looks. No shipped kit sets the
flat key today, so this pinned a hazard rather than a live break -- which is
exactly when it is cheapest to pin.

## Verification

- New tests: 28 passing; mutation-verified per passthrough, per casing, and
  per parametrization.
- Full backend suite: 2576 passed, 2 skipped.
- Confirmed against the real W-7 field through the real call chain:
  `10/12/2005` validates OK, the error text names the field's own layout, and
  impossible dates (`13/45/2020`) still reject.

## Follow-ups

- `polyglot-pdf-slfc5` -- resolve the remaining dropped properties.
- `polyglot-pdf-kt7c6` -- read dates back IN WORDS so ambiguity surfaces at
  verification. Blocked on this bead. Note that the SI currently lists dates
  among the digit-by-digit identifier read-backs, which contradicts that goal;
  a digit read-back would preserve the very ambiguity the words read-back exists
  to expose.
- The ISO default (`_DEFAULT_DATE_SPEC`) remains. With `help` restored it is no
  longer reachable for shipped kits. Worth noting the maintainer's point that
  ISO is an odd default for a US-forms product -- but the stronger fix is to make
  an unresolved layout LOUD rather than swap one silent guess for another. A
  friendlier default would have made this outage invisible instead of fixing it.
