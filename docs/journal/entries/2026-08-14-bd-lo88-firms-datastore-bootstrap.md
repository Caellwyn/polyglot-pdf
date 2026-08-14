---
date: 2026-08-14
bead: polyglot-pdf-lo88
title: "Firms datastore + bootstrap (firms collection, FirmsService, claim stamping)"
sprint: 19
tags: [security, testing]
---

## Trigger

Head bead of the sprint-19 remaining chain (epic polyglot-pdf-02ye child 1;
vccy/kkos/qfyxr all sit behind it). A prior session had escalated "Firestore
firms collection vs. something lighter" to the maintainer -- planning showed
the question was already answered: Firestore is not a new dependency (the
confirmation sink + users/authorized_emails already run on it via get_db()),
and the maintainer-approved sprint-19 plan (2026-08-05) settles
"Datastore: Firestore". During plan review the maintainer added two
requirements (captured as the sprint plan's 2026-08-14 addendum): a
FOUR-LEVEL access model (app admin / firm management / firm employee / firm
client) and session telemetry keyed by firm id + form id + originating
employee. Also ruled: the former prod Firebase project polyglot-forms-919f2
is DEAD -- nothing may reference it (purge bead polyglot-pdf-je6iy filed).

## What shipped

- backend/services/firms.py -- firms/{firm_id} access in the
  confirmation-sink style (module functions, lazy get_db import, per-call env
  gate FIRMS_FIRESTORE_ENABLED). get_allowed_kits FAILS CLOSED ([] on
  disabled/missing/suspended/malformed/error) because vccy will gate PRIVATE
  kit visibility on it -- the deliberate inverse of the sink's fail-open
  writes. upsert_firm is ungated and raises (operator path; read-first so
  re-runs never clobber created_at). firms_store_status is a READ-shaped
  probe (limit-1 stream, not the sink's write+delete) for the IAM-drift
  failure mode where fail-closed reads silently blank every firm's kits.
  get_firm was deliberately DROPPED from the surface (plan-review finding: a
  raw suspended-firm dict would let a consumer bypass the status gate).
- firestore.rules -- explicit firms/** client deny block (defense in depth;
  Admin SDK bypasses rules) with the deploy-path caveat in the comment
  (rules ship only on frontend/full deploys or an explicit
  firebase deploy --only firestore:rules).
- scripts/bootstrap_firm.py -- creates/updates the firm record and stamps
  firm_id + firm_role (manager|employee via --manager-email/--employee-email)
  on staff accounts. Read-then-spread claim merge (set_custom_user_claims
  REPLACES the whole claims object); required --project with a
  resolved-project assertion (auth ops resolve the project from the
  CREDENTIAL, so the init option alone is not enough); dead-project
  hard-reject; --dry-run does read-only lookups so unknown emails surface
  before the real run; exit codes 0/1/2.
- Tests: 22 across test_firms_service.py / test_bootstrap_firm_cli.py /
  test_firestore_rules_text.py, every one mutation-verified (19 mutations in
  4 batches, each batch reddening exactly the predicted tests, restores
  confirmed green). Full backend suite 2218 passed post-change.
- Beads: purge bead polyglot-pdf-je6iy filed; 2026-08-14 requirement addenda
  appended to epic 02ye and beads xwlt (incl. the websocket_routes.py:1016
  decoded-claims-discard gap), z6bk9 (manager-gating), ugm6 (employee_id in
  the link token; email delivery is a future provisioning ask).
- Deliberately deferred to vccy: deploy-env wiring of FIRMS_FIRESTORE_ENABLED
  (the deploy-all.sh env block also feeds the dead project's deploy path;
  full six-site enumeration recorded in the plan + config-deployment.md).
- Plan review: one maintainer-requested adversarial Opus fresh-eyes pass on
  the PLAN found 12 gaps (wrong-project stamping risk, incomplete env-var
  site set, non-inert deploy flag, fake-shape mismatches, vacuous-test risk,
  get_firm leak, WS claims discard, rules deploy path, slug bound, dead
  project in auth.md, doc-home notes) -- all incorporated before
  implementation.
- Closeout assess: recorded below after the loops ran (see the merge ping for
  the same breakdown).

## Lessons

- firebase_admin's auth user operations resolve the target project from the
  CREDENTIAL first -- initialize_app(options={"projectId": ...}) alone does
  not make an operator script deterministic. Assert
  firebase_admin.get_app().project_id equals the requested --project and
  abort otherwise: a custom claim stamped into the wrong project fails
  silently and is unrecoverable by inspection.
- set_custom_user_claims REPLACES the entire claims object. Any stamper must
  read user.custom_claims and spread them into the new payload, and the test
  that pins this (an unrelated existing claim survives) is the
  highest-value test in the bead.
- A fail-closed READ path inverts the observability problem of a fail-open
  WRITE path: the sink needed a probe because it looks healthy while writing
  nothing; a fail-closed reader under IAM drift makes features silently
  vanish with no error anywhere. Ship the read-shaped health probe WITH the
  reader, not after the first mystery outage.
- SERVER_TIMESTAMP + merge=True silently overwrites created_at on every
  re-run; idempotent upserts must read-first and OMIT created_at from the
  merge payload -- and the pinning test needs a POSITIVE first-write
  assertion (the sentinel itself), not just key-absence on the re-run.

## Doc freshness

- Bumped: docs/components/auth.md (new Firm identity section = the documented
  admin step; dead-project line fixed; Tracks + tests updated),
  docs/components/config-deployment.md (FIRMS_FIRESTORE_ENABLED bullet),
  docs/technical_guide.md (env row + single-live-project correction),
  scripts/README.md (first operator-script entry),
  docs/sprint_19_firm-tier-kit-lifecycle_plan.md (2026-08-14 addendum +
  firm_role/employee_id updates to the identity bullets).
- Reviewed and left (stale from OTHER beads' files, none tracked by this
  branch's changes): context-compression.md, jit-schema.md, pdf-view.md,
  schema-forms.md, tool-call-flow.md, websocket-routing.md,
  standards/ai-models.md.

## Files touched

- backend/services/firms.py (new)
- scripts/bootstrap_firm.py (new)
- firestore.rules
- backend/tests/unit/test_firms_service.py (new)
- backend/tests/unit/test_bootstrap_firm_cli.py (new)
- backend/tests/unit/test_firestore_rules_text.py (new)
- docs/components/auth.md
- docs/components/config-deployment.md
- docs/technical_guide.md
- docs/sprint_19_firm-tier-kit-lifecycle_plan.md
- scripts/README.md
- docs/journal/entries/2026-08-14-bd-lo88-firms-datastore-bootstrap.md (this entry)
