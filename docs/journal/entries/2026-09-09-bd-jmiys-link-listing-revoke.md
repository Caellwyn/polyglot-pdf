---
date: 2026-09-09
bead: polyglot-pdf-jmiys
title: "feat(admin): B4 link listing (allowlisted) + revoke on the admin service"
sprint: 22
tags: [security, testing, doctrine]
---

## Trigger

Epic 2 (admin console) Track B bead B4, plan section "Admin-service routes"
(Links): link listing and revocation on the admin service, so an operator
or a firm manager can see a firm's client links and shut one off. B4
depends on Track A bead A3 (bd polyglot-pdf-jecrl, "mint reserves the
credit before signing; open requires a mint record") for the OTHER half of
its own exit criterion 3 -- a revoked link must be refused at open.

## What shipped

- `GET /admin/firms/{firm_id}/links` (`admin_backend/routes/link_routes.py`,
  NEW file) -- `?channel=` REQUIRED (422 missing/unknown), `?status=`/
  `?employee_id=` optional filters. Joins `links[_<channel>]` mint records
  (bead A1) with `link_redemptions[_<channel>]` detail (`opened_at`,
  `completed_at`, bead ik7e's `spend_usd`/`turns`) into an explicit key
  ALLOWLIST built by hand, never `**doc`.
- `POST /admin/links/{jti}/revoke` (same file) -- `?channel=` REQUIRED.
  One `@firestore.transactional` body (mirrors `firm_routes.py`'s
  `_apply_firm_patch` shape) flips `status` from `minted` to `revoked` and
  stamps `revoked_by`/`revoked_at`, with the audit row in the SAME
  transaction. Only a `minted` record may be revoked; any other status is
  a 409 naming the current status.
- Both routes carry `require_app_admin_or_owning_manager`. Firm scoping is
  NOT `admin_auth.resolve_target_firm` (that helper's rule -- "a manager
  may not name ANY firm in the body" -- does not fit a route whose
  `firm_id` is a URL PATH segment a manager must name to GET their own
  firm's links at all). Instead a new, LOCAL
  `link_routes._require_owning_firm(actor, firm_id)` refuses a manager
  acting on any other firm with the SAME 404 an unknown firm/jti would get
  (never 403, which would confirm the other firm exists).
- Wired into `admin_backend/main.py`; added to the hand-maintained pinned
  route set in `test_admin_route_auth.py`; added a
  `MUTATION_KIND_FIRESTORE` entry (plus a tie-back test) in
  `test_admin_audit_coverage.py`.
- `admin_backend/tests/unit/test_admin_link_routes.py` (NEW, 22 tests):
  the allowlist property (mutation-verified via stray extra keys on both
  stored docs), the 404-not-403 firm-scoping rule on both routes, the
  409-on-non-minted enumeration (all five non-`minted` statuses), and the
  atomicity pin (a forced audit-write failure leaves the link's status
  unchanged), over the same fake-Firestore shape
  `test_sweep_routes.py` and `test_firm_routes.py` already use.
- `backend/tests/integration/test_revoked_link_open.py` (NEW) -- the
  bead's OTHER exit-criterion-3 half, over the REAL `backend.main.app`'s
  `POST /api/links/open`. See "Lessons" below: this file is deliberately
  RED right now, for a documented and legitimate reason.

## Lessons

**bd polyglot-pdf-jecrl (A3) shows CLOSED in beads with a PR number, but
its PR (#749) was still OPEN and unmerged into `origin/dev`** when this
bead's worktree was created off `origin/dev`. Confirmed three ways: `git
merge-base --is-ancestor feat/jecrl-mint-reserve-open-gate origin/dev`
said no; `gh pr view 749` showed `state: OPEN`, `mergedAt: null` (CI green,
mergeable, zero review comments); and diffing `origin/dev`'s
`backend/routes/link_routes.py` against that branch showed the entire
mint-reserve-then-sign + open-requires-a-mint-record change still absent.
This bead's own text ("a subsequent A3 open of that jti is refused with
the uniform 404") was written assuming A3 had already landed.

Closing a bead when its two pre-PR review passes clear, but before the PR
itself actually merges, leaves a real gap: a DEPENDENT bead (this one)
can be handed out, build its own worktree off `origin/dev`, and discover
mid-implementation that the dependency it was told is satisfied is not
actually in the base branch. The fix belongs to the ORCHESTRATION/closeout
process (a bead should not close until its PR is merged, or "closed
pending merge" should be a visibly different state from "closed"), not to
this bead -- documented here as a discoverable trigger for whoever files
that process fix.

**What this bead did about it, rather than blocking:** built and fully
tested everything B4 owns end-to-end (listing, revoke, the audit
atomicity, the firm-scoping 404 rule) against bead A1's already-merged
schema, which is real, working, shippable code independent of A3. For the
one assertion that genuinely needs A3 (`test_revoked_link_open.py`), wrote
a real, mutation-proof integration test over the ACTUAL open route rather
than a synthetic stand-in, verified it fails for the correct, single
reason (the open route does not yet consult `links_store` at all -- proven
by a companion control test on the same file, which passes, showing the
harness itself is sound), and left a docstring in that file plus a new
Surface contract (22, `docs/technical_guide.md`) explaining exactly what
still needs to land and how to tell a landing-order gap apart from an
actual bug in either route if this is read cold later.

**Reinforces CLAUDE.md scar #9 (test the tests) in a new direction**: it
is not enough to prove a NEW test can go red by reverting a fix -- here the
test was written for code that never landed at all, and the discipline
that mattered was proving the RED is for the right reason (the open route
truly does not check revocation) rather than a bug in the test harness
itself (verified via the passing control-case sibling test).

## Doc freshness

- `docs/components/admin-service.md` -- Tracks line gained
  `admin_backend/routes/link_routes.py`; new dated changelog paragraph;
  two new route-table rows; testing section gained
  `test_admin_link_routes.py` and a note on `test_revoked_link_open.py`'s
  landing-order dependency. Bumped to 2026-09-09 (same day as the
  existing top entry, appended above it).
- `docs/technical_guide.md` -- new Surface contract 22 (link listing +
  revoke: admin routes -> the mint record's `status` -> A3's open gate),
  covering the producer/consumer relationship, the landing-order gap, the
  N+1 join shape, and why the firm-scoping helper is not
  `resolve_target_firm`. `technical_guide.md` carries no top-of-file
  timestamp by design (CLAUDE.md doc map).

## Files touched

- `admin_backend/routes/link_routes.py` (new)
- `admin_backend/main.py` (router registration + docstring)
- `admin_backend/tests/unit/test_admin_link_routes.py` (new)
- `admin_backend/tests/unit/test_admin_route_auth.py` (pinned route set)
- `admin_backend/tests/unit/test_admin_audit_coverage.py` (MUTATION_KINDS
  entry + tie-back test)
- `backend/tests/integration/test_revoked_link_open.py` (new)
- `docs/components/admin-service.md`
- `docs/technical_guide.md`

Review outcomes recorded in the closeout ping.
