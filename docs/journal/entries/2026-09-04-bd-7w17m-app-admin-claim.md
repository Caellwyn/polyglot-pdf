---
date: 2026-09-04
bead: polyglot-pdf-7w17m
title: "feat(admin): 1.2 app_admin claim, require_app_admin, bootstrap_admin_user.py, route-auth set test"
sprint: 22
tags: [security, testing]
---

## Trigger

Epic 1 child 1.2 of the admin-console program
(`docs/sprint_22_admin-console_plan.md`): the admin service skeleton
(bd `polyglot-pdf-pnoik`) shipped `/health` and `/version` only, with a
docstring note that "routers and the require_app_admin gate land in bd
polyglot-pdf-7w17m." This bead is that landing: the first real gate, the
first real route, the bootstrap tool that creates the first admin account,
and the set test that keeps every future route on this service honest.

## What shipped

- `admin_backend/services/admin_auth.py` -- `APP_ADMIN_CLAIM = "app_admin"`
  (boolean), `AdminActor` (uid/email/label()), `require_app_admin`. Mirrors
  `backend/services/editor_auth.py`'s shape closely: dev bypass checked
  first and refused outright when `K_SERVICE` is set (fail-closed on a
  deployed instance), `verify_id_token` with `check_revoked` deliberately
  OFF (matching the editor and the public backend's scar #7 posture, even
  though admin-backend-sa actually holds `roles/firebaseauth.admin` and
  could afford the call -- left symmetric until a real need is measured),
  and a 401/403 split where the 403 for "valid account, no admin claim"
  carries a machine-readable `NO_ADMIN_ACCESS:` prefix so a future admin
  console can route it to a refused screen rather than an ordinary in-app
  refusal.
- `admin_backend/routes/whoami.py` -- `GET /admin/whoami`, gated by
  `require_app_admin`, wired into `admin_backend/main.py`. Deliberately the
  simplest possible route: it exists to prove the gate end to end before any
  business logic lands.
- `admin_backend/tests/unit/test_admin_route_auth.py` -- derives the
  complete registered route set from the live app object (no hand
  maintenance) and asserts every business route carries EXACTLY ONE of the
  four gate names the plan specifies (`require_app_admin`;
  `require_firm_manager`; `require_app_admin_or_owning_manager`;
  `require_google_oidc`) -- only the first exists yet, the other three are
  named as strings so a test importing a not-yet-real symbol cannot break
  collection. Includes a self-proving test
  (`test_a_route_added_without_a_gate_is_caught`) that registers a
  throwaway ungated route directly on the live app and confirms the
  derivation flags it, satisfying exit criterion 2 mechanically rather than
  by inspection.
- `admin_backend/tests/unit/test_admin_auth.py` -- unit coverage for the
  verifier itself: stamped passes, unstamped 403s with the prefix, a
  non-boolean-truthy claim value is refused (`is not True`, not a bare
  truthiness check), tokenless 401s, the dev bypass's K_SERVICE refusal, the
  check_revoked-is-off guard, self-init, and isolation from the editor's and
  voice app's claim namespaces.
- `scripts/bootstrap_admin_user.py` -- the only way to create the first
  admin. Mirrors `scripts/bootstrap_editor_user.py`'s CLI shape
  (`--email`/`--revoke`/`--list`, positional email accepted, claims merged
  via read-then-spread, revoke also calls `revoke_refresh_tokens` so a
  revoked admin's live session dies rather than surviving up to an hour) and
  borrows `scripts/bootstrap_firm.py`'s `--project` machinery: `--project`
  is REQUIRED, the script pre-initializes `firebase_admin` with that
  `projectId`, asserts the resolved app project matches, and refuses the
  dead project `polyglot-forms-919f2` outright before any Firebase call.
  Deliberately NOT sharing a base class with either sibling script (both
  document the same "future separation epic" reasoning for staying
  independent).
- `backend/tests/unit/test_bootstrap_admin_cli.py` -- CLI contract tests in
  the shape of `test_bootstrap_firm_cli.py` (project pin, dead-project
  refusal, exit codes) plus `test_editor_identity.py`'s claim-merge/revoke
  coverage, driven as `boot.main([...])`.
- `admin_backend/tests/unit/test_admin_health.py`'s
  `test_the_admin_app_registers_no_unauthenticated_business_route` (an
  explicit placeholder pending this bead) is replaced by
  `test_health_and_version_are_the_only_UNGATED_routes`, which keeps the
  narrower and still-true claim (these two paths carry no gate) now that
  `test_admin_route_auth.py` owns the complete-route-set pin.

## Lessons

Nothing new generalizes beyond what CLAUDE.md's scar tissue already covers
(#7 IAM envelope, #8 one home for a rule, #9 test-the-tests) -- this bead is
a straight application of patterns the editor and firm bootstrap scripts
already established. The one small departure worth naming: this service's
service account genuinely COULD afford `check_revoked` (unlike the editor
and public backend, which are barred by IAM), and the verifier still leaves
it off for symmetry with its siblings rather than because it is forbidden
here too -- called out explicitly in the module docstring so a future
reader does not assume the same IAM reasoning applies.

## Doc freshness

`docs/components/config-deployment.md` bumped: added
`admin_backend/services/admin_auth.py`, `admin_backend/routes/whoami.py`,
and `scripts/bootstrap_admin_user.py` to its Tracks line, and a paragraph
in the "One image, two services" section describing the gate, the route,
the set test, and the bootstrap script. No dedicated `docs/components/`
page exists yet for the admin service beyond this section; one may be
warranted once more admin routes land in later Epic 1/2 beads.

## Files touched

- `admin_backend/services/admin_auth.py` (new)
- `admin_backend/routes/whoami.py` (new)
- `admin_backend/main.py` (wires the whoami router)
- `admin_backend/tests/unit/test_admin_auth.py` (new)
- `admin_backend/tests/unit/test_admin_route_auth.py` (new)
- `admin_backend/tests/unit/test_admin_health.py` (placeholder test replaced)
- `scripts/bootstrap_admin_user.py` (new)
- `backend/tests/unit/test_bootstrap_admin_cli.py` (new)
- `docs/components/config-deployment.md` (Tracks line + new section, stamp bumped)
- `docs/journal/entries/2026-09-04-bd-7w17m-app-admin-claim.md` (this entry)

Review outcomes recorded in the closeout ping.
