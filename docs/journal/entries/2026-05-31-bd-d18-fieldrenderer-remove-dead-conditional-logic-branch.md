---
date: 2026-05-31
bead: polyglot-pdf-d18
title: "FieldRenderer: remove dead conditional_logic branch + fix number-case comment"
tags: [refactor]
---

# polyglot-pdf-d18: FieldRenderer dead branch + misleading comment

Two small, behavior-preserving fixes in
`frontend/src/schema-forms/components/FieldRenderer.tsx`, surfaced by the
fresh-eyes review of the schema-forms doc (PR #33, bd 93c).

## Trigger

Documenting `schema-forms.md` against the code, the reviewer noticed two
inconsistencies between FieldRenderer and what the types/components actually
support. Filed as d18 (a 1m2 duplicate was created by a retried `bd create` and
closed as a dup).

## What shipped

- **Removed a dead conditional clause.** `shouldUnlock` OR'd
  `field.conditional_behavior?.unlock_method` with
  `field.conditional_logic?.unlock_method`. `conditional_logic` is **not** a
  property of the `FormField` type (`types/schema.ts` has `conditional_behavior`,
  `controls_fields`, `conditional_fields`), and it was the *only* reference to
  `conditional_logic` in the entire frontend — so the clause was permanently
  `undefined`. Dropped it; `shouldUnlock` now reads `conditional_behavior` only.
  No behavior change (the live clause already covered every real case).
- **Corrected the `number` case comment.** It claimed "TextField with type=number
  (HTML5)", but the code passes `{ ...field, type: "text" }` and `TextField`
  computes its input type as `email`/`tel`/else-`text` — there is no `number`
  branch, so a number field renders as a plain text input. Comment now says that.

## Lessons

- **Docs review doubles as a code audit.** Verifying doc claims against source
  caught two latent code inconsistencies a reader (or a future maintainer relying
  on the comment) would have been misled by. Cheap to fix at the point of notice;
  kept out of the docs PR so each change stays single-purpose.

## Doc freshness

No tier-2 doc tracks FieldRenderer's internals directly (schema-forms.md describes
the routing behavior, which is unchanged and still accurate). No doc bump needed.

## Files touched

- `frontend/src/schema-forms/components/FieldRenderer.tsx` — remove dead clause +
  fix comment
- `docs/journal/entries/2026-05-31-bd-d18-...md` — this entry
