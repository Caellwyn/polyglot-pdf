# Sprint 24 -- Stripe billing, overage, and margin reports (admin console Epic 5)

**Epic:** `polyglot-pdf-m5exr`
**Approved:** 2026-09-23 (maintainer, in-session: first draft 2026-09-17, revised the same week after the maintainer's answers, approved as revised)
**Beads filed:** 2026-09-23 -- 5.1a `2c0kn`, 5.1b `6sezh`, 5.2 `7q77g`, 5.3 `65sra`, 5.4 `v56ef`, 5.5 `jnxg9`, 5.6 `cf2mx`, 5.7 `gf8ne`, 5.8 `t1s4g`; plan doc `33fst`. Head of the epic (start here): `polyglot-pdf-2c0kn`. The maintainer asked (2026-09-23) that no child be claimed until the beads tracker has finished moving to its new server; the maintainer starts the first session on the head bead.
**Program plan:** [`sprint_22_admin-console_plan.md`](sprint_22_admin-console_plan.md), section "Epic 5" -- this document is that epic's own `/plan-epic` pass and supersedes the outline there.

---

## Why

Firms pay for credits, but today credits come only from operator grants and the interim monthly scheduler. Firm managers need to subscribe and buy credits without the maintainer in the loop, the monthly allotment should follow a real payment rather than a clock, and the maintainer needs to see whether the product makes money per firm and per form. Everything this epic builds on already exists: the ledger with typed entries and a per-firm balance (Surface contract 18), the per-firm plan (contract 33), the income view (contract 25) and the cost reports (contract 29).

## Decisions (maintainer, 2026-09-23 -- do not relitigate)

1. **Overage is in scope now.** "Better to get it addressed now than let it sit there and possibly get forgotten." A firm whose plan carries an overage price keeps minting at zero balance; each overage form records an `overage_purchase` ledger entry at the plan's overage price beside the `mint_debit`. This narrows the program plan's "a firm at zero is REFUSED" rule to "refused at zero unless the plan allows overage". Billing the overage entries through Stripe is its own bead, blocked until a Stripe account exists; the mechanics, the ledger record and the visibility ship now.
2. **The interim scheduler stays** for manually billed firms (pilots, comped firms). Each firm carries a billing source (`manual` | `stripe`); the scheduler skips Stripe-billed firms and the webhook grants only to them.
3. **One Stripe mode per admin service.** The admin service serves both channels with one key set. Test mode until the first paying firm, then a key rotation. The maintainer's intended model for test firms is a Stripe **sandbox** account whose webhooks carry the same protocol as the live account; the webhook therefore accepts events from whichever account's signing secret the environment holds, and the code does not distinguish sandbox from live.
4. **Margin counts token cost only.** Per-firm margin is income minus model cost from the usage events; hosting is excluded from margin entirely.
5. **Pricing.** Starter: **$500 per month for 50 forms, $15 per overage form**. The starter plan's `monthly_credits` moves from 35 to 50 (the mock firm's stored plan is updated by the foundation bead). Rollover stays on, as decided 2026-09-15.
6. **Stripe setup is deferred.** No account, products, prices, webhook endpoint or keys are created in this sprint. Everything Stripe-shaped is built and proven without them: the webhook is verified on staging with a signing secret the project owns (the same HMAC scheme Stripe uses), and the checkout and portal actions ship behind a runtime flag (`app_config` key `BILLING_ENABLED`, default false) that renders "billing not yet available" until the account is configured. Going live is then a secret rotation plus flipping the flag, not a code change.

