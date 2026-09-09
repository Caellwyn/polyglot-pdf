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

### Fresh-eyes round 1 (post-review fixes)

The outer cross-surface review returned `GAPS-FOUND (2)`. Breakdown:

- **Adopted (blocker) -- `GET /admin/kits` did not catch `FormKitStoreError`
  from `store.list_kit_ids()`,** unlike every other `FormKitStore` call site
  in the repo (`backend/routes/form_kit_routes.py`'s six sites all wrap the
  call and return a 502). Fixed: `list_kits` now catches `FormKitStoreError`
  and raises the same 502-with-logged-error shape. New test
  `test_list_kits_on_a_store_outage_returns_a_clean_502` (mutation-verified:
  removing the try/except reddens it with an unhandled
  `FormKitStoreError` propagating through the route instead of a clean 502).
- **Adopted (blocker) -- GET and PUT used different field names
  (`cap_usd` vs `burn_cap_usd`) for the identical stored value,** with no
  shared constant and no test tying them together, so a console reading
  both responses for the same kit would need a per-route translation for
  one number. Fixed on the PUT side only (the shared A3 reader,
  `kit_commercials.resolve_commercial`, is unchanged per the plan's "do not
  write a second reader"): `PUT`'s response now carries the value under
  both `burn_cap_usd` (matching its own request body / the storage key) and
  `cap_usd` (matching what GET returns for the same kit) -- the identical
  float just validated and written, so the two cannot drift. New test
  `test_put_response_cap_usd_matches_get_response_cap_usd` (mutation-
  verified: dropping the `cap_usd` key reddens it with a `KeyError`).
- **Deferred (nits, filed as bead `polyglot-pdf-y2hht`,
  "chore(nits): deferred review nits from polyglot-pdf-f0kuu") --** the
  empty-`kit_id` test comment's inaccurate "falls through to GET
  /admin/kits" claim; `GET /admin/kits`'s sequential, unbounded,
  unparalleled per-kit Firestore fan-out; and the pre-existing (unchanged on
  `origin/dev`) chronological `bd <id>:` stamp-chain preamble style in
  `docs/components/admin-service.md` / `docs/technical_guide.md` (the
  reviewer could not file this themselves -- `bd dolt pull` timed out twice
  in their environment -- so it is filed here instead). None of the three
  change behavior or trace to an exit criterion.

### Fresh-eyes round 2 (post-review fixes)

The outer cross-surface review returned `GAPS-FOUND (1)`. Breakdown:

- **Adopted (rubric-fail) -- exit criterion 2's own named mechanism ("a test
  asserts the import") was vacuous.**
  `test_get_commercial_calls_the_shared_a3_reader` scanned
  `inspect.getsource(kit_routes)` -- the WHOLE MODULE, not the function that
  actually calls the reader -- for the literal string
  `"kit_commercials.resolve_commercial"`. That exact string already appears
  in the module's own docstring (line 26) and in `_validated_credit_cost`'s
  docstring (line 125), so a module-wide scan stays green even if both real
  call sites (`get_kit_commercial`, `list_kits`) were replaced with an
  inlined second reader -- the precise regression the test's own docstring
  says it exists to catch. Verified by direct simulation (reviewer) and by
  mutation (this round): inlining a hardcoded dict in place of the
  `kit_commercials.resolve_commercial` call in `get_kit_commercial` left the
  old module-scoped assertion green. Fixed: the test is now parametrized
  over both GET-side functions (`get_kit_commercial`, `list_kits`), each
  checked via its own AST-derived function body with the docstring `Expr`
  node stripped first, so a docstring mentioning the reader by name can no
  longer stand in for a real call in the body. Re-verified the mutation:
  the same inlined-dict mutation in `get_kit_commercial` now reddens
  `test_get_commercial_calls_the_shared_a3_reader[get_kit_commercial]`
  while `list_kits`'s parametrization (untouched by the mutation) stays
  green, confirming the check is scoped per-function rather than
  module-wide or all-or-nothing.
- **Other findings (non-rubric, not changed):** the reviewer re-confirmed
  the transactional write, the `Optional[dict]` typing on `display` (loose
  Pydantic typing is intentional -- `_validated_display` does the real
  validation manually), and the deliberate `merge=True` omission on the PUT
  write (a full-document overwrite, matching `KitCommercialPutRequest`'s own
  documented "a PUT replaces the whole commercial doc" contract) as correct
  as shipped -- no code change. The `list_kits` sequential per-kit Firestore
  read (no batching) was again flagged as a **nit**, explicitly not filed as
  a new bead (matches the existing codebase's per-admin-route convention,
  not a regression this diff introduces) -- already covered in spirit by
  `polyglot-pdf-y2hht`'s "sequential, unbounded, unparalleled per-kit
  Firestore fan-out" item from round 1.

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

- `admin_backend/routes/kit_routes.py` -- new: the three routes; fresh-eyes
  round 1 added the `FormKitStoreError` -> 502 catch in `list_kits` and the
  `cap_usd` echo in `put_kit_commercial`'s response.
- `admin_backend/main.py` -- registers the router, docstring note.
- `admin_backend/tests/unit/test_kit_routes.py` -- 47 tests (44 at initial
  ship, +2 in fresh-eyes round 1, +1 in fresh-eyes round 2: the shared-reader
  import-pin test was reworked into a 2-way parametrization, net +1 test).
- `admin_backend/tests/unit/test_admin_route_auth.py` -- route-set pin.
- `admin_backend/tests/unit/test_admin_audit_coverage.py` -- MUTATION_KINDS
  entry + tie-back test.
- `docs/components/admin-service.md` -- Tracks line, changelog, routes
  table, Testing section.
- `docs/technical_guide.md` -- Surface contract 24 extension, changelog,
  routes table.
