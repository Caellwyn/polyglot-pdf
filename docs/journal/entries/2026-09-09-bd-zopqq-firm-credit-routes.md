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

### A missing catch-all in credit_routes.py

While mutation-testing the "forced audit failure leaves the balance
unchanged" pin, a raw exception from a Firestore write (simulated via the
fake db's `audit_write_error`) propagated as an UNHANDLED exception through
FastAPI's default exception middleware instead of a clean 500 -- unlike
`config_routes.py` and `firm_routes.py`, which both wrap unexpected
exceptions from their transactional bodies into `HTTPException(500)`.
Added the same catch-all to `credit_routes.py::_run_append_entry`.

## Lessons

A route that joins an EXISTING shared transaction via a documented
extension point (rather than opening its own) is a legitimate shape a
set-derived mechanical guard needs to recognize explicitly -- the guard's
original design (one route module, one `@firestore.transactional` body)
predates any real consumer of `append_entry`'s `extra_writes` hook. This is
noted in `test_admin_audit_coverage.py`'s own docstring for the next reader
who adds a third such consumer (the Track A mint route, when it lands, will
be the second).

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

Review outcomes recorded in the closeout ping.