Planner decisions (reversible, mine): the monthly grant keys on the **paid invoice** event, not the checkout event (a subscription fires checkout once and an invoice every period, including the first; handling both double-grants); idempotency keys on the **Stripe event id** through a `stripe_events/{event_id}` processed-events record checked inside the same transaction as the grant, with the event id also stored on the ledger entry (the ledger's existing month `period` key cannot represent a redelivered event or a billing cycle that straddles months); refunds get their own `refund` entry type with a negative dollar amount (adjustments carry no dollars by design, so a refund recorded as one would overstate income); the webhook reads the **raw request body** for signature verification (a parsed body loses byte fidelity); prices are resolved by Stripe **lookup key** equal to the tier name so no environment carries hard-coded price ids; nothing in the webhook path logs customer email or payment details (uids and ids only, per `docs/standards/hipaa-pii-policy.md`).

## Exit rubric

| # | Criterion | Verify |
|---|---|---|
| 1 | With credit enforcement on, a zero-balance firm whose plan allows overage mints a link and its ledger shows an `overage_purchase` entry at the plan's overage price plus the `mint_debit`; a firm whose plan has no overage price is still refused (402). | Mock firm on staging at balance 0 with overage enabled: mint succeeds, ledger rows present. Overage disabled: mint refused with 402, no rows. |
| 2 | A signed paid-invoice event grants the subscription's credits exactly once per billing period; a resend of the same event grants nothing; an unsigned or tampered event is refused and writes no ledger, audit or event row; the monthly scheduler skips Stripe-billed firms. | Signed synthetic events (project-owned signing secret) posted to staging's webhook; the firm's ledger; a scheduler dry run listing the firm as skipped. |
| 3 | A firm manager's Billing page shows balance, plan (allotment, price, overage price), this month's overage count and amount, and recent ledger rows; the subscribe and buy actions are visible but disabled with an explanation while billing is off. | Sign in as the mock firm's manager on staging and open the page. |
| 4 | The Cost & income page shows per-firm margin as income minus token cost for a month range and exports the table as CSV; mock firms never appear in income. | Open the page and download the CSV after a synthetic purchase entry on a live-kind test firm; the income view definition keeps its hard-coded `firm_kind = 'live'` filter. |
| 5 | No signing secret or API key appears in code or logs, and the webhook route is present in every route set test (route-auth, audit-coverage, routes-table). | The CI secret scan; the three set tests. |

Rubric changes, if any, are recorded on the epic bead with the reason.

## Bead tree

Every child declares its `metadata.surfaces` (the collision guard keys on them), carries a `## Exit criteria` section inheriting at least one rubric criterion, and is wired parent-child to `polyglot-pdf-m5exr`. Ordering edges are plain blocks edges.

| Bead | Title | Surfaces | Inherits | After |
|---|---|---|---|---|
| 5.1a `2c0kn` | Plans and ledger foundation | `backend/services/plans.py`, `backend/services/credit_ledger.py`, `backend/services/firms.py`, `firestore.rules`, `backend/tests/unit/test_credit_ledger.py`, `backend/tests/unit/test_plans.py`, `backend/tests/unit/test_firestore_rules_text.py`, `scripts/backfill_firm_kind.py`, `docs/technical_guide.md` | 1, 2 | -- (first) |
| 5.1b `6sezh` | Overage mint path | `backend/routes/link_routes.py`, `backend/services/alerts.py`, `backend/tests/unit/test_link_routes.py`, `backend/tests/unit/test_alerts.py`, `frontend/src/console/MintLinkPage.tsx`, `docs/components/link-routes.md` | 1 | 5.1a |
| 5.2 `7q77g` | Webhook with the subscription path | `admin_backend/services/admin_auth.py`, `admin_backend/services/stripe_client.py`, `admin_backend/routes/billing_webhook.py`, `admin_backend/main.py`, `admin_backend/routes/credit_routes.py`, `deploy/channels/admin.env`, `backend/requirements.txt`, `admin_backend/tests/unit/`, `docs/runbooks/stripe-go-live.md`, `docs/components/admin-service.md` | 2, 5 | 5.1a |
| 5.3 `65sra` | Remaining webhook events | `admin_backend/routes/billing_webhook.py`, `admin_backend/services/stripe_client.py`, `admin_backend/tests/unit/test_billing_webhook.py`, `docs/components/admin-service.md` | 2 | 5.2 |
| 5.4 `v56ef` | Billing routes | `admin_backend/routes/billing_routes.py`, `admin_backend/main.py`, `admin_backend/tests/unit/test_billing_routes.py`, `docs/technical_guide.md` | 3 | 5.2 |
| 5.5 `jnxg9` | Firm console Billing page | `frontend/src/console/BillingPage.tsx`, `frontend/src/console/adminApi.ts`, `frontend/src/App.tsx`, `frontend/src/console/*.test.tsx`, `docs/components/firm-console.md` | 3 | 5.4 |
| 5.6 `cf2mx` | Admin console billing view | `admin-console/src/pages/FirmDetailPage.tsx`, `admin-console/src/utils/adminApi.ts`, `admin_backend/routes/firm_routes.py`, `admin-console/src/pages/FirmDetailPage.test.tsx` | 1 | 5.1a |
| 5.7 `gf8ne` | Margin report and CSV | `sql/telemetry_views.sql`, `admin_backend/services/bigquery_reports.py`, `admin_backend/routes/report_routes.py`, `admin-console/src/pages/CostReportsPage.tsx`, `backend/tests/unit/test_telemetry_views.py`, `admin_backend/tests/unit/test_report_routes.py` | 4 | 5.1a |
| 5.8 `t1s4g` | Bill overage through Stripe | `admin_backend/services/stripe_client.py`, `admin_backend/routes/credit_routes.py`, `admin_backend/tests/unit/` | 1 | 5.3, and the Stripe account (maintainer) |

MECE check: no two children share a write surface except the two webhook beads, which are sequenced (5.3 after 5.2) and the two `admin_backend/main.py` router registrations (5.2 then 5.4, sequenced); every rubric criterion is inherited by at least one child; no "etc." items. Parallelizable after 5.1a: 5.1b, 5.2, 5.6, 5.7. Then 5.3 and 5.4; then 5.5.

## Out of scope

- Creating the Stripe account, products, prices, webhook endpoint, sandbox account or keys (deferred by the maintainer; the go-live runbook written by 5.2 lists the exact steps).
- Tax, invoicing PDFs, multi-currency, per-seat pricing, tiers beyond `starter` (the tier table is data; adding a tier is a row).
- Customer Portal customisation beyond linking to it.
- Any change to the mint refusal rule beyond the overage exception above.
- The product pivot under consideration since 2026-09-11 (undecided; not assumed here).

## Verification (epic level)

Each rubric row above is the gate. Program-level: staging first, always -- the overage mint, the synthetic webhook events, the Billing page and the margin page are each proven on staging against the `kind: mock` firm before any demo deploy; every deploy remains its own per-instance ask.
