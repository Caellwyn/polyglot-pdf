---
date: 2026-08-03
bead: polyglot-pdf-z2is
title: "P0 prod-readiness: durable confirmation trail + auth on fill-pdf + drop client_ip + pin VERTEXAI"
tags: [security, testing]
---

## Trigger

The deployment/productization planning session (2026-08-03) verified four
production defects, all wiring rather than design, and judged them blocking
before any paying customer:

1. The liability confirmation trail wrote JSONL to Cloud Run's ephemeral
   tmpfs -- `CONFIRMATION_LOG_DIR` was set nowhere outside tests, write
   failures were swallowed, and `read_confirmation_log()` would have returned
   `[]` in the one scenario (a legal dispute) the trail exists for.
2. `POST /api/fill-pdf` -- the endpoint that renders user-entered field values
   into a PDF -- was unauthenticated on a service deployed
   `--allow-unauthenticated`, as were the form-kit catalogue reads.
3. The disclaimer-acceptance route logged the caller's IP (PII under
   GDPR/CCPA), making the "no personal data stored" posture literally false.
4. `VERTEXAI=false` (the AI Studio path, whose consumer terms permit human
   review/training use of request data) was one stray env flip away from
   carrying production client audio.

## What shipped

**Durable confirmation sink.** `confirmation_logger.py` mirrors every event to
a `confirmation_events` Firestore collection when
`CONFIRMATION_FIRESTORE_ENABLED=true` (now set in `deploy-all.sh`'s
`BACKEND_ENV`). Design points: fire-and-forget single-worker
`ThreadPoolExecutor` so the voice hot path (`callback_handler`'s confirm
round-trip) never blocks on a network write; failures log
`confirmation_firestore_write_failed` at error level (loud, never raised --
the parallel structlog line already reached Cloud Logging, so a failed mirror
degrades durability, not evidence); lazy `get_db` import keeps
`firebase_admin` out of the unit-test import chain and patchable;
`read_confirmation_log` prefers Firestore (equality query, client-side sort --
no composite index) with the local JSONL as dev fallback; optional
`CONFIRMATION_RETENTION_DAYS` stamps `expire_at` for a TTL policy whose
activation is deliberately deferred to counsel's retention answer (bd
polyglot-pdf-pol2); `flush_confirmation_sink()` wired as a FastAPI shutdown
handler. Firestore rules need no change: no matching rule = client deny, and
the backend writes via the Admin SDK.

**HTTP auth gates.** New `require_auth` dependency in `backend/services/auth.py`
(the HTTP counterpart of the `/ws/fill` token check; honors `VFF_DISABLE_AUTH`)
gates `POST /api/fill-pdf`, `GET /api/form-kits`, and
`GET /api/form-kits/{kit_id}/schema`. `GET /api/form-kits/{kit_id}/pdf` stays
DELIBERATELY public: the blank template is a public government form, the same
bytes ship in the static Hosting bundle, and the pdfjs viewer loads that URL
headerless -- gating it would break the viewer while protecting nothing not
already public (revisit when kits become firm-scoped). Frontend threads
`user.getIdToken()` via `fillPDF`'s new optional `getToken` param
(SchemaForm download/print, FilledPreviewModal) and attaches the header on
SchemaFormDemo's manifest/schema fetches, where a 401 now SURFACES as an error
instead of silently falling back to the stale static bundle.

**client_ip dropped** from the disclaimer-acceptance log; `user_agent` kept as
a deliberate low-sensitivity retention pending counsel. The exact log kwarg
set is pinned by an allowlist test (never a blacklist).

**AI Studio fail-closed guard.** `Settings` refuses to start with
`VERTEXAI=false` on Cloud Run (`K_SERVICE` present) unless `ALLOW_AI_STUDIO=true`
is also set -- reaching consumer terms in a deployed env is now a deliberate
two-flag decision. Local dev / the voice harness / probes (no `K_SERVICE`) are
unaffected; the demo (`VERTEXAI=true`) is unchanged; the documented 3.1 flip
now names both flags (`deploy-demo.sh` comment + `ai-models.md`).

