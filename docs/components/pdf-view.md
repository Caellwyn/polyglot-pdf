# pdf-view -- the Preview-mode PDF surface

**Tracks:** frontend/src/pdf-view/viewMode.ts frontend/src/pdf-view/PreviewPane.tsx frontend/src/pdf-view/PDFViewer.tsx frontend/src/pdf-view/FieldOverlay.tsx frontend/src/pdf-view/FieldEditPopover.tsx frontend/src/pdf-view/valuePainting.ts frontend/src/pdf-view/useSnapToField.ts frontend/src/pdf-view/FilledPreviewModal.tsx frontend/src/pdf-view/usePDFDocument.ts frontend/src/pdf-view/PDFPage.tsx frontend/src/pdf-view/pdfWorker.ts frontend/src/pdf-view/pdfCoordinates.ts

*Last updated: 2026-09-08 (bd polyglot-pdf-uum5g: click-to-edit stores the typed value UNVERIFIED -- it shares SchemaForm's handleFieldChange, so the PDF view gets the same rule as the schema form.)*


`frontend/src/pdf-view/` renders the actual form PDF in the browser (pdf.js)
with the user's answers painted at their printed positions -- the "Preview"
half of the dual view modes (epic `polyglot-pdf-js7q`, sprint 8 plan
[`docs/archive/sprint_8_preview-mode_plan.md`](../archive/sprint_8_preview-mode_plan.md)).
Related: the linear form and its state layer are in
[schema-forms.md](schema-forms.md); server-side fill is in
[pdf-filling.md](pdf-filling.md).

## Reachability: cut over, always on

The Preview UI is CUT OVER (bd `polyglot-pdf-v437`, maintainer-approved
2026-07-31): the Simplified/Preview toggle renders unconditionally, with no
query param or sessionStorage opt-in. The former `featureFlag.ts` /
`?previewUi=1` gate is deleted -- do not reintroduce a flag check here.

The cutover made Preview REACHABLE, not the landing view: a fresh mount still
starts in Simplified (see "View modes" below), and promoting Preview to the
default remains a separate maintainer call.

pdf.js is still lazy and is fetched only when the user actually opens a preview
surface: `SchemaForm` reaches this module through two `React.lazy` boundaries
(`FilledPreviewModal`, `PreviewPane`), so Rollup keeps pdfjs-dist in a shared
lazy `pdf-view-*.js` chunk that `index.html` does not modulepreload. The one
statically-imported file (`viewMode.ts`) is pdfjs-free -- keep it that way.

## View modes

`viewMode.ts`: `'simplified' | 'preview'`, sessionStorage-persisted,
deliberately OUTSIDE `SchemaFormState` (purely presentational; never in the WS
handshake). `initialViewMode(stored, viewportWidth)` decides fresh
mounts: Simplified by default everywhere; a stored `'preview'` choice is
honored at desktop width (mobile-width mounts always start
Simplified, epic rubric #5).

**Caller contract: `initialViewMode` RESOLVES a mode but does not PERSIST it.**
Whenever the resolved mode differs from what is stored, the caller must write
the result back (`storeViewMode`) -- i.e. the guard is `mode !== stored`, not
just the mobile case. That covers three situations: the mobile-width demotion of
a stored `'preview'` (otherwise state says Simplified while storage still says
`preview`, and the stale value resurrects Preview at the next desktop-width
mount); a junk stored value, which gets normalized; and a fresh mount with
nothing stored, which writes `'simplified'` (inert -- `stored ?? 'simplified'`
makes "never chose" and "chose Simplified" indistinguishable). SchemaForm's
`viewMode` initialiser implements exactly this; a second caller must too. This
mirrors the resize path, which has always written its demotion back, and the two
silently diverging is exactly the bug bd `polyglot-pdf-v437` had to fix once the
cutover made mobile Preview reachable.

`viewModeAfterResize(current)`
extends that intent to a LIVE same-tab resize (or device rotation): once the
resize classifies the viewport as MOBILE, it forces Preview back to Simplified
mid-session. It is one-directional -- leaving mobile never auto-restores
Preview, and a desktop-width resize never calls it -- so a deliberate desktop
choice is never overridden (bd `polyglot-pdf-ipin`). SchemaForm calls it from
the same debounced resize effect that classifies mobile/desktop, keyed on that
SAME mobile decision (the dead-zone hysteresis: `isMobile` flips at `<=700`, not
at 768) rather than an independent width threshold -- so the view mode can never
disagree with which overlay (mobile vs desktop) is showing (a desktop-styled
overlay never pairs with a mobile-defaulted Simplified form). SchemaForm renders
the toggle while keeping the voice overlays + ConnectionManager OUTSIDE the
switched container, so toggling never remounts them or disturbs the Gemini
session (pinned by `SchemaForm.test.tsx`, bd `polyglot-pdf-fdz8`).

## The live surface (PreviewPane -> PDFViewer -> FieldOverlay)

- `usePDFDocument` + `PDFPage` + `pdfWorker`: pdf.js loading and per-page
  canvas rendering (StrictMode-safe cancellation). **pdfjs-dist is pinned to
  4.10.38 and imported via the LEGACY build + `?url` worker import**: early
  4.x (incl. the schema editor's 4.0.379) carries a top-level await the app's
  es2020 Vite target rejects, and the raw `new URL()` worker form 403s under
  the worktree node_modules junction in dev.
- `pdfCoordinates.ts`: schema `pdf_position` values are top-left-origin PDF
  points (PyMuPDF widget rects), so screen position is a pure multiply by the
  render scale -- no Y-flip.
- `FieldOverlay`: one absolutely-positioned div per positioned field, colored
  by FILL state -- empty (gray outline), filled (blue), confirmed (green),
  current (orange) -- with the value painted inside (`valuePainting.ts`):
  fitted text, an X for single-box checkboxes. Radio/checkbox/checkbox_group
  selections whose options carry their own `pdf_position` (backfilled into
  the git-tracked kits -- f1040, w7; bd 5f41) paint an X mark at each SELECTED option's printed
  box (`selectedOptionRects`, bd lp5v): the marks render as sibling divs in
  the same page space while the field-level box stays as the `data-field-id`
  snap-to anchor and paints no duplicate label. Coverage is ALL-OR-NOTHING
  per selection: if any selected value lacks a usable same-page rect, the
  whole selection falls back to selected LABELS at the field-level rect
  (partial marks would silently hide the uncovered selections; a cross-page
  rect would paint in the wrong page container). Selects paint WHAT PRINTS at
  the field rect, never their label (a dropdown's options have no printed boxes
  of their own): the option's `pdf_on_value` -- the export code the filler
  writes (`resolve_select_fill_value`, bd `polyglot-pdf-g2fpr`) -- falling back
  to the raw value for a legacy option that carries none. Both arms mirror the
  filler, and a speakable label like "Armed Forces Americas (AA)" would
  clip in a 36pt state box (bd `polyglot-pdf-jpjcv`). A RADIO still paints its
  label, because its value is an internal slug that never prints.
  A single-box checkbox paints
  an X whether it is a plain boolean OR a legacy single-OPTION checkbox (the
  widget stores the checked state as a 1-element array, which would otherwise
  paint the option's label overflowing an ~8x8pt box); only a TRUE multi-option
  group (2+ options / `checkbox_group`) paints joined labels (bd
  `polyglot-pdf-jq17`). Schema-v2 forbids a `checkbox` with options outright, so
  the single-option path is defensive for hand-authored / pre-v2 kits.
  show_if-hidden fields render DIMMED (`pdf-field-overlay--dimmed`: 0.35
  opacity, dashed border), never removed -- they exist on paper -- and are
  not clickable; `current` wins over dimmed. PDFViewer computes `dimmed` via
  `shouldShowField` on the wrapped value map, so dimming flips live with the
  controlling field (bd lp5v). Each overlay resolves its field's value with the
  `[]`-alias-aware `readFieldEntryWithAlias` (bd 7sdc), so a checkbox-group value
  stored under the OTHER bracket variant than the schema id (Gemini drops/adds
  the trailing `[]`, bd 5k52) still paints -- a bare `fieldValues[field.id]` read
  rendered such a field blank after the got6 dedup collapsed the duplicate key.
- Click-to-edit (`FieldEditPopover`, bd 7esr): clicking a non-dimmed overlay
  (or one of its option marks -- extra hit targets for the SAME whole-field
  editor, never a direct toggle) opens a popover hosting the SAME
  `FieldRenderer` input Simplified mode uses (one widget per type, one
  validation path, read_only + flip_readonly_bit for free). It is absolutely
  positioned in page coordinate space (scrolls with the page, no scroll
  listeners): below the rect, flipped above near the page bottom, clamped
  horizontally, internal scroll for long option lists. Write-through on
  change via SchemaForm's `handleFieldChange` (which stores the value UNVERIFIED --
  typing is not an assertion, bd polyglot-pdf-uum5g -- so the click-to-edit path
  gets the same rule as the schema form, being the same handler; the `copy_to`
  fan-out itself lives one level down, at the
  `SchemaFormStateManager.updateField` chokepoint, so every write path gets it
  -- bd polyglot-pdf-gpaed) -- overlays repaint
  live while typing. **Known gap (bd `polyglot-pdf-1utg`, open):** the popover's
  incoming value is read via a bare `fieldValues[editingHere.id]`, not the
  alias-aware `readFieldEntryWithAlias` the overlay itself uses -- if a
  field's value is stored only under the OTHER `[]`-bracket variant, the
  overlay paints it filled/confirmed but clicking to edit opens the popover
  blank. Dismissal: Esc, click-outside, the X button, a voice
  advance (`currentFieldId` change), zoom (scale change), and the edited
  field's `show_if` flipping false mid-edit (no chrome-only popover over a
  now-dimmed field). PreviewPane owns the editing state; without the edit
  handlers the surface is read-only. Overlays are keyboard-activatable
  (`role=button`, Enter/Space).
- `fillStateFor` (PDFViewer): `[]` and `false` count as empty (a cleared
  checkbox_group must not paint as filled); `current` wins over all.
- Live updates ride the existing `schemaFormStateChange` channel one level up:
  SchemaForm (already subscribed) passes fresh `fieldValues` props per change.
  The page CANVAS never re-renders per fill (its effect deps are stable);
  only the overlay layer does.
- QA surface: fields with no usable `pdf_position` are console.debug-listed
  once per pane mount (the count varies by kit as extraction/backfill
  progresses; re-check the current kit rather than trust a cached number).

## Snap-to camera

`useSnapToField`: on every `currentFieldId` CHANGE (SchemaForm tracks it from
`next_field_hint` and clears it when that field is confirmed), the pane snaps
instantly to the field's overlay via `scrollIntoView(block:'center',
behavior:'auto')` -- deliberately NO animated motion. The free-wander rule:
user scrolling is never fought; snaps fire only on a field change or the
toolbar's "Snap to current field" button. Two hardenings matter here: the
`isSnappable` short-circuit (unpositioned fields never poll) is held in a REF
so no caller's identity churn can re-fire the snap effect (state reloads churn
object identities per fill -- keying the effect on them re-snapped on every
fill), and the pane is its own scroll viewport (`max-height`) so the toolbar
stays visible.

## The true preview (FilledPreviewModal)

The "Preview Filled PDF" button POSTs current values through the SAME
`fillPDF()` / `/api/fill-pdf` (PyMuPDF) path as download/print and renders the
returned bytes -- the modal shows the backend's own output, so it matches a
download exactly. Client-side value painting in the live surface is an
approximation for feedback; this modal (and download) is the ground truth.

## Fidelity caveats (accepted, current)

- Client-painted text sizing approximates the PyMuPDF fill (comb spacing,
  font shrink); the FilledPreviewModal is the exact render.
- Radio/checkbox-group selections paint marks at their own option boxes only
  where the schema carries per-option `pdf_position` (backfilled into the
  git-tracked kits -- f1040 and w7, measured 2026-09-03; a bucket kit may or
  may not carry it, so check the kit rather than assuming); a schema without
  option rects falls back
  to labels at the field-level rect (tiny for 10px option boxes).
- Retired gap (bd `polyglot-pdf-ks1y`): 8 choice fields on the OLD i-90
  (e.g. `p3_checkbox4[1]`) carried field-level rects derived under an older
  extraction rule, so their label-at-field-rect fallback could paint 42-108pt
  away from the correct printed box. That schema is gone: the canonical I-90 in
  the bucket is the applicant-only v2 extraction, self-consistent by
  construction and carrying per-option `pdf_position` on 14 of its choice
  fields. None of the named field ids still exist. (No I-90 is git-tracked --
  kits are bucket-canonical, CLAUDE.md scar #10 -- so this cannot be
  re-measured from a checkout; pull the kit first.)
- Known gap (bd `polyglot-pdf-1utg`, open): see the click-to-edit paragraph
  above -- the edit popover's value read is exact-key-only, so a value
  stored under the other `[]`-bracket variant opens the popover blank even
  though the overlay shows the field filled/confirmed.
- `signature` fields with a usable `pdf_position` DO get overlays: a
  signature is not paintable as text, so if one ever carried a string value
  it would render as raw text in its rect. (Coverage varies by kit -- a kit
  whose signature fields carry all-zero rects is rejected by
  `hasValidCoordinates` and renders no overlay.)
  Simplified mode has no signature INPUT widget yet
  (`FieldRenderer` marks the type not-yet-implemented), but that is a
  widget gap, not a value/paint gap -- nothing restricts `update_form_fields`
  by field type, so the overlay path is live.
- Textarea width-fitting assumes a single line; long wrapped values clip.
