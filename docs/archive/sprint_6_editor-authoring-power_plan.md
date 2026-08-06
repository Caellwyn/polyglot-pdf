# Sprint 6 -- Editor authoring power

> **ARCHIVED (2026-08-06, docs audit bd polyglot-pdf-2zk3).** Epic
> `polyglot-pdf-s4dp` is closed; the one remaining loop-proof bead
> `polyglot-pdf-ue5s` is tracked in beads, not here. Kept verbatim as the
> sprint's plan of record -- read it as history, not as current direction.
> The "Status" line below is the plan's state at approval time.

**Epic:** `polyglot-pdf-s4dp` -- Editor authoring power (grouping, preview,
help-from-instructions, versioning)

**Status:** planned (approved by maintainer); B1 ready to build, B4/B3/B2 blocked
behind it in build order.

---

## Why (L1)

Driving the PDF -> JSON FormSchema authoring loop by hand (the W-7 touch-up under
bd `polyglot-pdf-ue5s`) surfaced four walls where the schema-editor cannot express
what real immigration/tax forms require. Each forces the author to drop to raw-JSON
editing, or makes a field unauthorable entirely -- which defeats the authoring
loop's whole point (cut human labor; epic `polyglot-pdf-7a9`).

**Users:** schema authors (the maintainer now; outsourced help later) doing
touch-up, and downstream the LLM + subagents (validator, researcher) that consume
the help text and version metadata.

**Why now:** the "field merge/split" gap (B1) is exactly the work the closed
Track-A editor epic (`polyglot-pdf-hid`) intentionally **demand-gated** -- "file it
only after a real touch-up pass shows the good-enough pipeline leaves merge work
behind." That gate fired on the W-7 pass, alongside three more gaps the same pass
exposed.

---

## Exit rubric

| # | Criterion | Verify |
|---|-----------|--------|
| 1 | A human can select 2+ separate radio/checkbox fields in the editor and **merge** them into one consolidated `options[]` field (each widget's `pdf_field_name` preserved on its option), and **un-merge** back -- no hand-edited JSON. | In-editor, group W-7's `reason_a..e` into one radio field; save; the saved `schema.json` has one field with 5 options each carrying its `pdf_field_name`; un-group restores separate fields. |
| 2 | The editor has an **interactive preview** (independent of the voice app) where clicking fields exercises real behavior: radios mutually exclusive, checkboxes multi-select, and a `show_if` field hides/shows as its controller changes. | Open preview on W-7; click two radio options -> only one stays selected; toggle `us_person_ssn_itin`'s controller -> it shows/hides. |
| 3 | Extraction populates `help.instructions` from AcroForm `/TU` tooltips, AND the extraction flow accepts an **optional instructions-PDF upload** that enriches help when provided (absent -> `/TU`-only fallback). | Re-extract a form with `/TU` tooltips -> `help.instructions` non-empty where tooltips exist; provide an instructions PDF -> help richer; omit -> clean fallback. |
| 4 | Extraction **deterministically** populates the form's real version metadata (revision/edition, OMB number, expiration where present), and the editor displays the version visibly. | Re-extract W-7 -> version/edition "December 2024", `omb_number` "1545-0074"; I-90 -> `edition_date` "01/20/25", `expiration` "02/28/2027", OMB "1615-0082"; both shown on the editor's form card. |

---

## Bead tree (serialized -- build order)

Nothing is cleanly parallel: every pair shares at least one small editor file
(`App.tsx`, `FormCatalogue.tsx`, `FieldEditor.tsx`), and B3+B4 share
`extract_form.py`. Since execution is one bead at a time, the maintainer chose to
**serialize by dependency order** rather than re-cut for theoretical parallelism.
Build order = blocking-priority + the one hard data dependency (B3 reuses B4's
shared `extract_form.py` metadata pattern).

| Order | Bead | Inherits | Write surfaces | Blocked by |
|-------|------|----------|----------------|-----------|
| 1 | **`s4dp.1` B1** -- Group/ungroup options (field merge/split) | crit 1 | `schema-editor/src/App.tsx`, `components/FieldEditor.tsx`, `components/FieldList.tsx`, `src/utils/` (merge/split util) | -- (ready) |
| 2 | **`s4dp.2` B4** -- Version extraction + editor display | crit 4 | `scripts/authoring/extract_form.py` (+helper), `schema-editor/src/components/FormCatalogue.tsx`, `FieldEditor.tsx`, `src/types/schema.ts` | B1 (`FieldEditor.tsx`) |
| 3 | **`s4dp.3` B3** -- Help from `/TU` + optional instructions-PDF upload | crit 3 | `scripts/authoring/extract_form.py`, `schema-editor/vite-plugins/extractEndpoint.ts`, `src/utils/extractionClient.ts`, `src/components/FormCatalogue.tsx` | B4 (`extract_form.py` + `FormCatalogue.tsx`) |
| 4 | **`s4dp.4` B2** -- Interactive preview pane | crit 2 | `schema-editor/src/components/PreviewPane.tsx` (new), `src/App.tsx` | B1 (`App.tsx`) |

**Key design notes per bead:**

- **B1 (grouping):** the model + runtime already fully support `options[]`
  (`FieldOption.pdf_field_name`); this is purely editor mutation. The care is in
  the **merge semantics**, not the UI: which field's `id`/`section_id`/`spoken_name`
  wins; each widget's `pdf_field_name` moves onto its `option.pdf_field_name`; the
  operation must be **reversible** (un-group restores separate fields). Schema is
  held + mutated in `App.tsx` (`commitSchema`); add `handleMergeFields` /
  `handleUnmergeField` + a pure merge/split util; multi-select in `FieldList`.

- **B4 (versioning):** `FormMetadata` already has
  `version`/`edition_date`/`omb_number`/`expiration_date`/`form_number`. The info
  is reliably extractable (verified): W-7 from `metadata.title` "(Rev. December
  2024)" + page-1 text + OMB "1545-0074"; I-90 from page-1 "Edition 01/20/25" /
  "Expires 02/28/2027" / OMB "1615-0082". **Proven regex already exists** in
  `scripts/bakeoff/prior_extractor/extractor.py::extract_complete_metadata()` --
  port it (deterministic, no LLM). Stop defaulting `version` to "draft".

