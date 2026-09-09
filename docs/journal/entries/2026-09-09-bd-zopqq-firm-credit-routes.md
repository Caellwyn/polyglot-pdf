---
date: 2026-09-09
bead: polyglot-pdf-zopqq
title: "feat(admin): B1 firm CRUD + credit grant/adjust routes on the admin service"
sprint: 22
tags: [testing, security]
---

## Trigger

Epic 2 Track B bead B1 (plan: docs/sprint_22_admin-console_plan.md, "Epic 2
-- Firms, users, credits, form commercials, link tracking", Track B: "B1
firm CRUD + grants"). Epic 1's admin service (require_app_admin, the
in-transaction audit helper) and Epic 2 Track A's credit ledger
(backend/services/credit_ledger.py's append_entry, reconcile_expired_for_firm)
had both landed with no consumer on the admin service yet -- this bead is
the first business surface that lets an operator actually create/manage
firms and move credits without a script.

## What shipped

Two new route modules on the admin service, both behind `require_app_admin`
(not the composite gate -- a firm manager never creates or reclassifies
firms in this bead):

- `admin_backend/routes/firm_routes.py`: `POST`/`GET /admin/firms`,
  `GET /admin/firms/{firm_id}`, `PATCH .../status`, `PATCH .../allowed_kits`,
  `PATCH .../kind`. Each mutation opens its own Firestore transaction
  (mirrors `config_routes.py`'s shape exactly: read `before`, write, audit,
  all inside one `@firestore.transactional` body) and reuses
  `backend/services/firms.py`'s document shape rather than adding a second
  writer. `GET /admin/firms/{firm_id}` runs
  `credit_ledger.reconcile_expired_for_firm` once per known channel (demo,
  staging) BEFORE reading the balance -- a lazy catch-up for links the
  hourly sweep (Track B bead B5, not yet built) has not reached. A
  per-channel reconciliation failure is logged and skipped rather than
  failing the whole page.
- `admin_backend/routes/credit_routes.py`: `POST .../credits/grant`
  (subscription_grant | purchase | promo_grant, usd_amount required for the
  first two and refused otherwise) and `POST .../credits/adjust` (any sign,
  reason required). Both go through `credit_ledger.append_entry` -- the one
  writer of a firm's balance -- with `actor` the admin's uid and `channel`
  always None. The audit row joins `append_entry`'s OWN transaction via its
  documented `extra_writes(tx, firm)` hook rather than opening a second
  transaction, since `append_entry` already reads the firm doc and the plan
  is explicit that everything goes through the one helper.

Grants to mock firms are allowed by design (plan: "Grants to mock firms are
allowed" -- staging needs credits to test); neither route checks `firm.kind`
at all, since kind only ever gates minting, never granting or adjusting.

### Fresh-eyes round: adopt/reject/defer

The pre-PR fresh-eyes review raised four findings (STATUS: GAPS-FOUND (2)).
Rubric verdict was PASS on all three named exit criteria either way; the two
GAPS were blockers against the diff's own internal consistency, not the
rubric.

- **ADOPTED -- doc/docstring accuracy (blocker).** `docs/technical_guide.md`,
  `docs/components/admin-service.md`, and `firm_routes.py`'s own module and
  `create_firm` docstrings claimed `POST /admin/firms` creates via
  `backend/services/firms.py::upsert_firm`. It never did -- `create_firm` and
  `_apply_firm_patch` each do their own transactional read-patch-write,
  because `upsert_firm`'s get()-then-set() is not transactional and cannot be
  called from inside a transaction without a second, transaction-illegal
  read. Rewrote all three doc/docstring sites to state this accurately, and
  added `test_apply_firm_patch_merged_dict_matches_upsert_firm_payload_keys`
  (AST-derived, not hand-listed, per CLAUDE.md scar #8) pinning that the two
  independent writers' non-first-create field-key sets stay in sync --
  mutation-verified by dropping `status` from `_apply_firm_patch`'s payload
  and confirming the new test goes red.
- **ADOPTED -- missing asyncio.to_thread (blocker).** Every route in
  `firm_routes.py` was `async def` but called synchronous Firestore
  operations directly, inconsistent with `credit_routes.py`'s own explicit
  design rule in the same diff ("both handlers run it under
  asyncio.to_thread"). Restructured all six routes into a thin `async def`
  handler (keeps cheap DB-free validation, so a bad request still 422s
  without touching a thread) plus a private synchronous `_do_*` helper
  carrying the actual Firestore/credit_ledger work, run via
  `asyncio.to_thread` -- matching `credit_routes.py`'s `_run_append_entry`
  shape. `test_admin_audit_coverage.py`'s in-transaction guard walks the
  whole module for `@firestore.transactional`-decorated functions, so moving
  the transactional bodies into `_do_*` helpers needed no change there.
- **DEFERRED (nit) -- `_public_firm_view`'s balance fallback and
  `get_firm`'s unbounded ledger read.** Both are real but small-scale,
  low-confidence observations (a malformed non-int balance reports `0` with
  no distinguishing flag; `read_entries(limit=None)` reads a firm's whole
  ledger into memory on every profile view). Filed as
  `polyglot-pdf-0w13i` ("chore(nits): deferred review nits from
  polyglot-pdf-zopqq") rather than fixed inline, since the reviewer did not
  file one.

### The extra_writes gap in the audit coverage guard

`admin_backend/tests/unit/test_admin_audit_coverage.py` derives, per route,
whether its audit call sits inside a `@firestore.transactional` body -- but
its AST walk only looked at the route module's OWN source file for that
decorator. `credit_routes.py`'s routes never open their own transaction
(they join `append_entry`'s via `extra_writes`), so the existing check
could not tell "audited correctly, via the documented extension point" from
"never audited at all" -- it read both as the latter and failed the real,
correct routes. Extended `_calls_inside_transactional_bodies` to also treat
a function passed as `extra_writes=` to `append_entry` /
`refund_expired_link` as in-transaction (both helpers' docstrings and their
own tests guarantee the hook runs inside the commit), and the "the mutation
itself is in there" check to accept the module-level call to one of those
two names as evidence when the route's own module contains no `tx.set`.
Added synthetic correct-form / audit-outside-callback cases (both mutation-
verified to flip the right way) and a tie-back test against the real
`credit_routes.py` module, matching the file's existing prove-both-ways
pattern for the plain and external forms.

### Cross-surface review round: adopt/reject/defer

The outer cross-surface review (STATUS: GAPS-FOUND (2)) traced `firms/{firm_id}`
consumers outside this diff's own files and found `scripts/backfill_firm_kind.py`
as a second, untouched-file consumer of the document shape `_apply_firm_patch`
writes.

- **ADOPTED -- `_apply_firm_patch` invents `kind`/`status`/`allowed_kits` on a
  doc that never had them (blocker, findings 1+2, enumerated and fixed
  together per CLAUDE.md scar #8).** `_apply_firm_patch`'s old `merged` dict
  coerced a missing `kind` to `firms.FIRM_KIND_LIVE` (and missing
  `status`/`allowed_kits` to their own defaults) and wrote it back on EVERY
  patch, even a status-only or allowed_kits-only one. `scripts/
  backfill_firm_kind.py` gates both its `--mock` allowlist and its
  `--seed-credits` grant on `"kind" in firm` (`had_kind`) -- a stray write
  that materializes `kind` here during the still-open pre-backfill window (A6
  exit criterion 2 has no journal-recorded staging run yet) would silently
  and permanently misclassify an unclassified firm as a paying live one, and
  it would lose its seed-credit grant too. Reproduced the reviewer's repro
  (seed a doc with no `kind`, PATCH `.../status`, watch `kind: "live"`
  appear) before fixing. Fix: `merged` is still one dict literal (so
  `test_apply_firm_patch_merged_dict_matches_upsert_firm_payload_keys`'s
  AST-derived key-set pin still finds it) but each value now reads via
  `current.get(key, _ABSENT)` (a module-level sentinel distinct from any real
  stored value, including `None`) instead of a hard default, and a
  dict-comprehension right after the literal drops every `_ABSENT` entry
  before `patch` is applied -- so a field the stored doc never had stays
  absent from the re-write. Added five pinning tests covering all three
  patch routes against a kindless doc plus a guard test that a
  fully-classified doc's `kind`/`allowed_kits` still survive a status-only
  patch unchanged. Mutation-verified: reverting the sentinel-based merge back
  to the old hard-defaulted literal turned all four bug-catching tests red
  (`kind`/`allowed_kits` reappeared on the doc); the guard test stayed green
  under that mutation as expected, confirming it is not accidentally coupled
  to the same code path.
- **NOT RE-FILED -- finding 3 (unused `Optional` import, unused `doc` param
  on `_apply_firm_patch`).** Already filed by the reviewer as
  `polyglot-pdf-zs9yb`. The finding-1/2 fix above removes `_apply_firm_patch`'s
  `doc` parameter and all three call sites as a direct consequence of
  rebuilding `merged` from the in-transaction snapshot only (the function
  never read the passed-in `doc` to begin with) -- so that half of zs9yb's
  exit criterion is already satisfied by this round; also dropped the now-
  fully-unused `Optional` import in the same file for the same reason
  (finishing the other half). `polyglot-pdf-zs9yb` is left open rather than
  closed here since fixing it was not this round's assignment; whoever picks
  it up next will find both items already done and can close it against this
  commit.
- **CONFIRMED STILL OPEN -- pre-existing nit `polyglot-pdf-0w13i`.** Reviewer
  re-verified it is open and correctly scoped; no action needed here.

### A missing catch-all in credit_routes.py

While mutation-testing the "forced audit failure leaves the balance
unchanged" pin, a raw exception from a Firestore write (simulated via the
fake db's `audit_write_error`) propagated as an UNHANDLED exception through
FastAPI's default exception middleware instead of a clean 500 -- unlike
`config_routes.py` and `firm_routes.py`, which both wrap unexpected
exceptions from their transactional bodies into `HTTPException(500)`.
Added the same catch-all to `credit_routes.py::_run_append_entry`.

### Second cross-surface round: the balance_credits guard's dead corner

A follow-up cross-surface review traced `firms/{firm_id}.balance_credits`
and `.balance_updated_at` specifically (both fields this bead's
`_do_create_firm` writes on first create) and found the scar-#8 set-guard
itself had a blind spot the two earlier rounds never exercised (STATUS:
GAPS-FOUND (1)).

- **ADOPTED -- the balance_credits set-guard walks only `backend/`, so this
  bead's own write in `admin_backend/` escapes it (blocker).**
  `backend/tests/unit/test_credit_ledger.py`'s
  `test_credit_ledger_is_the_only_module_that_writes_balance_credits` roots
  its AST walk at `backend/` only; `admin_backend/` is a sibling package at
  the repo root and was never examined, so `firm_routes.py:351`'s
  `payload["balance_credits"] = 0` (behaviourally correct -- it mirrors
  `upsert_firm`'s zero-init for a brand-new firm with no ledger) got no
  mechanical objection at all despite being a real second writer inside the
  file this bead added. Widened the walk to cover both `backend/` and
  `admin_backend/`, added `firm_routes.py` to the allowlist, and also
  allowlisted `credit_routes.py` -- not because it writes the field, but
  because the guard's own dict-literal check cannot distinguish its
  `before={"balance_credits": firm.get(...)}` audit READ from a write, so
  the widened walk now flags that pre-existing false positive too. Corrected
  the three doc/docstring sentences that claimed `upsert_firm` is "the ONE"
  or "the one deliberate other" writer: `docs/technical_guide.md`,
  `docs/components/auth.md`, and `firm_routes.py`'s own module docstring
  (which had contradicted itself ~330 lines above its own `create_firm`).
  Mutation-verified two ways: (1) added a synthetic
  `payload["balance_credits"] = 1` to `admin_backend/routes/audit_routes.py`
  (a module NOT on the allowlist) and confirmed the widened guard goes red,
  then reverted; (2) temporarily removed `firm_routes.py` from the allowlist
  and confirmed the guard catches the REAL production write at
  `firm_routes.py:351` (not just a synthetic probe), then restored. Full
  backend suite (3530 passed), admin_backend suite (300 passed), and root
  tests (1432 passed) all green after the fix.
- **FILED, NOT FIXED -- `balance_updated_at` type split (pre-existing,
  `polyglot-pdf-d0jan`).** `credit_ledger.py`'s ledger-movement write stores
  a plain epoch float; `firms.py`'s (and now `firm_routes.py`'s)
  first-create write stores `firestore.SERVER_TIMESTAMP`. Reproduces
  unchanged on `origin/dev`; this bead mirrors the existing create-time
  convention rather than introducing or worsening the split, so left as the
  reviewer's own filed bead rather than fixed here.
- **NO NEW NITS BEAD** -- both non-blocker findings from this round were
  either the blocker above (fixed) or already filed
  (`polyglot-pdf-d0jan`); `polyglot-pdf-0w13i` from the prior round already
  covers the two nits deferred earlier and needed no update.

### Third cross-surface round: firm_id slug validation was set-incomplete

A third outer cross-surface review traced `POST /admin/firms` and the
path-segment `{firm_id}` routes against the repo's two OTHER firm-slug-
validating sites and found this module had joined that set without
actually enforcing the shared rule (STATUS: GAPS-FOUND (1)).

- **ADOPTED -- `_validated_firm_id` checked only non-blank, defeating the
  case-collision rule scripts/bootstrap_firm.py and
  admin_backend/routes/user_routes.py both enforce (blocker, finding 1).**
  Confirmed by the reviewer's 7/7 probe: "Acme", "ACME Corp", "acme/../x",
  "-lead", a 200-char id, and "acme\n" all 201'd through this route while
  both other sites already refuse them via `FIRM_ID_RE =
  ^[a-z0-9][a-z0-9_-]{0,127}$`. A firm created under a case-colliding or
  embedded-newline spelling is then unreachable from `POST /admin/users`
  (same regex, same 422), so no staff account could ever be attached to
  it. Fix: added the same `FIRM_ID_RE` constant (restated, not imported --
  matching the reasoning both other sites already give for restating
  rather than cross-importing) to `firm_routes.py`, and changed
  `_validated_firm_id` to `FIRM_ID_RE.fullmatch(...)` instead of the old
  blank-only check. Applied uniformly to EVERY call site -- create's
  `body.firm_id` and every path-segment route's `{firm_id}` alike -- since
  a firm that somehow already exists under a non-conforming id must not be
  reachable for status/allowed_kits/kind mutation or its detail page
  either. Added a set-derived test
  (`test_every_firm_id_validating_site_applies_the_same_slug_rule`) that
  AST-walks all three `FIRM_ID_RE` definitions and asserts they are
  identical, plus asserts `firm_routes.py` calls `.fullmatch` (not
  `.match`) -- so a future fourth site, or a drift in any of the three
  existing ones, fails CI instead of a future review round (CLAUDE.md
  scar #8: pin the SET, not the instance). Also added two behavioral
  parametrized tests covering the reviewer's own 7 cases against both the
  create route and the four path-segment routes. Mutation-verified:
  reverting `_validated_firm_id` to the blank-only check turned all three
  new tests red across every non-empty case (6/6 create-body cases, 5/5
  reachable path-segment cases, plus the set-derived parity test); restored
  after confirming.

  One case ("acme/../x") could not be driven through the path-segment
  routes as a literal single-segment value: an un-encoded "/" splits the
  URL into multiple path segments before FastAPI's router ever matches a
  route, and percent-encoding it as "%2F" is rejected by Starlette's own
  router with a bare 404 before ANY route -- including this one -- can
  match, so this route cannot be the thing that lets that specific
  spelling through via a path segment. The create-body test (where the id
  arrives as a JSON string field, not a URL path) still covers it, which
  is the actual reachable surface for that case.

## Lessons

A route that joins an EXISTING shared transaction via a documented
extension point (rather than opening its own) is a legitimate shape a
set-derived mechanical guard needs to recognize explicitly -- the guard's
original design (one route module, one `@firestore.transactional` body)
predates any real consumer of `append_entry`'s `extra_writes` hook. This is
noted in `test_admin_audit_coverage.py`'s own docstring for the next reader
who adds a third such consumer (the Track A mint route, when it lands, will
be the second).

A set-derived guard's walk ROOT is as load-bearing as its allowlist: a guard
that correctly enumerates every writer under one package still misses a
sibling package entirely if that is where its `rglob` starts. `admin_backend/`
existing as a sibling of `backend/` (not a subpackage of it) made this
invisible until a route actually landed there and wrote the guarded field --
worth checking any future set-derived guard in this repo (there are others
per CLAUDE.md scar #8) against both top-level Python packages, not just the
one the guard's own module happens to live in.

## Doc freshness

- `docs/technical_guide.md` (no stamp by design, bd polyglot-pdf-abn4o):
  added the eight new routes to the Admin service routes table, sorted by
  path then method per the doc's own rule.
- `docs/components/admin-service.md`: Tracks line gains
  `admin_backend/routes/firm_routes.py` and `credit_routes.py`; added a
  dated entry and rows in the Routes table. Confirmed `OK` (fresh) by
  `scripts/check_doc_freshness.py` after the edit.
- Every other doc `check_doc_freshness.py` flagged STALE at closeout
  (`auth.md`, `config-deployment.md`, `websocket-routing.md`, and the
  standards docs) tracks files this bead did not touch -- reviewed and
  left as-is; `git diff origin/dev...HEAD --stat` confirms the branch's
  full diff is exactly this bead's own 9 files.

## Files touched

- `admin_backend/routes/firm_routes.py` (new)
- `admin_backend/routes/credit_routes.py` (new)
- `admin_backend/main.py` (register the two new routers)
- `admin_backend/tests/unit/test_firm_routes.py` (new)
- `admin_backend/tests/unit/test_credit_routes.py` (new)
- `admin_backend/tests/unit/test_admin_route_auth.py` (registered-route-set
  pin gains the eight new routes)
- `admin_backend/tests/unit/test_admin_audit_coverage.py` (MUTATION_KINDS
  gains the six new mutating routes; extended the in-transaction check to
  recognize the extra_writes extension-point shape)
- `docs/technical_guide.md`, `docs/components/admin-service.md`
- `backend/tests/unit/test_credit_ledger.py` (second cross-surface round:
  widened `test_credit_ledger_is_the_only_module_that_writes_balance_credits`'s
  walk to cover `admin_backend/` and allowlisted `firm_routes.py` +
  `credit_routes.py`)
- `docs/components/auth.md` (second cross-surface round: corrected the
  "one deliberate other site" / "fails on any third" sentences)
- `admin_backend/routes/firm_routes.py` (third cross-surface round:
  `_validated_firm_id` now enforces `FIRM_ID_RE.fullmatch`, matching
  scripts/bootstrap_firm.py and user_routes.py)
- `admin_backend/tests/unit/test_firm_routes.py` (third cross-surface
  round: two behavioral parametrized tests plus the set-derived
  `test_every_firm_id_validating_site_applies_the_same_slug_rule`)

Nit findings from the third round (`polyglot-pdf-y1t68`,
`polyglot-pdf-4bchr`) were filed by the reviewer and left unfixed here per
the deferred-nit convention.

Review outcomes recorded in the closeout ping.
