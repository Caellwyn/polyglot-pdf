# PDF filling

**Tracks:** backend/routes/pdf_fill_routes.py backend/services/form_kits.py frontend/src/schema-forms/utils/pdfFiller.ts

*Last updated: 2026-08-05 (bd polyglot-pdf-oagt: the fill route now REFUSES
interpreter/preparer certification fields -- a legal invariant enforced
server-side by `backend/services/certification_denylist.py`, not by the schema,
because the route trusts the client-supplied `form_schema` and never reads the
kit's stored schema.json; see "Certification blocks are NEVER filled"). Prior:
2026-08-03 (bd polyglot-pdf-z2is: /api/fill-pdf is auth-gated;
fillPDF gained the optional getToken param). Prior: 2026-08-01. See [the v96b journal entry](../journal/entries/2026-07-05-bd-v96b-store-with-issues.md) for the kit JSON-artifact surface; [the h76m.17 entry](../journal/entries/2026-07-05-bd-h76m.17-runtime-group-consumers.md) for runtime group consumers; [the eb4z entry](../journal/entries/2026-07-14-bd-eb4z-7sdc-alias-symmetry.md) for the field_mappings []-alias exact-wins fix. Prior: 2026-08-05 (docs audit bd polyglot-pdf-2zk3: claims re-verified against code, no drift found).*

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
   form_schema}` and an `Authorization: Bearer <idToken>` header via its optional
   `getToken` callback -- the route is auth-gated (bd polyglot-pdf-z2is; the body
   carries user-entered values). Callers inside the authed app thread
   `user.getIdToken()`; local dev against a `VFF_DISABLE_AUTH` backend may omit it.
   (Backend HTTP base: env override → `VITE_BACKEND_HTTP_URL` →
   current origin via Firebase rewrite → `localhost:8000` dev fallback.)
3. The backend (`backend/routes/pdf_fill_routes.py`) loads the blank PDF from the
   form-kit store, fills it, and returns `application/pdf` bytes.
4. The client wraps the bytes in a Blob: `downloadPDF` (anchor download) or
   `printPDF` (opens a new window → `print()`; falls back to download if the popup
   is blocked — the tablet print path).

## Backend fill (PyMuPDF / `fitz`)

`POST /api/fill-pdf` opens the PDF from `stream=` (never a temp path for input),
builds a `field_id → pdf_field_name` map + a `field_id → field` lookup from
`form_schema.fields`, then fills per field by type. Both maps are built in **two
passes** so a real exact schema id always wins over any sibling's `[]`-alias: pass
1 writes every real exact id unconditionally; pass 2 registers `[]`-alias variants
(Gemini drops/adds the trailing `[]`, bd `5k52`) but SKIPS any alias key that is
itself a real schema id. So a value keyed under the other bracket variant fills a
gap, but never shadows a distinct real field that happens to lack its own
`pdf_field_name` (bd `polyglot-pdf-eb4z`; the frontend mirror is
`readFieldEntryWithAlias`).

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

### Certification blocks are NEVER filled (legal invariant)

`backend/services/certification_denylist.py` refuses to write any third-party
certification field -- USCIS I-90 Part 6 (Interpreter's Certification) and Part 7
(Preparer's Declaration), F1040's "Paid Preparer Use Only" block, the W-7's
"Acceptance Agent's Use ONLY" block, and anything matching the same patterns on a
future kit. Our position is that we are not the preparer; the STRUCTURAL version
of that claim (the tool *cannot* fill the block) is far stronger than a
disclaimer (bd `polyglot-pdf-oagt`).

**Two tiers, because one flat list cannot express this.** Tier 1 is global:
professional ROLES (`interpreter`, `preparer`, `attorney`, `notary`,
`civil_surgeon`, `accredited_rep`, `acceptance_agent`, `translator`, `witness`,
`affiant`, `panel_physician`, `joint_sponsor`, a `ptin`) that are never the
applicant on any form. Tier 2 is keyed on `kit_id`, for form-specific facts:
`p6_`/`p7_` is the interpreter/preparer block **on the I-90 only** -- on the
N-400 those parts are the applicant's employment and travel history, so a global
prefix would silently blank answers the client spoke and confirmed.

**An unrecognized `kit_id` applies EVERY kit's rules, not none.** `kit_id`
arrives in the untrusted request body, and matching it exactly once made this
invariant depend on a string's spelling: `"I-90"` instead of `"i-90"` silently
dropped 27 of the I-90's 37 protections. Kit onboarding really does produce such
variants (`_derive_kit_id` turns the standard `Form I-90.pdf` download into
`form-i-90`), so the id is normalized (case, separators, a leading `form`) AND
an unknown id falls back to the union of all kits. The failure mode is now an
over-refusal -- a blank a human completes -- rather than a filled attestation.
Registering the kit in `_KIT_SCOPED_PATTERNS`, which means someone read that
form, buys the precision back.

**This is enforced server-side and NOT by the schema.** `/api/fill-pdf` builds
its field map from `request.form_schema` -- the CLIENT'S copy -- and never loads
the kit's stored `schema.json`. The editor's `_ignored_fields` quarantine only
removes a field from that client copy, so a stale bundle or hostile caller that
sends the field anyway would get it written. The denylist therefore applies
regardless of what any schema says.

**FOUR guards, all required.** Each is pinned by its own test -- with all of them
live, deleting any one leaves the others covering, so an outcome-only test cannot
see a layer die:

1. The per-field dispatch loop, keyed on the schema field id, placed BEFORE the
   schema lookup so an unlisted field is still refused. Every write branch
   (text / radio / checkbox / checkbox_group) is downstream of it.
   (`test_each_guard_layer_refuses_on_its_own`)
2. `fill_widget`, keyed on the name of the REAL widget in the PDF, which no
   client-supplied schema can misrepresent.
   (`test_each_guard_layer_refuses_on_its_own`)
3. The shared-field radio's direct xref path, which bypasses `fill_widget`
   entirely. No shipped kit uses that shape for a certification field, so it is
   exercised by a synthetic v2 kit.
   (`test_the_shared_radio_xref_path_refuses_certification_widgets`)
4. `apply_field_flag_changes`, so a certification widget is never UNLOCKED.
   Clearing the read-only bit is itself a write that persists into the emitted
   PDF, and several call sites run it before the value-write guard.
   (`test_a_certification_widget_is_never_UNLOCKED`)

Matching is asymmetric by design in the ROLE tier: a false positive leaves a
preparer field empty (correct anyway -- a human completes that block by hand); a
false negative fills a perjury attestation. But kit-scoped rules must be scoped,
because there the false-positive cost is a client's own spoken answer silently
vanishing from their form.

The applicant-field allowlist is empty, measured with each kit's `kit_id`:
37 I-90 + 7 F1040 + 9 W-7 fields matched, zero applicant fields. Those counts are
pinned by `test_the_documented_match_counts_are_accurate`.

**Every pattern in BOTH tiers is individually pinned** -- each has a test input
only it satisfies, so deleting it names itself. This is not optional bookkeeping:
an unpinned pattern is either dead or redundant, and a dead one (`ptin`, which a
leading `\b` prevented from ever matching after an underscore) is how the W-7
acceptance-agent block went unprotected through a whole review round. When adding
a pattern, add its pin -- and verify by deleting the pattern and watching exactly
one named case fail.

Authoring-time flagging in the editor is bd `polyglot-pdf-zerz`; the voice path
still soliciting these fields, and the audit trail recording them as confirmed,
is bd `polyglot-pdf-sxyp`.

### The widget gotchas (scar tissue)

- **COMB widgets truncate on RENDER, not on read-back.** A text widget with the
  Comb flag (`field_flags & 1<<24`) splits its box into exactly `MaxLen` cells and
  prints ONE glyph per cell -- there is no cell `MaxLen+1`. PyMuPDF stores and
  reads back a longer value perfectly, so the AcroForm VALUE round-trips while the
  **rendered page** silently shows only the first `MaxLen` characters. Three W-7
  fields are comb-8, so `03/14/1990` printed as `03/14/19` -- a wrong date of birth
  on a filed ITIN application that no value-level check, lint, or test could see
  (bd `polyglot-pdf-br7t`). `fit_comb_value` clears the Comb flag when the value
  is longer than the cells, so it renders in full as ordinary text.
  **It never rewrites the value** -- appearance only. That restraint is the whole
  design: an earlier cut also stripped formatting punctuation so an identifier like
  `123-45-6789` would still fit its comb-9 box, and three review rounds each found
  another input where stripping REORDERED meaning instead of reformatting it
  (`1990-03-14` -> `19900314`, `14.03.1990` -> `14031990`), each of which then fit
  comb-8 and printed a plausible-looking WRONG date in a `month / day / year` box.
  Every guard added just attracted a new separator, so the strip is gone and the
  class is unreachable by construction. The cost is cosmetic but REAL, not rare:
  nothing gates the download path (`handleDownloadPDF` calls `fillPDF` with no
  validation) and a `type: "date"` field cannot be length-gated at all
  (`validateField` early-returns to `validateDateValue`, which never reads
  `max_length`), so the W-7 dates render un-combed on **every** UI submission, and
  a separator-bearing SSN on i-90/f1040 renders as ordinary text. That is the
  deliberate trade: visibly-odd beats a reordered date that looks correct and gets
  filed. Restoring the cell look belongs in INPUT normalization, where the field's
  semantic type is known -- never a rewrite in the filler (bd
  `polyglot-pdf-2ho7`, closed won't-do for exactly this reason).
  **Verify any change here by RENDERING** -- `page.get_text("text",
  clip=widget.rect)` -- never by reading `widget.field_value` back, which is
  exactly the check this class of bug defeats. Note `widget.text_maxlen = 0` does
  NOT persist through save (bd `polyglot-pdf-9oae`); clearing the flag is what
  works. Relaxing also does not make an arbitrarily long value fit -- it still
  clips at the box WIDTH, which is currently silent (bd `polyglot-pdf-8i43`).

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
(`put_schema`, `put_metadata`, `load_metadata`, `list_kit_files`,
`put_pdf_bytes`, and `put_json_artifact` / `load_json_artifact` for per-kit JSON
artifacts such as the persisted AcroForm dump `acroform.json`, bd
`polyglot-pdf-v96b`) consumed by the token-gated `/api/editor/*` routes
(`backend/routes/editor_kit_routes.py`) that back the hosted schema editor (bd
`polyglot-pdf-92qe.1`). PDF filling and the public `/api/form-kits*` routes never
call the write surface; drafts stay invisible to the voice app (the complete-only
manifest gate is unchanged).

## Debugging

`DEBUG_PDF_FILLING.md` (repo root) is the field-by-field debug runbook for the
"blank PDF" failure modes — wrapped-value symptoms (`{value:...}` reaching the
backend = unwrap failed), `field_count=0` (frontend not sending), `filled=0`
(pdf_field_name mismatch — dump real widget names with a `fitz` one-liner), and a
curl recipe against `/api/fill-pdf`.
