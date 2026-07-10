# Sprint 10 -- Deterministic form divisions: name-convention + heading-anchored strategies

**Epic:** `polyglot-pdf-6cfu` · **Approved:** 2026-07-10 (maintainer) ·
**Origin:** planning session 2026-07-10 (plan file
`~/.claude/plans/currently-forms-are-split-abundant-petal.md`, approved with
maintainer input: no non-deterministic splitting; investigate naming
conventions as primary division; editor gains add/remove/merge sections;
retrofit last).

## Context

Sections today are cut by the extraction LLM with **zero splitting policy** in the
contract (`scripts/bakeoff/schema_contract.py` gives no guidance at all), which is
why boundaries are arbitrary and need human touch-up. Their original purpose --
10-20 question chunks as Gemini session-reset points -- is obsolete now that
sliding-window context compression exists (and a `CONTINUOUS_SESSION` path is
already built). Maintainer requirements: **deterministic** divisions (hard: no
non-deterministic splitting), **aligned with the sections the form itself
prints** ("Filing Status", "Part 1. Information About You"), chunk sizes that
stay near the flash-lite validator's tested 10-20 band, and a schema editor
that can **add, remove, and merge sections** manually.

**Evidence gathered this session (probes on checked-in PDFs + kits):**

1. **USCIS widget names encode the structure directly.** i-90 `pdf_field_name`s
   are `P{part}_Line{item}{sub}_{Label}[idx]` (e.g. `P1_Line3a_FamilyName[0]`,
   `P8_Line5b_PartNumber[2]`): part membership AND item ordering, independent
   of geometry. This defeats the two-column trap the maintainer flagged (i-90
   p2: "Reason for Application" sits top-right but belongs to Part 2, which
   starts lower-left -- the `P2_` prefix resolves it with no geometry at all).
2. **IRS widget names encode page + reading-order sequence only**
   (`topmostSubform[0].Page1[0].f1_04[0]`, checkbox counter `c1_N` separate
   from text counter `f1_N`): ordering signal, no section signal.
3. **IRS printed headings are mechanically detectable** (PyMuPDF text spans):
   on f1040, "Filing Status", "Digital Assets", "Dependents", "Income", "Tax
   and Credits", "Payments and Refundable Credits" are the ONLY lines in the
   bold-condensed font at size 10-11 (body = 8), all at the left margin; w7
   same pattern (Name / Mailing Address / Birth Information / Other
   Information / Sign Here...). i-90 additionally prints `Part N.` headings
   (bold 12, regex-matchable) and bold-italic sub-headings ("Your Full Name",
   "Mailing Address", "Reason for Application").
4. Every field already carries deterministic `pdf_position` (page/x/y/w/h)
   backfilled from the AcroForm dump (`_backfill_positions`,
   `scripts/authoring/extract_form.py`) -- not from the LLM. No re-extraction
   needed for any of this.

## Design

**Sections become a deterministic derivation, computed by code at extraction /
editor time and stored in `schema.json` exactly as today.** Runtime contracts
(handshake manifest, `schema.sections`, navigation, validation) are unchanged;
only the source of boundaries changes. The derivation is a **strategy ladder**
-- different form families get different deterministic strategies, chosen by a
deterministic applicability test:

### Strategy 1 -- Name-convention (USCIS family; PRIMARY division)
Applicability: a dominant share (e.g. >=80%) of widget names match
`P(\d+)_Line(\w+)_...` (exact threshold/patterns tuned in the prototype).
- **Parts** = `P{N}` prefix. **Ordering** = part number, then Line item
  (natural sort: 3a < 3b < 10), immune to column layout.
- **Sub-division within a part** (parts can exceed the cap): printed
  sub-headings (bold-italic style, per probe) assigned column-aware -- within
  a text column, a sub-heading governs the fields below it until the next
  heading; spans are then concatenated in Line-number order. Fallback:
  cap-split in Line order.