**Latent bug fixed en passant:** `log_form_session_start`/`log_form_session_end`
raised a `TypeError` on every call (`**event` collided with structlog's
positional event name) -- never seen because they had no live caller until the
sink tests. Both now filter the key, mirroring `log_field_confirmation`;
wiring them for completion/abandonment telemetry is now safe.

**Deferred:** wiring `log_form_session_start`/`end` into the session lifecycle
was deliberately NOT done here -- a form-session spans reconnects, so naive
per-WS-disconnect wiring would log spurious "abandoned" events; that design
belongs to the existing logging-roadmap beads (g0e chain). Deployed-instance
verification (a confirmation record retrievable after scale-to-zero; a live
401 on the demo) is pending the next gated demo deploy per the deploy
authorization rules.

**Fresh-eyes triage (round 1, sonnet): GAPS-FOUND (2 rubric + 2 supporting).**
All four adopted and fixed inline:
1. ADOPTED (rubric): `read_confirmation_log` had no operational caller -- the
   durable trail was writable but not practically retrievable. Fixed:
   `scripts/read_confirmations.py` (support/legal retrieval tool; JSONL or
   summary output) + the confirmation-and-audit doc names it as the entry
   point.
2. ADOPTED (concurrency): a TOCTOU race -- `flush_confirmation_sink()` could
   shut the executor between `_get_executor()` and `submit()`, silently
   dropping an event during exactly the Cloud Run SIGTERM window. Fixed:
   submit-after-shutdown `RuntimeError` now falls back to a SYNCHRONOUS write
   (blocking briefly mid-shutdown is fine; the event is never dropped).
   Regression-pinned by `test_shutdown_race_falls_back_to_synchronous_write`.
3. ADOPTED (rubric): zero frontend regression coverage on the token-threading
   half of the auth change. Fixed: `pdfFiller.auth.test.ts` (Authorization
   header attached with getToken, absent without) +
   `SchemaFormDemo.auth.test.tsx` (ID token on the manifest fetch; a 401
   SURFACES and does NOT fall back to the static bundle; a plain network
   failure still does).
4. ADOPTED (doc): the retrieval function's unwired state was undocumented
   while the lifecycle pair's was -- folded into fix 1's doc line.
**Fresh-eyes round 2 (Opus, via the effort-400 Workflow fallback):
GAPS-FOUND (5).** The round's payoff was a live-infrastructure catch no code
read could have made:
1. ADOPTED (rubric FAIL -> fixed): the Cloud Run runtime SA
   (polyglot-backend-sa) holds NO Firestore role -- verified against the live
   demo project -- so every sink write would 403 and be swallowed: the exact
   silently-empty-liability-trail failure this bead exists to eliminate.
   Fixed: `roles/datastore.user` added to `scripts/setup-gcp-project.sh`'s
   ROLES array (re-runnable against an existing project); the live binding +
   end-to-end write check ride the next gated demo deploy (deploy-all.sh's
   printed next-steps now include the read_confirmations.py verification).
2. ADOPTED: a FAILED Firestore read was indistinguishable from "no events" --
   for a legal-retrieval tool, opposite answers. Fixed: `ConfirmationReadError`
   + `read_confirmation_log(strict=True)`; the script now prints RETRIEVAL
   FAILED (exit 2) vs not-found (exit 1). Pinned by test.
3. ADOPTED (filed by the reviewer as bd polyglot-pdf-wv3j, fixed inline here,
   bead closed by this PR): flush's swap-then-drain could leave a freshly
   created sibling executor undrained. Fixed: flush loops swap+drain until no
   executor remains. Deterministically pinned by hijacking the first
   executor's shutdown to spawn a mid-drain sibling.
