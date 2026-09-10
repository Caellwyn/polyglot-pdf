---
date: 2026-09-09
bead: polyglot-pdf-scaig
title: "fix(admin): employee-role staff accounts cannot reach GET /admin/firms/{firm_id}/links at all (403), breaking C5's employee link history"
sprint: 22
tags: [security, testing]
---

## Trigger

Discovered while building bd polyglot-pdf-x22hm (Epic 2 Track C bead C5,
the firm-console link history page). The plan (docs/sprint_22_admin-
console_plan.md, "Frontend" main-app section) says `/console/links/history`
shows a manager the firm's links and shows an employee ONLY their own
links, with both firm and employee taken from the verified token. The
page's own author checked and found the server side did not support this
at all: `GET /admin/firms/{firm_id}/links` and `POST /admin/links/{jti}/
revoke` both carry `require_app_admin_or_owning_manager`
(`admin_backend/services/admin_auth.py`), which has exactly TWO actor
kinds -- app admin, or a firm manager (`backend.services.firms.
manager_firm_id`). An employee-role staff account (`firm_role="employee"`)
was refused with a flat 403 (the `NO_ADMIN_ACCESS:` prefix) before the
route's own `employee_id` filtering logic ever ran. The plan's own named
tests for this (`test_employee_link_listing_response_is_allowlisted`,
`test_employee_history_scoped_to_token`) did not exist in
`test_admin_link_routes.py` as shipped by bd polyglot-pdf-jmiys (B4). x22hm
filed this bead rather than fixing it itself, since the fix belongs on
`admin_backend/` surfaces B4/jmiys owns, not x22hm's frontend-only ones.

## What shipped

A new, route-scoped FastAPI dependency,
`require_app_admin_or_owning_manager_or_employee`
(`admin_backend/services/admin_auth.py`), wired ONLY onto `GET
/admin/firms/{firm_id}/links`. It shares its token-verification body with
the original `require_app_admin_or_owning_manager` via a new private
`_resolve_admin_or_manager_or_employee_actor(token, allow_employee=...)`
helper, so the branch order (app admin checked first, so an account
holding both claims acts as the wider role) cannot drift between the two
functions -- only whether the employee branch is even reachable differs.

The employee branch resolves via a new sibling rule,
`backend/services/firms.py::employee_firm_id(claims)` -- the exact same
shape as `manager_firm_id` (accept only `firm_role == "employee"` with a
non-empty string `firm_id`), living right beside it. `CompositeActor`
gained a third kind (`ACTOR_KIND_FIRM_EMPLOYEE`) and an `employee_id`
field, populated from the token's own uid.

`link_routes.py`'s `list_firm_links` now forces `employee_id` to
`actor.employee_id` whenever the actor is an employee, silently overriding
whatever (if anything) the `?employee_id=` query names -- the plan's own
words, "ids come from the token, not the query". This is a different rule
from `resolve_target_firm`'s body-field refusal (naming ANY firm at all is
itself the 403 there): here there is exactly one value an employee's own
filter could ever legitimately mean, so substituting it silently is
applying the only correct answer, not hiding a disagreement.
`_require_owning_firm` needed no employee-specific branch at all -- an
employee actor carries `firm_id` identically to a manager actor, so the
existing check already covers both.

**Decision: a new dependency (shape b), not a widened existing one (shape
a).** The bead's own description flagged both shapes and asked whoever
picked it up to weigh them. Widening `require_app_admin_or_owning_manager`
itself was rejected because that gate is ALSO the gate on the four
`/admin/users` routes (bd polyglot-pdf-dmjl5) and on `POST
/admin/links/{jti}/revoke`, where an employee has never had access and
must continue not to --
`test_composite_gate.py::test_neither_an_admin_nor_a_manager_is_403`
already pinned an employee claims dict as a 403 through that exact name
before this bead, and widening it would have silently widened those other
routes too (exactly the risk the bead's own text named for shape (a)).
Revoke was left entirely untouched -- an employee must never revoke a
link, and keeping it on the narrower, unwidened dependency makes that
structurally true (the dependency graph, not an in-route check) rather
than merely policy.

The fifth gate is deliberately OUTSIDE
`test_admin_route_auth.py`'s four-gate vocabulary (the plan's own named
list of exactly four: `require_app_admin`, `require_firm_manager`,
`require_app_admin_or_owning_manager`, `require_google_oidc`) -- it is
pinned directly on its one route instead
(`test_only_the_link_listing_route_carries_the_fifth_gate`), the same way
`require_google_oidc`'s specific route already got a pin beyond the
generic four-gate set check.

## Lessons

