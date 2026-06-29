---
date: 2026-06-29
bead: polyglot-pdf-sbfk
title: "feat(backend): single-kit READ routes -- serve a kit's schema JSON + PDF bytes from the store"
tags: [security, testing, conventions]
---

## Trigger

First slice of the hosted-schema-editor epic (`polyglot-pdf-92qe`): package the
standalone `schema-editor/` as a hosted web app a contractor uses, backed by the
existing GCS form-kits bucket for collaboration (maintainer pushes draft kits,
contractor pulls/edits/saves them back). The design surfaced a known gap: in GCS
mode nothing serves a single kit's `schema.json`/`form.pdf` *bytes* to the
browser. The manifest (`GET /api/form-kits`) returns storage PATHS like
`/form-kits/<id>/schema.json`, but no host route backs those paths -- under
Firebase Hosting the `/api/**` rewrite only covers the manifest endpoint and the
catch-all swallows everything else to `index.html`. This bead fills that gap with
backend routes that stream a kit's schema + PDF directly from the `FormKitStore`.
Chosen first because it is independently useful, has no auth surface, and is the
lowest-risk slice (read-only, additive).

## What shipped

Two additive routes in `backend/routes/form_kit_routes.py`, both working in local
AND gcs mode (they go through the existing `get_form_kit_store()` abstraction, so
no store changes were needed for this bead):

- `GET /api/form-kits/{kit_id}/schema` -> the kit's schema JSON via
  `store.load_schema`, returned as `JSONResponse` with `Cache-Control: no-store`
  (so a re-pull after a later save is never stale).
- `GET /api/form-kits/{kit_id}/pdf` -> the kit's PDF bytes via
  `store.load_pdf_bytes("form.pdf")`, `media_type="application/pdf"`, also
  `no-store`.

Security: a reusable `_safe_kit_id` guard (`^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$`
plus an explicit `".." in kit_id` reject) sanitizes the path segment BEFORE the
store is touched, so a hostile id (e.g. `../../secret`) cannot escape the store
prefix/root when interpolated into a blob path or filesystem path. Error mapping:
`FormKitNotFound` -> 404, bad id -> 400, `FormKitStoreError` -> 502. The existing
`GET /api/form-kits` manifest route is untouched.

Schema/PDF filenames default to the conventional `schema.json`/`form.pdf`;
custom-filename resolution (a kit can declare a custom schema filename via
`metadata.json`) is deferred to Bead 2, which adds the store's metadata reader --
noted inline in the route docstring.

Tests (`backend/tests/unit/test_form_kit_routes.py`, +12): schema body + content
type, PDF bytes + content type, 404 on a missing kit, a parametrized 400 sweep of
unsafe kit ids (`../secret`, `..`, `a/b`, `a..b`, `-leading`, `with space`, empty)
that also asserts the store is never reached, and a direct guard sanity check.
Verified end to end with a `TestClient` against a `LocalFormKitStore` over a tmp
kit dir: schema 200/`no-store`, pdf 200/`application/pdf`, missing 404, `bad..id`
400, and URL-encoded traversal (`..%2f..%2f`) 404 (Starlette splits on the decoded
slash so it never matches the single-segment route -- defense in depth on top of
the guard).

Pre-PR assess: exit-criteria rubric all PASS (see PR body); fresh-eyes loop
NO-GAPS. No out-of-scope beads filed.

## Lessons

Path-segment user input that flows into a storage key or filesystem path needs a
sanitization guard that fires *before* the store call, not validation inside it --
the guard is reused by every `{kit_id}` route so the rule lives in one place. The
URL-encoded-traversal test documents that Starlette's path matching is a second
layer (a decoded `/` won't match a single-segment route), but the code should not
rely on that alone.

## Doc freshness

- `docs/technical_guide.md`: bumped -- added the two new routes to the API route
  table and stamped `Last updated: 2026-06-29` (it was flagged stale by this
  branch's edit to `form_kit_routes.py`).
- The other docs the freshness check flagged (auth, voice-ai, tool-call-flow,
  context-compression, stateless-architecture, and ~13 more) are stale from OTHER
  contributors' same-day backend edits (`websocket_routes.py`,
  `live_ai_gemini.py`, `callback_handler.py`, `config.py`), NOT this branch --
  left for their own closeouts per the doc-freshness rule.

## Files touched

- `backend/routes/form_kit_routes.py` -- `_safe_kit_id` guard + the two read routes.
- `backend/tests/unit/test_form_kit_routes.py` -- +12 tests for the read routes + guard.
- `docs/technical_guide.md` -- API route table + Last-updated bump.
