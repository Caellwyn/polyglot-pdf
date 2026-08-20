---
date: 2026-08-20
bead: polyglot-pdf-z6bk9
title: "Firms retire their own private forms: the firm tier's first write path"
sprint: 19
tags: [security, testing, architecture]
---

## Trigger

Maintainer decision captured 2026-08-07: "A firm can retire its own
proprietary intake forms but not shared government ones." The firm tier as
planned (epic polyglot-pdf-02ye) was read + telemetry only -- firms see forms
and their usage is tracked; they do not change what is live. This bead adds
MUTATION, which is why the bead body spelled out four requirements rather
than just "add a route."

## The surface question was a real fork, and it was the maintainer's

The bead deliberately left one thing open: "Either the client app grows a
small forms-management view, or the firm console (deferred, bd
polyglot-pdf-gob8l) owns it. Decide which; do not bolt firm write actions
onto the editor."

I checked before treating it as decided: there is no firm-facing UI anywhere
(the `firm_role`/`owner_firm_id` grep against `frontend/src` returns nothing
outside unrelated voice tests), and `form_kit_routes.py` had zero mutation
routes. So the fork was live, and it is a product-direction call -- where a
customer-facing management action lives is not an implementation detail.

MAINTAINER DECISION (2026-08-20): backend now, console owns the UI. This bead
ships the capability with no button; bd gob8l gains the button later, and that
decision is recorded on gob8l too so the console work inherits it rather than
rediscovering it.

## What shipped

`POST /api/form-kits/{kit_id}/retire`. Three authorization checks beyond
`require_auth`, each refusing a different real attacker:

1. `firm_role == "manager"` -- an EMPLOYEE of the owning firm is refused. The
   four-level access model (02ye addendum) has employees sending links and
   tracking status, never taking a form out of service. This is the first
   route to read that claim at all.
2. `owner_firm_id == firm_id` -- another firm is refused, INCLUDING one whose
   allowlist legitimately names the kit.
3. `visibility == "private"` -- a shared/government form is refused.

Every refusal is a 404, never a 403, for the same reason the read gates 404:
a 403 confirms the kit exists to a firm that cannot see it.

## The trap: visibility is NOT authorization

Contract 7 (firm-scoped kit visibility, bd vccy) admits any kit in the
caller's `allowed_kits` -- including kits the firm does not own. It says so
explicitly: `owner_firm_id` is "bookkeeping for the write path, NOT the read
gate." This write path INVERTS that: it ignores `allowed_kits` entirely and
requires ownership.

Both directions of a future change are silent bugs -- a read gate that starts
consulting `owner_firm_id`, or this route starting to consult `allowed_kits`
(which would let a firm retire a form it merely licenses). That is now
Surface contract 8 in the technical guide, written as the inversion rather
than as a feature description, because the inversion is the thing a reviewer
needs to see.

## Scar: my mutation test proved nothing for the check that mattered most

All 12 tests passed on the first run. Then the mutations:

- delete the role check -> 1 red. Good.
- delete the ownership check -> 3 red. Good.
- **delete the visibility check -> 12 PASSED.**

The government-form promise -- the literal words of the maintainer's decision,
and half of exit criterion 2 -- was completely unpinned. The cause was the
fixture, not the assertion: my only government kit (`w7`) had no
`owner_firm_id`, so the OWNERSHIP check refused it first and the visibility
check was never the deciding factor in any test. The parametrization looked
thorough and covered nothing.

The fix is a fixture that isolates the check: `w7-mis-tagged`, a shared kit
that DOES carry the firm as owner (a mis-tagged onboard, or a government form
a firm sponsored). Ownership passes, so only visibility can refuse it. That
mutation now goes red.

GENERAL LESSON, and it is not "write more tests": when several guards refuse
the same input, the EARLIER guard masks the later ones, and a test suite full
of inputs refused for the first reason tells you nothing about the rest. Every
guard needs a fixture that reaches IT specifically -- one that satisfies every
check except the one under test. The tell is exactly what happened here: a
deletion that should be catastrophic leaves the suite green.

This also cost a wasted round earlier: my first mutation script wrote its
backup to `/tmp`, which Python on Windows resolved to a nonexistent path, so
all five mutations silently failed to apply and reported "12 passed" five
times. A mutation run that cannot prove the mutation APPLIED is not evidence.
Every mutation now asserts `s != before` before writing.

## The archive helper moved, and why

Retirement must archive first (bd w3zw): it is the last moment the published
bytes exist unaltered, and a confirmation record naming that revision has to
stay resolvable. The staff route already did this via
`_archive_published_revision` in `editor_kit_routes.py`.

Importing it from `form_kit_routes` would be circular -- `editor_kit_routes`
already imports `_safe_kit_id` from `form_kit_routes`. So the helper moved
into `backend/services/kit_gates.py` and is imported back under its original
private name, leaving all three staff call sites untouched (339 tests passed
on the move alone, before the new route existed). Its marker-precedence and
sibling-disambiguation logic is contract 6's retrieval guarantee; both tiers
now share ONE implementation instead of risking a divergent copy.

Note `resolve_edition_marker` lives in `backend/utils/confirmation_logger.py`,
not `form_kits` -- an import I got wrong first and only caught because the
module failed to import.

## The route-set guard did its job

Adding the route reddened
`test_http_route_auth.py::test_the_complete_require_auth_route_set_is_pinned`,
which names the two prose enumerations that must stay in step
(`docs/components/auth.md`, `docs/components/config-deployment.md`). That is
the ENUMERATE-THE-SET discipline paying out: the failure message told me
exactly which three places to update, instead of a reviewer finding the stale
doc two rounds later. `auth.md` gained a table of the three authorization
checks, because "gated by require_auth" badly undersells what protects this
route.
