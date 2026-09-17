---
date: 2026-09-17
bead: polyglot-pdf-o2fub
tags: [security-audit, backend, deploy, rate-limit]
surfaces: [backend/utils/rate_limit.py, backend/routes/link_routes.py, backend/routes/signup_routes.py, backend/routes/disclaimer_routes.py, cloudbuild.yaml]
---

# PF-5: the per-instance limiter on the three unauthenticated write doors, and the instance ceiling

Sprint 23's one P1 that was a decision rather than code: no rate limiting
on the unauthenticated doors (`docs/sprint_23_security-audit_plan.md`
PF-5; the options memo on the C4 bead `6088m`). The maintainer decided on
2026-09-17: the in-app limiter plus a Cloud Run instance ceiling, with
Cloud Armor and a load balancer deferred until abuse is observed. This is
that decision built.

## What shipped

- **`backend/utils/rate_limit.py`**: a token bucket per caller address per
  door, held in the process. The address is the first `X-Forwarded-For`
  hop (Cloud Run's front end sets it; `request.client.host` there is the
  proxy), else the socket peer locally. Budget and window are settings read
  at call time (`RATE_LIMIT_ENABLED`, `RATE_LIMIT_BUDGET` 30,
  `RATE_LIMIT_WINDOW_SEC` 60), refilling continuously. The map is pruned
  once it passes 1024 keys.
- **The three doors**, wired as a dependency: `POST /api/links/open` and
  `POST /api/signup/check` refuse over budget with the door's OWN 404
  phrase -- byte-identical to a wrong token or a miss, so a limited caller
  learns nothing a probing caller would not -- and the handler never runs
  for the refused call; `POST /api/disclaimer-acceptance`, which has no
  oracle to protect, answers a plain 429. The refusal log line
  (`rate_limited`) carries the door, the budget and the window, never the
  address (the address is the bucket key only).
- **The suite runs with the limiter off** (`backend/tests/conftest.py` sets
  `RATE_LIMIT_ENABLED=false`): TestClient is one address hitting the same
  doors hundreds of times per run. `backend/tests/unit/test_rate_limit.py`
  turns it on per test with a budget of three.
- **The ceiling**: `--max-instances=10` on the backend deploys and `=3` on
  the admin service in `cloudbuild.yaml`; `tests/test_cloudbuild_yaml.py`
  requires the flag on every `gcloud run deploy` step. Defended numbers:
  the backend has never needed more than a handful of instances; ten is
  headroom for a launch-day burst at a bill still bounded in the tens of
  dollars an hour; the admin service serves a few staff. Both are one
  flag to raise.
- **Docs**: `config-deployment.md` gains a "Rate limiting on the
  unauthenticated doors" section (the two controls, the settings, the
  refusal shapes, the accepted weakness); `security-posture.md`'s three
  door rows, the accepted-risk bullet and the PF-5 decision row (now
  shipped); `technical_guide.md`'s three route rows.

## The set

`test_every_deliberately_ungated_write_door_is_rate_limited` derives the
door list from the access matrix's `_DELIBERATELY_UNGATED_HTTP_ROUTES`
(every POST there except the dev-only console sink, which is closed on
Cloud Run) and walks each route's dependant graph for the limiter's mark,
so a fourth unauthenticated write door fails CI here until it is limited,
and a door limited but not classified fails too.

## Verification

- Targeted: the limiter's tests, the cloudbuild pins, the access matrix,
  the route-auth pin, the disclaimer and signup route tests, the PII
  guard -- green (211 + the limiter's 11).
- Scar #9, one interpreter each, all RED: the limiter dependency removed
  from the signup door (the set test names it; its own case fails); the
  links/open refusal changed to a 429 (the byte-identical pin); the
  address added to the refusal log kwargs (the kwarg pin); `_take` made to
  never refuse (every limit case).
- Full suite: SUITE_RESULT

REVIEW_RECORD

## Lessons

- **A limiter on an oracle-sensitive door must refuse in the door's own
  voice.** A 429 on `/api/links/open` would have told a probing caller
  "you are being counted", which is one bit more than a wrong token gives.
  The dependency takes the refusal per door for that reason.
- **The suite is one client.** A limiter keyed on the caller address turns
  every integration test file into one very busy caller; the suite-wide
  off switch with per-test opt-in is the only shape that does not
  couple test order to a bucket.

## Files

`backend/utils/rate_limit.py` (new), `backend/config.py`,
`backend/routes/link_routes.py`, `backend/routes/signup_routes.py`,
`backend/routes/disclaimer_routes.py`, `backend/tests/conftest.py`,
`backend/tests/unit/test_rate_limit.py` (new), `cloudbuild.yaml`,
`tests/test_cloudbuild_yaml.py`, `docs/components/config-deployment.md`,
`docs/standards/security-posture.md`, `docs/technical_guide.md`.
