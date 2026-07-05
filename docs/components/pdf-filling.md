# PDF filling

**Tracks:** backend/routes/pdf_fill_routes.py backend/services/form_kits.py frontend/src/schema-forms/utils/pdfFiller.ts

*Last updated: 2026-07-05. See [the h76m.17 journal entry](../journal/entries/2026-07-05-bd-h76m.17-runtime-group-consumers.md) for closeout details.*

How filled answers become a downloadable/printable PDF. The flow is **stateless**:
the client sends field values + schema, the backend fills a fresh copy of the
blank PDF with PyMuPDF and returns the bytes — nothing is stored. The form state
that feeds this is in [schema-forms.md](schema-forms.md); the no-persistence rule
is [../standards/stateless-architecture.md](../standards/stateless-architecture.md).

## Request flow

1. `SchemaForm` (Download/Print buttons) **unwraps** each `FieldValue` →
   `unwrapFieldValue` (a raw wrapper breaks fill) and calls `fillPDF(kitId, pdfUrl,
   values, schema)` in `frontend/src/schema-forms/utils/pdfFiller.ts`.
2. `fillPDF` POSTs to **`/api/fill-pdf`** with `{kit_id, pdf_filename, field_values,
   form_schema}`. (Backend HTTP base: env override → `VITE_BACKEND_HTTP_URL` →
   current origin via Firebase rewrite → `localhost:8000` dev fallback.)
3. The backend (`backend/routes/pdf_fill_routes.py`) loads the blank PDF from the
   form-kit store, fills it, and returns `application/pdf` bytes.
4. The client wraps the bytes in a Blob: `downloadPDF` (anchor download) or
   `printPDF` (opens a new window → `print()`; falls back to download if the popup
   is blocked — the tablet print path).

## Backend fill (PyMuPDF / `fitz`)

`POST /api/fill-pdf` opens the PDF from `stream=` (never a temp path for input),
builds a `field_id → pdf_field_name` map + a `field_id → field` lookup from
`form_schema.fields`, then fills per field by type:

- **text / number / etc.** — `fresh_widget.field_value = str(value)` then
  `widget.update()`.
- **radio** — find the selected `option` by `value`, fill each option's
  `pdf_field_name` widget on/off. An option with NO `pdf_field_name` of its
  own may instead carry `pdf_on_value` (schema v2, bd `h76m.17`): the shared
  field-level `pdf_field_name` is one true-AcroForm radio field whose kid
  widgets differ only by on-state, and the filler writes `/V` + `/AS`
  directly (xref surgery) onto the kid whose appearance table carries that
  state (`find_widget_by_state`) -- only the SELECTED option writes; a radio
  field holds one value, so there is no per-kid Off pass.
