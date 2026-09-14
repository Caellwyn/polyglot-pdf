---
date: 2026-09-14
bead: polyglot-pdf-0euzk
title: "feat(credits): firm plan (tier, monthly_credits, rollover) + scheduled monthly top-up to the cap (maintainer: 35 credits/month starting point)"
sprint: 22
tags: [testing, security]
---

## Trigger

Epic 2 follow-up from the maintainer's 2026-09-14 pricing decision: "35
credits per month cap as a starting place; leave room for tiered
subscription levels with different allotments, and pay-as-you-go or
overage later." The bead's job was to model that decision as DATA on the
firm (a `plan` field) plus ONE scheduled top-up route, rather than as a
one-off script or a hardcoded number, so a second tier or overage becomes a
new row/writer later instead of a new code path.

## What shipped

1. **`backend/services/plans.py` (new).** `PLAN_TIERS` (a closed tuple,
   today `("starter",)`), `DEFAULT_PLAN` (`{tier: "starter",
   monthly_credits: 35, rollover: False}`), and `validate_plan()` (refuses
   an unknown tier or a non-positive `monthly_credits` before any write).
2. **`firms/{firm_id}.plan`.** Written on firm create
   (`admin_backend/routes/firm_routes.py::create_firm`, mirroring the
   existing `balance_credits` 0-init), read with a `DEFAULT_PLAN` fallback
   for a doc with none stored (`_public_firm_view`), and backfilled for a
   pre-existing firm by `scripts/backfill_firm_kind.py` (a THIRD
   independent check alongside `kind`/`balance_credits`, gated on `"plan"
   not in firm`).
3. **`PATCH /admin/firms/{firm_id}/plan`.** Validates via
   `plans.validate_plan` before any write, then re-writes the doc through
   `_apply_firm_patch`'s existing transaction. Deliberately NO confirm-twice
   (unlike `kind`) -- a plan change only changes a monthly amount, never a
   minting-eligibility rule, so the bead's own exit criterion says "one
   write per save" is enough.
