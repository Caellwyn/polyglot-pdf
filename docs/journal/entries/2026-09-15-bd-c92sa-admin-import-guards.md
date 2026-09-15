---
date: 2026-09-15
bead: polyglot-pdf-c92sa
title: "Batch of self-contained bug-hunt fixes across 13 sonnet/haiku beads"
tags: [testing, security, refactor]
---

## Trigger

A maintainer-directed "bug hunt": self-select simple beads marked `tier: sonnet`
or `tier: haiku` from the bead store (835 ready issues at the time; 336 matched
sonnet/haiku and a non-cross-surface work_class) and independently close as many
as possible, re-flagging anything that turned out more complex than advertised
rather than forcing it through. This entry covers the first completed PR, which
bundles 13 beads -- individually too small to each warrant a separate PR cycle,
per the bead/PR contract in CLAUDE.md.

## What shipped

Thirteen beads closed. Three were found INVALID/stale on investigation (the bead's
premise no longer matched the current code); the other ten were real, independently
verified fixes:

- **polyglot-pdf-5kicr** (CLOSED INVALID): the bead claimed `import os` in
  `runtime_config.py` was dead. It is not -- 3 live `os.getenv()` calls exist in
  `_legacy_env_default()`. The bead's own "AST walk found nothing" claim was
  incorrect; verified by direct grep.
- **polyglot-pdf-uidpu** (fixed) + **polyglot-pdf-n5zum** (closed as duplicate):
  both beads independently found the same dead `_positive_int()` in
  `backend/services/link_budget.py` (zero call sites since bd bg313 moved
  `firm_link_cap()` to delegate to `runtime_config`). Removed once, closed both.
- **polyglot-pdf-zs9yb** (CLOSED STALE): both findings (an unused `Optional`
  import, an unused `doc` parameter on `_apply_firm_patch`) were already resolved
  by later work on `admin_backend/routes/firm_routes.py` -- verified by grep and
  by reading the current function signature.
- **polyglot-pdf-30y0t** (fixed): `tests/test_deploy_form_kit_hints.py`'s
  `_gcloud_env_flag_invocation_lines`-scoped comprehension could never match,
  because `deploy-form-kit.sh` prints the `gcloud run services update <svc>`
  line and its `--update-env-vars` flag as two SEPARATE lines. The test only
  passed via its own fallback whole-text regex. Simplified to use the working
  whole-text regex directly. Mutation-verified.
