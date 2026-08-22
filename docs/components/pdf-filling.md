# PDF filling

**Tracks:** backend/routes/pdf_fill_routes.py backend/routes/editor_kit_routes.py backend/services/form_kits.py frontend/src/schema-forms/utils/pdfFiller.ts

*Last updated: 2026-08-20 (bd polyglot-pdf-i9e79: added the "Draft
snapshots" paragraph documenting the bounded `_drafts/<n>/` ring (bd
polyglot-pdf-y2l0p) alongside the revision archive, and added
`backend/routes/editor_kit_routes.py` to this doc's tracked-source
declaration above -- the file the archive/lifecycle/lock sections already
cite extensively, but which the Tracks line had never named.)*

How filled answers become a downloadable/printable PDF. The flow is **stateless**:
the client sends field values + schema, the backend fills a fresh copy of the
blank PDF with PyMuPDF and returns the bytes — nothing is stored. The form state
that feeds this is in [schema-forms.md](schema-forms.md); the no-persistence rule
is [../standards/stateless-architecture.md](../standards/stateless-architecture.md).

## Request flow

1. `SchemaForm` (Download/Print buttons) **unwraps** each `FieldValue` →
   `unwrapFieldValue` (a raw wrapper breaks fill) and calls `fillPDF(kitId, pdfUrl,
   values, schema, getToken, pdfFile)` in `frontend/src/schema-forms/utils/pdfFiller.ts`.
2. `fillPDF` POSTs to **`/api/fill-pdf`** with `{kit_id, pdf_filename, field_values,
   form_schema}` and an `Authorization: Bearer <idToken>` header via its optional
   `getToken` callback -- the route is auth-gated (bd polyglot-pdf-z2is; the body
   carries user-entered values). `pdf_filename` is the manifest's explicit
   `pdfFile` (threaded as a prop from `SchemaFormDemo`, bd polyglot-pdf-vccy) --
   a PRIVATE kit's `pdfUrl` is the backend route `.../pdf`, so the old
   URL-tail derivation would post the literal "pdf" and 404 the store read;
   the URL split survives only as the fallback for a missing `pdfFile`.
   Callers inside the authed app thread
   `user.getIdToken()`; local dev against a `VFF_DISABLE_AUTH` backend may omit it.
   (Backend HTTP base: env override → `VITE_BACKEND_HTTP_URL` →
   current origin via Firebase rewrite → `localhost:8000` dev fallback.
   Manifest `/api/` asset paths resolve via `resolveKitAssetUrl` -- same base.)
3. The backend (`backend/routes/pdf_fill_routes.py`) runs the shared
   client-tier kit gates (`backend/services/kit_gates.py`: publish status +
   firm visibility -- the body's caller-supplied `kit_id` made this the
   fourth gated read, bd polyglot-pdf-vy6id; a private kit 404s for
   non-members), then loads the blank PDF from the form-kit store, fills it,
   and returns `application/pdf` bytes.
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

**Revision archive** (bd `polyglot-pdf-w3zw`): `put_archived_revision`,
`load_archived_revision`, and `list_archived_markers` keep SUPERSEDED schemas
readable at `<kit_id>/_archive/<marker>/`. Kit storage is one slot per kit_id, so
a republish overwrites in place -- and the confirmation audit trail records
`kit_id` + a revision marker that is *not* a storage address, so without this a
republish destroyed the schema an old record was confirmed against. The marker is
resolved from the superseded revision's OWN schema (`resolve_edition_marker`,
through ALL THREE ranks -- `edition_date`, then `author_version`, then the shape
fingerprint) and encoded into one safe path segment by `encode_marker` (it
encodes rather than rejects: real markers contain `/` and `:`, which
`safe_filename` bars). The archive MUST resolve through the same ranks the
confirmation record did: keyed on anything else, the bytes are on disk under a
key no record names and the retrieval this whole mechanism exists for silently
fails (bd `polyglot-pdf-xzw5` -- an `author_version` kit archived under a
`sha256:` fingerprint until this was fixed; the agreement is pinned by a test
that resolves both sides). The
archive is written whenever a PUBLISHED revision is retired -- on
revert-to-draft, on unpublish, on the outgoing kit of a `replaces_kit_id`
supersede (bd `polyglot-pdf-6dz0`), and on the CLIENT-TIER firm retire route
(bd `polyglot-pdf-z6bk9`), the one writer that is NOT an editor route. Every
editor route
that writes `schema.json` refuses while the kit is write-locked (save, repair,
translate-options, derive-divisions, regenerate-guidance, and extract -- the
last of these was ungated until bd `polyglot-pdf-w3zw` and is now pinned by a
property test), so retirement is the last moment the published bytes exist. A
marker is not a unique key -- two revisions can share one `edition_date` -- so
the archive skips only when the stored copy IS the same schema, and a distinct
revision under a taken marker lands on a fingerprint-disambiguated sibling
(`<marker>--<fingerprint>`). Retrieval therefore searches the marker AND its
siblings: `scripts/read_kit_revision.py` returns the revision when exactly one
answers to the marker, and **exits 3 (AMBIGUOUS) without guessing** when
several do -- for a confirmation record, a confident wrong schema is worse than
an honest "cannot tell". `--segment` reads one exact archived segment after the
operator disambiguates from `--list`.

