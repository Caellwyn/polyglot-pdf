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
  `<kit_id>/_archive/<marker>/` (marker = resolved edition marker:
  edition_date, else author_version, else fingerprint; collision-suffixed by
  published_at). Works local + GCS; `list_kit_files` already ignores paths
  nested deeper than `<kit>/<file>`, so archives stay out of the editor
  catalogue for free. Retrieval: `load_archived_schema(kit_id, marker)` plus
  an operator script (sibling of `scripts/read_confirmations.py`) that takes a
  confirmation record's kit_id + marker and returns the exact schema,
  current-or-archived.
- **Statuses become `draft | complete | unpublished`.** Unpublished is hidden
  like draft but WRITE-LOCKED like complete (draft is editable, and editing a
  superseded revision would corrupt the bytes the audit trail references);
  reversible to complete through the full publish gate.
- **Author-supplied version.** When `form_metadata.edition_date` is absent
  (a firm's proprietary intake sheet), the publish modal shows a version box
  prefilled with the current date (ISO yyyy-mm-dd), previous value shown,
  normalized input; stored as `form_metadata.author_version` -- a NEW field,
  never written into edition_date (documented as strictly the government
  marker). `resolve_edition_marker` precedence becomes edition_date >
  author_version > fingerprint; existing fingerprint-marked records stay
  valid.
- **Guarded hard delete.** DELETE /api/editor/kits/{kit_id} (author role).
  Backend queries `confirmation_events` by kit_id equality (cheap; no
  composite index needed) -- any hit returns 409 with a "records exist;
  unpublish instead" payload; zero hits deletes the whole kit prefix
  (including archives) after the editor UI's type-the-kit-id confirmation
  modal.
- **Coordination with sprint 18 (epic polyglot-pdf-4qul, active).** Sprint 18
  C8 moves the token-spending translation bake OUT of the /status promotion
  route (the free coverage CHECK stays). The lifecycle beads touch the same
  route: the archive hook and replace-current semantics must attach to
  whatever the promotion transition is when they land, and 7jmy.2 must not
  race a C8 rework of the same lines -- check 4qul's state at claim time.

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
- **Firm identity propagation.** The firm_id claim rides the existing
  require_auth decoded claims and the WS ?token= verify; threaded into the
  fill session the way kit_id was in 47r3. `log_form_session_start`/`_end`
  (defined, currently zero callers) finally get wired from
  `_handle_fill_session` and gain firm_id; `log_field_confirmation` gains
  firm_id. Per-firm usage = Firestore queries keyed by firm_id.
- **Static pipeline.** `generate-form-manifest.ts` filters to
  status=complete AND visibility=public -- which also closes the existing
  hole where DRAFT kits ship publicly in the Hosting bundle. Private kits
  exist only in GCS and are served exclusively through authenticated backend
  routes.
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
| 5 | Unpublish removes a kit from the client manifest without deleting files, blocks schema edits while unpublished, and is reversible through the normal publish gate | Local flow: unpublish -> manifest empty, files present, PUT schema -> 409; republish -> visible again |

### Epic 02ye -- firm tier

| # | Criterion | Verify |
|---|-----------|--------|
| 1 | A firm exists as a datastore record (profile + allowed-forms) created by a documented admin step, and a staff user carries that firm's identity in their auth token | Run the bootstrap script; read firms/{firm_id} in Firestore; decode a staff ID token and see firm_id |
| 2 | A private kit is invisible outside its firm on EVERY surface: catalogue list, schema read, kit-PDF GET, and the built static Hosting bundle (which also no longer contains drafts) | curl matrix as firm-A staff / firm-B staff / legacy authed user; grep frontend/public/form-kits after a build |
| 3 | Form sessions run under a firm identity produce session-start/end and confirmation events keyed by firm_id, so a per-firm usage count is answerable by query | Run a local voice session as firm staff; query confirmation_events by firm_id |

## Bead tree

Serial chain within each epic where surfaces overlap (editor_kit_routes.py and
confirmation_logger.py are hubs); cross-epic ordering edge 7jmy.2 -> 02ye.2.

### 7jmy children

| Bead | Scope | Surfaces | Inherits |
|------|-------|----------|----------|
| revision-archive | Archive-on-republish in the store + retrieval helper + operator script | backend/services/form_kits.py, scripts/ (retrieval script) | 7jmy #2 |
| lifecycle-statuses | `unpublished` status (write-locked, hidden, reversible) + replace-current cross-kit publish + editor UI | backend/routes/editor_kit_routes.py, backend/routes/form_kit_routes.py, schema-editor/src/components/RemoteCatalogue.tsx, schema-editor/src/utils/remoteKitStore.ts | 7jmy #1, #5 |
| author-version | author_version field + modal version box (prefill/normalize/show-previous) + marker precedence + lint update | backend/models/form_models.py, backend/utils/confirmation_logger.py, backend/services/schema_lint.py, schema-editor publish-modal component | 7jmy #3 |
| guarded-delete | DELETE route + kit_id-keyed confirmation existence query + confirm modal UI | backend/routes/editor_kit_routes.py (delete route), schema-editor catalogue delete UI | 7jmy #4 |

Ordering: revision-archive -> lifecycle-statuses -> author-version ->
guarded-delete (blocks edges; the latter two could in principle run
concurrently but share editor-UI + confirmation_logger surfaces -- kept
serial).

### 02ye children

| Bead | Scope | Surfaces | Inherits |
|------|-------|----------|----------|
| firms-store | firms collection model + FirmsService + firestore.rules deny block + bootstrap/claim-stamping admin script | backend/services/firms.py (new), firestore.rules, scripts/ (admin script, new) | 02ye #1 |
| kit-scoping | visibility/owner_firm_id metadata + firm filter on manifest/schema/pdf routes + test updates | backend/routes/form_kit_routes.py, backend/services/form_kits.py, backend/tests/unit/test_http_route_auth.py | 02ye #2 |
| static-scoping | Static pipeline filters to complete + public (closes the draft leak) | frontend/scripts/generate-form-manifest.ts | 02ye #2 (static half) |
| firm-telemetry | firm_id threading (claims -> WS session) + wire log_form_session_start/end + firm_id on confirmation events | backend/routes/websocket_routes.py, backend/utils/confirmation_logger.py | 02ye #3 |
| magic-links (BLOCKED) | Per-firm API key + link minting + EntryGate + fragment routing (settled design) | frontend/src/schema-forms/, backend auth | deferred until first paying firm |
| limits (BLOCKED) | Per-jti/per-firm rate limits + per-session cost ceiling | backend (new middleware) | required before first public link |

Ordering: 7jmy lifecycle-statuses -> 02ye kit-scoping (shared
form_kit_routes.py). firms-store and static-scoping are parallelizable with
everything (disjoint surfaces). firm-telemetry after firms-store (needs the
firm model) and after 7jmy author-version/guarded-delete (shared
confirmation_logger.py).

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
