# Sprint 9 -- Editable Preview mode (click-to-edit + option rects + show_if dimming)

**Epic:** `polyglot-pdf-oaiz` · **Approved:** 2026-07-08 (maintainer, plan-mode review) ·
**Origin:** Phase 2 of the preview-mode exploration (plan file
`~/.claude/plans/i-d-like-to-explore-wise-newell.md`), explicitly deferred out
of sprint 8 ([`sprint_8_preview-mode_plan.md`](sprint_8_preview-mode_plan.md),
"Out of scope"; epic `polyglot-pdf-js7q`, closed).

## Why

Preview mode (sprint 8) shows progress on the real PDF but cannot act on it: a
user who spots a wrong value must switch back to Simplified mode and hunt for
the field. This sprint makes Preview a first-class interaction surface --
click the field on the document, fix it in a popover that reuses the existing
validated field inputs. Two fidelity gaps also close: radio/checkbox
selections paint at their own printed boxes instead of label text at the
group rect (requires per-option coordinates in the schema -- new at the
option level; field-level `pdf_position` already exists), and
`show_if`-hidden fields dim instead of painting as live (dim, never hide --
they exist on paper).

## HARD CONSTRAINT: still default-off

Everything ships behind the existing `?previewUi=1` opt-in flag
(`frontend/src/pdf-view/featureFlag.ts`). Flag off = the deployed UI and
bundle are unchanged (pdf-view stays inside its React.lazy chunk). The
cutover default-flip remains a separate, maintainer-gated decision. No WS
protocol changes; the backend stays stateless.

## Exit rubric

| # | Criterion | Verify |
|---|-----------|--------|
| 1 | On i-90 in Preview, selecting a radio/checkbox_group option paints a mark at that option's own PDF rect; schemas without option rects fall back to label-at-field-rect. | Vitest half (fixture-driven valuePainting/FieldOverlay tests) verifies at P2.2's closeout; the manual i-90 radio check via run-local `?previewUi=1` needs P2.1's backfilled schemas and **formally defers to P2.4** (P2.1/P2.2 may run in parallel). |
| 2 | Every radio/checkbox_group option in i-90, f1040, w7, w7-2 has a usable `pdf_position`; the backfill tool is idempotent and reports 0 unmatched. | `backfill_option_positions.py --kit <each> --check` exits 0; pytest green. P2.1's PR includes the `--check` output for all four kits as evidence in the merge report (demonstrate, don't assert). |
| 3 | Clicking a visible positioned overlay opens a FieldRenderer-backed popover; a change lands in sessionStorage with `confirmed`/`manual_edit`, propagates `copy_to`, repaints live; Esc / click-outside / voice-advance dismiss. | Vitest interaction test (open, change, assert state + dismissal) + manual voice-session toggle-and-edit. |
| 4 | `show_if`-hidden fields render dimmed (never removed), are not clickable, and dimming flips live when the controlling field changes. | Vitest PDFViewer dimming test + manual on an i-90 conditional field. |
| 5 | Flag-off bundle unchanged (pdf-view stays lazy) and no pdf plumbing (`pdf_field_name`, `pdf_on_value`, `pdf_position`) in model-facing payloads. | `npm run build` flag-off chunk check; pytest asserting `get_next_field_schema` strips pdf keys from options. |

## Bead tree

| Bead | Title | Surfaces (writes) | Inherits | Order |
|------|-------|-------------------|----------|-------|
| `polyglot-pdf-oaiz` | Epic | -- | all | -- |
| `polyglot-pdf-5f41` | P2.1: option pdf_position -- model + backfill tool + kit schemas + JIT option sanitizer | `backend/models/form_models.py`, `scripts/authoring/backfill_option_positions.py` (new), `scripts/authoring/extract_form.py`, `form-kits/{i-90,f1040,w7,w7-2}/schema.json`, `backend/services/manifest_service.py`, backend tests | 2, 5 (token half) | parallel with P2.2 |
| `polyglot-pdf-lp5v` | P2.2: Preview overlay upgrades -- TS type sync, option-rect painting, show_if dimming | `frontend/src/schema-forms/types/schema.ts`, `schema-editor/src/types/schema.ts`, `frontend/src/pdf-view/{valuePainting.ts,FieldOverlay.tsx,PDFViewer.tsx,pdf-view.css}` | 1 (vitest half), 4 | parallel with P2.1 |
| `polyglot-pdf-7esr` | P2.3: click-to-edit popover | `frontend/src/pdf-view/FieldEditPopover.tsx` (new), `frontend/src/pdf-view/{FieldOverlay,PDFViewer,PreviewPane}.tsx`, `frontend/src/pdf-view/pdf-view.css`, `frontend/src/schema-forms/components/SchemaForm.tsx` | 3, 5 (bundle half) | after P2.2 (shared surfaces) |
| `polyglot-pdf-95q0` | P2.4: epic verification pass (rubric execution + `docs/components/pdf-view.md`) | docs only | rubric execution, 1 (manual half) | last |