**Draft snapshots** (bd `polyglot-pdf-y2l0p`): `put_draft_snapshot`,
`list_draft_snapshots`, and `load_draft_snapshot` keep a bounded ring of
overwritten DRAFT copies readable at `<kit_id>/_drafts/<n>/`
(`schema.json` + `meta.json`), capped at `DRAFT_SNAPSHOT_LIMIT = 10` --
oldest evicted first. This is a distinct namespace from the archive above:
draft snapshots never land under `_archive/<marker>/`, and the archive
never sees a draft. The routes are `GET
/api/editor/kits/{kit_id}/draft-snapshots` (list, newest first) and `POST
/api/editor/kits/{kit_id}/draft-snapshots/{snapshot_id}/restore`. The two
write paths are DELIBERATELY asymmetric: a plain save snapshots the
schema it is about to overwrite BEST-EFFORT (a snapshot failure is logged
but never blocks the save -- the editor's current work outranks protecting
an older copy), while a restore snapshots the CURRENT draft it is about to
replace and REFUSES if that snapshot fails (a restore knowingly destroys
the live draft, so declining when the safety net can't be laid down is the
honest failure -- a recovery feature that silently loses work is worse than
one that says no).

**The kit lifecycle has FOUR statuses** (bd `polyglot-pdf-hqztg`):
`draft -> submitted -> complete`, plus `unpublished` for a retired revision.
`submitted` exists because editors are SUBCONTRACTORS: marking a form ready
must not release it. An editor may submit and may reopen their own submission;
publishing and reaching back into a live kit are author-only, enforced per
TRANSITION inside the one `/status` handler rather than per route. `submitted`
is write-locked like `complete` -- otherwise an author would review one version
and publish another -- and reopening it CLEARS any author version, since a kit
that was never live has no confirmation record naming its version (the xzw5
immutability lock protects PUBLISHED versions only).

An **editing lock** (`POST`/`DELETE /api/editor/kits/{kit_id}/lock`) sits over
that: an author can always take a kit back from an editor, never the reverse,
and that preemption doubles as the stale-lock release. **A status transition
also releases it** -- handing a kit up for review, sending it back, publishing
it or retiring it all end the editing turn, and the retired kit in a
replace-publish is released too. The one exception is REOPENING a live kit
(`complete -> draft`), which begins an editing turn rather than ending one, so
the author who reopened it keeps their own lock; a stale lock held by anyone
else is still cleared. Without the release, an author who sent a kit back left
the editor unable to touch their own draft, with no control offered to
self-rescue. It is ROLE-scoped, not
user-scoped, because the editor API has only two shared tokens -- two editors
sharing one still collide (bd `polyglot-pdf-ijntk`). A preempted editor finds
out on their NEXT SAVE, which 409s: there is no channel from server to editor,
so the save is the notification. Every route that rewrites a schema honours the
lock, enforced through one `_require_edit_lock` helper and pinned by a property
test that derives the route list from the shipped module.

**The one thing that removes an archive** is `DELETE /api/editor/kits/{kit_id}`
(bd `polyglot-pdf-6x1j`) -- author-only, and guarded by a THREE-state check
rather than a warning: records exist -> 409 offering unpublish; no records and
the check *succeeded* -> deleted; the check could not run -> 409 refusing.
`confirmation_logger.kit_has_confirmation_records` RAISES
`ConfirmationCheckUnavailable` rather than returning False when the Firestore
sink is off or its query fails, because the local JSONL fallback dies with the
instance -- reading that silence as "no records" would let an author working
locally destroy the evidence this archive exists to preserve. Taking the
archive with the kit is deliberate: a kit with no confirmation records has
nothing naming its superseded revisions, so leaving them strands bytes no
record can retrieve. `FormKitStore.delete_kit` is the store's ONLY destructive
primitive; both impls confine the delete to the kit's own prefix (the local one
resolves and re-checks containment, since `_kit_dir` is a bare join; the GCS one
appends a trailing slash, without which `w7` would also sweep away `w7-2024`). Archives are invisible to the RUNTIME catalogues for free: `list_kit_files`
ignores anything deeper than `<kit>/<file>` in both backends, and `_archive` is
outside `_KIT_ID_RE`. The static-bundle copy is a separate matter and needed an
explicit fix -- `copyKitsToPublic` in `frontend/scripts/generate-form-manifest.ts`
is recursive, so it now filters underscore-prefixed dirs at EVERY level (the
deploy scripts' own `_*` guards skip only top-level entries like
`form-kits/_translation`, which is why a nested `_archive` slipped past them).
Archives DO belong in the GCS bucket: that is the authenticated backend store
the operator read goes through. `scripts/read_kit_revision.py` is the operator read
(current-or-archived, by `kit_id` + marker).

## Debugging

`DEBUG_PDF_FILLING.md` (repo root) is the field-by-field debug runbook for the
"blank PDF" failure modes — wrapped-value symptoms (`{value:...}` reaching the
backend = unwrap failed), `field_count=0` (frontend not sending), `filled=0`
(pdf_field_name mismatch — dump real widget names with a `fitz` one-liner), and a
curl recipe against `/api/fill-pdf`.
