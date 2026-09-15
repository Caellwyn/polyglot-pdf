---
date: 2026-09-15
bead: polyglot-pdf-6088m
title: "fix(backend): C4 -- the unauthenticated surface fails closed: dev route, byte-accurate upload caps, a parse timeout, a bounded disclaimer timestamp"
tags: [security-audit, backend, pdf-filling, testing]
---

## Trigger

Sprint 23 (the security + data-leak audit, epic `polyglot-pdf-uijam`, plan
`docs/sprint_23_security-audit_plan.md`), workstream C4, threat actor T1
(the anonymous caller). PF-10: the dev-only console-ingest route was gated
on a marker FILE whose real production control was a `.dockerignore`
line nobody pinned; `MAX_UPLOAD_MB` was declared, reported by `/health`
and enforced nowhere; `/api/resume-form` base64-decoded the whole body
before its size check and ran `fitz.open` on attacker bytes with no
timeout; the disclaimer-acceptance timestamp was unbounded (bd `q34sy`).
PF-5, rate limiting, is a cost decision and is escalated, not built.
Built by a Sonnet builder in an isolated worktree over two rounds; the
orchestrator ran the review loops, three doc fixes and closeout.

## What shipped

- `/dev/console-log` returns 404 whenever `K_SERVICE` is set, in addition
  to the marker check; `tests/test_dockerignore_env_exclusion.py` pins the
  `.dockerignore` lines that keep `backend/.env*` out of the image.
- **Byte-accurate upload caps.** The first build gated on Content-Length,
  and fresh-eyes showed the obvious bypass: omit the header and FastAPI
  parses the whole body. The builder then found that FastAPI reads the
  body BEFORE it resolves any dependency, so no `Depends` can ever stand
  in front of the parse. The cap is therefore a custom `APIRoute` subclass
  on the pdf-fill router: its handler wrapper consumes `request.stream()`
  counting bytes, raises 413 the instant the running total exceeds the
  route's cap, and caches the accepted bytes where Starlette's own
  `body()` looks for them so the normal parse replays them. `/api/fill-pdf`
  is capped at `MAX_UPLOAD_MB` (read at call time, so a settings override
  actually applies -- the first tests had passed by coincidence);
  `/api/resume-form` at its own 25 MB decoded limit plus base64 inflation,
  with the base64 string length checked before any decode. The tests drive
  the ASGI app through `httpx.ASGITransport` because `TestClient` buffers
  a streaming body before the app ever runs.
- `/api/resume-form`'s structural parse runs in a dedicated small thread
  pool under `RESUME_FORM_PARSE_TIMEOUT_S` (default 8 s, env-overridable)
  and answers 408 on timeout; a hung parse cannot starve the shared pool.
- The disclaimer `timestamp` must fall in [2025-11-01 UTC, now + 5 min] or
  the route answers 422 before any log line or durable write (closes
  `q34sy`).
- `backend/tests/unit/test_upload_caps.py` also carries an AST-derived
  enumeration of every POST/PUT route in `backend/routes/` that accepts an
  upload, a base64 field or an unbounded dict body, with a disposition per
  route: two guarded here, two already capped by the extractor's reader,
  and four editor schema-body routes UNGUARDED -- outside this bead's
  surfaces, filed as `polyglot-pdf-07vpc`.
- The rate-limit options memo (Cloud Armor + load balancer; an in-process
  token bucket; instance caps) is on the bead with the builder's
  recommendation; the choice is the maintainer's.

## Review record

**Fresh-eyes (sonnet): two rounds.** Round 1 GAPS-FOUND (2): the cap
trusted the Content-Length header (omit it and the whole body parsed), and
the fill-pdf cap tests passed by coincidence because a `Depends(get_settings)`
default had bound the original function at import, so the fixture's
override never reached it -- both fixed in round 2 (the route-class cap;
settings read at call time with override tests in both directions); nits:
the resume 413 label named the wrong number, one em-dash. Round 2
GAPS-FOUND (1): the pdf-filling doc still described the header check as the
enforcement -- rewritten; a test now pins the Starlette body-cache replay
the mechanism depends on.

**Opus cross-surface review:** one round, GAPS-FOUND (1): this diff had
falsified a technical-guide sentence claiming the two WebSocket dev routes
share the console route's gate (they still gate on the marker only; C2
adds their `K_SERVICE` backstop) -- reworded. Traced clean: the router is
mounted once with only CORS in front, so the route-level stream read is
first; no other code caches a request body; all four disclaimer producers
send millisecond timestamps; the resume cap has two orders of magnitude of
headroom over real saved PDFs. Filed: `polyglot-pdf-ij9ue` (the 5 MB
fill-pdf cap is only ~2x above a large TRANSLATED schema, since the client
sends the whole schema the backend never reads -- measure the real ceiling
before a client hits it), `polyglot-pdf-lhrln` (the client shows a wrong
message for the new 408 and a generic one for 413); a third duplicated
C2's scope and was closed.

**Housekeeping reviewed and left:** other sessions' in-progress beads; the
stale-doc flags for files this branch did not touch (many docs track
`backend/config.py`). Prep suite: 6007 passed before round 2, 6014 after.

## Lessons

- **A cap that trusts a header is a suggestion.** Content-Length is
  attacker-controlled and optional; the only cap that holds is one that
  counts the bytes it reads.
- **Know where the framework reads the body.** FastAPI parses before it
  resolves dependencies, so the guard had to move up a layer. Ten minutes
  reading `fastapi/routing.py` replaced a whole class of wrong fixes.
- **A test that passes for the wrong reason is worse than no test.** The
  settings-override tests were green because the override happened to
  equal the default; the fix was to prove the override changes the
  outcome in both directions.
- **`TestClient` cannot exercise streaming.** It buffers the whole body
  before the app runs; the byte-accurate layer needed a transport that
  hands the app one chunk at a time.

## Doc freshness

Bumped: `docs/components/pdf-filling.md` (caps + timeout),
`docs/components/config-deployment.md` (the dockerignore pin),
`docs/standards/hipaa-pii-policy.md` (the dev-console row: fails closed on
`K_SERVICE`), `docs/technical_guide.md` (the WS dev routes' gate sentence).

## Files touched

- backend/routes/dev_console_routes.py -- K_SERVICE fail-closed
- backend/routes/pdf_fill_routes.py -- the body-cap route class, base64 pre-check, parse timeout
- backend/routes/disclaimer_routes.py -- timestamp bound
- backend/config.py -- RESUME_FORM_PARSE_TIMEOUT_S
- backend/tests/unit/test_upload_caps.py, test_dev_console_routes.py, test_disclaimer_acceptance_route.py; tests/test_dockerignore_env_exclusion.py
- docs/components/pdf-filling.md, docs/components/config-deployment.md, docs/standards/hipaa-pii-policy.md, docs/technical_guide.md
- docs/journal/entries/2026-09-15-bd-6088m-unauth-surface-hardening.md -- this entry
