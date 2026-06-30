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
  `store.load_pdf_bytes`, `media_type="application/pdf"`, also `no-store`.

Security: a reusable `_safe_kit_id` guard (`^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$`
via `fullmatch` -- `match`'s `$` would let a trailing newline through -- plus an
explicit `".." in kit_id` reject) sanitizes the path segment BEFORE the store is
touched, so a hostile id (e.g. `../../secret`, `i-90\n`) cannot escape the store
prefix/root. Error mapping: `FormKitNotFound` -> 404, bad id -> 400,
`FormKitStoreError` -> 502. The existing `GET /api/form-kits` manifest route's
output contract is unchanged.

Filename resolution + allowlist (`_resolve_kit_filenames`): the routes resolve a
kit's real `schemaFile`/`pdfFile` from the manifest (honoring a custom filename a
kit declares via `metadata.json` -- bd snpi), falling back to `schema.json` /
`form.pdf`. The manifest is the ALLOWLIST: when it loads but does NOT list the
requested kit, the routes 404 rather than serving a guessed object -- the GCS
deploy gate keeps draft/unmarked kits out of the manifest, so a fallback would
leak them. When NO manifest exists at all (GCS without an `index.json`) the routes
fall back to convention, preserving the read-gap fix. To make local custom-filename
kits resolvable, `LocalFormKitStore.load_manifest` now reads each kit's
`metadata.json` for `schema`/`pdf`/`label`/`description` (it previously hardcoded
`schema.json`). `LocalFormKitStore.load_schema`/`load_pdf_bytes` now wrap a
present-but-unreadable asset (malformed JSON / OSError) as `FormKitStoreError`, so
local mode maps it to 502 like GCS already did (no uncaught 500).

Scope note: wiring the BROWSER to call these `/api/...` routes is NOT in this bead
-- the public manifest still advertises `/form-kits/<id>/...` paths, and the hosted
editor's remote source (which calls `/api/form-kits/{id}/schema`) is Bead 3 of the
epic. Codex flagged the unwired state P1 across both rounds; it is correctly
deferred, tracked under epic polyglot-pdf-92qe, not folded into this read-route
slice.

Tests (`backend/tests/unit/test_form_kit_routes.py`, +17): schema/PDF body +
content type against both a `_FakeStore` and a real `LocalFormKitStore` over a tmp
dir; 404 on a missing kit; a parametrized 400 sweep of unsafe ids
(`../secret`, `..`, `a/b`, `a..b`, `-leading`, `with space`, empty) AND
trailing-newline ids (`i-90\n`, `\r`), each asserting the store is never reached;
custom-filename resolution (manifest + local `metadata.json`); no-manifest
fallback; manifest-loaded-but-kit-absent -> 404; and local malformed-JSON -> 502.

Round-3 hardening (Codex P1, after the round-2 metadata/allowlist work surfaced
adjacent edges): a corrupt/unreadable manifest (`FormKitStoreError`) now FAILS
CLOSED with 502 instead of falling back to convention (only a truly missing
manifest falls back) -- a malformed manifest must not bypass the allowlist;
manifest-supplied `schemaFile`/`pdfFile` are run through `_safe_filename`
(separator/`..` reject -> degrade to the conventional name) so a traversal value
in kit-controlled metadata can't escape the kit dir; non-dict local `metadata.json`
(valid JSON that is a list/str/number) is treated as absent rather than crashing
the manifest with `AttributeError`; a non-UTF-8 schema now maps to 502
(`UnicodeDecodeError` is wrapped in both stores and tolerated in local manifest
generation); and the route-table doc no longer calls the manifest "complete-only"
unconditionally (local mode is ungated).

Round-4 STRUCTURAL fix (Codex P1 x5, after the maintainer ran a 4th review): all
five findings were the SAME bug class -- an untrusted manifest/metadata value
(non-string, traversal, or a non-dict container) reaching a path-join or `.get()`
at a layer that hadn't been guarded. Rounds 3 and 4 recurred because the earlier
fixes were POINTWISE (patch each value Codex named) instead of central. The fix:
a single `safe_filename(value, default)` in `form_kits.py` that coerces ANY
unsafe value (non-str, separator, `..`, bad charset) to the conventional name,
applied at BOTH the local manifest generator AND the route resolver; type-safe
iteration of `forms` (skip non-dict entries; a non-list `forms` -> 502) in BOTH
the resolver and the public `list_form_kits`; and `GCSFormKitStore.load_manifest`
now wraps `UnicodeDecodeError` like the schema loader. After applying it I AUDITED
every untrusted-value-to-path / `.get()` site (grep of `kit_dir /`, `.get(`) and
hardened the one the findings hadn't named yet (`list_form_kits`'s non-dict entry)
to avoid a round 5.

