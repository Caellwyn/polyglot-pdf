---
date: 2026-09-08
bead: polyglot-pdf-dmjl5
title: "feat(admin): B2 user management routes (claims allowlist) + require_firm_manager and the composite gate"
sprint: 22
tags: [security, refactor, testing]
---

## Trigger

Epic 2 Track B bead B2 of the admin-console program
([plan](../../sprint_22_admin-console_plan.md), "Admin-service routes" ->
Users, plus Epic 1's gating section). The admin console needs to create and
manage a firm's staff accounts, and bd `polyglot-pdf-gob8l` had already
established that a firm's own manager does this without an operator in the
loop -- so the same four routes serve two different actors.

Two of the plan's four gates were still unbuilt, and each was scheduled to
ship with its first consuming route rather than untested:
`require_app_admin_or_owning_manager` (the composite these routes need) and
`require_firm_manager`, whose rule was sitting inline in the retire route's
helper and was about to be hand-written a second time here.

## What shipped

**The manager rule has ONE home.**
`backend/services/firms.py`'s `manager_firm_id(claims)` is now the only code
that decides "is this caller a manager, and of which firm". It is a pure,
side-effect-free predicate over an ALREADY-VERIFIED claims dict --
authorization, not authentication.

Where it lives was the interesting call. The bead named
`backend/services/auth.py`, and `auth.py` does get the FastAPI dependency
`require_firm_manager` plus a re-export of the name, so its own callers read
it from their own auth module. But the predicate itself sits in `firms.py`,
because `admin_backend/services/admin_auth.py` **may not import
`backend/services/auth.py`** -- that module is deliberately liftable, and
`test_admin_auth.py::test_admin_auth_does_not_import_the_other_two_auth_modules`
pins it. That guard is about not depending on another surface's VERIFIER;
`firms.py` is neither surface's verifier, it is the module that already owns
what a firm is. So the rule is shared without a verifier being shared, and
the isolation test needed no amendment.

**Two consumers, two refusal shapes, deliberately.**
`require_firm_manager` raises 403. `form_kit_routes.
_require_firm_owns_private_kit` consumes the PREDICATE instead and keeps its
404, because a 403 there would confirm to a firm that another firm's kit
exists. Retire behaviour is byte-identical and its existing tests passed
unmodified.

**The composite gate.** `require_app_admin_or_owning_manager` checks
`app_admin` FIRST -- an account holding both claims acts as the wider role;
the reverse order would silently downgrade it to its own firm, which is the
outcome someone debugs for an hour. Both branches verify the token with
`admin_auth.py`'s own `verify_id_token`. `resolve_target_firm(actor,
body_firm_id)` is the one home for the two-actor rule: an app admin must
name a firm (422 otherwise), a manager may not name one **at all**.

That last point is the design decision worth recording. A manager who names
their OWN firm is refused too. "The same value" is not the test; "did you
try to choose" is. Accepting a matching value would make the refusal depend
on what the caller happened to send, so the next console version that sent
it on every request would silently stop being refused -- and at that point a
bug sending the wrong firm becomes a cross-firm write, with no test that
notices.

**Four routes** (`admin_backend/routes/user_routes.py`): `POST
/admin/users` (create + password-reset link, no outbound email in this
epic), `PATCH /admin/users/{uid}/disable`, `PATCH .../role`, `GET
/admin/users`. The two by-uid routes prove the target account is in the
resolved firm before touching it -- a uid is a bearer of nothing, so without
that a manager could disable any account in the project by pasting its uid
-- and refuse with the SAME 404 a nonexistent uid gets, so the status code
is not an existence oracle. Every Firebase Auth call runs through
`asyncio.to_thread`.

**The claims allowlist** (`admin_backend/services/user_admin.py`) is a
property rather than a promise: `merge_firm_claims()` builds its output from
`WRITABLE_CLAIMS = {firm_id, firm_role}` plus the account's existing claims,
so no request value can reach `app_admin`, `schema_editor_role` or
`vff_dev`, and nothing pre-existing is destroyed. `set_custom_user_claims`
REPLACES the whole claims object -- the same trap
`scripts/bootstrap_firm.py` calls its highest-risk line -- so without the
merge, promoting a firm's dev to manager would strip their `vff_dev` claim
and lock them out of the voice app.

**Auditing** uses the pending-then-committed form, and these are its first
consuming routes: Firebase Auth mutations cannot join a Firestore
transaction, so there is nothing to join. A row stuck at `pending` says
exactly "this may have taken effect".

## Lessons

**An ordering assertion needs a log that spans BOTH systems.** The first
version of the audit-order test read the fake Firestore's write log and
asserted the pending row came first. Mutating the route to write the pending
row AFTER the Auth call left all 72 tests green: the Firestore log contains
only Firestore writes, so the pending row is first no matter where the Auth
call moves. The claim "pending BEFORE the action" is about two systems, and
only a shared timeline both fakes append to can pin it. This generalizes:
whenever an assertion is about the order of events in two different
subsystems, a per-subsystem log cannot state it, and the test will pass
vacuously rather than fail loudly. Caught here only because the mutation was
actually run (CLAUDE.md scar #9).

**"One home" is pinned by enumerating the SET, not by testing the helper.**
Testing `manager_firm_id` proves the helper works; it says nothing about
whether anyone uses it. `test_require_firm_manager.py` therefore AST-walks
every non-test module under `backend/`, `admin_backend/` and `scripts/` and
fails on any comparison against the literal `"manager"` outside a short
justified allowlist -- so the next route that hand-writes the check fails CI
instead of drifting for a release (CLAUDE.md scar #8). A second test pins
that the retire helper actually CALLS the shared rule, since deleting the
check entirely would also pass a no-literal scan -- guard the property, not
the code shape you deleted.

**A liftability guard can be honoured by moving the shared thing down, not
by weakening the guard.** The obvious reading of the isolation test was that
it blocked sharing the rule at all. It did not: it blocked depending on
another surface's verifier. Putting the pure predicate in the domain module
both surfaces already legitimately import satisfied the guard untouched.
Reach for that before amending a deliberate constraint.

## Doc freshness

- `docs/components/admin-service.md` -- bumped. Four route rows; new
  sections for `require_app_admin_or_owning_manager` and
  `require_firm_manager`; "the latter three do not exist yet" is down to
  one.
- `docs/components/auth.md` -- bumped. New "The manager rule" section with
  the two-refusal-shape table, plus staff-account management. Two stale
  claims this bead falsified were corrected: "`firm_role` is still a future
  consumer" and "no in-console user management yet".
- `docs/technical_guide.md` -- four routes-table rows (sorted by
  `(path, method)`, as `tests/test_technical_guide_routes_table.py`
  requires) and new **Surface contract 19**. Contract 8's "there is no
  shared helper yet because there is one caller" was made false by this bead
  and now points at the shared rule. No stamp by design.
- No CLAUDE.md change.

Review outcomes recorded in the closeout ping.

## Files touched

- `backend/services/firms.py` -- `FIRM_ROLE_MANAGER`/`_EMPLOYEE` and
  `manager_firm_id()`, the rule's one home.
- `backend/services/auth.py` -- re-exports the rule; adds
  `require_firm_manager` (403).
- `backend/routes/form_kit_routes.py` -- the retire helper consumes the
  predicate; behaviour unchanged.
- `admin_backend/services/admin_auth.py` -- `CompositeActor`,
  `require_app_admin_or_owning_manager`, `resolve_target_firm`.
- `admin_backend/services/user_admin.py` (new) -- the claims allowlist and
  the Firebase Auth calls.
- `admin_backend/routes/user_routes.py` (new) -- the four routes.
- `admin_backend/main.py` -- router registration.
- `admin_backend/tests/unit/test_admin_route_auth.py` -- route-set pin
  extended; three of four gates now exist.
- `admin_backend/tests/unit/test_admin_audit_coverage.py` -- the three
  mutations declared as `external`; a tie-back from the synthetic external
  checks to the real module.
- `admin_backend/tests/unit/test_user_routes.py` (new) -- the three exit
  criteria.
- `backend/tests/unit/test_require_firm_manager.py` (new) -- the rule over
  the whole claim space, and the one-home set pin.
- `docs/components/admin-service.md`, `docs/components/auth.md`,
  `docs/technical_guide.md`.
