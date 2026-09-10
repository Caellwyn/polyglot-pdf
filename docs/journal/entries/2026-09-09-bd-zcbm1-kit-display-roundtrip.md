---
date: 2026-09-09
bead: polyglot-pdf-zcbm1
title: "resolve_commercial never returns display -- console PUT silently wipes seeded kit labels"
sprint: 22
tags: [testing, review]
---

## Trigger

While building bd polyglot-pdf-mzblw (the admin console's Kit Commercials
page, Epic 2 Track C bead C1), self-review turned up a real data-loss risk
outside that bead's own assigned files:
`backend/services/kit_commercials.py`'s `resolve_commercial` deliberately
never returned a kit's stored `display` value (its own docstring said so:
"not read here") -- it only resolved `credit_cost`/`cap_usd`/`source` for
the mint path. Both `admin_backend` GET routes (`GET /admin/kits`,
`GET /admin/kits/{kit_id}/commercial`) reuse that same reader and spread
its return dict verbatim, so neither GET route the console can call could
ever surface `display` either. Concretely: `KitCommercialsPage.tsx`'s
Save PUTs the whole commercial doc (by design -- a partial update that
silently kept a stale ceiling is the exact failure mode the per-kit
ceiling rule exists to prevent), so it had nothing to read a kit's
existing label from and always sent `display: {}`, silently erasing any
label `scripts/seed_kit_commercials.py` had seeded. mzblw's author filed
this bead rather than fixing it in-place (out of that bead's own Surfaces)
or shipping the data loss silently.

## What shipped

- `backend/services/kit_commercials.py`: `resolve_commercial` now returns
  `display` alongside `credit_cost`/`cap_usd`/`source`. A new `_display`
  helper mirrors the module's existing defensive-parsing posture -- a
  non-dict stored value, or a dict with a non-string key/value, degrades
  to `{}` rather than being handed to a caller raw. Unlike
  `credit_cost`/`cap_usd`, `display` has no GLOBAL default to fall back
  to (there is no runtime-config notion of a default label) -- `{}` simply
  IS its default, not a fallback FROM something. `display` is never used
  by the mint path itself; it only rides along for a GET-side console
  reader.
- `admin_backend/routes/kit_routes.py`: no route code changed -- both GET
  routes already spread `resolve_commercial`'s return dict, so `display`
  reaches the console for free. Docstrings updated to say so.
- `admin-console/src/utils/adminApi.ts`: `KitCommercial` gains
  `display: Record<string, string>`.
- `admin-console/src/pages/KitCommercialsPage.tsx`: the page still has no
  UI to EDIT the label, only to stop clobbering it. The fresh GET on Edit
  now captures the kit's current `display` map into state
  (`displayRef`), and Save echoes that same map back on the PUT,
  unchanged, instead of the hardcoded `{}` it sent before.

## Lessons

Read-side gaps that block a write-side feature are easy to under-scope:
the bug lived entirely in `kit_commercials.py` (a file mzblw never
touched), but its symptom only appeared in `KitCommercialsPage.tsx`'s
Save button. Filing a separate bead for the read-side fix, rather than
reaching into `kit_commercials.py` from inside the console bead or
shipping the silent data loss, kept both PRs correctly scoped to their own
Surfaces -- this generalizes as "a discovered gap outside your bead's
files is a new bead, not a scope-creep edit" (already CLAUDE.md doctrine;
this is a clean instance of it working as intended).

## Doc freshness

- `docs/components/admin-service.md`: the bd polyglot-pdf-mzblw paragraph
  (which described the KNOWN DATA-LOSS GAP this bead closes) rewritten in
  place to describe current state -- display is preserved, not a known
  gap. No new dated block added (current-state-only convention): the
  paragraph's existing 2026-09-09 date stamp already covers today.
- `docs/technical_guide.md`: Surface contract 24's `resolve_commercial`
  return-shape description and its Console consumer paragraph both
  updated to include `display`; the `GET /admin/kits/{kit_id}/commercial`
  Surface-contracts table row updated too. No stamp on this file by
  design.
- `docs/components/auth.md` tracks `backend/services/kit_commercials.py`
  but was reviewed and left AS-IS: its only mention of that module
  describes the mint-path fail-soft resolution of `credit_cost`/
  `burn_cap_usd`, which this bead does not touch (`display` is additive
  and never read by the mint path) -- the doc remains accurate.
  `check_doc_freshness.py` flags both `admin-service.md` and `auth.md` as
  STALE purely because their file mtimes are a few minutes older than the
  code files this same PR touched (both docs already carry today's date);
  this is a same-day mtime-ordering artifact of the checker, not a real
  content gap in either doc.

## Files touched

- `backend/services/kit_commercials.py` -- `resolve_commercial` returns
  `display`; new `_display` helper.
- `backend/tests/unit/test_kit_commercials.py` (new) -- 10 tests on the
  reader, mutation-verified.
- `admin_backend/routes/kit_routes.py` -- docstring updates only.
- `admin_backend/tests/unit/test_kit_routes.py` -- `display` assertions
  on existing GET tests, a new single-kit GET display test, a new list
  GET display test, and a new end-to-end GET-then-PUT-then-GET
  acceptance test.
- `admin-console/src/utils/adminApi.ts` -- `KitCommercial.display`.
- `admin-console/src/pages/KitCommercialsPage.tsx` -- capture-and-echo
  `displayRef` state.
- `admin-console/src/pages/KitCommercialsPage.test.tsx` -- two new tests
  (preserve a seeded label; don't leak one across kits), plus an
  explicit `display` assertion added to the existing round-trip test.
- `docs/components/admin-service.md`, `docs/technical_guide.md` -- current
  state updated (see Doc freshness above).
