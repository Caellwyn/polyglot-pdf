---
date: 2026-08-18
bead: polyglot-pdf-vccy
title: "Firm-scoped kit visibility on backend routes"
sprint: 19
tags: [security, testing]
---

## Trigger

Sprint-19 chain, epic polyglot-pdf-02ye child 2 -- the first consumer of the
lo88 firms store and firm_id claims. Started the moment the y2l0p claim
released (the write-overlap guard's first real catch: both beads declare
backend/services/form_kits.py, so vccy waited for y2l0p to land rather than
racing it). Some firms carry proprietary intake forms other firms must never
see; this bead makes kit visibility firm-scoped on every backend surface
while keeping a private kit fully USABLE for its own firm.

## What shipped

- Kit metadata gains visibility: "public" | "private" + owner_firm_id
  (absence = public; anything but the exact string "private" coerces public,
  so a typo can neither hide nor half-expose a kit). normalize_manifest and
  the local manifest synthesis pass the keys through; the ROUTE gate reads
  LIVE metadata (the GCS index.json is deploy-time stale).
- Route gates (backend/routes/form_kit_routes.py): the catalogue list, the
  schema read, and the pdf read all filter to complete AND (public OR kit_id
  in the caller's firm allowed_kits), firm resolved from the require_auth
  firm_id claim via firms.get_allowed_kits (fail-closed [], run off the
  event loop). Denial is 404 -- the kit's EXISTENCE is the secret. The
  deliberately-public pdf GET became public-for-PUBLIC-kits-only: it parses
  an OPTIONAL bearer token; an invalid token degrades to anonymous (404 on
  private kits, never 401), and the tokenless public read still serves bytes
  end to end (both pinned; test_form_kit_pdf_is_deliberately_public updated
  DELIBERATELY per the bead).
- The private-kit serving seam: list_form_kits rewrites a private kit's
  schema_path/pdf_path to the authenticated backend routes (the
  static-bundle exclusion is PENDING bd kkos -- exposure tracked as bd
  polyglot-pdf-17opi), FormKitInfo gains explicit
  schema_file/pdf_file, and the frontend stops URL-splitting filenames
  (SchemaFormDemo mapping; fillPDF's new pdfFile param threaded as a prop
  through SchemaForm and FilledPreviewModal). usePDFDocument does the
  header-carrying fetch -> blob URL for /api/ paths, and resolveKitAssetUrl
  resolves /api/ manifest paths against the backend base (a relative /api/
  fetch works on Hosting via the rewrite but not against the Vite dev
  server).
- Deploy wiring (the lo88 handoff set, all three sites): FIRMS_FIRESTORE_
  ENABLED=true in deploy-all.sh's BACKEND_ENV, the deploy-form-kit.sh
  drop-list hint names it, and test_deploy_form_kit_hints.py pins the
  enumeration.
- Tests: 14 new backend matrix tests (firm-A / firm-B / legacy / anonymous /
  invalid-token x list / schema / pdf, the fail-closed empty-allowlist pin,
  the tokenless public-pdf success path) + 4 frontend pins (explicit
  pdf_filename in the fill POST, /api/ path resolution) + the deploy-hint
  pin. Every new test mutation-verified: three backend mutation batches (6
  mutations, each red set exactly explained), two frontend mutations, one
  hint mutation. One process scar re-confirmed: a git-checkout mutation
  restore reverted an UNCOMMITTED real edit (the drop-list hint) -- caught
  by the post-restore red run and re-applied; restore mutations by
  re-editing when the file carries uncommitted work.
- Docs: auth.md (pdf-route gate paragraph rewritten, firm_id marked
  CONSUMED), config-deployment.md + technical_guide.md env rows flipped to
  wired, the three form-kit route-table rows gained their firm-scoping
  notes, and Surface contracts entry 7 records the four coupled contracts
  (metadata keys, allowlist chain, path rewrite, explicit filenames) -- the
  entry lo88 deferred until a live consumer existed.
- THE OUTER REVIEW'S CATCH (bd polyglot-pdf-vy6id, P1, closed by this PR):
  the Opus cross-surface pass enumerated the client-tier kit-read SET --
  exactly four sites -- and found the fourth ungated: POST /api/fill-pdf
  takes a caller-supplied kit_id, and with empty field_values its 200
  response is the kit's blank template verbatim, handing any authed user
  the private bytes the pdf GET 404s. Fix: the gates moved to
  backend/services/kit_gates.py (shared, not a route-to-route import), the
  fill route runs them, and the SET is pinned mechanically
  (test_every_client_tier_kit_read_is_visibility_gated derives the read
  sites from the shipped route sources and asserts each is gated), so a
  fifth read site fails CI instead of shipping ungated. Scar #7 in its
  purest form: the first three gates were correct -- they just were not the
  whole set, and only the reviewer whose JOB is the blast radius saw it.
- Outer round 2 (Opus): two more findings. HIGH -- this diff's own comment +
  technical_guide entry asserted "the static bundle excludes private kits"
  as shipped fact, but that exclusion is bd kkos (still open), and this PR
  wires the feature flag on; both statements reworded to PENDING-kkos with
  an explicit no-private-kits-before-kkos operational bar, and the reviewer
  filed the exposure as bd polyglot-pdf-17opi (P1, blocked by kkos). The
  static filter itself deliberately stays in kkos -- next bead, unblocked by
  this PR's merge. LOW -- the list route's manifest-entry visibility
  fallback answered the question differently than the single-kit gates when
  live metadata was absent; the list now calls the SAME
  kit_gates.kit_visibility verdict (live metadata is the only source,
  everywhere).
- Closeout assess: recorded in the merge ping after the loops ran.

## Lessons

- `pytest ... | tail -N` in a backgrounded run MASKS the exit code (the
  pipeline exits with tail's 0) AND discards the failure names -- two
  "full suite green" verdicts here were actually 10-failed runs, caught
  only by reading the COUNTS line. Never pipe a verdict-bearing test run;
  read counts, never exit codes alone (both directions of the scar).
- A bare MagicMock store double AUTO-CREATES whatever attribute new code
  reaches for -- here twice in one fixture: a non-awaitable load_metadata
  (TypeError) and a truthy enforce_complete_on_public_reads (armed the
  publish gate against None metadata). When production code grows a new
  store touchpoint, every MagicMock double needs that attribute pinned
  explicitly.
- A rebase DROPS merge commits -- including any conflict RESOLUTION and any
  ride-along edits committed with them. After closeout_finish's mandatory
  pull --rebase on a branch that had merged dev, re-verify every piece of
  content the merge commit carried (this branch lost the combined doc
  stamp, a test-fixture fix, and these lessons to exactly that; all
  re-applied post-rebase and re-verified by suite).

- The write-overlap guard's first live catch worked exactly as designed:
  vccy and the in-flight y2l0p both declared form_kits.py, the engine
  refused the pick, and waiting for the claim release cost two hours instead
  of a cross-session merge conflict in the kit store.
- A route whose auth is OPTIONAL (public kits open, private kits gated)
  cannot use a Depends(require_auth) -- parse the header manually and let an
  invalid token degrade to ANONYMOUS, because a 401 on a private kit leaks
  that the kit exists. 404-for-everyone-unauthorized is the invisibility
  contract, and the test matrix must include the anonymous AND garbage-token
  rows or the degradation path is unpinned.
- Direct-call tests leave FastAPI's Header()/Depends() default OBJECTS in
  parameters -- isinstance checks, not truthiness, before touching them.
- When a fake store double lacks a metadata loader, the manifest entry is
  the visibility fallback -- resolve the source once per entry
  (meta-if-dict else manifest) instead of assuming either side exists.

## Doc freshness

- Bumped: docs/components/auth.md, docs/components/config-deployment.md,
  docs/components/pdf-filling.md, docs/technical_guide.md (all track files
  this branch changed; each stamp points here).
- Reviewed and left: the standards/* stales flagged by the checker predate
  this branch (other beads' files).

## Files touched

- backend/routes/form_kit_routes.py
- backend/services/form_kits.py
- backend/tests/unit/test_http_route_auth.py
- frontend/src/schema-forms/SchemaFormDemo.tsx
- frontend/src/schema-forms/components/SchemaForm.tsx
- frontend/src/schema-forms/utils/pdfFiller.ts
- frontend/src/schema-forms/utils/pdfFiller.filenames.test.ts (new)
- frontend/src/pdf-view/usePDFDocument.ts
- frontend/src/pdf-view/FilledPreviewModal.tsx
- deploy-all.sh
- scripts/deploy-form-kit.sh
- tests/test_deploy_form_kit_hints.py
- docs/components/auth.md, docs/components/config-deployment.md,
  docs/components/pdf-filling.md, docs/technical_guide.md
- docs/journal/entries/2026-08-18-bd-vccy-firm-scoped-kit-visibility.md (this entry)