MECE notes: P2.1 (backend/scripts/kits) and P2.2 (frontend) have disjoint
write surfaces and are parallelizable; P2.3 is strictly ordered after P2.2 by
shared files; every rubric criterion is inherited by >= 1 child. The one
deliberate verification seam: criterion 1's manual check needs BOTH P2.1's
schemas and P2.2's painting, so it lives in P2.4 by construction -- P2.2's
own closeout is judged on the vitest half only.

## Design decisions of record

- **Click-to-edit is a popover, never in-place inputs** at PDF coordinates
  (tiny hit targets, comb fields, mobile keyboards, a11y). New
  `FieldEditPopover.tsx` absolutely positioned inside
  `.pdf-viewer__page-inner` (scrolls with the page; no scroll listeners),
  reusing `FieldRenderer` standalone; writes flow through SchemaForm's
  existing `handleFieldChange` (single place stamping
  `{confirmed: true, confirmationMethod: 'manual_edit'}` + `copy_to`
  fan-out); write-through on change, no Save button. Dismiss on Esc,
  click-outside, X, scale change, and `currentFieldId` change (voice
  advance).
- **Clicking an option rect opens the whole-field popover -- no direct
  toggle.** ~10px boxes are exactly the tiny-target problem; an adjacent-box
  misclick would silently change an answer. Option rects act as extra click
  anchors; direct toggle is a possible later enhancement.
- **Option-rect backfill is a mechanical patch, not a re-extract.** No LLM.
  The AcroForm dump (`scripts/bakeoff/acroform_dump.py`) already records
  per-widget `rect` and `on_value`; the new
  `scripts/authoring/backfill_option_positions.py` patches existing
  schema.json files (idempotent, `--check`, reports unmatched -- never
  guesses) and the extract pipeline shares the same implementation by
  EXTENDING the existing `_backfill_positions` option walk (no parallel
  option-iterating path to drift).
- **Dimmed (`show_if`-hidden) fields are not clickable**: editing a
  conditionally-hidden field writes state invisible in Simplified mode and
  can contradict the controlling field. `current` wins over dimmed.
- **JIT option sanitizer (defense-in-depth on a dormant path):**
  `manifest_service.get_next_field_schema` copies option dicts verbatim into
  the JIT `confirm_field` tool response -- gated on `USE_JIT_SCHEMA`
  (default false; DTI supersedes it), so NOT live exposure, but the new
  option field would widen it. Sanitize to `{value, label, spoken_label}` +
  a pytest locking the invariant. Model-facing channels audited safe
  otherwise (SI text, DTI guidance, secretary catalog all render options as
  labels/values only). WS handshake grows ~5 KB of bytes (not tokens) on
  `full_schema` -- negligible.
- **Frontend type sync rides P2.2**: `frontend/src/schema-forms/types/schema.ts`
  `FieldOption` also gains the missing `pdf_on_value` (stale vs backend
  since bd h76m.3); the schema-editor copy gains `pdf_position` so editor
  round-trips don't strip it.

## Reused existing assets (do not rebuild)

- The whole sprint-8 pdf-view stack (`frontend/src/pdf-view/` -- see
  [`docs/components/pdf-view.md`](components/pdf-view.md)).
- `FieldRenderer` + field components
  (`frontend/src/schema-forms/components/`) -- verified standalone-usable.
- `shouldShowField` (`frontend/src/schema-forms/utils/validation.ts`) --
  works on the wrapped FieldValue map.
- The schema-editor `FieldOverlay` click/selection pattern
  (`schema-editor/src/components/FieldOverlay.tsx`).
- `acroform_dump.dump_pdf` + `_backfill_positions`
  (`scripts/authoring/extract_form.py`).

## Out of scope (explicit)

Desktop/mobile default-mode decisions and the cutover default-flip; mobile
Preview pinch-zoom polish; dedicated a11y pass (Simplified stays the
screen-reader path); XFA (f1040) render verification; rendered text
translation; direct option-toggle-on-click; bottom-sheet mobile popover;
union-of-option-rects field boxes (radio field-level rects currently equal
option 1's widget rect -- cosmetic, accepted).
