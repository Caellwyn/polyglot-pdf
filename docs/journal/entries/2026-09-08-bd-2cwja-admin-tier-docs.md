---
date: 2026-09-08
bead: polyglot-pdf-2cwja
title: "docs(admin): 1.8 document the admin tier -- surface contracts, config-deployment, auth, promotion-tiers"
sprint: 22
tags: [conventions, doctrine]
---

## Trigger

Epic 1 child 1.8 of the admin-console program (plan
`docs/sprint_22_admin-console_plan.md`, "Beads and order": "1.8 docs (the
admin tier as current state...)"). Beads 1.1-1.7 (`pnoik`, `7w17m`, `3l2vp`,
`li9x0`, `bg313`, `9hzod`, `b6943`) shipped `admin_backend/`, the `app_admin`
claim, the audit log, runtime config, `/version`, and the `admin-console/`
app -- all merged to `dev`. This bead is the doc-catch-up: make the admin
tier discoverable the same way every other surface is, as current-state
prose with no history sections.

## What shipped

An audit of the five surfaces the bead names found `docs/technical_guide.md`
(Surface contracts 12-17) and `docs/components/config-deployment.md` already
current -- each prior admin-console bead (`pnoik`, `li9x0`, `bg313`, `b6943`)
had bumped its own stamp and added its own contract entry as part of landing
the code, so nothing was owed there. The real gaps were:

- **`docs/components/admin-service.md` (NEW).** One doc tracking
  `admin_backend/` and `admin-console/` end to end: why a second service
  exists (CLAUDE.md scar #7), the shared-image `APP_MODULE` split, the
  complete route table (cross-checked against
  `test_admin_route_auth.py`'s live-route-set pin), `require_app_admin`,
  `bootstrap_admin_user.py`, the audit log (pointing to Surface contract 15
  for the full shape), the `admin-backend-sa` role table (cross-checked
  against `setup-admin-service.sh` and its pin test), CORS, the
  tagged-revision deploy flow (`deploy-admin.sh`), the console's
  pages/API-client/build-SHA, and the candidate-then-live console deploy
  flow (`deploy-admin-console.sh`).
- **`docs/components/auth.md`.** Had three credential systems (firm staff,
  schema editor, firm client) documented but not the fourth (`app_admin`,
  shipped across `7w17m`/`li9x0`/`b6943`). Added it as a fourth table row
  plus its own subsection, cross-linked to the new `admin-service.md`.
- **`docs/doctrine/promotion-tiers.md`.** Covered only the public app's
  worktree -> dev -> staging -> demo flow. Added a section explaining the
  admin tier's DIFFERENT staging shape (tagged Cloud Run revision +
  permanent candidate Hosting site, since one admin service backs both
  channels' data and there is no second service to rehearse against).
- **`docs/INDEX.md`.** Added the `admin-service.md` row to the Components
  table.

No code changed. Every code path cited in the new/updated prose was checked
to exist (file paths for `admin_backend/`, `admin-console/`, and the
relevant `scripts/`/`deploy-*.sh`, plus the specific constants/tests named:
`KNOWN_CHANNELS`, `test_admin_route_auth.py`'s pinned route set,
`test_admin_sa_iam_envelope.py`'s role-list source).

## Lessons

Landing a doc catch-up bead LAST in a bead chain does not mean the docs are
all stale -- three of the five named docs (`technical_guide.md`,
`config-deployment.md`, plus half of `auth.md`'s ground) had already been
kept current by each prior bead's own commit. Auditing actual doc state
before writing (grep the doc for the surface's own file/route/constant
names, check the `*Last updated:*` stamp against `**Tracks:**`) avoided
restating contracts that already existed and let the bead focus effort on
the genuine gaps: a wholly missing doc, and one existing doc that was one
credential system behind. No new generalizable rule beyond following the
existing "trigger read + fix the doc first, separately" discipline this
repo already has.

## Doc freshness

- `docs/components/admin-service.md`: created (`*Last updated: 2026-09-08*`).
- `docs/components/auth.md`: bumped (fourth credential system + `**Tracks:**`
  line extended to `admin_backend/services/admin_auth.py` and
  `scripts/bootstrap_admin_user.py`).
- `docs/doctrine/promotion-tiers.md`: bumped (admin-tier staging section;
  doctrine docs carry no `**Tracks:**` line by existing convention, so
  freshness here is by inspection/review, matching every other doctrine
  doc).
- `docs/INDEX.md`: bumped (new Components row; also carries no
  `**Tracks:**` line, same convention).
- `docs/technical_guide.md`, `docs/components/config-deployment.md`:
  reviewed, found already current (Surface contracts 12-17 and the "Admin
  service" section already reflect the shipped code from prior beads) --
  left untouched.
- `python scripts/check_doc_freshness.py` reports every touched doc `OK`
  (or "no Tracks line, skipped" for the two doctrine-tier docs, matching
  every other file in `docs/doctrine/`) and exits 0.

## Files touched

- `docs/components/admin-service.md` (new)
- `docs/components/auth.md`
- `docs/doctrine/promotion-tiers.md`
- `docs/INDEX.md`
- `docs/journal/entries/2026-09-08-bd-2cwja-admin-tier-docs.md` (this entry)

Review outcomes recorded in the closeout ping.
