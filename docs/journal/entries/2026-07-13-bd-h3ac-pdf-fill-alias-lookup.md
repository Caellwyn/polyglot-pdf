---
date: 2026-07-13
bead: polyglot-pdf-h3ac
title: "PDF fill lookup is []-alias-aware (a field value under the other bracket variant fills, not blanks)"
sprint: 12
tags: [refactor, testing]
---

## Trigger

Surfaced by the got6 (bd polyglot-pdf-got6) Opus outer review as a high-confidence
regression the got6 fix would EXPOSE, and flagged as resolve-before-merge. Bundled
into the got6 PR because got6 causes the exposure and this is its fix -- shipping
got6 alone would regress the PDF.

`backend/routes/pdf_fill_routes.py` built its `field_lookup` (and `field_mappings`)
keyed by the RAW schema `field.id` and did `field_lookup.get(field_id)` with NO
`[]`-alias fallback -- unlike the frontend STATE readers (readFieldEntryWithAlias,
buildValidatorFields.valueFor, markFieldsSteered, get_form_state), which all try
both bracket variants. (One frontend reader is NOT alias-aware -- the in-browser
PDF preview overlay, PDFViewer.tsx, reads exact-key only; got6 exposes it there
too, tracked separately as bd polyglot-pdf-7sdc. That is preview-only cosmetic --
the DOWNLOADED PDF is correct once this backend fill fix lands.) Gemini
inconsistently adds/drops the trailing `[]` on
checkbox-group ids (bd 5k52), so a value can arrive under `race` while the schema
id is `race[]` (or vice-versa). The exact-key lookup missed, logged
`field_not_in_schema`, and SKIPPED the field -> it filled BLANK on the
downloaded/printed/previewed PDF.

This was MASKED before got6: `updateField` used to leave BOTH bracket-variant keys
in `fieldValues` after a migration, so the schema-id-matching copy (often stale)
still filled the PDF. got6 correctly dedups to one entry under the last-written
key, EXPOSING this backend gap -- if the surviving key is the non-schema-id
variant, the correct value is now dropped from the PDF.

## What shipped

The PDF fill lookup is now `[]`-alias-aware, matching every frontend reader. When
building `field_lookup` + `field_mappings`, each field is ALSO registered under its
`[]`-alias variant (guarded: an exact id write is unconditional and wins; an alias
only fills a gap), so `field_lookup.get(field_id)` / `field_mappings.get(field_id)`
resolve whichever bracket variant the payload key uses. A field whose id is `x[]`
fills from a payload keyed `x`, and vice-versa.

**The exact-wins invariant** holds even when BOTH `x` and `x[]` are real distinct
schema fields: the exact registration is unconditional (so a real exact id always
overwrites any alias registered for it), and the alias registration is guarded
(`if alias_id not in ...`), so a real exact id is never clobbered by another
field's alias -- each resolves to its own widget. Pinned by a test.

## Lessons

An alias/dual-key scheme needs CONSISTENT alias handling across every reader, not
just the frontend. The frontend had alias-aware reads everywhere; the backend PDF
lookup did not, and the frontend's duplicate-key sloppiness (the got6 bug) was
quietly compensating for it. Fixing the frontend hygiene (got6) surfaced the
backend inconsistency (this bead) -- two halves of "readers and writers must agree
on key canonicalization." Fixing the exact-key readers to be alias-aware is more
robust than relying on a duplicate to mask them.

## Doc freshness

No doc change: the `[]`-alias handling is an internal contract-2 detail already
described in the terminology/validation docs (field-id brackets); this restores the
backend PDF reader to the alias-aware behavior the frontend readers already have.

## Files touched

- backend/routes/pdf_fill_routes.py -- register each field's `[]`-alias variant in
  `field_lookup` + `field_mappings` (exact wins; alias fills a gap).
- backend/tests/test_pdf_widget_lookup.py -- 3 alias-resolution tests (value keyed
  without brackets fills a bracketed schema id; the reverse; exact wins when both
  variants are real distinct fields).
