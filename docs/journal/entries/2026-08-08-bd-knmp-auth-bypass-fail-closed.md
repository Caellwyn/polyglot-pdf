---
date: 2026-08-08
bead: polyglot-pdf-knmp
title: "VFF_DISABLE_AUTH fails closed on a deployed service"
tags: [security, conventions, testing]
---

## Trigger

`backend/services/auth.py` honored `VFF_DISABLE_AUTH=true` unconditionally,
returning a stub `{'uid': 'dev_user'}` for every caller. Since bd
polyglot-pdf-z2is that single bypass gates `/ws/fill` AND every `require_auth`
route -- including `POST /api/fill-pdf`, which renders the client's entered
PII into a PDF. The service deploys `--allow-unauthenticated`, so a stray
`--set-env-vars VFF_DISABLE_AUTH=true` would have made the entire backend
world-open with no startup failure and only a per-request warning log.

bd polyglot-pdf-5e6a had just hardened exactly this shape for `VERTEXAI`
(refuse to start when `K_SERVICE` is set), establishing the fail-closed-on-
deploy pattern. The auth bypass -- a strictly larger blast radius -- had no
equivalent. Filed out-of-scope by that bead's reviewer.

## What shipped

Two layers, mirroring the sibling guard's shape. `K_SERVICE` is set by Cloud
Run and by nothing else, so it is the deployment signal both use.

1. **Startup** (`backend/config.py`, in the existing `_resolve_model`
   validator next to the VERTEXAI guard): a deployed service with the flag set
   raises, so it cannot boot. No override flag, for the same reason the AI
   Studio guard has none -- no legitimate deployed use of a blanket auth
   bypass exists.
2. **Runtime** (`backend/services/auth.py`): `verify_token` ignores the bypass
   when `K_SERVICE` is set and falls through to real verification, so the
   request fails CLOSED.

Layer 2 is deliberately not redundant: it holds where `Settings` is never
constructed, and it fails the individual request rather than trusting that
startup validation ran. Both layers are pinned SEPARATELY (the
redundant-guards-need-per-layer-tests lesson) -- deleting either one reddens
only its own cases, which a single combined test would have hidden.

WHY THE GUARD READS THE ENV rather than a `Settings` field: `auth.py` reads
`os.getenv` directly, so introducing a field would create a second source of
truth that could drift from the code actually enforcing. The guard reads the
same variable, the same way (`.lower()`), and a parametrized case pins that
case-handling agreement -- a case-sensitive guard would let
`VFF_DISABLE_AUTH=TRUE` boot while `verify_token` still honored it.

ENUMERATED THE SET first (scar tissue #7): `VFF_DISABLE_AUTH` appears in 40+
places, but exactly ONE is a functional read (`auth.py:31`). Everything else
is docs, dev scripts (`dev-local.ps1`/`.sh`, which default it to true), tests,
and the voice-harness runbook. Every auth path funnels through `verify_token`
(grep of `verify_token`/`require_auth` callers), so one runtime guard covers
the WS gate and all FIVE `require_auth` HTTP routes (fill-pdf, the two
form-kit reads, and the TTS spellback route -- the outer review caught that
two tier-2 docs enumerate only four; filed as bd polyglot-pdf-qs7m6).

Mutation-verified per layer: deleting the startup guard reddens 6 cases;
deleting the runtime guard reddens 3; neither mutation touches the other's.

## Lessons

- A "never set this in prod" comment is a convention, not a control. When the
  same shape has already been hardened once (VERTEXAI), the second instance is
  not a new decision -- it is an unfinished sweep. Worth asking, when a
  fail-closed guard lands, which OTHER flags have the same blast radius.
- Pin a guard's INPUT PARSING, not just its outcome. The bypass reader and the
  guard both lowercase; a guard that did not would pass every outcome test
  while leaving `TRUE` live.

Fresh-eyes (sonnet): NO-GAPS round 1, both criteria PASS; it reproduced both
per-layer mutation counts independently. Two doc nits adopted -- the Testing
section of auth.md now names this test file (a reader asking "where is the
K_SERVICE guard tested" would not have found it), and the test count here is
stated as 9 tests / 12 parametrized invocations rather than "12 cases". It
could not finish the full both-roots suite in its session; that run completed
here at 2940 passed, 3 skipped.

Opus cross-surface round 1: NO-GAPS. It empirically confirmed the startup
refusal fires at IMPORT of backend.main (module-scope get_settings at
main.py:71), so "refuses to start" is accurate rather than a lazy
per-request raise -- the one claim that would have been wrong if Settings
were first constructed inside a request. It filed two PRE-EXISTING findings
as beads rather than blockers: polyglot-pdf-qs7m6 (two tier-2 docs enumerate
four require_auth routes; there are five -- the TTS spellback route is
missing) and polyglot-pdf-5xhbb (backend/tests/conftest.py has no autouse
K_SERVICE isolation, a latent exposure this diff widens to a second
deployment-sensitive env var).

## Doc freshness

`docs/components/auth.md` and `docs/components/config-deployment.md` both
described the bypass as "local dev only -- never set in prod", which was
convention and is now enforcement; both updated to state the two guards and
the absence of an override, with their `Last updated` stamps refreshed (both
carried multi-clause chains, replaced with the per-entry pointer shape).

## Files touched

- backend/config.py -- the startup guard beside the VERTEXAI one
- backend/services/auth.py -- the runtime guard in verify_token
- backend/tests/unit/test_auth_bypass_guard.py (new; 9 tests, 12
  parametrized invocations)
- docs/components/auth.md, docs/components/config-deployment.md
- docs/journal/entries/2026-08-08-bd-knmp-auth-bypass-fail-closed.md