4. NOTED (deploy-time verification, no code fix possible pre-deploy): this is
   the first Authorization header ever sent through the Hosting /api/**
   rewrite in this codebase; the authed curl is now a printed post-deploy
   step and is called out for the next demo test-drive.
5. ADOPTED (the deploy-all.sh half): the printed post-deploy verification
   told the operator to expect an open /api/form-kits, which now correctly
   401s -- rewritten to expect the 401 and verify the authed path. The
   deploy-form-kit.sh half (env-clobbering --set-env-vars hint) is
   pre-existing and stays with the reviewer-filed bd polyglot-pdf-pnye.
Round 3 (Opus) on the updated diff: outcome recorded below.

## Lessons

- **A "durable" artifact is only durable if a deploy sets its sink.** The
  confirmation logger was correct code writing to a filesystem that dies on
  scale-to-zero, with the enabling env var set only in tests. When a control
  exists for liability, verify the DEPLOYED wiring, not the module.
- **Scaffolded-but-unwired functions rot invisibly.** The session-lifecycle
  pair carried a crash-on-first-call TypeError for months because nothing
  called them. A defined-but-uncalled function is a liability, not a head
  start, until a test gives it a caller.
- **Gate deliberately, and pin the NON-gate too.** The kit-PDF GET staying
  public is a decision with a rationale; the test asserting it returns 404
  (not 401) tokenless makes a future blanket-auth sweep fail loudly instead of
  silently breaking the pdfjs viewer.

## Doc freshness

Bumped with substance: `docs/components/auth.md` (require_auth + gated routes +
test pointer), `docs/standards/confirmation-and-audit.md` (two-sink model +
lifecycle-pair fix), `docs/standards/hipaa-pii-policy.md` (disclaimer row;
Firestore mirror note on the confirmation row),
`docs/components/pdf-filling.md` (fill-pdf auth + getToken),
`docs/standards/ai-models.md` (ALLOW_AI_STUDIO guard),
`docs/components/config-deployment.md` (three new env vars + auth-gate note).
`docs/technical_guide.md` tracks files this branch changed, so it WAS bumped
(routes table auth annotations, VERTEXAI guard note, CONFIRMATION_FIRESTORE
row). Other checker-flagged stale docs (`voice-instance-lifecycle`,
`ws-protocol`) track files this branch did NOT touch (audioManager,
VoiceOverlay, schemaFormState) -- reviewed and left per the
"already stale before you" rule.

## Files touched

- backend/services/auth.py -- require_auth dependency
- backend/routes/pdf_fill_routes.py -- auth gate on fill-pdf
- backend/routes/form_kit_routes.py -- auth gates on list/schema; documented public pdf GET
- backend/routes/disclaimer_routes.py -- client_ip dropped
- backend/config.py -- ALLOW_AI_STUDIO + Cloud Run fail-closed guard
- backend/utils/confirmation_logger.py -- Firestore sink, read path, lifecycle-pair fix
- backend/main.py -- shutdown drain handler
- deploy-all.sh -- CONFIRMATION_FIRESTORE_ENABLED=true in BACKEND_ENV
- deploy-demo.sh -- 3.1-flip comment names ALLOW_AI_STUDIO
- frontend/src/schema-forms/utils/pdfFiller.ts -- optional getToken, auth header
- frontend/src/schema-forms/components/SchemaForm.tsx -- token threading (download/print)
- frontend/src/pdf-view/FilledPreviewModal.tsx -- useAuth + token threading
- frontend/src/schema-forms/SchemaFormDemo.tsx -- authed fetches, 401 surfaces
- backend/tests/unit/test_http_route_auth.py -- new (auth gates + deliberate non-gate)
- backend/tests/unit/test_confirmation_firestore_sink.py -- new (allowlist/failure/retention/read)
- backend/tests/unit/test_vertexai_guard.py -- new (guard matrix)
- backend/tests/unit/test_disclaimer_acceptance_route.py -- new (log-kwarg allowlist)
- docs: auth.md, confirmation-and-audit.md, hipaa-pii-policy.md, pdf-filling.md, ai-models.md, config-deployment.md
