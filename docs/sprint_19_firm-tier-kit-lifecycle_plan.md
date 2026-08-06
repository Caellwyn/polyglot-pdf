# Sprint 19 -- Firm tier + kit lifecycle: one entry per form, firm-scoped kits

Epics: polyglot-pdf-7jmy (kit lifecycle) + polyglot-pdf-02ye (firm tier),
planned together per the maintainer's instruction in 7jmy ("Plan these together
or make the seam explicit"). Maintainer-approved 2026-08-05 via /plan-epic,
including two product calls confirmed in-session: (1) firm identity via a
firm_id custom claim only (a firm-held API key is designed into the deferred
magic-link bead, not built now); (2) same-kit republish always archives and
replaces, with a "replace current" control only for the cross-kit supersede
case.

## Why (L1)

**Kit lifecycle (7jmy).** A REVISION of a form is not a new FORM. A client
picking a form must see "W-7" once, never fifteen dated variants -- while the
confirmation audit trail (pinned to kit + form + edition since bd 47r3) must
still name the exact revision the client confirmed against. Today those goals
conflict: kit storage is one directory per kit_id with destructive
overwrite-in-place, so republishing a kit silently destroys the schema that
old confirmation records reference, and there is no unpublish or delete path
at all.

**Firm tier (02ye).** The product is moving from a demo behind a Google
sign-in wall to real customer organizations (law firms / nonprofits). Each
firm needs its own identity so usage/completion/error statistics can be
tracked per firm without touching client PII; a profile with an allowed-forms
list because some firms have internal, proprietary forms other firms must not
see; and a datastore to hold those profiles. Kit visibility must become
firm-scoped on every surface: catalogue list, schema read, the
deliberately-public kit-PDF GET, and the static Hosting bundle (which today
ships EVERY kit -- including drafts -- publicly).

**The seam.** A firm's proprietary kit is exactly the kit with no government
edition date (the author-version requirement), and per-firm allowed-forms
needs revision-stable kit identity (the archive-in-place design). kit_id stays
stable across revisions, so firm allowlists never churn on republish.

## Settled decisions (maintainer, carried from the epic beads + approval)

- Superseded revisions: keep files in storage, hide from the manifest. Never
  overwrite-in-place destructively.
- Hard-delete guard: REFUSE (not warn) when confirmation records exist for the
  kit; offer unpublish instead.
- Firm identity now = firm_id custom claim on staff Firebase accounts, stamped
  by an admin bootstrap step. The per-firm API key (for the firm's console to
  request magic links from our mint endpoint -- we sign, the firm never holds
  a signing key) ships with the deferred magic-link bead.
- Client tier stays account-less; firm identity identifies FIRMS, never
  clients. Magic links carry {firm_id, kit_id, jti, exp} and deliberately no
  client identifier.
- Same-kit republish always archives + replaces (no checkbox); the "replace
  current" control appears only when publishing a different kit directory that
  supersedes a live kit for the same form, and unpublishes the old kit
  atomically.

## Design

### Kit lifecycle (7jmy)

- **Revision archive.** On promotion to complete when a complete revision with
  a different schema already exists, copy the current schema + metadata to
  `<kit_id>/_archive/<marker>/`. The marker is resolved FROM THE SUPERSEDED
  REVISION'S OWN schema (its edition_date, else its author_version, else its
  fingerprint; collision-suffixed by published_at) -- so a fingerprint-era
  revision archives under the exact `sha256:` marker its old confirmation
  records already carry, and those records stay retrievable even after the kit
  later gains an author_version. Works local + GCS; `list_kit_files` already
  ignores paths nested deeper than `<kit>/<file>`, so archives stay out of the
  editor catalogue for free. Retrieval: `load_archived_schema(kit_id, marker)`
  plus an operator script (sibling of `scripts/read_confirmations.py`) that
  takes a confirmation record's kit_id + marker and returns the exact schema,
  current-or-archived; for a `sha256:` marker it may additionally fall back to
  recomputing fingerprints over the current + archived schemas.
