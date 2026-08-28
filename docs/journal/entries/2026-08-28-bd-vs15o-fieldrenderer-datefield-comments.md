---
date: 2026-08-28
bead: polyglot-pdf-vs15o
title: "chore(schema-forms): stale FieldRenderer comment + documented DateField format-key gap"
tags: [schema-forms, doc-freshness]
---

## Trigger

Two small alignment gaps noticed while tracing bd md20o/mpfmr out into
untouched files: a comment describing TextField's pre-md20o behavior that
no longer holds, and a latent priority-chain mismatch between the frontend
DateField and the backend's `_resolve_date_format` over a flat `format` key
the frontend never reads.

## What shipped

1. `FieldRenderer.tsx`'s `case "number"` comment rewritten to describe
   TextField's actual current behavior (unconditional `type="text"`), with
   the reason the `{...field, type: "text"}` rewrite still matters even
   though TextField no longer special-cases email/tel.
2. `DateField.tsx` gets a documented, named gap (not a behavior change,
   per the bead's own escape hatch): the backend's `_resolve_date_format`
   reads a flat `format` key before `help.format_hint`; the frontend never
   reads `field.format` at all. Verified across all 8 shipped date fields
   (i-90, w7, f1040) that none sets the flat `format` key, so this specific
   priority-inversion is latent -- though 2 of those 8 (f1040's deceased-date
   fields) set neither key, a separate pre-existing gap not addressed here.
   Pinned with a new test in `no-coercing-input-types.test.tsx`
   (mutation-verified: adding a `field.format` fallback to the placeholder
   resolution correctly reddens the new test).

## Lessons

Nothing novel -- a routine comment-and-documentation-align bead with an
explicit "or document it" escape hatch in its own exit criteria, which
kept this from becoming a behavior-change decision.

## Files touched

- `frontend/src/schema-forms/components/FieldRenderer.tsx` -- stale comment
  fixed.
- `frontend/src/schema-forms/components/fields/DateField.tsx` -- gap
  documented at the placeholder-resolution line.
- `frontend/src/schema-forms/components/fields/no-coercing-input-types.test.tsx`
  -- new pinning test for the documented gap.