- **B3 (help):** `/TU` tooltip text is **already captured** in the AcroForm dump
  (`acroform_dump.py` widget `tu`) but unused. Map it into `help.instructions`
  (deterministic). The **optional instructions-PDF upload** threads:
  `FormCatalogue.tsx` (file input) -> `extractionClient.ts` -> `extractEndpoint.ts`
  (new optional `instructionsPdfFile` + spawn arg) -> `extract_form.py`
  (`--instructions-pdf` + a text-merge pass).

- **B2 (preview):** **must be voice-app-independent** (maintainer steer -- possibly
  the seed of a separate product). Do NOT embed `frontend/src/schema-forms/`
  wholesale (wired to voice/WS/connection state). REUSE the field-**rendering**
  logic in a new standalone `PreviewPane.tsx` with its own local field-value state.

---

## Out of scope (explicit)

- **Compound `and`/`or`/`not` conditional logic** -- the model only supports a
  single `show_if` condition today; representing compound logic is a wire-format
  change touching the runtime filler + validator, not just the editor. It gets its
  **own epic with a dedicated design pass** (planned next; the maintainer asked for
  2-3 representation options to be proposed there). A small adjacent piece --
  `bd polyglot-pdf-jplx` (array-value editor for `in`/`not_in`) -- belongs to that
  effort.
- **Deep parsing / structured ingestion of the full instructions PDF** beyond
  enriching `help.instructions` (B3 does `/TU` + a straightforward text-merge from
  the optional upload). A richer instructions-doc pipeline is a follow-up.
- **Standalone preview as its own product** -- the direction the maintainer floated
  for B2; noted, not built here (B2 is just the in-editor preview pane, built
  cleanly enough to extract later).

---

## Provenance

- Feedback source: maintainer's real W-7 touch-up pass (this session), bd `ue5s`.
- Codebase ground truth: two Explore investigations this session (feature-gap map +
  exact write-surface collision matrix; version-string extractability).
- Demand gate: `polyglot-pdf-hid` close reason (field merge/split deferred until a
  real touch-up proved the need).
