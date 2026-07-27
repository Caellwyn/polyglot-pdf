---
date: 2026-07-26
bead: polyglot-pdf-u8t6
title: "Editor UX: per-field human review status (unreviewed / reviewed-correct / needs-follow-up) + notes"
tags: [editor, frontend, ux]
---

## Trigger

Maintainer report: the schema-editor had no way to mark an amber "needs review"
field as reviewed-and-correct, and no place for editors to leave notes. Red
error fields also read as "there is an error" without (the maintainer noticing)
where the reason was shown.

## What the status model was

Field status was ENTIRELY derived, never author-owned. `checkFieldComplete()`
computes green/amber/red purely from the field's contents (spoken name, help
text, PDF mapping); a backend lint ERROR also forces red. The error/amber REASONS
were already exposed -- in the status icon's hover `title` tooltip (FieldList) and
the "Why this field is flagged" banner (FieldEditor, bd 0x10.6) -- but there was
no human sign-off layer at all, so an auto-amber field could never be dismissed
by a person's judgment.

## What shipped

A per-field, author-owned review status with three states + a notes box, layered
OVER the automatic derivation (maintainer-approved design, both defaults taken):

- `types/schema.ts`: `FieldReview { status, note? }` and `_review?` on
  `FormField`. `FieldReviewStatus = unreviewed | reviewed_correct | needs_followup`.
- `utils/reviewStatus.ts` (new, single source of truth): `getReview`,
  `withReviewStatus`, `withReviewNote`, `effectiveStatus`, `isReviewTarget`.
  Precedence: **error > needs_followup > reviewed_correct > automatic**. A real
  ERROR ALWAYS wins -- you cannot sign off a structurally broken field (they block
  the publish gate). `reviewed_correct` turns an auto-amber field green;
  `needs_followup` is a flagged review target with a note. The write helpers drop
  the `_review` key when a field is reset to neutral with no note, so a reset
  field serializes clean.
- `FieldList.tsx`: `getFieldStatus` now delegates to `effectiveStatus`; a distinct
  amber FLAG icon for `followup`; the review note/sign-off leads the tooltip; the
  "Next to review" jump + `hasReviewTarget` use `isReviewTarget` (skip
  reviewed_correct, stop on needs_followup).
- `FieldEditor.tsx`: a "Review" section (status `<select>` + notes `<textarea>`)
  above Basic Properties, committing through the `_review` helpers.

## Why it is round-trip-safe (no backend change)

`_review` is PURE editor-workflow metadata; it never reaches the voice runtime or
the Pydantic model. It survives save/load because:

- Local (File System Access) save: `stripEditorState` only strips the `_ungroup`
  session stash; `_review` passes through `JSON.stringify` untouched.
- Hosted draft save (`PUT /api/editor/kits/{id}/schema`) and lint
  (`POST /api/editor/lint`) both take a RAW `dict` and store/lint it verbatim --
  no Pydantic round-trip.
- The publish gate (`POST /kits/{id}/status` -> complete) VALIDATES via
  `FormSchema.model_validate` but does not re-store the parsed object, so the
  extra key survives promotion in the stored blob. The backend `FormField` uses
  Pydantic default `extra="ignore"`, which drops unknown keys only from the
  VALIDATED object, never from the stored JSON.

## Tests

- `utils/reviewStatus.test.ts` (14): precedence (error beats sign-off; lint ERROR
  beats sign-off; reviewed_correct beats auto-amber; unreviewed falls through),
  target predicate, clean serialization, and a `stripEditorState` round-trip.
- `components/FieldList.review.test.tsx` (5): green-over-amber, red-stays-red,
  flag icon + note tooltip, jump skips reviewed_correct / stops on followup,
  disabled jump when all signed off.
- `components/FieldEditor.review.test.tsx` (4): control renders current state,
  status/note commits carry `_review`, reset-to-neutral drops the key.
- Full schema-editor suite green (57 files, 793 tests); `tsc --noEmit` clean.

## Scope note

Fields only -- no section-level review (maintainer-approved). A section rollup
was considered and deferred; not filed as a bead (speculative, no demand).

## Closeout notes

- Doc-freshness (closeout_prep) flagged STALE `docs/components/*` and
  `docs/standards/*` docs, but ALL are backend/frontend docs stale vs OTHER recent
  `dev` commits (config.py, live_ai_gemini.py, schema-forms/types/schema.ts et al.,
  dated 2026-07-25/26) -- NONE caused by this change. This diff touches only
  `schema-editor/` + this journal entry; the nearest-looking one,
  `docs/components/schema-forms.md`, is stale vs the frontend voice-app
  `frontend/src/schema-forms/types/schema.ts`, a different file in a different app
  than the editor's `schema-editor/src/types/schema.ts`. No doc update owed by this
  bead.
- Prep ran the backend pytest suite (1299 passed, 1 skipped); this change is
  frontend-only (schema-editor), covered by its own vitest suite (793 passing).

## Follow-on work (out of scope, filed)

While verifying the editor, the maintainer surfaced red/amber "phantom" signature
fields: a `pdf_field_name` is set but no widget highlights in the PDF preview, and
the error ("Missing PDF field name") is misleading. Root-caused to the extraction
pipeline: the LLM enrichment can ADD fields the deterministic PyMuPDF dump never
identified, `type=signature` is ONLY ever LLM-inferred (the deterministic dump maps
a real signature widget to a `text` field), and a missing/degenerate widget rect
yields a field with no `pdf_position` (so no preview highlight) -- with neither
`schema_repair` nor `schema_lint` flagging it. Filed as bd `polyglot-pdf-emap`
(pipeline reconcile LLM output against the dump). Editor-side mitigations (accurate
error text + a non-destructive 'ignore' state reusing this bead's `reviewStatus.ts`;
NO delete, per maintainer -- deletion risks unrecoverable loss) are a SEPARATE
follow-up PR, not this one.
