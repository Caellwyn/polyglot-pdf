---
date: 2026-06-12
bead: polyglot-pdf-w3ic
title: "Empty-value handling: confirm blank optional fields (w3ic) + clear selects on empty update (jbxm)"
tags: [hotfix, testing]
---

## Trigger

Two maintainer live-demo reports (2026-06-11), bundled because they share
files and a theme (Gemini vs empty values): (1) polyglot-pdf-w3ic -- Gemini
got stuck when the user said they had no middle name; the frontend blocked
confirm_field on the empty value ("confirm_field cannot take (no usable
value)"); (2) polyglot-pdf-jbxm -- Gemini could not clear the state dropdown
when the user moved from West Virginia to British Columbia.

## What shipped

w3ic: handleConfirmFieldRequest's hasUsableValue treated every '' as
unconfirmable. For a REQUIRED field '' can never land (the wpw.3 apply gate
rejects it), so an entry holding '' is always an intentionally blank OPTIONAL
field -- now confirmable (carve-out keyed on field.validation?.required,
mirroring the existing blank-optional-checkbox-group carve-out).

jbxm: fieldManager.handleSelect had no empty-string path -- update_form_fields
with '' on a select logged a warning and left the old selection. Now '' clears
the select (placeholder option if present, else selectedIndex -1) and
dispatches change/input. Backend field_validator already skips validation for
'' (no backend change). One terse CONSTRAINTS bullet added to both
SYSTEM_INSTRUCTION and JIT_SYSTEM_INSTRUCTION telling Gemini to use
update_form_fields("") for N/A optional fields and for clearing any field.

Test spec updated at closeout: the confirmloop test asserting "entry exists
but empty -> unconfirmable" encoded the pre-w3ic contract; it now splits into
required-empty (loop-breaker still fires) and optional-empty (confirms, no
re-prompt). Frontend suite 273/273 green; backend 290 passed.

Deferred (decision noted): no per-field preferred_empty_value schema property
in this pass -- empty string is the default N/A convention; a schema-level
convention can be a follow-up bead if a form needs a literal 'N/A' printed.

Fresh-eyes triage breakdown: recorded in the PR merge ping.

## Lessons

A carve-out that changes a guard's contract ("empty = unconfirmable") has a
test encoding the OLD contract somewhere -- run the affected suite before the
PR, and update the spec deliberately (split the case, keep both behaviors
pinned) rather than deleting the assertion.

## Doc freshness

No tier-2 doc quotes the unconfirmable-guard or select-clear behavior. Docs
flagged stale by the checker track files this branch did not change
(worktree-creation mtime noise); reviewed and left.

## Files touched

- frontend/src/webFormConnection.ts -- optional-empty carve-out in
  hasUsableValue (w3ic).
- frontend/src/shared/fieldManager.ts -- empty-string clear path in
  handleSelect (jbxm).
- backend/config.py -- one CONSTRAINTS bullet in both instruction templates.
- frontend/src/webFormConnection.confirmloop.test.ts -- spec update + new
  optional-empty test.
- docs/journal/entries/2026-06-12-bd-w3ic-jbxm-empty-value-handling.md --
  this entry.
