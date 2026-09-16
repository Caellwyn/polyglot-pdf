---
date: 2026-09-15
bead: polyglot-pdf-hnlj3
title: "feat(credits): credits roll over by default; factor topup_firm() so a Stripe webhook can call it later (maintainer 2026-09-15)"
sprint: 22
tags: [refactor, testing]
---

## Trigger

Maintainer decision 2026-09-15, made the day after bd polyglot-pdf-0euzk
shipped the firm plan + monthly top-up mechanism: "credits roll over -- no
real reason not to." The 2026-09-14 pricing decision had launched with
`rollover: False` (a use-it-or-lose-it cap) as the default for a new or
backfilled firm; the maintainer's follow-up flips that default without
changing the underlying mechanism, which 0euzk already built to support
both values. The same conversation named the monthly top-up's real future
trigger: Epic 5's Stripe payment webhook (invoice.paid / subscription
renewal) will eventually call the top-up per firm at the moment a payment
clears, rather than only on the Cloud Scheduler's fixed monthly date --
this bead's second half factors the per-firm grant logic into a standalone
function so that webhook has something to call without duplicating the
grant/idempotency logic.

## What shipped

1. **`backend/services/plans.py`'s `DEFAULT_PLAN.rollover` flips from
   `False` to `True`.** A firm created via `admin_backend/routes/
   firm_routes.py`'s create route, or backfilled by
   `scripts/backfill_firm_kind.py` for a pre-existing firm with no stored
   `plan`, now accumulates its monthly credit allotment by default instead
   of being topped up TO a cap. `rollover: False` remains a fully valid,
   settable value via `PATCH /admin/firms/{firm_id}/plan` for a firm that
   should keep the old cap behavior -- only the DEFAULT changed, not the
   mechanism. The one existing firm at the time (staging-mock) had already
   been switched to rollover by hand on 2026-09-15, ahead of this code
   change, so the stored data and the new code default agree.

2. **`topup_firm(db, firm_id, firm, *, period, actor=None)`** is a new,
   directly-callable function in `admin_backend/routes/credit_routes.py`,
   factored out of the monthly top-up route's per-firm loop (previously an
   inline, underscore-prefixed helper). It is the SAME logic, unchanged in
   behavior -- validates the firm's plan, checks the two-layer idempotency
   guard, computes the grant amount for rollover vs. no-rollover, and
   writes the `subscription_grant` via `credit_ledger.append_entry` with
   an in-transaction audit row. The ONE addition is an `actor` parameter,
   defaulting to the route's existing `MONTHLY_TOPUP_ACTOR` constant so
   the Cloud Scheduler route's own call site needed no change. This is the
   seam Epic 5's Stripe webhook will call directly for one firm (passing
   its own actor string, e.g. `"system:stripe_webhook"`), instead of
   waiting for the monthly cron pass -- the route's own module docstring
   now states explicitly that the Cloud Scheduler trigger is INTERIM.

3. **Tests updated for the new default, plus a new test pinning it
   directly.** `backend/tests/unit/test_plans.py`'s
   `test_default_plan_is_the_maintainers_starting_numbers` now asserts
   `rollover: True`; `backend/tests/unit/test_backfill_firm_kind_cli.py`'s
   two tests that assert `DEFAULT_PLAN`'s exact shape were updated the
   same way (tests seeding an EXPLICIT pre-existing plan with
   `rollover: False`, to prove it survives a re-run untouched, were left
   as-is -- those pin preservation, not the default).
   `admin_backend/tests/unit/test_monthly_topup.py` gained a new test,
   `test_a_firm_on_the_actual_default_plan_rolls_over`, which is the ONE
   test in that file that seeds a firm with `plans.DEFAULT_PLAN` itself
   (dict-copied) rather than a hand-written plan literal -- every other
   scenario in that file deliberately hand-writes its own plan dict so a
   future default change cannot silently alter what those prove; this new
   test is what actually pins "a firm with no plan editor visit rolls
   over." All three touched/new assertions were mutation-verified: flipping
   `DEFAULT_PLAN.rollover` back to `False` reddens all three.

