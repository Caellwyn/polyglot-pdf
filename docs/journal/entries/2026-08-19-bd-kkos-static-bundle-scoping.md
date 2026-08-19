---
date: 2026-08-19
bead: polyglot-pdf-kkos
title: "Static bundle ships only complete AND public kits"
sprint: 19
tags: [security, testing]
---

## Trigger

The third link of the sprint-19 firm-tier chain, unblocked by vccy's merge
and carrying its P1 exposure bead (polyglot-pdf-17opi): vccy made every
BACKEND read firm-scoped, but the frontend build still copied every COMPLETE
kit into the world-readable Firebase Hosting bundle -- a private kit's schema
(field ids, labels, pdf mappings) and blank PDF were one direct request away
for anyone, bypassing the routes' 404s. vccy shipped with an explicit
"no firm may be granted a private kit before kkos" bar; this bead removes
the bar.

## What shipped

- kitPublishFilter.isPubliclyServable now requires status "complete" AND
  demonstrably-public visibility: the key ABSENT (existing kits, sprint-19
  "absence means public") or the exact string "public". ANY other value --
  "private", a case variant, a typo ("prvate"), JSON null -- withholds.
  This is a DELIBERATE divergence from the backend routes' coercion
  (anything except exact "private" serves public): the fail directions
  differ by surface. A route wrongly hiding a public kit is a visible,
  reversible service break; the bundle wrongly shipping a mistyped private
  kit is the silent, irreversible leak the firm tier exists to prevent.
  Documented in the filter, technical_guide entry 7, and pinned by test.
- generate-form-manifest.ts: KitMetadata declares `visibility` (the
  undeclared-field omission is exactly how the original draft leak
  happened, per that interface's own comment) and the withhold warning
  prints both status and visibility.
- The vccy-era PENDING-kkos statements (route comment, technical_guide
  entry 7) flipped to current-state; the operational no-private-kits bar is
  lifted. Set enumerated by grep -- no other pending statement remained.
- Tests: formKitBundle.visibility.test.ts drives the REAL build script
  against a temp tree (the status-test harness), whole visibility dimension
  parametrized, BOTH halves (index + shipped files) asserted per case,
  stale-bundle clearing proven for a previously-shipped private kit, plus
  the exit criterion's seeded draft+private pair. Mutation-verified twice:
  deleting the visibility gate reddened 5 tests; weakening it to the
  backend's anything-but-"private" coercion reddened the 4 strict-allowlist
  rows -- each red set exactly as predicted.
- Closeout assess: recorded in the merge ping after the loops ran.

## Lessons

- When two surfaces answer "is this public?" with different failure
  stakes, matching their predicates is WRONG: the routes coerce toward
  serving (hiding a public kit breaks service), the world-readable bundle
  coerces toward withholding (shipping a mistyped private kit is
  unrecoverable). Encode the divergence deliberately and pin BOTH
  directions (the weakened-to-backend-coercion mutation is the one that
  matters).

## Doc freshness

- Bumped: docs/technical_guide.md (entry 7's rewrite paragraph is now a
  shipped boundary; stamp). The route comment in form_kit_routes.py flipped
  in the same commit.
- Reviewed and left: standards/* stales predate this branch.

## Files touched

- frontend/scripts/kitPublishFilter.ts
- frontend/scripts/generate-form-manifest.ts
- frontend/src/formKitBundle.visibility.test.ts (new)
- backend/routes/form_kit_routes.py (comment only)
- docs/technical_guide.md
- docs/journal/entries/2026-08-19-bd-kkos-static-bundle-scoping.md (this entry)