- **checkbox / checkbox_group** — a `bool` fills one widget; a `list` is a
  checkbox *group* (fill each selected option's widget). The v2
  `checkbox_group` TYPE (bd `h76m.17`) shares this branch -- it is the same
  options-bearing multi-select, explicit in the type instead of inferred from
  `options[]`; before that routing it fell to the scalar path and printed
  blank (v2 forbids the field-level `pdf_field_name` the scalar path needs).
  A `str` value on an options-bearing checkbox
  field is first split on commas into the list shape (bd `polyglot-pdf-h76m.2`):
  the voice path historically stored a group selection as one comma-separated
  string of option values, and without the split it fell to the
  unsupported-value branch and the group silently stayed empty. The frontend
  now canonicalizes the same string to `string[]` at the AI-value ingress
  (`webFormConnection.canonicalizeAiCheckboxGroupValue`); the backend split is
  the defensive layer for sessions whose stored values predate that fix.

### The widget gotchas (scar tissue)

- **Same-name kids: re-fetch by xref, not name.** `fill_widget` re-fetches a
  fresh widget from the page to dodge PyMuPDF weakrefs; radio kids of a
  shared AcroForm field all carry the SAME `field_name`, so the re-fetch
  matches by `xref` first (name stays as fallback) or it would grab the
  wrong sibling (bd `h76m.17`).

- **Must pass the page that contains the widget.** `fill_widget` re-fetches a
  **fresh** widget from `page.widgets()` by `field_name` before writing — PyMuPDF
  widget refs are weak and go stale ("weakly-referenced object no longer exists")
  if you hold one across operations. This is the central correctness rule of the
  filler.
- **XFA path matching.** `find_widget` tries an **exact** `field_name` match first,
  then an **`endswith`** match — XFA PDFs expose full paths like
  `form1[0].#subform[0].P1_Line1_AlienNumber[0]` while the schema's
  `pdf_field_name` is often just the leaf (`P1_Line1_AlienNumber[0]`). It scans all
  pages and returns `(widget, page)`.
- **XFA checkboxes: set, don't `update()`.** For checkbox/radio widgets the filler
  sets `field_value` **and** the `/AS` appearance key directly
  (`doc.xref_set_key(xref, "AS", f"/{on_state}")`) and deliberately does **not**
  call `update()` — it lets the viewer regenerate the appearance. The "on" state is
  derived from `widget.button_states()` (`get_button_on_state`, default `"Yes"`);
  "off" is `"Off"`.
- **`need_appearances` is intentionally NOT set** — commented out, because for these
  XFA forms the viewer generates appearances and forcing it blanked the checkboxes.
- **Dynamic flag manipulation for conditional fields.** `apply_field_flag_changes`
  honors a field's `pdf_field_flag_change` (`{bit, current_value, required_value}`)
  to flip a read-only bit and unlock a locked widget before filling — the PDF-side
  counterpart of the frontend `flip_readonly_bit` unlock (see
  [schema-forms.md](schema-forms.md)). The descriptor is read from
  `conditional_logic` first, then `conditional_behavior` as a fallback: the gold
  schemas store it under `conditional_logic` while `conditional_behavior` carries
  only `unlock_method`, so reading only the latter (the prior behavior) meant the
  unlock never fired and read-only fields silently stayed locked
  (bd `polyglot-pdf-7a9.16`).

Output is saved to a `NamedTemporaryFile` with `garbage=3, deflate=True`, read back,
and that temp file is always removed in `finally`. Counts (`filled`/`skipped`/
`errors`) are logged; **values are never logged** (PII/PHI — bd `polyglot-pdf-hjo`).

## Form-kit store (where the blank PDF comes from)

`backend/services/form_kits.py` — `get_form_kit_store()` (lru-cached) returns one of
two backends by `FORM_KITS_MODE`:

- **`local`** (default) — `LocalFormKitStore` reads `<FORM_KITS_LOCAL_ROOT>/<kit_id>/`
  (`schema.json`, `form.pdf` or first `*.pdf`); generates the manifest by scanning.
- **`gcs`** — `GCSFormKitStore` reads `gs://<FORM_KITS_GCS_BUCKET>/<prefix>/<kit_id>/...`
  via an authenticated `storage.Client` (requires `FORM_KITS_GCS_BUCKET`).

`load_pdf_bytes` raises `FormKitNotFound` (→ 404) / `FormKitStoreError` (→ 502).

The same store also carries an **additive editor write/list surface**
(`put_schema`, `put_metadata`, `load_metadata`, `list_kit_files`) consumed by the
token-gated `/api/editor/*` routes (`backend/routes/editor_kit_routes.py`) that
back the hosted schema editor (bd `polyglot-pdf-92qe.1`). PDF filling and the
public `/api/form-kits*` routes never call the write surface; drafts stay
invisible to the voice app (the complete-only manifest gate is unchanged).

## Debugging

`DEBUG_PDF_FILLING.md` (repo root) is the field-by-field debug runbook for the
"blank PDF" failure modes — wrapped-value symptoms (`{value:...}` reaching the
backend = unwrap failed), `field_count=0` (frontend not sending), `filled=0`
(pdf_field_name mismatch — dump real widget names with a `fitz` one-liner), and a
curl recipe against `/api/fill-pdf`.