4. **`admin-console/src/utils/adminApi.ts`'s own `DEFAULT_PLAN` mirror**
   (a TypeScript constant kept byte-identical to the Python one, used as a
   documented fallback shape) was updated the same way -- not itself
   consumed by any render path today (`FirmDetailPage.tsx` reads the live
   plan off the `GET /admin/firms/{firm_id}` response, never this
   constant), but left stale it would have silently disagreed with the
   backend default the next time something reads it. Not in the bead's
   declared surfaces list; fixed anyway as the same class of DEFAULT_PLAN
   mirror the backend tests above needed, per CLAUDE.md's "enumerate the
   set before fixing any of it."

5. **`FirmDetailPage.tsx`'s existing rollover checkbox label ("Rollover
   (add, don't cap)") was checked and found already correct** -- it
   describes what the checkbox does, not a claim about which value is the
   default, so nothing needed changing there despite the bead naming this
   file as a surface for the "cap" wording correction.

6. **Docs.** `docs/technical_guide.md`'s Surface contract 33 gained a note
   that "cap" is no longer the right general word for `monthly_credits`
   now that rollover is the default (the maintainer's own 2026-09-14 quote
   is left as a direct quotation, not edited), updated its `DEFAULT_PLAN`
   example to `rollover: True`, and documented `topup_firm()` plus the
   Stripe-webhook-is-the-real-future-trigger rationale.
   `docs/components/admin-service.md` gained a new dated entry recording
   the same change. `scripts/backfill_firm_kind.py`'s own docstring
   (a comment, not logic -- the script reads `plans.DEFAULT_PLAN` directly
   and needed no code change) was updated to match.

## Lessons

Confirmed again: a "flip one default" bead is rarely one line. The actual
touched-file count was nine, not one, because `DEFAULT_PLAN`'s exact shape
is asserted in five separate places (two Python test files, one TS
constant, two docstrings) -- exactly CLAUDE.md scar #8's shape ("enumerate
the set before fixing any of it"). Grepping for `DEFAULT_PLAN` across the
whole worktree up front (rather than only the bead's own declared
surfaces list) is what caught `test_plans.py` and `adminApi.ts`, neither
of which the bead's `Surfaces` metadata named.

## Doc freshness

`docs/technical_guide.md` (no stamp, current-state by design) and
`docs/components/admin-service.md` (Tracks line covers
`admin_backend/routes/credit_routes.py`; stamp bumped to 2026-09-15) both
updated. `docs/sprint_22_admin-console_plan.md` was checked and contains
no rollover/cap language predating this decision to correct.

## Files touched

- `backend/services/plans.py` -- `DEFAULT_PLAN.rollover` False -> True, docstring updated.
- `admin_backend/routes/credit_routes.py` -- `_topup_one_firm` renamed/extracted to public `topup_firm(db, firm_id, firm, *, period, actor=None)`; module docstring gains the "Scheduler trigger is interim" note.
- `backend/tests/unit/test_plans.py` -- default-shape assertion updated to `rollover: True`, mutation-verified.
- `backend/tests/unit/test_backfill_firm_kind_cli.py` -- two DEFAULT_PLAN-shape assertions updated, mutation-verified.
- `admin_backend/tests/unit/test_monthly_topup.py` -- new test `test_a_firm_on_the_actual_default_plan_rolls_over`; renamed references to `topup_firm`.
- `admin-console/src/utils/adminApi.ts` -- `DEFAULT_PLAN` TS mirror updated to `rollover: true` (not a declared bead surface; fixed as the same DEFAULT_PLAN-mirror class).
- `scripts/backfill_firm_kind.py` -- docstring's DEFAULT_PLAN example updated (no logic change).
- `docs/technical_guide.md` -- Surface contract 33 updated: cap-wording note, DEFAULT_PLAN example, topup_firm() + interim-Scheduler documentation.
- `docs/components/admin-service.md` -- new 2026-09-15 dated entry.
