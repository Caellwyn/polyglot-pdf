---
date: 2026-07-14
bead: polyglot-pdf-eb4z
title: "Two []-alias holdouts closed: field_mappings exact-wins symmetry (backend) + PDFViewer overlay alias read (frontend)"
sprint: 12
tags: [bugfix, testing, pdf-fill]
---

## Trigger

Two latent []-alias gaps left behind by the h3ac fix
([the h3ac entry](2026-07-13-bd-h3ac-pdf-fill-alias-lookup.md)), both filed as
follow-up beads:

- **polyglot-pdf-eb4z** (backend): h3ac's own journal claimed an "exact-wins
  invariant ... each resolves to its own widget", but that was true only for
  `field_lookup`, not for `field_mappings`.
- **polyglot-pdf-7sdc** (frontend): h3ac's journal claimed "every FRONTEND reader
  tries both variants", but `PDFViewer.tsx` (the in-browser overlay preview) did
  NOT -- it read `fieldValues[field.id]` exact-key only.

Neither is reachable in any CURRENT kit (a repo scan found ZERO distinct `x`/`x[]`
id collisions, and the overlay one is cosmetic-only), so no shipped regression --
these close the invariant holes before a schema that would trip them can exist.

## eb4z -- backend field_mappings alias asymmetry

In `backend/routes/pdf_fill_routes.py`, `field_lookup` wrote each field's EXACT id
unconditionally, so a real exact id always won over any sibling's alias. But
`field_mappings` wrote the exact id only INSIDE `if pdf_field_name:`. So when two
DISTINCT schema fields `x` and `x[]` both exist and the exact-id field (`x`) has NO
field-level `pdf_field_name` (legit for a mapping-less text field), `x` never wrote
its own `field_mappings` entry -- and the sibling `x[]`'s guarded alias write
(`field_mappings['x'] = W_bracket`) was then the only answer to
`field_mappings.get('x')`. A text value keyed `x` filled `x[]`'s widget.

**Fix:** collect the set of real schema ids first, then split the build into two
passes: pass 1 writes every real exact id (lookup + mapping) unconditionally; pass
2 registers `[]`-alias variants but SKIPS any alias key that is itself a real
schema id. This is order-independent and gives `field_mappings` the same
"a real exact id is never answered by a sibling's alias" guarantee `field_lookup`
already had. (It also tightens `field_lookup`: an alias can no longer shadow a real
field there either, regardless of iteration order.)

Tests: `test_mapping_less_exact_field_is_not_filled_by_a_siblings_alias` and its
reverse-bracket twin in `backend/tests/test_pdf_widget_lookup.py`.

## 7sdc -- PDFViewer overlay exact-key read

`frontend/src/pdf-view/PDFViewer.tsx` resolved a field's overlay value with a bare
`fieldValues[field.id]`. After the got6 dedup (bd polyglot-pdf-got6) collapsed the
duplicate schema-id-keyed entry, exactly ONE `fieldValues` entry survives under the
last-written key -- so a checkbox-group value written under the OTHER bracket
variant than the schema id left `fieldValues['race[]']` undefined and the overlay
rendered BLANK for a field that actually has a value. NOT data loss: the downloaded
PDF sends the whole map to the h3ac-alias-aware backend fill, so it is correct; the
lightweight in-browser overlay was the only wrong surface.

**Fix:** read via the existing `readFieldEntryWithAlias`
(`frontend/src/schema-forms/utils/fieldValue.ts`) -- the same bracket fallback the
validator projection and backend fill use. One-line reader swap; `fillStateFor`
already consumes the resolved wrapped entry.

Test: `frontend/src/pdf-view/PDFViewer.aliasOverlay.test.tsx` renders the real
`PDFViewer` and asserts the overlay's `data-fill-state` for a bracketed schema id
whose value sits under the unbracketed key (and the reverse), plus the neither-key
empty case.

## Scope note

The click-to-edit `FieldEditPopover` (also in `PDFViewer.tsx`) still reads
`fieldValues[editingHere.id]` exact-key. That is an EDIT surface, not the "shows
blank" overlay the bead targets, and its exit criteria name only the overlay's
value resolution -- left as-is, deliberately out of scope.