The recurring shape this bead is one more instance of: a composite gate
built for TWO actor kinds gets a THIRD kind's requirement discovered later
by a downstream consumer (here, the frontend page that needed it). The
generalizable point, already covered by CLAUDE.md's escalation doctrine and
scar #8 (one rule, one home): when a shared gate needs widening for ONE
consumer but is load-bearing for OTHERS, the safe default is a NEW,
narrowly-scoped dependency sharing the verification body, not a parameter
that changes the old one's behavior for every caller -- and a pinned test
on the OLD gate's narrower behavior (here, `test_neither_an_admin_nor_a_
manager_is_403`'s employee case) is exactly the signal that a widen-in-
place would be the wrong shape. No new standards doc needed; this is an
instance of the existing doctrine, not a new lesson.

## Doc freshness

Bumped (current-state edits, not history chains):
- `docs/components/admin-service.md` -- new dated note, the route table row
  for `GET /admin/firms/{firm_id}/links`, a corrected claim about revoke's
  gate (it no longer says "both routes"), a new subsection for the fifth
  gate, and updated testing-inventory prose.
- `docs/components/auth.md` -- new dated note and a paragraph on the
  sibling `employee_firm_id` rule beside "The manager rule" section.
- `docs/components/config-deployment.md` -- new dated note and a pointer
  to the fifth gate in the gate-inventory prose (no deploy-time env var or
  config key changed).
- `docs/technical_guide.md` -- fixed Surface contract 22's route table row
  and added an addendum explaining the widened gate (no stamp on this doc
  by design).

`scripts/check_doc_freshness.py` confirms all four are fresh. Other STALE
docs it reports (`schema-key-visibility.md`, `stateless-architecture.md`,
etc.) track files this bead did not touch and are left for whoever's work
actually changed them.

## Files touched

- `backend/services/firms.py` -- new `employee_firm_id(claims)`.
- `admin_backend/services/admin_auth.py` -- new `ACTOR_KIND_FIRM_EMPLOYEE`,
  `CompositeActor.employee_id`, `_resolve_admin_or_manager_or_employee_
  actor`, new `require_app_admin_or_owning_manager_or_employee`.
- `admin_backend/routes/link_routes.py` -- `list_firm_links` now depends on
  the new gate and forces `employee_id` for an employee actor;
  `_require_owning_firm`'s docstring updated (no behavior change needed).
- `admin_backend/tests/unit/test_admin_link_routes.py` -- employee-actor
  listing tests (own-firm access, token-not-query scoping, never seeing
  another employee's links, 404-not-403 cross-firm, allowlisted response,
  status filter still applies) and a direct pin that revoke's wiring still
  carries only the narrower gate.
- `admin_backend/tests/unit/test_composite_gate.py` -- the new gate's own
  branch resolution, 401/403 splits, dev bypass, and a pin that the
  original gate still 403s an employee claims dict unchanged.
- `backend/tests/unit/test_require_firm_manager.py` -- `employee_firm_id`'s
  whole-claim-space enumeration and a check that the two rules never both
  accept the same claims.
- `admin_backend/tests/unit/test_admin_route_auth.py` -- the fifth gate
  recognized as a legal single gate, plus a new test pinning it to exactly
  one route.
- `docs/components/admin-service.md`, `docs/components/auth.md`,
  `docs/components/config-deployment.md`, `docs/technical_guide.md` -- see
  "Doc freshness" above.

## Cross-surface review round 1

The Opus outer reviewer traced every changed contract (the new dependency,
`CompositeActor.employee_id`, the new `ACTOR_KIND_FIRM_EMPLOYEE`,
`employee_firm_id`, the listing route's forced `employee_id`, the new
Firestore query shape, and the gate-set vocabulary) into every consumer file
outside the diff and returned GAPS-FOUND(1):

- **Adopted (fixed inline):** `docs/technical_guide.md:192`'s `/health`
  row said "every other route ... carries one of the four gates named in
  `test_admin_route_auth.py`" -- true on `origin/dev`, false on HEAD (that
  test's `known_gate_names` is now five, and the link-listing route carries
  the fifth). This diff had already fixed the doc's OTHER two mentions
  (Surface contract 22's row and its own addendum) but never enumerated the
  rest of the file's restatements (CLAUDE.md scar #8) -- this was the one
  instance in `technical_guide.md` itself. Reworded to name both the
  four-gate plan vocabulary AND the fifth route-scoped gate explicitly,
  pointing at the test file as the enumeration's source of truth rather than
  hand-repeating a count that will go stale again the next time the set
  changes.
- **Deferred (already filed as beads, not touched here):** three more
  "four gates" restatements in files this bead's diff never touched at all
  (`admin_backend/main.py:25`, `test_admin_route_auth.py:202`'s assertion
  message, `test_admin_health.py:109`), plus a docstring in
  `test_admin_route_auth.py` that names a test (`test_link_listing_route_
  gate_set`) which does not exist -- the real test is `test_only_the_link_
  listing_route_carries_the_fifth_gate`, and the docstring's claimed guard
  mechanism (a second gate-only route becoming an "unrecognized-combination
  offender") is also wrong (the fifth gate IS in `known_gate_names`, so it
  would pass the set pin; the real guard is the separate `carriers == [...]`
  assertion). Both filed as `polyglot-pdf-xwm32` (comment-align, nit) by
  the reviewer before this round; the docstring inaccuracy is a nit on a
  correct, mutation-verified guard, not a functional gap.
- **Refuted (no code change; recorded so it is not re-hunted):** the
  reviewer's own trace initially flagged the new unconditional
  `firm_id`+`employee_id` Firestore query as needing a composite index
  absent from `firestore.indexes.json`. Retracted in the same report: the
  query is all-equality even with `?status=` added, and
  `test_firestore_indexes.py`'s own stated rule is that Firestore's
  automatic single-field index merging covers all-equality queries --
  no index owed, correct as shipped.
- **Deferred (already filed, not touched here):** the employee scoping in
  `link_routes.py` fails OPEN (not closed) if a `CompositeActor` is ever
  constructed with `kind=ACTOR_KIND_FIRM_EMPLOYEE` and `employee_id=None` --
  unreachable today (the sole production constructor 401s on a falsy uid
  before building the actor), but the invariant lives in one constructor's
  control flow rather than the type. Filed as `polyglot-pdf-wiju0`
  (local-bug, nit) by the reviewer before this round.

Full backend + admin_backend suite re-run after the fix: 4176 passed, 67
skipped, 3 deselected, 1 xfailed, 0 failed. Root-level suite: 1472 passed,
46 skipped. No new or changed test in this round (the fix is a doc-only
correction), so no mutation-verification was owed.

Review outcomes recorded in the closeout ping.