Round-5 ROOT-CAUSE fix (Codex P1 x4 + a maintainer decision to do the real
structural fix): rounds 3-4 had patched the untrusted-value bug class POINTWISE in
the consumers, and round 5 surfaced four more variants the consumers still missed
(a non-object top-level manifest, a non-string `label`, a non-dict custom
`schema_data`, plus a security gap: a MISSING GCS `index.json` fell back to
convention and reopened unlisted/draft blobs). The fix moves validation to the
TRUST BOUNDARY: a single `normalize_manifest(raw)` in `form_kits.py` validates the
shape ONCE (non-object or non-list `forms` -> `FormKitStoreError` -> 502) and
coerces every entry (skip non-dicts, drop id-less rows, `_safe_str` the label,
`safe_filename` the filenames). BOTH stores' `load_manifest` now return through it,
so every consumer (`list_form_kits`, the single-kit resolver) receives a
guaranteed-clean shape and its scattered per-field guards were DELETED (the route
now plain-subscripts `manifest["forms"]` / `form["id"]`). The fail-closed security
gap is fixed with a store capability flag `allow_convention_fallback` (False for
GCS, True for local): the resolver only falls back to convention on a MISSING
manifest when the store allows it, so GCS fails closed on a missing index.json.
After applying it I re-AUDITED every `.get()`/path-join/`json.loads` site in both
files (documented in the closeout) and confirmed each is now behind the boundary
or an explicit `isinstance` -- the audit that round 4's "structural" claim skipped.

Pre-PR assess: exit-criteria rubric all PASS; fresh-eyes loop NO-GAPS (1 gap found
+ fixed: added the LocalFormKitStore-backed test). Codex outer review: 5 rounds
(3 + 5 + 5 + 5 + 4 P1). Adopted every code finding -- custom-filename resolution; the
local/GCS 502 mappings (malformed JSON, OSError, UnicodeDecodeError for both
schema AND manifest); the manifest-allowlist 404 + fail-closed-on-corrupt; the
central `safe_filename` value sanitization (non-string + traversal) at both
layers; the non-dict-metadata and non-dict-forms-entry guards; the trailing-
newline `fullmatch` fix; and the doc corrections. Deferred only the recurring
"wire the browser to these /api routes" finding to Bead 3 (it would change the
voice app's manifest contract, out of scope for this read slice). Lesson recorded
below: a recurring same-class finding is the signal to stop patching pointwise
and fix the trust boundary once, then audit the class. No out-of-scope beads filed.

## Lessons

Path-segment user input that flows into a storage key or filesystem path needs a
sanitization guard that fires *before* the store call, not validation inside it --
the guard is reused by every `{kit_id}` route so the rule lives in one place. Use
`re.fullmatch`, never `re.match`, for an allowlist anchor: `match` lets `$` match
just before a trailing newline, so `i-90\n` slips through a "single-segment" check.

A read route that hangs off a gated manifest must treat that manifest as an
ALLOWLIST, not just a filename hint: falling back to a conventional path on a
manifest miss re-exposes exactly the draft/unlisted objects the gate exists to
hide. "Resolve the filename" and "is this kit allowed to be served" are the same
lookup -- a miss is a 404, not a default. A corrupt (unreadable) manifest must
fail CLOSED (502), only a truly-missing one may fall back.

When a reviewer keeps returning the SAME finding class round after round (here:
"untrusted kit-controlled value reaches a path/`.get()` unguarded"), stop patching
the specific value/site it names and fix the trust boundary ONCE. But be precise
about WHERE the boundary is: round 4 "centralized" a `safe_filename` helper yet
still called it from each CONSUMER, so round 5 found the consumers it hadn't been
added to. The real boundary is the PARSE point -- normalize the untrusted JSON into
a guaranteed-clean, fully-typed shape inside `load_manifest` (the one function that
turns bytes into the structure), and every downstream consumer can then plain-
subscript it with NO guards. "Validate where it's consumed" scales with the number
of consumers (and misses new ones); "normalize where it's parsed" is O(1) and
makes a missed consumer impossible. A capability flag on the producer
(`allow_convention_fallback`) is the same idea for behavior that must differ by
backend (GCS fails closed on a missing manifest; local falls back) -- encode it on
the store, not as a mode-check in the consumer.

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

- `backend/routes/form_kit_routes.py` -- `_safe_kit_id` guard (fullmatch),
  `_resolve_kit_filenames` (manifest allowlist + sanitized custom names +
  type-safe forms iteration + fail-closed-on-corrupt), the two read routes, and a
  non-dict-entry skip in `list_form_kits`.
- `backend/services/form_kits.py` -- the shared `safe_filename` sanitizer (the
  trust-boundary guard); `LocalFormKitStore.load_manifest` reads + sanitizes
  `metadata.json` filenames/label and tolerates non-dict metadata;
  `load_schema`/`load_pdf_bytes` and both `load_manifest`s wrap read/decode
  failures (`JSONDecodeError`/`OSError`/`UnicodeDecodeError`) as
  `FormKitStoreError` (502 parity, local + GCS).
- `backend/tests/unit/test_form_kit_routes.py` -- ~30 tests for the read routes,
  guard, filename resolution + sanitization, allowlist 404, fail-closed 502, and
  the untrusted-value (non-string / traversal / non-dict) guards.
- `docs/technical_guide.md` -- API route table + the GCS-vs-local manifest note.
- `docs/technical_guide.md` -- API route table + Last-updated bump.
