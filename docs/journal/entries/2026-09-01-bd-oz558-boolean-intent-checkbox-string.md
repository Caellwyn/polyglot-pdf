---
date: 2026-09-01
bead: polyglot-pdf-oz558
title: "fix(pdf-filling): a standalone checkbox sent as the STRING \"true\" printed blank"
tags: [backend, pdf-filling]
---

## Trigger

`backend/routes/pdf_fill_routes.py`'s checkbox fill branch only handled a
real `bool` for a standalone checkbox. A STRING `"true"`/`"false"` -- the
literal boolean-intent forms `config.py` documents for the voice tool
contract, and the forms every FRONTEND reader
(`unwrapToBoolean`, `isCheckboxChecked`,
`validation.ts`'s boolean-intent carve-out) already treats as
checked/unchecked -- matched neither the comma-split branch (deliberately
excluded, since it is not an option selection) nor the
`isinstance(value, bool)` fill branch, so it fell to
`checkbox_unsupported_value` and was SKIPPED.

Net effect: a standalone checkbox the model set via voice could validate,
store, render ticked in the UI, paint ticked in the preview -- and print
BLANK on the PDF. Pre-existing on `origin/dev`, not introduced by any
recent branch.

## Fix

Coerce a boolean-intent string to a real `bool` immediately before the
existing `isinstance(value, bool)` check, but ONLY for a standalone
(no-options) checkbox -- mirroring the pre-existing comma-split branch's
own `options` scoping. An options-bearing `checkbox_group`'s `"true"` is
not a real option value either way, and is left to fall through to the
accurate `checkbox_unsupported_value` diagnostic, unchanged.

## Testing

New file `test_pdf_fill_checkbox_boolean_intent_string.py`, driving the
real `/fill-pdf` route against the shipped F1040 kit (a standalone
checkbox) and the shipped W-7 kit (an options-bearing `checkbox_group`,
for the scoping test) -- the `i-90` kit the bead's own exit criteria
named no longer exists on `dev` (removed by an unrelated, later PR), so
this test targets the two kits currently shipped with the matching field
shapes instead.

Mutation-verified the string coercion: removing it reddened exactly the
string-input tests (`"true"`, `"True"`), while the real-bool tests and
the `"false"` string test correctly stayed green.

Mutation-verified the options-bearing scoping guard, through TWO rounds
of self-correction:

1. My first version of that test asserted only on the resulting widget
   state (nothing ticked), which passed under BOTH the correct code and
   the mutated one -- a group field has no top-level `pdf_field_name`,
   so even a wrongly-coerced bool still fails closed via the unrelated
   `checkbox_no_pdf_mapping` check, producing the same "nothing ticked"
   outcome either way. Caught this by deliberately dropping the
   options-exclusion guard and observing the test stay green. Rewrote
   the assertion to check the DIAGNOSTIC event name instead
   (`checkbox_unsupported_value` vs. `checkbox_no_pdf_mapping`), using
   `structlog.testing.capture_logs`.
2. That version passed standalone but FAILED when the full backend
   suite ran (`1 failed, 3072 passed` -- caught only by running the
   complete suite, not this file alone). Root cause:
   `backend/utils/logging.py` configures structlog with
   `cache_logger_on_first_use=True`, and `pdf_fill_routes.py`'s `_log`
   is bound once at import time
   (`structlog.get_logger().bind(module=...)`); once some earlier test
   file has imported the module and triggered that caching,
   `capture_logs()`'s processor-chain reconfiguration never reaches the
   already-cached logger. `test_kit_guarded_delete.py` had already hit
   and documented this exact trap. Fixed by following its proven
   pattern: `monkeypatch.setattr(pfr, "_log", _Spy())` on the module
   object directly, rather than reconfiguring structlog globally.
   Re-ran the full backend suite after the fix: 3073 passed, 0 failed.

Also updated `docs/components/pdf-filling.md`'s checkbox contract
paragraph, which described only the `bool`/`list`/comma-string shapes and
said nothing about the boolean-intent string case this bead fixes.

## Review

Two rounds, both `NO-GAPS`. The Opus cross-surface round found one
(non-blocking, fixed inline) doc/comment inaccuracy: the original
docstring's justification for making the new coercion case-insensitive
overstated frontend agreement -- it named `unwrapToBoolean` and
`isCheckboxChecked` as already treating these strings as boolean, but
both compare CASE-SENSITIVELY (`=== 'true'`); only `validation.ts`'s own
carve-out is case-insensitive. Corrected the doc, the matching code
comment, and the test docstring to name `validation.ts` specifically and
note that a mixed-case value is not actually reachable in practice
anyway -- the backend's own `field_validator.py` is case-sensitive too,
so a mixed-case AI-applied value never survives into `form_state` for a
client to disagree over. Filed as `polyglot-pdf-l1rtq`, fixed in this
same diff.
