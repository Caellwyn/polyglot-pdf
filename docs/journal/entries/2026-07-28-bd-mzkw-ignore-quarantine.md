---
date: 2026-07-28
bead: polyglot-pdf-mzkw
title: "Sprint-17 C4: the Ignored (grey) quarantine escape hatch"
tags: [editor, frontend, ux]
---

## Trigger

Epic polyglot-pdf-did2 (sprint 17), C4 -- the last child. A field with no real
PDF widget behind it cannot be fixed by a human at all (there is nothing to bind
it to), so one un-fixable field could block a whole form from being completed.
The maintainer asked for a way to set such a field aside: "a human only flag,
and fully reversible... a non-destructive way to get past these kinds of
apparent errors."

Framing that shaped every decision: this is an ESCAPE HATCH, not a primary tool
-- it leaves cruft in the schema, and C1's extraction invariant should make it
rarely needed. NO delete capability (the maintainer barred it: "I don't want
legitimate fields getting accidentally deleted with no way to get them back").

## Mechanism: quarantine, not a flag

Ignoring MOVES the field object out of `schema.fields` into a top-level
`_ignored_fields` stash and drops its id from its section, in ONE schema commit.

That choice (over an in-place `_review.status='ignored'`) buys correctness for
free. Everything downstream reads `schema.fields`: the Pydantic model, the
backend lint, the mark-complete gate, the 783r translation-coverage sweep, the
voice app's field lookups, the PDF filler. A quarantined field is invisible to
all of them with ZERO changes on those paths -- an in-place flag would have
required every one to learn to skip it. The stash survives every save path
(stripEditorState strips only the per-field `_ungroup` key) and the backend
tolerates it (FormSchema uses Pydantic's default extra="ignore"; the draft-save
route stores the raw dict verbatim). Because useSchemaHistory snapshots whole
schemas, one Cmd+Z reverses the whole move for free.

## What shipped

- `utils/ignoreField.ts` (new): `IgnoredFieldEntry` (the field verbatim + its
  section id + its index + a timestamp), `getIgnoredFields`, `isIgnored`,
  `dependentsOf`, `ignoreBlockReason`, `describeIgnoreBlock`, `ignoreField`,
  `restoreField` -- all pure, returning a NEW schema for one commit.
- **The dependents detector** walks all seven surfaces a field id can hide in,
  taken from fieldRename.ts's retarget walk (the one place that already had to
  know them all): other fields' show_if/require_if (legacy AND composite
  buckets), section.show_if, copy_to, copy_from, address_fields, and
  supplements[].fields. It is fieldRename's read-only twin -- rename REWRITES
  references, ignore must REFUSE while any exist, because there is no correct
  automatic rewrite for "this trigger is going away". Section membership is
  deliberately NOT a dependent: that is the field's own home, which ignoring
  relocates by design. Exact-string id matching, matching every other reference
  walker (no bracket-alias cleverness -- that class of bug lives in runtime
  value lookups, and diverging would disagree with the rename path).
  It reuses validation.ts's `conditionAtoms`, now exported: three near-identical
  flatteners already exist across the codebase and a fourth would be worse.
- **Gates**: required first (parking a required field would silently drop an
  answer the form needs), then dependents. Both return a reason the UI shows.
- **UI**: "Ignored -- not on this form" as a fourth option in the review
  dropdown, but routed through its OWN callback (`App.handleIgnoreField`), not
  `withReviewStatus` -- quarantining relocates the field, which a single-field
  patch structurally cannot do. `window.confirm` first (matching
  SectionManager's precedent), worded to say the field is set aside and NOT
  deleted. Selection drops on success (the field has left fields[]).
  A grey "Ignored (N)" bucket in FieldList, sourced from the stash and
  deliberately outside `visibleOrderedFields`, so the review jump never stops on
  a parked field and nothing counts it. Each row carries an Un-ignore button and
  shows the author's review note ("phantom field") as its tooltip -- ignoring
  pairs with the note that records WHY.
- **Restore-to-orphan fallback**: if the original section was deleted while the
  field sat quarantined, it comes back WITHOUT a section_id (the editor's
  Uncategorized bucket) rather than pointing at a dead section, which would be a
  validation error.

## Tests

- `ignoreField.test.ts` (21): every gate (each of the seven dependent surfaces,
  composite-bucket nesting, required, self-reference, section-membership-is-not-
  a-dependent), exact-position restore, the section-deleted fallback, index
  clamping, note preservation, no-op on unknown ids, input immutability,
  stripEditorState + JSON round-trip survival, and malformed-stash tolerance.
- `FieldEditor.ignore.test.tsx` (8): the option appears only when wired,
  confirm-before-ignore (including that the dialog says NOT deleted), cancel
  does nothing at all, Ignored NEVER routes through onUpdateField (a guard
  against a future refactor collapsing it into withReviewStatus), ordinary
  statuses still do, disabled-with-reason, and handler-returned block reasons.
- `FieldList.ignored.test.tsx` (7): the bucket's presence/absence, count,
  expansion, Un-ignore wiring, read-only mode, the note tooltip, exclusion from
  the review jump, and exclusion from the section count.
- Full schema-editor suite green (61 files, 871 tests); tsc clean.

## Live verification

Ran the real modules from the dev server against the shipped 132-field i-90
kit: a field with genuine dependents was refused ('has-dependents'); a free
field quarantined cleanly (132 -> 131 fields, one stash entry, completion total
dropped to match); and restore came back byte-identical in both fields and
sections.

## Robustness note

The first App-level run surfaced `TypeError: schema.sections is not iterable` --
the detector runs on every FieldEditor render, including mid-load states where
an array may be absent. All four entry points now guard their inputs, matching
the never-throw-on-shape discipline every other walker in the editor follows.