- **Statuses become `draft | complete | unpublished`.** Unpublished is hidden
  like draft but WRITE-LOCKED like complete (draft is editable, and editing a
  superseded revision would corrupt the bytes the audit trail references);
  reversible to complete through the full publish gate. The third status must
  be threaded through every hardcoded two-value site, or it silently coerces
  to "unknown" and the write-lock never fires: `_status_of`'s
  `("draft", "complete")` allowlist (editor_kit_routes.py:387, guarding five
  write-path gates -- its `== "complete"` checks must become
  is-write-locked checks), `KitStatusBody`'s `Literal["draft","complete"]`
  (which would 422 the unpublish request itself), the schema-editor's LOCAL
  `KitStatus` type in formKitDirectory.ts:19 + the FormCatalogue status
  bucketing built on it, AND the HOSTED path's own two-value sites in
  remoteKitStore.ts -- `RemoteKitEntry.status` (:33), `KitStatusResult`
  (:417-419), and `setRemoteStatus`'s parameter type (:431-432, which as
  written cannot express the unpublish call at all) -- plus RemoteCatalogue's
  status bucketing/badge styling. (Do not confuse these with the backend
  Pydantic `KitStatusResponse` -- its status field is a bare str, no change
  needed -- or the LOCAL-mode `setKitStatus` in formKitDirectory.ts.) The
  hosted path is the one that talks to the backend /status route, so it is
  the path rubric #5's verify exercises.
  form_kit_routes.py itself needs NO change for hiding: `_require_published`
  and the manifest filter are already complete-or-hidden inclusion tests, so
  a third status hides automatically.
