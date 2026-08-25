---
date: 2026-08-25
bead: polyglot-pdf-md20o
title: "fix(schema-forms): a native <input type=date> was coercing every PDF date to ISO"
tags: [schema-forms, validation, dates, pdf-filling]
---

## Trigger

Live-testing the bd `polyglot-pdf-mpfmr` backend date fix, the maintainer
answered the W-7 date of birth by voice and watched it store `1980-10-26` on a
field whose kit declares `MM/DD/YYYY`. The backend fix was working -- validation
correctly REJECTED that value -- and it reached storage anyway.

Maintainer's call, which is the principle this bead implements: "since these are
pdfs, we shouldn't be enforcing DOM types like that. We need to conform to the
format hints in the form schema... this is just the wrong kind of validation to
apply."

## Root cause

`DateField` rendered `<input type="date">`. Per the HTML spec that element's
`.value` is ALWAYS `yyyy-mm-dd`; it physically cannot hold `10/26/1980`. So the
widget coerced every date to ISO before the value ever reached the client's
write path, which is why backend validation could reject it without stopping it.

These are PDF AcroForm fields, not web-form fields. The kit schema's
`help.format_hint` is the authority on a value's shape, and `pdf_fill_routes.py`
writes the stored string verbatim.

## Why this was not cosmetic

`pdf_fill_routes.py:200-236` already documented this exact widget as an accepted
cost -- "the two `type="date"` fields cannot be length-gated at all... so a W-7
date of birth renders un-combed on every UI submission" -- because at the time it
only affected APPEARANCE.

The voice path changed that. The model reads the stored value back, so an ISO
string is no longer a rendering nit: it is the stored answer, and it teaches the
model the wrong format for every subsequent turn.

The same docstring is also why ISO-everywhere is the WRONG architecture here,
which settled an open question this work started with. An earlier cut of the PDF
code normalized punctuation and was removed after three review rounds, because
stripping separators REORDERED dates: `1990-03-14` -> `19900314`, which then FIT
the comb-8 box and printed a plausible-looking WRONG date (month=19) on a filed
ITIN application. An ISO value reaching a comb-8 date widget is that same
failure. Canonical storage is the kit's format; the docstring even prescribes
the fix ("Restoring the one-digit-per-cell look belongs in INPUT normalization,
where the field's semantic type is known").

## What shipped

The scan the maintainer asked for covered every field widget:

- **`DateField`** -- now `type="text"`, never `date`/`month`. Placeholder is the
  `format_hint`, so the expected shape stays discoverable once the native
  picker's implicit affordance is gone. Dropped `min`/`max`, which are inert on
  a text input; `validateDateValue` already enforces `min_date`/`max_date` from
  the field directly.
- **`TextField`** -- `type="text"` for `email`/`tel`. The browser's own validity
  check can reject a value the KIT considers valid, and the w7 tel fields
  declare no layout constraint at all, so the browser's convention would win by
  default.
- **`TextField` maxLength** -- a field's top-level `max_length` is the PDF
  widget's COMB CELL COUNT, not always a text limit. W-7 dates are comb-8 while
  `MM/DD/YYYY` is 10 chars, so the old wiring truncated a correct date to
  `10/26/19` -- a wrong year on a filed form, silently, as the user types. Now
  the cap is only applied when the field's own declared format fits inside it; a
  nested `validation.max_length` is a real author-set limit and is still
  honored.
- **`case "number"` (unchanged)** -- already renders as text with a comment
  explaining the identical coercion reason. This was the PRECEDENT the rest now
  follow, and it matters: f1040 has 57 number fields, and `<input type="number">`
  strips leading zeros and rejects commas.
- **checkbox / radio / select (unchanged)** -- genuine closed enumerations, not
  free-text coercion. A native type is correct there.

## Two existing tests pinned the bug

`TextField.test.tsx` asserted `input.type === 'email'` and `=== 'tel'`. Those
described what the code did, not what it should do -- exactly the "a test can
PIN a bug as correct" shape. Updated to pin the text-type contract with their
value assertions intact, rather than deleted.

## Scar tissue: a heuristic that fired on 26 fields to fix 2

The cross-surface review caught the maxLength guard's first cut being badly
wrong. It suppressed the cap when `help.format_hint.length > max_length` -- which
is only meaningful if the hint IS the value's shape. Across the shipped kits it
usually is not:

| hint | len | cap |
|---|---|---|
| `"5 digits"` | 8 | 5 |
| `"Alphanumeric postal code"` | 24 | 9 |
| `"9 digits (XXX-XX-XXXX)"` | 22 | 9 |
| `"10 digits (XXX-XXX-XXXX)"` | 24 | 13 |

Prose is almost always longer than the cap it describes. So the guard fired on
**26 fields when only 2 are dates**, uncapping SSN, ZIP, phone and ITIN inputs --
none of which carry a `validation.max_length` fallback, on a download path
(`SchemaForm.handleDownloadPDF`) that runs no validation at all. The fix for a
truncation bug would have shipped an over-length bug on more fields than it
repaired.

Now gated on the hint being a LAYOUT LITERAL -- only placeholder characters and
separators (`MM/DD/YYYY`, `YYYY-MM-DD`) -- so prose is never mistaken for a
shape. Verified against the real kits: exactly the 2 date fields are suppressed,
all 24 prose-hint fields keep their caps. Note `'MM/DD/YYYY or "Never Entered
US"'` correctly classifies as PROSE: its `max_length: 16` is a genuine cap.

**Why my own mutation testing missed it:** the fixtures used `"MM/DD/YYYY"` and
`"ABCDE"` -- both layout-literal-shaped, so both branches behaved identically
under the broken and correct versions. The bug lived entirely in the space of
inputs the fixtures never sampled. The replacement cases are derived from the
SHIPPED KITS rather than invented, and reverting to the raw-length heuristic now
reddens 8 of them. General lesson, and the second time this exact shape bit in
one PR: **a fixture drawn from imagination samples the cases you already thought
of; a fixture drawn from production data samples the ones you did not.**

## Verification

- New `no-coercing-input-types.test.tsx` enumerates the schema-type ->
  input-type mapping and fails CI on any coercing type, so a future widget
  cannot reintroduce the class.
- Mutation-verified: restoring the native date input reddens 3 tests; restoring
  the raw `maxLength` wiring reddens 1.
- Rendered the REAL shipped W-7 `date_of_birth` through the REAL `FieldRenderer`
  and asserted the DOM input actually holds `10/26/1980` -- with `max_length: 8`
  present on the field and correctly not truncating. A synthetic fixture would
  not have proven the comb-count interaction.
- Frontend suite: 1590 passed. `tsc --noEmit` clean.

## Still open

The model sent ISO on a COLD FIRST ATTEMPT, before any validation error existed,
despite guidance reading `Format: MM/DD/YYYY` plus booklet text. That is a
model-compliance question this bead does not address -- tracked in
`polyglot-pdf-mq2je`, along with the model relaying a rejection to the user as
"I'm sorry, there was an error" while holding the specific reason.
