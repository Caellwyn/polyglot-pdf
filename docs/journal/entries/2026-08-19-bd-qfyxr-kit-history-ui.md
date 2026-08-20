---
date: 2026-08-19
bead: polyglot-pdf-qfyxr
title: "Kit history UI: one entry per form, per-form archived-versions disclosure"
sprint: 19
tags: [security, testing]
---

## Trigger

MAINTAINER REQUIREMENT (2026-08-06, verbatim in the bead): firms should never
scroll outdated forms -- one version per form at the top layer, older
versions under an "archived versions" menu specific to that form,
chronological by release date, read/update obvious. bd w3zw shipped the
revision archive as storage + operator CLI only; there was NO UI anywhere.
Unblocked by vccy (the firm-scoped serving seam the client half rides).

## What shipped

- Backend, client tier (form_kit_routes.py): GET /api/form-kits/{kit_id}/
  archive (revisions newest-first by the archived snapshot's published_at,
  stampless last) and .../archive/{marker}/schema (read-only). Both carry
  the FULL gate stack -- publish + firm visibility -- so a kit's history is
  visible exactly when the kit is; a private kit's archive 404s for
  non-members. Markers validated to encode_marker's exact contract
  ([A-Za-z0-9._-]{1,128}, no ".."); a hostile marker is refused by
  VALIDATION (400), pinned so a store-miss 404 can't masquerade as the
  guard. The require_auth route-set pin grew from five to seven routes
  (with both doc enumerations, same edit set), and the client-tier read-set
  pin now includes load_archived_revision.
- Backend, editor (editor_kit_routes.py): the same two reads token-gated,
  mirroring the draft-snapshots shape (404 for a missing kit vs empty list
  for no archive -- different answers). Deliberately NO write counterpart:
  archived bytes are what the audit trail names; returning to an old
  revision goes through draft/publish, never the archive.
- Editor UI: a shared leaf component (ArchivedVersions.tsx) mounted by BOTH
  catalogues -- RemoteCatalogue (card grid + selector strip, which move
  together) and FormCatalogue (card, rendered only when the local backend
  is reachable, its established server-actions gate). Collapsed by default,
  lazy first-fetch, newest-first list, and a READ-ONLY amber viewer
  (metadata header + schema summary + collapsible raw JSON) with zero form
  controls -- unmistakably not the editor. The catalogues stay deliberate
  siblings; the leaf is shared because a dialog duplicated twice is drift
  with no compensating benefit.
- Client UI: ArchivedVersionsLink in the post-selection header --
  deliberately NOT in the onboarding modal, where surfacing superseded
  revisions mid-form-pick invites exactly the current-vs-archived confusion
  exit criterion 3 forbids. Authed fetches through the new routes (Bearer
  token; /api/ paths resolved via resolveKitAssetUrl); read-only viewer in
  the same unmistakable register.
- Decision (the bead's point 5, decided-and-stated): firms DO see their own
  form history -- the client routes carry the firm gates, so a firm's
  private-kit history is exactly as visible as the kit.
- Tests: 16 new backend tests (the firm-gate matrix on both archive routes,
  sorting, marker validation per-row expected codes, the editor routes
  against the REAL LocalFormKitStore over a temp tree) + 6 component tests
  (collapsed-by-default, lazy single fetch, empty state, read-only viewer
  with no inputs, Bearer threading). Every pin mutation-verified (seven
  route mutations in two batches, two component mutations) -- each red set
  exactly as predicted, restores by re-edit.
- CLICK-THROUGH VERIFICATION (exit criterion 3 demands it): a seeded temp
  kits tree with two archived revisions, the real backend on :8001, the
  hosted-mode editor on :3001, driven in the browser -- disclosure
  collapsed by default with the primary action visible beside it; expanding
  listed 2025-06 then 2024-01; opening 2025-06 produced the dialog headed
  "Archived version of W-7 Demo -- read only" with zero form controls and
  the archived title/date. (A raw pixel screenshot was not compositable in
  the headless pane; the DOM assertions above are the record.) Fixture
  stack torn down by port; a stray backend on :8000 from another session
  was left untouched (the port-8001 sidestep).
- Fixture scar re-confirmed: a minimal seeded schema crashes the full
  editor VIEW on open (FieldList expects richer shape) -- the catalogue
  disclosure path needs no open, which is also why the click-through went
  through the cards.

- Closeout assess (fresh-eyes, sonnet-routed): round 1 rubric-PASS with
  four fixes -- the kit_gates set-count docstring falsified by this diff's
  own call sites; the archive LIST answering 200-empty for a GHOST kit in
  local mode (manifest-membership check + pin, reproduced live by the
  reviewer); the marker regex duplicated across route files (one
  is_safe_marker in kit_gates now); the client/editor viewer 404
  asymmetry. Round 2: the client 404 branch my own r1 fix added was
  UNTESTED (the brief overclaimed it) -- pinned + mutation-verified; a
  paste-duplicated comment; the archived-schema read's ghost-kit check
  made deliberate + pinned. Round 3: the EDITOR twin's vanished-revision
  branch untested (the exact mirror of r2's client finding -- twins keep
  teaching the same lesson; both now pinned) + the single-read pin
  extended to the archive route. Round 4: rubric PASS x3, terminal -- its
  one finding (the error-banner rendering branches on both twins,
  UNCHANGED since the original commit, untested) classified a true nit and
  deferred with the catalogue-mount integration assertions to the
  closeout nit bead. Round 4 also independently re-mutation-verified two
  of round 3's pins (both genuinely red-then-green). Outer review
  recorded in the merge ping.

## Lessons

- A URL path segment that is itself an ENCODED value (the archive marker)
  gets validated to the ENCODER's exact output contract -- and the test for
  "validation refused it" must assert 400 specifically, because a dropped
  guard degrades to the store's 404 and an in-(400,404) assertion calls
  that green.
- A raw ".." path segment is untestable through an HTTP client -- the
  client normalizes /archive/../schema into a DIFFERENT route before the
  server ever sees it (safe: that route carries its own gates); the
  %2e%2e row is the one that actually reaches the validator.

## Doc freshness

- Bumped: docs/technical_guide.md (four route rows + stamp),
  docs/components/auth.md (route enumeration five->seven),
  docs/components/config-deployment.md (VFF_DISABLE_AUTH bullet
  enumeration) -- the latter two in the same edit set as the route-set pin,
  per that test's own instruction.
- Reviewed and left: the standards/* stales predate this branch.

## Files touched

- backend/routes/form_kit_routes.py, backend/routes/editor_kit_routes.py
- backend/tests/unit/test_http_route_auth.py,
  backend/tests/unit/test_kit_archive_routes.py (new)
- schema-editor/src/utils/remoteKitStore.ts,
  schema-editor/src/components/ArchivedVersions.tsx (new) + test,
  schema-editor/src/components/RemoteCatalogue.tsx,
  schema-editor/src/components/FormCatalogue.tsx
- frontend/src/schema-forms/components/ArchivedVersionsLink.tsx (new) +
  test, frontend/src/schema-forms/SchemaFormDemo.tsx
- docs/technical_guide.md, docs/components/auth.md,
  docs/components/config-deployment.md
- docs/journal/entries/2026-08-19-bd-qfyxr-kit-history-ui.md (this entry)