- **Author-supplied version.** When `form_metadata.edition_date` is absent
  (a firm's proprietary intake sheet), the publish modal shows a version box
  prefilled with the current date (ISO yyyy-mm-dd), previous value shown,
  normalized input; stored as `form_metadata.author_version` -- a NEW field,
  never written into edition_date (documented as strictly the government
  marker). `resolve_edition_marker` precedence becomes edition_date >
  author_version > fingerprint; existing fingerprint-marked records stay
  valid. The field lands in BOTH TypeScript `FormMetadata` mirrors
  (schema-editor/src/types/schema.ts and
  frontend/src/schema-forms/types/schema.ts) -- FieldEditor's metadata setter
  is typed `keyof FormSchema['form_metadata']`, so omitting the editor mirror
  is a compile error -- and the kit-card version label
  (`versionInfoFromSchema`, formKitDirectory.ts:226-235) gains an
  author_version slot in its precedence chain so a freshly-versioned kit
  stops rendering as 'unknown (verify)'.
- **Guarded hard delete.** DELETE /api/editor/kits/{kit_id} (author role).
  Backend queries `confirmation_events` by kit_id equality (cheap; no
  composite index needed) -- any hit returns 409 with a "records exist;
  unpublish instead" payload; zero hits deletes the whole kit prefix
  (including archives) after the editor UI's type-the-kit-id confirmation
  modal. The prefix delete is a NEW store-level primitive on `FormKitStore`
  (the ABC has no delete of any kind today) with both implementations --
  local recursive dir removal and GCS list_blobs + batch delete -- the route
  never touches the filesystem or bucket directly, or GCS mode breaks.
- **Coordination with sprint 18 (epic polyglot-pdf-4qul, active) -- TWO
  beads, not one.** (a) C8 moves the token-spending translation bake OUT of
  the /status promotion route (the free coverage CHECK stays); the archive
  hook and replace-current semantics must attach to whatever the promotion
  transition is when they land. (b) C2 (bd polyglot-pdf-apmo, open) reworks
  the WRITE-LOCK semantics themselves across three of the lifecycle bead's
  files (editor_kit_routes.py, RemoteCatalogue.tsx, FormCatalogue.tsx): it
  adds a SIXTH write-path lock (the extract route joins the five == complete
  gates -- treat the gate inventory as "every write-path lock at claim time",
  not a fixed five) and introduces an author-only Unlock action. Unlock
  semantics against `unpublished` are pinned HERE: Unlock applies to COMPLETE
  kits only; an unpublished kit is never unlockable to draft (it returns to
  complete only through the full publish gate), because unlocking it to an
  editable draft would let the bytes an audit record references be edited --
  the exact corruption the status exists to prevent. Check BOTH beads' state
  at claim time; do not race either.

### Firm tier (02ye)

- **Datastore: Firestore** collection `firms/{firm_id}`: profile (name,
  contact), `allowed_kits: [kit_id]`, status, created_at; usage rollups
  later; token_hash deferred to the magic-link bead. Admin-SDK-only access
  with an explicit default-deny block in firestore.rules. Bootstrap via an
  admin script: create the firm record, stamp the firm_id custom claim on the
  firm's staff accounts (keyed by their emails).
- **Kit visibility -- two orthogonal axes.** Lifecycle status (7jmy) x
  visibility. Kit metadata gains `visibility: "public" | "private"` +
  `owner_firm_id` (set at onboard/publish; existing kits default public). A
  firm sees: complete AND (public OR kit_id in its allowed_kits).
  Anonymous/legacy authed users see public only. The deliberately-public
  kit-PDF GET stays open for public kits and gates for private ones
  (test_form_kit_pdf_is_deliberately_public is updated deliberately, not
  broken).
- **Private-kit SERVING seam (the third piece the form_kit_routes.py revisit
  comment names).** Today every manifest entry carries schemaPath/pdfPath as
  STATIC Hosting paths and the viewer fetches them verbatim -- so a private
  kit excluded from the bundle would be unloadable by its own firm. Where the
  paths come from matters for the fix: in GCS mode they are BAKED into
  index.json by deploy-all.sh:383 (the store's load_manifest passes them
  through; `normalize_manifest` only supplies defaults and is a firm-agnostic
  store-boundary validator with no request context -- do NOT attack it); in
  local mode LocalFormKitStore.load_manifest emits them. The per-request
  rewrite therefore belongs in `list_form_kits` (form_kit_routes.py:162-180),
  the one site that already holds the caller's decoded claims and already
  post-filters entries: for PRIVATE kits it rewrites schemaPath/pdfPath to
  the authenticated backend routes (`/api/form-kits/<id>/schema` + `.../pdf`)
  -- SchemaFormDemo's comment already anticipates manifest entries carrying
  `/api/...` paths. Viewer fetches become header-carrying on those paths: the
  schema fetch already attaches the Bearer token; the pdf-view overlay
  (SchemaForm -> PreviewPane.tsx:57 -> usePDFDocument.ts:47, which passes the
  raw URL to `pdfjsLib.getDocument` with no header capability) needs the
  fetch-with-header -> blob URL form that FilledPreviewModal.tsx:85 already
  demonstrates. Public kits keep the static paths unchanged. The seam has a SECOND consumer beyond display: pdfFiller.ts:96
  derives the `pdf_filename` it POSTs to /api/fill-pdf by taking the last URL
  segment (`pdfUrl.split('/').pop()`), and SchemaFormDemo.tsx:109-111 does the
  same for schema/pdf filenames -- under backend-route paths those segments
  become the literals "pdf"/"schema" and the fill 404s in
  `store.load_pdf_bytes`. The fix is on the BACKEND side of the wire: the
  client manifest's `FormKitInfo` response model (form_kit_routes.py:124-128)
  today exposes only paths, no filenames -- and the frontend
  `FormKitDescriptor.pdfFile` is populated by splitting those very URLs
  (SchemaFormDemo.tsx:109-111), so it breaks identically under rewritten
  paths. `FormKitInfo` gains `schema_file`/`pdf_file` (the normalized manifest
  entries already carry them), and SchemaFormDemo populates
  `FormKitDescriptor.schemaFile`/`pdfFile` from those fields instead of the
  URL split, so the filled-PDF download keeps working for private kits. (The
  editor route already ships schemaFile/pdfFile keys -- that is the
  token-gated editor catalogue, not this client manifest; don't let the grep
  hit satisfy you.) `fillPDF` has three call sites in
  two more files -- SchemaForm.tsx:623 (download) / :659 (print) and
  FilledPreviewModal.tsx:62 (preview), all fed by a `pdfUrl` prop from
  SchemaFormDemo -- so the explicit-filename fix threads a `pdfFile` prop
  through both components' interfaces as well.
- **Firm identity propagation.** The firm_id claim rides the existing
  require_auth decoded claims and the WS ?token= verify; threaded into the
  fill session the way kit_id was in 47r3. `log_form_session_start`/`_end`
  (defined, currently zero callers) finally get wired from
  `_handle_fill_session` and gain firm_id; `log_field_confirmation` gains
  firm_id. Per-firm usage = Firestore queries keyed by firm_id.
- **Static pipeline.** `generate-form-manifest.ts` restricts BOTH of its
  outputs to status=complete AND visibility=public: the index.json listing AND
  the byte copy into frontend/public/form-kits (today `copyKitsToPublic` is a
  blanket recursive `fs.cp` that ignores the descriptor list -- filtering only
  the index would still ship the bytes). The filter is NOT per-kit only: it
  must also exclude underscore-prefixed entries at BOTH levels (root and
  within each kit dir), or a passing kit's `<kit>/_archive/**` subtree rides
  the copy onto public Hosting once the revision archive (7jmy) exists --
  the root-level `form-kits/_translation/` dir ships publicly today by
  exactly this mechanism (the deploy scripts skip `_`-entries only at root,
  and only for GCS). This also closes the existing hole where DRAFT kits ship
  publicly in the Hosting bundle. Private kits exist only in GCS and are
  served through the authenticated backend routes via the serving seam above.
- **Deferred (filed as blocked children).** Magic-link minting + EntryGate +
  fragment routing; per-jti/per-firm rate limits + per-session cost ceiling
  (required before the FIRST PUBLIC LINK, which does not exist until
  magic-link entry ships; nothing exists today to extend -- it is new
  infrastructure).

## Exit rubrics

### Epic 7jmy -- kit lifecycle

| # | Criterion | Verify |
|---|-----------|--------|
| 1 | After republishing a changed revision of an already-published kit, the client catalogue shows exactly ONE entry for that form, serving the new revision | Local stack: publish, edit, republish; curl GET /api/form-kits + schema read |
| 2 | A confirmation record naming a superseded revision (kit_id + marker) still retrieves the EXACT schema JSON it confirmed against, via a documented operator step | Replace a kit's schema, then run the retrieval script with the old record's kit_id + marker; diff against the pre-replace schema |
| 3 | Publishing a kit with no government edition_date requires an author version (prefilled with the current date, previous value shown), and subsequent confirmation events carry that marker instead of a bare fingerprint | Publish a no-edition kit in the editor; inspect the modal, then a logged event doc |
| 4 | Hard delete is REFUSED (with an unpublish suggestion) for any kit with confirmation records, and succeeds -- removing storage -- for a kit with none, only after an explicit confirmation modal | Seed one confirmation event for kit A: DELETE returns 409. Kit B (no events): DELETE removes the prefix from the store |
| 5 | Unpublish removes a kit from the client manifest without deleting files, blocks schema edits while unpublished, and is reversible through the normal publish gate | Against the GCS-mode gating path (enforce_complete_on_public_reads -- local mode is deliberately ungated and serves drafts, so a local curl cannot show the hiding): unpublish -> manifest omits the kit, files present, PUT schema -> 409; republish -> visible again |

### Epic 02ye -- firm tier

| # | Criterion | Verify |
|---|-----------|--------|
| 1 | A firm exists as a datastore record (profile + allowed-forms) created by a documented admin step, and a staff user carries that firm's identity in their auth token | Run the bootstrap script; read firms/{firm_id} in Firestore; decode a staff ID token and see firm_id |
| 2 | A private kit is invisible outside its firm on EVERY surface: catalogue list, schema read, kit-PDF GET, and the built static Hosting bundle (which also no longer contains drafts) -- while remaining fully USABLE for its own firm: it loads, fills, and downloads the filled PDF | curl matrix as firm-A staff / firm-B staff / legacy authed user; grep frontend/public/form-kits after a build; complete a fill + filled-PDF download of the private kit as firm-A staff |
| 3 | Form sessions run under a firm identity produce session-start/end and confirmation events keyed by firm_id, so a per-firm usage count is answerable by query | Run a local voice session as firm staff; query confirmation_events by firm_id |

## Bead tree

Serial chain within each epic where surfaces overlap (editor_kit_routes.py and
confirmation_logger.py are hubs); cross-epic ordering edge 7jmy.2 -> 02ye.2.

### 7jmy children

| Bead | Scope | Surfaces | Inherits |
|------|-------|----------|----------|
| revision-archive | Archive-on-republish in the store + retrieval helper + operator script | backend/services/form_kits.py, scripts/ (retrieval script) | 7jmy #2 |
| lifecycle-statuses | `unpublished` status (write-locked, hidden, reversible; threaded through the `_status_of` allowlist, the `KitStatusBody` Literal, and BOTH editor catalogues' status types/bucketing -- local formKitDirectory/FormCatalogue and hosted remoteKitStore/RemoteCatalogue) + replace-current cross-kit publish + editor UI | backend/routes/editor_kit_routes.py, schema-editor/src/components/RemoteCatalogue.tsx, schema-editor/src/components/FormCatalogue.tsx, schema-editor/src/utils/remoteKitStore.ts, schema-editor/src/utils/formKitDirectory.ts | 7jmy #1, #5 |
| author-version | author_version field (Pydantic + both TS FormMetadata mirrors) + modal version box (prefill/normalize/show-previous) + kit-card version-label precedence + marker precedence + lint update | backend/models/form_models.py, schema-editor/src/types/schema.ts, frontend/src/schema-forms/types/schema.ts, schema-editor/src/utils/formKitDirectory.ts (version label), backend/utils/confirmation_logger.py, backend/services/schema_lint.py, schema-editor publish-modal component | 7jmy #3 |
| guarded-delete | DELETE route + kit_id-keyed confirmation existence query (lands in confirmation_logger.py) + NEW store-level prefix-delete primitive (local + GCS impls on FormKitStore) + confirm modal UI | backend/routes/editor_kit_routes.py (delete route), backend/services/form_kits.py (delete primitive), backend/utils/confirmation_logger.py, schema-editor catalogue delete UI | 7jmy #4 |

Ordering: revision-archive -> lifecycle-statuses -> author-version ->
guarded-delete (blocks edges; the latter two could in principle run
concurrently but share editor-UI + confirmation_logger surfaces -- kept
serial).

### 02ye children

| Bead | Scope | Surfaces | Inherits |
|------|-------|----------|----------|
| firms-store | firms collection model + FirmsService + firestore.rules deny block + bootstrap/claim-stamping admin script | backend/services/firms.py (new), firestore.rules, scripts/ (admin script, new) | 02ye #1 |
| kit-scoping | visibility/owner_firm_id metadata + firm filter on manifest/schema/pdf routes + the private-kit serving seam (per-request path rewrite in list_form_kits; header-carrying viewer fetches incl. the pdf-view overlay; `FormKitInfo` gains schema_file/pdf_file and the frontend reads them instead of URL-splitting -- a pdfFile prop threads through SchemaForm and FilledPreviewModal -- so the pdf-fill call survives) + test updates | backend/routes/form_kit_routes.py, backend/services/form_kits.py, frontend/src/schema-forms/SchemaFormDemo.tsx, frontend/src/schema-forms/components/SchemaForm.tsx, frontend/src/pdf-view/FilledPreviewModal.tsx, frontend/src/pdf-view/PreviewPane.tsx, frontend/src/pdf-view/usePDFDocument.ts, frontend/src/schema-forms/utils/pdfFiller.ts, backend/tests/unit/test_http_route_auth.py | 02ye #2 |
| static-scoping | Static pipeline filters to complete + public, and excludes `_`-prefixed entries at root AND kit level (closes the draft leak and the `_translation`/future `_archive` sweep) | frontend/scripts/generate-form-manifest.ts | 02ye #2 (static half) |
| firm-telemetry | firm_id threading (claims -> WS session) + wire log_form_session_start/end + firm_id on confirmation events | backend/routes/websocket_routes.py, backend/utils/confirmation_logger.py | 02ye #3 |
| magic-links (BLOCKED) | Per-firm API key + link minting + EntryGate + fragment routing (settled design) | frontend/src/schema-forms/, backend auth | deferred until first paying firm |
| limits (BLOCKED) | Per-jti/per-firm rate limits + per-session cost ceiling | backend (new middleware) | required before first public link |

Ordering: 7jmy lifecycle-statuses -> 02ye kit-scoping -- a behavioral edge,
not a file collision: kit-scoping layers the firm filter onto the same
manifest/read gating (`_require_published`, the complete-only manifest
filter) whose complete-or-hidden semantics the unpublished status relies on,
so the status semantics settle first. firms-store and static-scoping are
parallelizable with everything (disjoint surfaces). firm-telemetry after
firms-store (needs the firm model) and after 7jmy
author-version/guarded-delete (shared confirmation_logger.py).

## Out of scope

- Admin dashboard / per-firm stats UI (bd polyglot-pdf-nt0, blocked on the
  BigQuery chain) -- this sprint only makes the DATA exist.
- Fingerprint widening (bd polyglot-pdf-8x56) and the legacy non-JIT
  handshake kit_id gap (bd polyglot-pdf-d95y).
- Client-tier accounts -- clients stay account-less (magic link / kiosk).
- Backend email delivery of completed forms (ruled out in the deployment
  plan).
- Retention policy activation (gated on the attorney answer, bd
  polyglot-pdf-pol2).
- Kiosk device enrollment (deployment plan, separate track).
- Data migration of existing kits' metadata (existing kits default
  visibility=public; absence of the key means public).