- **polyglot-pdf-u05km** (fixed): removed a dead `import re` from
  `write_kits_manifest.py`; fixed `promotion_gate.py`'s refusal message, which
  suggested an illegal `_TARGET=admin-service-staging` remedy (admin-service has
  no separate staging target -- cloudbuild.yaml's `admin-service-record-
  deployment` step records its own staging row from the SAME build). Added
  `tests/test_promotion_gate_remedy_target.py`, mutation-verified.
- **polyglot-pdf-ay530** (fixed): `consoleStyles.test.ts`'s file-discovery
  claimed to guard "every page component" but actually matched every top-level
  `.tsx`, wrongly requiring `FirmAlertsBanner.tsx` (a real presentational
  sub-component that landed after this bead was filed) to import the
  stylesheet itself. Split into `consoleComponentFiles()` (all `.tsx`, used by
  the class-definition check, correct for any component) and
  `consolePageFiles()` (`*Page.tsx` only, used by the stylesheet-import check).
  Verified with the bead's own suggested scratch-file scenario.
- **polyglot-pdf-un0es** (fixed): `setup-telemetry.sh`'s usage string and
  runtime error both hid the optional `BILLING_EXPORT_TABLE` second argument;
  a comment above it wrongly said "REQUIRED" while the code treated it as
  optional-with-skip; the no-billing-arg path's final printed line read as
  unqualified success even though zero views were created. Fixed all three;
  added 3 pinning tests, each mutation-verified independently.
- **polyglot-pdf-o8xmk** (fixed): `admin-console/.env.hosted`'s
  `VITE_ADMIN_API_BASE_URL` fallback was a fabricated Cloud Run URL with no
  project hash segment, so it could never resolve even as a fallback. Resolved
  the real URL via `gcloud run services describe polyglot-admin` (same hash,
  `won24rgefq`, as the sibling `polyglot-backend` service) and replaced it.
  Added a pinning test asserting the URL shape.
- **polyglot-pdf-s8bhx** (fixed): `ErrorsPage.tsx`'s `loadChannel` cleared
  `groups` in its catch block but not `service`, so a failed channel-tab switch
  left the PREVIOUS channel's service name on screen while a different channel
  was visually selected and an error banner showed. Added `setService('')`
  alongside the existing `setGroups([])`. Scoped strictly to this bead's own
  exit criteria (ErrorsPage.tsx) -- the bead named a sibling bug in
  `CostReportsPage.tsx` (bd polyglot-pdf-fk142, same "derived label outlives
  its data" shape) and instructed grepping for the same shape across other
  admin-console pages per CLAUDE.md scar #8; that grep found the pattern
  appears in `catch` blocks across most pages, which is real but substantial
  cross-file work better scoped as its own bead than folded into this fix.
- **polyglot-pdf-c92sa** (fixed): `ops_routes.py`'s `_fetch_backend_probe` and
  `error_stats.py`'s `_fetch_group_stats` both did a bare `import requests` as
  their first statement, OUTSIDE their try/except -- a missing module would
  propagate an uncaught `ImportError` (500) instead of the documented failure
  shape (`reachable: false` / 503) every sibling lazy-SDK-import in the admin
  service already guards (`bigquery_reports.py`'s pattern). Guarded both.
  2 new tests simulate a missing module via a scoped `builtins.__import__`
  patch; mutation-verified.
- **polyglot-pdf-wiju0** (fixed): `CompositeActor`'s `employee_id` had no
  invariant tying it to `kind` -- an actor with `kind=firm_employee` and
  `employee_id=None` was constructible, and the route's
  `if employee_id is not None` scoping filter FAILED OPEN on it, listing the
  WHOLE FIRM's links instead of none. Not reachable through any production
  constructor today, but structural: a future constructor (a test helper
  promoted to production, a deserialization path) could reintroduce it
  silently. Added a pydantic `model_validator(mode="after")` pinning the
  pairing in BOTH directions (employee kind requires an id; non-employee kinds
  must not carry one) -- the bead's own preferred fix, "guard the property, not
  the code shape" (CLAUDE.md scar #8). 5 new tests, mutation-verified.
- **polyglot-pdf-xdbqm** (fixed): `GET /admin/audit` collapsed EVERY Firestore
  exception into a flat 503 "audit store unavailable," including
  `FAILED_PRECONDITION` (most often a missing composite index, whose message
  carries a console URL that creates it in one click) and `INVALID_ARGUMENT`
  (a malformed cursor). Both call for the opposite operator action from a
  genuine outage (click a link / fix input vs. wait). Added a narrower except
  clause mapping those two to 400 with an `AUDIT_QUERY_ERROR:`-prefixed detail,
  ahead of the existing generic 503 fallback. 2 new tests (the distinguishable
  case, and a guard-the-guard confirming an ordinary Firestore failure still
  503s), mutation-verified.

**Skipped, not fixed (re-flagged for future work, not forced through):**

- **polyglot-pdf-o3l5z** (`record_mint` name collision between
  `link_metering.py` and `links_store.py`): the collision described in the bead
  has not actually happened yet -- only `link_metering.record_mint` is imported
  today. The bead's own exit criteria explicitly accept resolving it "before
  [the future A3 mint-route-rewrite bead] lands," but renaming now would touch
  5 files including 3 test files, which exceeds a simple/self-contained fix and
  risks colliding with in-flight A3 work. Left open for that bead or a
  dedicated follow-up.
- **polyglot-pdf-js6qj** (`UsageEventMetadata` TypedDict drifted ~12 keys
  behind its 3 real emitters): the bead's own exit criteria require reading
  three separate call sites (`live_ai_gemini.py`, `text_ai_gemini.py`,
  `spellback_tts.py`), enumerating every emitted key, and writing a test that
  derives the emitted set from a real call on each path -- legitimate
  cross-surface enumeration work per CLAUDE.md scar #8, not a sonnet-tier
  local fix. Left open.

All ten fixed beads are self-contained to 1-2 files each with their own test
coverage; none touch a shared cross-cutting contract, so they were bundled into
one PR rather than run through 10 separate review cycles.

## Lessons

- **A bead's own factual claims can be stale by the time you pick it up** (5kicr,
  zs9yb). Both were filed correctly at the time but the code had since changed
  underneath them (a different fix landed, or the bead's own AST-walk claim was
  simply wrong). Always re-verify a bead's premise against the CURRENT code
  before starting the fix, not just before closing it -- the fix time is the
  cheapest place to catch a stale bead, not after writing code for it.
- **Duplicate beads happen** (uidpu/n5zum): two beads, filed 4 days apart, found
  the exact same dead-code instance independently. Worth a quick title/grep scan
  across open beads for the same file before starting, though in this case the
  duplication was only caught by having claimed both and noticing the
  descriptions matched.
- **"Simple" beads can hide a scope decision that belongs to a human, or a
  cross-file sweep that doesn't fit a sonnet-tier fix** (o3l5z, js6qj, and the
  partial scope-narrowing on s8bhx). The bug-hunt mandate was explicit about
  re-flagging rather than forcing these through -- worth restating as a general
  pattern: a bead's own exit criteria sometimes reveal, on read, that the
  "simple" fix is actually gated on a future bead landing, or requires
  enumerating a set the bead author flagged but didn't complete themselves.
- **`bd_safe.py claim`/`close` calls in this repo can take 2-3+ minutes each**
  (dolt remote round trips), and firing them concurrently in the background
  risks colliding on the dolt store (`bd.exe`/`python.exe` processes stacking
  up). Sequenced one bd write at a time, waiting for each to complete before
  the next, after an early batch of concurrent claims left one bead's claim
  silently dropped mid-chain.

## Doc freshness

`docs/components/admin-service.md` was genuinely stale from this branch (tracks
`ops_routes.py`, `error_stats.py`, `admin_auth.py`, `audit_routes.py`,
`admin-console/`, all touched here) -- updated the `/admin/audit` route's table
row to document the new 400/503 split, and the `/admin/health` + `/admin/errors`
prose to note the `requests` import guard now matches `bigquery_reports.py`'s
existing pattern. Bumped its stamp.

Reviewed and left as-is (stale by file-mtime tracking, but nothing they assert
is contradicted by this branch's changes -- their staleness is from unrelated
concurrent work on the same tracked files):
`docs/components/auth.md`, `docs/components/config-deployment.md`,
`docs/standards/logging-and-cost.md`, and the remaining ~20 STALE docs the
freshness checker listed (context-compression.md, jit-schema.md,
pdf-filling.md, pdf-view.md, schema-forms.md, tool-call-flow.md, voice-ai.md,
websocket-routing.md, ai-models.md, bead-tiers.md, risk-rating.md,
schema-key-visibility.md, section-reset-deprecation.md, si-reduction.md,
stateless-architecture.md, terminology.md, testing.md,
validation-delegation.md, voice-and-vad.md, ws-protocol.md,
technical_guide.md) -- none track a file this PR's diff actually changed in a
way that contradicts their prose; their staleness predates this branch and
traces to other in-flight work.

**Pre-existing issue noted, not fixed:** `docs/components/admin-service.md`
already carries multiple stacked `*Last updated:*` lines forming a
`Previously:`-style chronological chain, which is itself a violation of
CLAUDE.md's current-state-only doc rule (`docs/doc-architecture.md` section 3).
This predates this PR; fixing the whole file's structure is out of scope for a
bug-hunt batch and is a candidate for its own docs-only bead.

## Files touched

- `backend/services/link_budget.py` -- removed dead `_positive_int()`
- `frontend/src/console/consoleStyles.test.ts` -- split component-file
  discovery from page-file discovery
- `scripts/setup-telemetry.sh` -- usage strings, REQUIRED->OPTIONAL comment,
  no-views-created final message
- `tests/test_setup_telemetry_script.py` -- 3 new pinning tests
- `admin-console/.env.hosted` -- fixed the fabricated fallback URL
- `tests/test_admin_console_env_hosted_fallback_url.py` -- new
- `admin-console/src/pages/ErrorsPage.tsx` -- clear `service` in the catch
  block
- `admin-console/src/pages/ErrorsPage.test.tsx` -- 1 new pinning test
- `admin_backend/routes/ops_routes.py` -- guarded lazy `import requests`
- `admin_backend/services/error_stats.py` -- guarded lazy `import requests`
- `admin_backend/tests/unit/test_ops_routes.py` -- 2 new pinning tests
- `admin_backend/services/admin_auth.py` -- `CompositeActor` model_validator
- `admin_backend/tests/unit/test_composite_gate.py` -- 5 new pinning tests
- `admin_backend/routes/audit_routes.py` -- FAILED_PRECONDITION/
  INVALID_ARGUMENT -> 400
- `admin_backend/tests/unit/test_audit_log.py` -- 2 new pinning tests
- `scripts/write_kits_manifest.py` -- removed dead `import re`
- `scripts/promotion_gate.py` -- fixed illegal `_TARGET` remedy suggestion
- `tests/test_promotion_gate_remedy_target.py` -- new
- `tests/test_deploy_form_kit_hints.py` -- fixed dead comprehension
- `docs/components/admin-service.md` -- documented the 400/503 split and the
  import-guard hardening; bumped stamp
