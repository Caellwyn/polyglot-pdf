---
date: 2026-07-06
bead: polyglot-pdf-bvmu
title: "roundtrip_fill.py (bakeoff filler) gains v2 checkbox_group + shared-field radio parity"
tags: [testing]
---

## Trigger

Continued the low-risk bead-clearing run. `scripts/bakeoff/roundtrip_fill.py`
is the offline eval/bakeoff harness's OWN PDF-fill implementation (deliberately
NOT importing the production filler, so it can independently verify). After bd
h76m.17 taught the PRODUCTION filler (backend/routes/pdf_fill_routes.py) the
schema-v2 group vocabulary, this harness diverged and would mis-score v2 kits.

## What shipped

Brought `roundtrip_fill.py` to parity with production for the two v2 group
shapes (mirroring the route VERBATIM in semantics, per the file's stated
fidelity contract):

- **checkbox_group (v2):** now shares the checkbox branch -- every selected
  option's own `pdf_field_name` is its widget; the field-level `pdf_field_name`
  is forbidden on a v2 group (form_models `_collect_v2_problems`). Previously a
  `checkbox_group` fell to the text-like else-branch and used the (forbidden)
  field-level name -> zero target widgets -> scored unfilled. Fixed in
  `_target_widgets_for_field`, `synth_value`, and `score_value_convention`.
- **shared-field radio (v2):** an option carrying only `pdf_on_value` (no own
  `pdf_field_name`) now resolves against the FIELD-level `pdf_field_name` -- one
  AcroForm field, several kid widgets told apart by on-state. New
  `_find_widget_by_state` / `_widget_has_on_state` mirror the route's
  state-matching kid lookup; the write is a direct xref V+AS to the chosen kid
  (no get_button_on_state/update, as production does). A synthetic
  `f"{name}\x00{on_value}"` target marker + `choice_shared` kind route it to the
  state-matching resolver instead of a plain name lookup.
- **Read-back** handles the shared-radio collision: sibling kids share one
  field_name (so a name-keyed expectation would overwrite) and xrefs are not
  trusted to survive save()'s GC/renumber -- so shared entries are keyed
  `xref:{n}` at write time and re-matched by name+on-state on read-back, scoped
  to that shared field's own kids.

Production filler UNCHANGED; existing text/radio/checkbox behavior unchanged.

## Verification

New `tests/test_roundtrip_fill.py` (8 tests): a synthetic v2 checkbox_group and
a synthetic shared-field radio PDF, asserting the expected per-option / kid
widgets resolve and round-trip as filled. Synthetic fixtures (NOT the real i-90
gold, which is still v1 -- schema_version None, type "checkbox" not
"checkbox_group"; the gold migration is bd h76m.15, not yet done) -- the
criterion is about the FILLER logic, which the synthetic v2 fields exercise
directly. Full backend+harness suite 1596 passed / 3 skipped.

## Fresh-eyes findings (adopted over two rounds): the _PDF_NAME_UNSAFE parity gap

Two Opus assess rounds, each catching a real gap:

**Round 1** caught that the harness had no `_PDF_NAME_UNSAFE` guard at all:
production's shared-radio write path (pdf_fill_routes.py `_PDF_NAME_UNSAFE`, bd
h76m.17) REFUSES to write an on-state carrying PDF-Name-unsafe chars
(`[\s/#()<>\[\]{}%]`), counting the field as skipped/unfilled -- but the harness
would attempt/write it, so the two scorers DISAGREE, defeating the harness's
purpose.

**Round 2** caught that my round-1 fix mirrored the REFUSAL but not the SCORING:
I skipped emitting the target for an unsafe on-state, which made the field
VANISH from the denominator entirely (not "unfilled" -- ABSENT). Probe:
safe-field + unsafe-shared-radio scored 100% in the harness where production
fills 50% -- the harness reported a HIGHER score than reality, hiding exactly
the fill defect it exists to surface. Production's refusal is `skipped_count +=
1` (in the denominator); "emit nothing" is `attempted == 0` (out of it). The two
production-identical outcomes were scored oppositely.

**Final fix:** the unsafe on-state STILL emits the `choice_shared` target; the
`_PDF_NAME_UNSAFE` check moved into `run()`, where it records an
ATTEMPTED-but-unfilled write (a `found:False` + `refused_unsafe_on_state:True`
attempt, no `resolved_widget`), exactly like the widget-not-found sibling -- so
`tally()` counts it in `attempted` but never in `filled`, matching production's
skipped/unfilled accounting. `failures` reports `reason:
"refused_unsafe_on_state"`. The test now drives `run()` and asserts
`attempted==1, filled==0, pct==0.0` (in the denominator, not vanished) plus a
target-emission test (the guard must NOT filter at target-selection time). 8
tests total.

## Note (subagent process hiccup, not a work defect)

The implementing subagent's final turn ended without a clean report (it got
stuck waiting on a background test run). The orchestrator verified the work
directly: the diff is correctly scoped (eval script + its new test only),
mirrors production with cited route line numbers, is ASCII-clean, and the full
suite passes. No defect from the incomplete report.

## Doc freshness

None -- offline eval script + test only; no tier-1/2 doc tracks it.
