---
date: 2026-07-06
bead: polyglot-pdf-f6lj
title: "Scope the PDF-fillability rule's shared-name clause to radio"
tags: [refactor, conventions]
---

## Trigger

`backend/models/form_models.py`'s v2 PDF-fillability rule computed, for BOTH
`checkbox_group` and `radio`, `fillable = option.pdf_field_name OR (field-level
pdf_field_name AND option.pdf_on_value)`. The second clause -- the shared-NAME
shape -- is live for radio (a shared-field radio is valid v2) but DEAD for
checkbox_group: the rule immediately above rejects any checkbox_group that carries
a field-level `pdf_field_name` at all, so that clause can never fire for a group.
The dead branch read as if v2 supports a shared-name checkbox matrix, which it
does not (radio-only by design). It was exactly what made bd u632 (closed
won't-fix) look like a valid-but-unfillable shape and cost a full investigation to
disprove.

## What shipped

Split the single `if f.type in (CHECKBOX_GROUP, RADIO)` fillability loop into two
type-specific branches:
- **checkbox_group**: an option is fillable only via its own `pdf_field_name`
  (message: "a checkbox_group option needs its own pdf_field_name"). The
  shared-name path is not offered -- with a comment citing the :827 forbid and the
  producers (picker / migrator / editor-merge) that all strip a lifted name.
- **radio**: unchanged -- fillable via option `pdf_field_name` OR the shared-name
  (field-level `pdf_field_name` + option `pdf_on_value`) shape.

Behavior-preserving: the set of schemas that validate is identical (a
checkbox_group with a `pdf_on_value`-only option was already non-fillable, because
the field-level name it would need is forbidden at :827; now it is rejected
directly by the group branch instead of slipping past a clause that could never
apply to it). Only the checkbox_group failure MESSAGE changed ("needs its own
pdf_field_name" vs the old shared "needs option pdf_field_name, or a field-level
pdf_field_name plus option pdf_on_value") -- more accurate for a group.

Added `test_v2_checkbox_group_pdf_on_value_only_option_is_not_fillable` to pin the
intent so the dead clause cannot silently return. Full model suite 51/51; model +
roundtrip + lint + group-fill 100/100.

## Lessons

Nothing new generalizes. The meta-lesson is already banked from u632: a validator
that offers a code path a sibling rule forbids is a latent trap -- it reads as
support for a shape that is actually illegal. Keep type-specific contract rules
type-specific.

## Doc freshness

No tier-2 doc `**Tracks:**` this specific validator rule (form_models.py is not in
a component doc's tracks for the fillability logic; the v2 contract is described at
the terminology/standards level, unaffected -- the SET of valid schemas is
unchanged). Nothing to bump.

## Files touched

- `backend/models/form_models.py` -- split the fillability rule into
  checkbox_group (own-name-only) and radio (own-name-or-shared) branches.
- `backend/tests/test_form_models_v2.py` -- pin the checkbox_group
  pdf_on_value-only rejection.
- `docs/journal/entries/2026-07-06-bd-f6lj-fillability-clause-radio-only.md` -- this entry.
