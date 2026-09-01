---
date: 2026-09-01
bead: polyglot-pdf-tj430
title: "test(resume): split the 502 test so it actually pins BOTH store-error loads"
tags: [backend, testing]
---

## Trigger

`test_an_UNREADABLE_kit_is_a_502_not_an_unhandled_500` was written to pin
the `FormKitStoreError -> 502` mapping on BOTH loads in `resume_form`
(the reference PDF load, `pdf_fill_routes.py:912`; the schema load,
`pdf_fill_routes.py:942`), but only actually exercised the first: the
test set `store.load_pdf_bytes = _boom` AND `store.load_schema = _boom`,
and since the reference load runs first and raises, the schema load's
own `except FormKitStoreError` handler -- the gap an earlier review round
found and the reason this handler exists at all -- was never reached.

Verified by mutation before fixing: deleting only the schema-load
handler left the test green (25 deselected, 1 passed on the targeted
file); deleting only the reference-load handler correctly failed it.
Separately, the assertion `exc.value.status_code in (404, 502)` doesn't
pin the 502 mapping specifically even for the load it does reach.

## Fix

Split into two tests, each isolating exactly ONE load's failure:
- `test_an_UNREADABLE_REFERENCE_pdf_is_a_502_not_an_unhandled_500`:
  only `load_pdf_bytes` fails.
- `test_an_UNREADABLE_SCHEMA_is_a_502_not_an_unhandled_500`: the
  reference load SUCCEEDS (returns the real W-7 bytes) so the schema
  load is actually reached, and only `load_schema` fails.

Both now assert `status_code == 502` exactly, not `in (404, 502)`.

## Testing

Mutation-verified both directions: deleting only the schema-load
handler reddens exactly the schema test (an unhandled `FormKitStoreError`
propagates), leaving the reference test green. Deleting only the
reference-load handler reddens exactly the reference test, leaving the
schema test green. Restored; full `test_resume_form_route.py` (43
passed, 14 skipped -- the skips are pre-existing i-90-kit-dependent
tests, unrelated) stays green.