### Strategy 2 -- Printed-heading detection (IRS family)
Applicability: no structural name convention; headings detectable.
- **Heading detection** from PyMuPDF text spans: per-page style census
  (font, size); body = dominant style by char mass; headings = bold styles
  with size >= body, short text, at a column start; merge vertically-adjacent
  same-style lines (multi-line headings like "Applicant's / Mailing /
  Address"); rank heading levels by size.
- **Field assignment**: fields ordered by the name-sequence counter
  (`f{page}_{seq}` / `c{page}_{seq}`, interleaved by geometry where the two
  counters mix); each field belongs to the nearest preceding heading in its
  column. (f1040/w7 are single-column in practice, so this is simple there;
  the prototype measures how well it holds.)
- **Parts** = pages for this family.

### Strategy 3 -- Fallback: page + cap
No convention, no detectable headings: each page is one section, labeled
"Page N".

### Rules applied to every strategy's output
- **Hard page boundary**: a section never spans pages ("X (continued)" --
  matching what the forms themselves print).
- **Size cap ~20 fillable fields** (keeps the validator in its tested band):
  oversize sections sub-split in reading order at field-group boundaries
  (never splitting a group/family), labeled "X (1 of 3)".
- **Labels** come from the form's own printed heading / part text -- no LLM in
  the loop. Only cap-splits and page-crossings get synthetic suffixes.
- **Determinism**: same PDF in -> byte-identical sections out, both strategies.
- **Page-number normalization**: derived sections write 1-based
  `page_number(s)` matching field `pdf_position.page` (existing kits are
  inconsistent: 0-based in w7/f1040, absent in i-90; nothing in the frontend
  reads section page numbers today, so safe).

Rejected alternatives: whitespace-gap cutting (f1040 has no meaningful gaps --
probe-confirmed); pure pages + UX rework (105-field chunk vs a validator
tested at 10-20); constrained LLM splitting (still non-deterministic; ruled
out by maintainer).

## Bead chain (exploration -> implementation -> testing -> retrofit)

Epic + beads filed via pull/push-bracketed `bd create`, each with exit
criteria. Bead 1 is the go/no-go checkpoint back to the maintainer.

### Bead 1 -- Prototype + comparison report (exploration)
`scripts/authoring/derive_sections.py` standalone: input = form PDF +
existing `schema.json` (for `pdf_field_name` + `pdf_position`), output =
derived sections + a comparison report vs the kit's current LLM-cut sections.
Includes: (a) a naming-convention inventory across all checked-in PDFs
(i-90, f1040, w7, w7-2, w9-heldout) -- which strategy each form selects;
(b) per form: detected parts/headings, field count per derived section,
fields that moved vs today, cap-splits triggered, unassigned fields;
(c) the i-90 two-column page verified specifically (Part 2 / "Reason for
Application" assignment correct via `P2_` prefixes).
**Exit:** (1) report for all 5 forms; (2) i-90 divisions match its printed
Part structure incl. the two-column page; (3) f1040/w7 headings match the
printed section names; (4) no derived section exceeds the cap; (5) derivation
run twice is byte-identical. Results go to the maintainer before beads 2+.

### Bead 2 -- Integrate into extraction
Wire the splitter into `extract_form.py` after `_backfill_positions`; the LLM
contract stops asking for `sections`/`section_id` (or its output is
overwritten); splitter assigns `section_id` + emits `schema.sections`/`parts`.
Update `_backfill_unclaimed_widgets` page->section filing (`_section_for_page`
already exists) and `schema_repair`.
**Exit:** extraction output sections are 100% derivation output; re-running
extraction is section-stable.

### Bead 3 -- Schema editor: section management + regenerate
Two halves (maintainer-directed):
- **Manual section CRUD**: add a section, remove a section (fields re-file to
  a neighbor or orphan bucket), merge two sections, rename; plus the existing
  reassign-field dropdown. Group-mutation `show_if` rewrite ledger
  (`schema-editor/utils/fieldGrouping.ts`, bf923ba5) must keep working when
  sections merge/vanish.
- **"Regenerate divisions"**: re-runs derivation from the kit's PDF; manual
  edits after regeneration are ordinary schema edits (regenerating again
  overwrites them -- confirm-dialog).
**Exit:** add/remove/merge/rename all function on a loaded kit and survive
save/reload; regenerate reproduces bead-1 output.

### Bead 4 -- Simplified view alignment (small)
Expected near-zero change (`SchemaForm` reads `schema.sections` generically).
Verify navigation/validation/progress on derived sections; sensible rendering
of "(continued)" / "(1 of 3)" labels; handshake manifest
(`buildHandshakeManifest` -> `manifest.parts`) unchanged in shape.
**Exit:** full form-fill walkthrough on derived-section f1040 + i-90 in the
local stack, simplified + PDF views consistent.

### Bead 5 -- Validator re-test
Re-measure flash-lite validator accuracy on the new chunk boundaries (sizes
stay 10-20 via the cap; boundaries/content differ).
**Exit:** accuracy on derived sections measured vs the existing baseline;
regression (if any) reported to maintainer.

### Bead 6 -- Retrofit existing kits (last, per maintainer)
Regenerate sections for f1040, i-90, w7, w7-2 from existing kit data + PDFs
(pure derivation, no re-extraction), incl. 1-based page-number normalization;
verify each in the UI.
**Exit:** all kits on derived sections; demo walkthrough clean.

## Decisions made (noted, not asked)

- **Cap = 20 fillable fields** (validator's tested upper bound); a tunable
  constant, revisited with bead 1's numbers.
- **Sections remain stored in schema.json** (derived at authoring time) -- no
  runtime/wire changes; cheapest reversible shape.
- **Strategy selection is automatic** (deterministic applicability test on
  widget names), with the chosen strategy recorded in the extraction metadata
  so it's auditable.
- **Section-level `show_if` untouched** in this epic (modeled + editor-
  maintained but never evaluated by the simplified runtime; separate cleanup
  candidate) -- except that bead 3's merge/remove operations must not corrupt
  it (existing rewrite ledger).

## Key files

- `scripts/authoring/extract_form.py` (`_backfill_positions`,
  `_backfill_unclaimed_widgets`/`_section_for_page`, pipeline order)
- `scripts/bakeoff/schema_contract.py` (LLM contract: drop section emission)
- `scripts/authoring/derive_sections.py` (new -- strategy ladder + splitter)
- `backend/models/form_models.py` (`FormSection.page_number(s)` convention;
  no shape change expected)
- `schema-editor/` (`App.tsx`, `components/FieldList.tsx`,
  `components/FieldEditor.tsx`, `utils/fieldGrouping.ts` -- section CRUD +
  regenerate)
- `frontend/src/schema-forms/` (verify-only; `state/schemaFormState.ts`,
  `utils/manifestUtils.ts`)
- Session probe evidence to promote into bead 1: scratchpad
  `probe_headings.py` + the `pdf_field_name` inventory one-liner.

## Verification

- Bead 1 report is the primary artifact: strategy chosen per form +
  derived-vs-current section tables for all 5 forms, maintainer-reviewed
  before beads 2+.
- Determinism check: run derivation twice per PDF, diff (byte-identical).
- The i-90 two-column page as a named regression case.
- End-to-end: local stack (`/run-local`) form-fill walkthrough on f1040 +
  i-90 with derived sections, both views; full backend suite (not -k
  filtered) + frontend vitest; schema-editor tests for the new section CRUD.
- Validator accuracy re-test (bead 5) against the existing baseline.
