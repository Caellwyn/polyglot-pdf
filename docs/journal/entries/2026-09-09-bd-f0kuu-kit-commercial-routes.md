---
date: 2026-09-09
bead: polyglot-pdf-f0kuu
title: "feat(admin): B3 kit commercial settings routes (credit_cost, burn_cap_usd) on the admin service"
sprint: 22
tags: [security, testing]
---

## Trigger

Epic 2 Track B bead B3 (plan: `docs/sprint_22_admin-console_plan.md`,
"Admin-service routes" -> Kits: `GET`/`PUT /admin/kits/{kit_id}/commercial`).
Bead B1 (firm CRUD + credits), B2 (users), B4 (link listing + revoke) and B5
(the sweep) had all already shipped; B3 was the one Track B route group
still missing, and it blocks C1 (the console's kit-commercials page, bead
`polyglot-pdf-mzblw`). The read side already existed --
`backend/services/kit_commercials.py::resolve_commercial`, shipped with
Epic 2 bead A3's mint transaction -- so this bead's job was narrow: the
write side, plus a listing route, on top of a reader that must not be
duplicated.

## What shipped

`admin_backend/routes/kit_routes.py`, three routes, all behind
`require_app_admin`:

- `GET /admin/kits` -- every kit id in the form-kit store
  (`backend/services/form_kits.py`'s async `list_kit_ids()`), each joined
  with its resolved commercial doc (or the global defaults) via the SAME
  reader the other two routes use.
- `GET /admin/kits/{kit_id}/commercial` -- calls
  `kit_commercials.resolve_commercial(kit_id)` directly. This bead adds NO
  second reader; a test (`test_get_commercial_calls_the_shared_a3_reader`)
  asserts the import by NAME so a future rewrite that inlines a second copy
  of the fallback logic is caught even if it happens to compute the same
  numbers today.
- `PUT /admin/kits/{kit_id}/commercial` -- sets `credit_cost`,
  `burn_cap_usd`, `display`. Validates BEFORE any write: `credit_cost` must
  be a positive int (bool explicitly excluded -- bool is an int subclass,
  so an unguarded `isinstance(x, int)` check would price a form at 1 credit
  on a stray `true`), `burn_cap_usd` must be a positive FINITE float (NaN
  and +-inf both refused explicitly), `display` must be a small string map
  (key count and value length capped). This is deliberately STRICTER than
  the read side's own defensive fallback
  (`kit_commercials.resolve_commercial` / `link_budget.cost_ceiling_usd_for_kit`
  fall back to a default on a bad STORED value, because an old bad edit must
  never remove a form's ceiling) -- the write path's job is the opposite
  half of that same invariant: refuse the bad edit outright so it never
  reaches the store as a "successful" write the fallback then has to paper
  over. The write and its audit row share ONE `@firestore.transactional`
  body, mirroring `firm_routes.py`'s `_apply_firm_patch` shape (this route
  is the only writer of `kits/{kit_id}`, so there is no other transaction to
  join via `extra_writes`).

Registered in `admin_backend/main.py`. Extended
`test_admin_route_auth.py`'s route-set pin with the three new
`(method, path)` tuples, and `test_admin_audit_coverage.py`'s
`MUTATION_KINDS` declaration (`PUT /admin/kits/{kit_id}/commercial` ->
`MUTATION_KIND_FIRESTORE`) plus its own shipped-module tie-back test
(`test_the_shipped_kit_routes_pass_the_synthetic_firestore_check`), matching
the pattern every other Firestore-mutating admin route already follows.

`admin_backend/tests/unit/test_kit_routes.py`: 44 tests over the same
buffer-and-commit fake-Firestore shape `test_config_routes.py` established
-- exit criterion 1 (one committed audit row; a forced audit failure leaves
the doc unchanged; every malformed-body shape refused with no write) and
exit criterion 2 (a kit with no commercial doc returns the global defaults
and says `source: "default"`; the shared-reader import pin). NaN/+-inf for
`credit_cost`/`burn_cap_usd` are sent as raw JSON body bytes rather than via
httpx's `json=` param, because httpx's own client-side JSON encoder refuses
to serialize a Python `float("nan")`/`float("inf")` at all -- a raw body is
the faithful equivalent of a caller that put those literal (non-standard,
but Python-`json`-parseable) tokens on the wire directly.

## Lessons

**A parametrized "malformed shape" list needs to be checked against what the
transport layer can actually carry, not just what Python can construct.**
Three parametrized cases in the first draft of `test_kit_routes.py` could
not fire as written: `float("nan")`/`float("inf")` cannot be JSON-encoded by
httpx's client at all (ValueError at encode time, not a 422 from the
server); a non-string dict KEY (`{5: "x"}`) is impossible over real JSON
(object keys are always strings on the wire -- `json=` would silently
stringify it before sending); and `../` / an embedded newline in a URL path
segment get normalized or rejected by httpx's own URL parser before the
request ever reaches the app, so asserting a 422 on them tests the HTTP
client, not the route. All three were caught by literally reverting the
route's own validation for that field and confirming the corresponding test
went red (CLAUDE.md's "test the tests" rule) -- the NaN/inf case initially
failed with a `ValueError` from `json.encoder`, not a 422, which is what
surfaced the transport-layer gap. Fixed by sending the two float cases as
raw request bodies (bypassing httpx's encoder) and by narrowing the kit_id
and display-key parametrizations to shapes reachable as a real HTTP
request, with each removed case's reasoning left in the test's own
docstring rather than silently dropped.

## Doc freshness

`docs/components/admin-service.md` (Tracks line, changelog entry, three
routes-table rows, Testing section) and `docs/technical_guide.md`
(extended Surface contract 24 -- the mint reservation and open gate -- with
the write side of the mechanism that contract already documented the read
side of, rather than minting a new contract number for an addition to an
already-documented reader; three routes-table rows at their sorted
(path, method) position, verified by
`tests/test_technical_guide_routes_table.py`) both bumped to 2026-09-09.
`scripts/check_doc_freshness.py` reports both `OK` (not stale) after the
edit; every other STALE doc it lists tracks files this bead did not touch
(schema-editor, WS protocol, VAD, terminology, etc.) and is left for its own
bead. Review outcomes recorded in the closeout ping.

## Files touched

- `admin_backend/routes/kit_routes.py` -- new: the three routes.
- `admin_backend/main.py` -- registers the router, docstring note.
- `admin_backend/tests/unit/test_kit_routes.py` -- new: 44 tests.
- `admin_backend/tests/unit/test_admin_route_auth.py` -- route-set pin.
- `admin_backend/tests/unit/test_admin_audit_coverage.py` -- MUTATION_KINDS
  entry + tie-back test.
- `docs/components/admin-service.md` -- Tracks line, changelog, routes
  table, Testing section.
- `docs/technical_guide.md` -- Surface contract 24 extension, changelog,
  routes table.