4. **`credit_ledger.py`'s `subscription_grant` type widened.**
   `USD_REQUIRED_TYPES` shrinks to `{purchase}`; a new `USD_OPTIONAL_TYPES =
   {subscription_grant}` validates `usd_amount` WHEN GIVEN but no longer
   requires it. This is the mechanism that lets the monthly top-up write a
   `subscription_grant` with `usd_amount=None` ("no money moved" -- the
   plan's own words) while a human operator's manual grant
   (`POST .../credits/grant`) still requires it via that route's own,
   UNCHANGED, stricter 422 check. `scripts/grant_credits.py`'s CLI literal
   is likewise unchanged (still the union of both service sets).
5. **`credit_ledger.append_entry()` gains a nullable `period` field**
   (`"YYYY-MM"`), stored as `None` everywhere except the one new caller.
6. **`POST /admin/credits/monthly-topup`
   (`admin_backend/routes/credit_routes.py`).** Gated by
   `require_google_oidc`, the identical factory-closure shape the existing
   hourly sweep route uses, with its OWN Cloud Scheduler identity
   (`MONTHLY_TOPUP_SCHEDULER_SA_EMAIL`, deliberately separate from the
   sweep job's) and its own audience. For every active firm with a plan:
   queries the ledger for an existing `subscription_grant` with the
   current `period` (the WHOLE idempotency mechanism -- a re-run in the
   same month writes nothing); computes the amount (top-up-to-cap for
   `rollover=false`, always-add for `rollover=true`, a negative balance
   brought up to the cap too); writes one `subscription_grant`, audited via
   `append_entry`'s `extra_writes` hook. A per-firm failure is logged and
   skipped, never aborting the whole pass. Mock firms are topped up too
   (staging needs credits).
7. **A reserved, writer-less ledger type**: `TYPE_OVERAGE_PURCHASE =
   "overage_purchase"`, deliberately kept OUT of `ENTRY_TYPES` until Epic
   5's Stripe work actually writes it -- the seam the bead asked for,
   without needing a schema change later.
8. **`scripts/setup-admin-service.sh` + `deploy-admin.sh`**: a second Cloud
   Scheduler declaration (its own SA, `admin-monthly-topup-scheduler-sa`,
   cron `5 0 1 * *` UTC -- offset from the sweep job's hourly trigger so
   the two never race at a month boundary) and the matching
   `MONTHLY_TOPUP_SCHEDULER_SA_EMAIL` env-var wiring into
   `deploy-admin.sh`'s `BACKEND_EXTRA_ENV`, mirroring the sweep job's own
   fix (bd polyglot-pdf-8vgfh finding 3) so the value is re-asserted on
   every deploy rather than a separately erasable hand-run step.
   `deploy-admin.sh` was not on the bead's declared surface list, but
   wiring the new env var through it is a small, mechanical, one-for-one
   mirror of an existing pattern the bead's own text names ("the same
   scheduler identity and pattern as the expired-link sweep") -- without
   it the route would 503 forever in production, so this was decided
   in-scope rather than filed as a separate bead.
9. **Console**: `FirmDetailPage.tsx` gains a plan editor (tier select,
   monthly-credits number input, rollover checkbox) -- one write per Save,
   then a re-read, no confirm-twice. `adminApi.ts` gains `FirmPlan`,
   `PLAN_TIERS`, `DEFAULT_PLAN`, `setFirmPlan`, and `plan: FirmPlan` on
   `FirmRow`/`FirmDetail`.

## Fresh-eyes round 1 (post-review fixes)

The pre-PR cross-surface review found one genuine gap and four nits, all
addressed in this round -- nothing deferred, nothing filed as a separate
bead (all four nits were trivial, in-scope doc/comment fixes rather than
scoped work):

- **ADOPTED (blocker, fixed).** The monthly top-up's idempotency was
  check-then-act, not atomic: `_already_topped_up_this_period` read the
  ledger BEFORE `append_entry`'s own transaction opened, so two
  overlapping invocations (an overlapping Scheduler retry, or two manual
  triggers close together) could both pass that check and both commit --
  a double grant the module's own docstring claimed was impossible. Fixed
  by adding a SECOND, race-safe check INSIDE `append_entry`'s transaction
  itself (`query_period_entries()` + a new `DuplicatePeriodEntry`
  exception, raised before any write): Firestore re-runs a contended
  transaction body on the loser, so the loser's retry sees the winner's
  just-committed `period` row and refuses there, on real state --
  mirroring how `refund_expired_link`'s redemption/status read already
  makes THAT function race-safe. The pre-transaction fast-path check
  stays as a pure optimization (skips a wasted transaction round-trip for
  the overwhelmingly common non-racing re-run) but is no longer what makes
  the guarantee true. Proven with a new staged-concurrency test,
  `test_concurrent_monthly_topups_for_the_same_period_grant_exactly_once`
  (test_credit_ledger.py), built on the same interleaved-transaction fake
  the existing double-mint-race test uses -- mutation-verified by hoisting
  the check back out of the transaction body and watching it double-grant
  again. The existing `test_dropping_the_period_check_breaks_idempotency`
  test was rewritten as `test_dropping_the_fast_path_check_alone_does_not_
  double_grant` (now correctly expects NO double-grant with only the fast
  path disabled, since the transactional layer is a real backstop) plus a
  new `test_dropping_both_period_checks_breaks_idempotency` (stubs the
  shared query helper both checks call, proving the pair together -- not
  either alone -- is what the guarantee rests on). The reviewer's own
  flagged absence of a Cloud Run --concurrency/--max-instances=1
  constraint on the admin service is no longer a live gap once the
  operation is atomic at the data layer -- not added, since the fix
  addresses the race at its actual source rather than papering over it
  with instance-level serialization.
- **ADOPTED (nit, fixed).** A stale file-path reference in a
  `credit_ledger.py` comment (`admin_backend/routes/
  monthly_topup_routes.py`, a file that does not exist -- the real route
  is in `credit_routes.py`, the very file the comment called "bypassed").
- **ADOPTED (nit, fixed).** Corrupted triple-apostrophe artifacts in five
  `adminApi.ts` JSDoc comments (an artifact of the scripted worktree-write
  workflow), cleaned to plain apostrophes.
- **ADOPTED (nit, fixed).** A self-contradicting test docstring in
  `test_backfill_firm_kind_cli.py` (claimed the test "cannot distinguish"
  what its own next line explicitly asserts via an identity check) --
  corrected to describe what the assertions actually prove.
- **REFUTED.** The reviewer's own "checked and it's fine" note on
  `_run_monthly_topup`'s per-firm exception handling (outcome append vs.
  the except block) was independently re-verified by re-reading the
  control flow -- no bug, matches the reviewer's own conclusion.

## Fresh-eyes round 2 (post-review fixes)

The pre-PR outer review found one legitimate blocker-tier gap (a missing
boundary test) plus two low-confidence notes and one pre-existing nit --
one item adopted, the rest refuted or deferred as pre-existing/not
bead-worthy:

- **ADOPTED (blocker, fixed).** `credit_routes.py`'s no-rollover at-cap
  check (`if balance >= monthly_credits:`) had no test pinning the exact
  `balance == monthly_credits` boundary -- every existing scenario used a
  balance strictly under the cap (10) or strictly over it (40), so a
  future one-character `>=` -> `>` regression would ship with all tests
  green, computing `amount = 0`, tripping `credit_ledger._validate`'s
  "amount must be non-zero" `LedgerError` (uncaught by `_topup_one_firm`,
  which only catches `DuplicatePeriodEntry`), and silently miscounting the
  firm as `failed` instead of `skipped_at_cap` in production. Added
  `test_no_rollover_exactly_at_the_cap_is_skipped_not_failed`
  (`admin_backend/tests/unit/test_monthly_topup.py`), seeding
  `balance=35, monthly_credits=35, rollover=False` and asserting
  `skipped_at_cap == ["firm-a"]` with no ledger row. Mutation-verified by
  applying the exact predicted regression (`>=` -> `>`) in a scratch copy:
  the new test went red with precisely the predicted failure mode (a
  `LedgerError` propagating to the generic exception handler, the firm
  landing in `failed` instead of `skipped_at_cap`); reverted, confirmed
  `credit_routes.py` byte-identical to HEAD afterward.
- **REFUTED (no code change).** The reviewer's own boundary-check claim --
  "the current code correctly uses `>=`, not `>`" -- independently
  re-verified by reading `credit_routes.py:447` directly; no bug, matches
  the reviewer's conclusion.
- **DEFERRED (pre-existing, not bead-worthy).** `_public_firm_view`'s
  `plan` fallback checks `isinstance(dict)` only, not key-completeness
  (mirrors the existing `kind` fallback's identical shallow-check
  pattern). Low-confidence, unreachable under every current writer (all
  writers apply either `DEFAULT_PLAN` or a `validate_plan`-gated shape);
  the reviewer's own report explicitly declined to flag it as a gap or
  file a bead for it, and this round agrees it does not warrant one.
- **DEFERRED (pre-existing, confirmed via `git show origin/dev`).**
  `deploy-admin.sh`'s `SWEEP_ENV` variable name also carries
  `MONTHLY_TOPUP_SCHEDULER_SA_EMAIL` and (pre-existing)
  `BACKEND_URLS_JSON` -- a naming nit the reviewer confirmed predates this
  diff (`git show origin/dev:deploy-admin.sh` shows the same
  multi-purpose accumulation already present) and explicitly declined to
  file as a bead given its triviality. Not filed here either -- no new
  bead created this round, since the reviewer's own report already
  classified both remaining notes as non-actionable rather than leaving
  them for this round to pick up.

Full test suites re-run after the fix: `admin_backend/tests/` (556
passed), root `tests/` (1698 passed, 46 skipped), `backend/tests/` (3864
passed, 67 skipped, 3 deselected, 1 xfailed) -- all green, `-m "not
external"`.


## Lessons

- **A "no money moved" grant needs its own validation category, not a
  loosened blanket rule.** The natural first instinct -- drop
  `subscription_grant` from `USD_REQUIRED_TYPES` entirely -- would have
  also let a HUMAN operator's real paid grant through the admin console
  with no dollar figure, silently breaking income tracking there. The fix
  needed a THIRD category (`USD_OPTIONAL_TYPES`: validated when present,
  never required, never refused) distinct from both "always required" and
  "always refused" -- and the human-facing route's own separate,
  UNCHANGED, stricter check is what keeps the loosening invisible to every
  existing caller.
- **`tx.set(..., merge=True)` already preserves fields a patch route never
  names** -- an explicit "preserve the plan field" block written by hand
  for a new field turned out to be dead code once mutation-tested (removing
  it changed nothing), because Firestore's own merge semantics already do
  it. Caught by test-the-tests: a mutation that should have broken
  "does a status-only patch still carry the plan forward" instead passed
  clean, which is the signal the code was never load-bearing in the first
  place.
- **A native HTML5 constraint (`min`/`step` on a number input) can silently
  block a form's own JS validation from ever running in jsdom** -- a test
  asserting the JS error message text went red not because the logic was
  wrong, but because the browser-level constraint intercepted submission
  first. Fixed by dropping the redundant native constraints (the JS check
  already covers the same range), which also made the guard directly
  testable end-to-end rather than only provably-safe-by-inspection.

## Doc freshness

- `docs/components/admin-service.md`: bumped (new dated entry describing
  the plan field, the two new routes, the ledger type split, and the
  console editor).
- `docs/technical_guide.md`: new Surface contract 32; the admin service
  routes table gained two rows (`POST /admin/credits/monthly-topup`,
  `PATCH /admin/firms/{firm_id}/plan}`) to satisfy
  `test_technical_guide_routes_table.py`'s shipped-route guard.
  `technical_guide.md` carries no `*Last updated:*` stamp by design
  (per CLAUDE.md).
- `docs/components/auth.md` is flagged stale by
  `scripts/check_doc_freshness.py` (tracks `backend/services/firms.py`,
  which this bead did not touch) -- pre-existing staleness, left as-is.

## Files touched

- `backend/services/plans.py` (new)
- `backend/services/credit_ledger.py`
- `admin_backend/routes/firm_routes.py`
- `admin_backend/routes/credit_routes.py`
- `scripts/backfill_firm_kind.py`
- `scripts/setup-admin-service.sh`
- `deploy-admin.sh`
- `admin-console/src/utils/adminApi.ts`
- `admin-console/src/pages/FirmDetailPage.tsx`
- `admin_backend/tests/unit/test_monthly_topup.py` (new)
- `backend/tests/unit/test_plans.py` (new)
- `tests/test_setup_admin_service_monthly_topup_scheduler.py` (new)
- `admin_backend/tests/unit/test_firm_routes.py`
- `admin_backend/tests/unit/test_admin_route_auth.py`
- `admin_backend/tests/unit/test_admin_audit_coverage.py`
- `backend/tests/unit/test_credit_ledger.py`
- `backend/tests/unit/_fake_firestore.py` (fresh-eyes round: where()/get(transaction=) support)
- `backend/tests/unit/test_backfill_firm_kind_cli.py`
- `backend/tests/unit/test_grant_credits_cli.py`
- `tests/test_deploy_admin_sweep_env_vars.py`
- `admin-console/src/pages/FirmDetailPage.test.tsx`
- `admin-console/src/pages/FirmsPage.test.tsx`
- `admin-console/src/pages/UsagePage.test.tsx`
- `docs/components/admin-service.md`
- `docs/technical_guide.md`

Review outcomes recorded in the closeout ping.
