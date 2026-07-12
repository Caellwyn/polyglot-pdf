---
date: 2026-07-12
bead: polyglot-pdf-6cfu.6
title: "All four shipped kits retrofitted onto derived divisions (post-#401 positions); f1040 income lines re-filed; w7/w7-2 sections now label-match content; both suites green"
tags: [extractor, schema-editor, testing, form-kits]
---

## Trigger

Sprint 10's last bead (deliberately LAST per maintainer direction:
exploration -> implementation -> testing -> retrofit). With derivation in
extraction (6cfu.2), editor section management + the To-review gate (6cfu.3),
the simplified view verified (6cfu.4) and the validator window measured
(6cfu.5), the shipped kits move onto derived divisions.

The bead was first run on 2026-07-11 (branch feat/6cfu6-retrofit-kits), but
that run derived w7/w7-2 divisions from the PRE-fix pdf_positions and so
produced sections whose LABELS did not match their field CONTENT (the shipped
field-to-widget off-by-one). PR #401 (bd polyglot-pdf-ivh9) has since MERGED,
correcting w7/w7-2 pdf_field_name + pdf_position. This entry records the
re-run onto origin/dev (post-#401), which supersedes the parked branch.

## What shipped

`derive_sections.derive_and_apply` re-ran over the four tracked kits
(pure derivation from existing `pdf_position`/widget names + the PDFs -- no
re-extraction), on top of origin/dev (post-#401 positions). Results:

| kit | strategy | parts/sections | notes |
|-----|----------|----------------|-------|
| f1040 | printed-heading | 2p / 13s | Dependents split 21+21 balanced; Income = 34 fields after re-file |
| i-90 | name-convention | 8p / 28s | parts from P{N} widget prefixes; two-column pages correct |
| w7 | printed-heading | 1p / 8s | Other Information stays whole (21 fields, cap 40); sections now label-match content |
| w7-2 | printed-heading | 1p / 8s | same shape as w7 |

**The human re-filing step, performed as part of the retrofit:** f1040's four
positionless fields (`fld_1a..fld_1d`, income lines 1a-1d -- a pre-existing
kit gap, no `pdf_position`) landed in "To review (unplaced)" as designed; a
shipped kit must not carry an un-reviewed bucket (the `to-review-pending`
lint ERROR blocks publishing), and their semantic home is unambiguous, so the
retrofit re-filed them into **Income** (34 fields, still under cap 40) and
dropped the emptied to-review section + `part_to_review` part, exactly the
workflow the editor's merge path performs. Every kit now:
`FormSchema.model_validate` clean, ZERO lint errors, zero to-review sections,
all section `page_number(s)` 1-based.

**Divisions-only contract held:** field content is byte-identical to
origin/dev for all four kits apart from `section_id` -- no field added,
removed, or otherwise mutated. (Verified by diffing each field body with
`section_id` stripped: 0 content changes across 176/132/59/59 fields.)

## w7/w7-2 label-vs-content now correct (bd polyglot-pdf-1i79)

The #401 mapping fix moved each field onto its true printed row, so
re-deriving clusters fields under the RIGHT headings. Verified live in the
local stack (W7):

- Section 2 **Name** -> the 1a/1b name fields only
- Section 3 **Applicant's Mailing Address** -> `mailing_street`, `mailing_city`
- Section 4 **Foreign (non-U.S.) Address** -> `foreign_street`, `foreign_city`
- Section 5 **Birth Information** -> `dob` (previously mis-clustered under
  Foreign Address before #401)

This resolves bd polyglot-pdf-1i79 (a duplicate of the ivh9/#401 mapping fix
that also asked for the division regeneration this retrofit performs). One
residual, filed as known-and-accepted: `applicant_phone`/`delegate_name`
cluster under **Acceptance Agent's Use ONLY** rather than **Sign Here** --
W-7's signature block is a two-column layout (applicant left, acceptance
agent right, both headings at y~613); those two boxes sit below both headings
and the geometric clusterer assigns them by column. This is a heading-boundary
nuance of the two-column layout, NOT the off-by-one bug (pdf_positions are
correct and the fill path round-trips), and it is materially better than the
pre-#401 state.

## Verification

- **Backend suite: 1016 passed, 2 skipped** (full run, not -k filtered; the
  unfillable-field baseline test unaffected -- fillability did not change,
  only divisions).
- **Frontend vitest: 923 passed** (57 files, forks pool).
- **Local-stack walkthrough (vite :5173 + uvicorn :8000 on the retrofitted
  kits, FORM_KITS_LOCAL_ROOT=worktree/form-kits):** the demo lists all four
  kits and opens W7 -- "Section 1 of 8 . Page 1 (top)", then Name / Mailing /
  Foreign / Birth sections each render with correct label-and-content (field
  DOM `name` attributes confirmed: mailing_street/mailing_city, foreign_street/
  foreign_city, dob). W7's schema also round-trips the /api/fill-pdf endpoint
  (valid 162 KB PDF). f1040/i-90/w7-2 derived content is byte-identical to the
  6cfu.4 walkthroughs and the backend serves their derived sections (13/28/8)
  cleanly.
- Determinism: derive_and_apply is the byte-stable pass pinned by the 6cfu.2
  tests.

## Known-and-accepted

- w7 `applicant_phone`/`delegate_name` two-column signature-block clustering
  (above) -- heading-boundary nuance, not a mapping bug.
- The frontend/public/form-kits scaffolding in a checkout is gitignored;
  deploy tooling syncs it from form-kits/. This worktree's copy was refreshed
  manually for the walkthrough.
- The pre-existing no-backend static-manifest-fallback bug (its own bead) is
  unrelated to this change.

## Files touched

- `form-kits/{f1040,i-90,w7,w7-2}/schema.json` (divisions only -- fields'
  content, options, help, validation untouched apart from section_id)
- this journal entry
