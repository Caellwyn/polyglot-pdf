---
date: 2026-09-09
bead: polyglot-pdf-bo95a
title: "feat(telemetry): E3.5 alert docs with deterministic ids -- link budget exhausted, credit low/exhausted"
sprint: 22
tags: [security, testing]
---

## Trigger

Epic 3 bead 5 of the admin-console program
([plan](../../sprint_22_admin-console_plan.md), "Alerts"). The plan calls for
two telemetry hooks -- a client link hitting its spend ceiling, and a firm's
credit balance crossing a low or zero threshold -- to land as Firestore alert
docs with deterministic ids for dedup, so a repeated trigger (a client
retrying a spent-out link, a firm debiting several times in one day while
already low) does not page an operator once per occurrence. This bead builds
the write path only; the email dispatcher (`POST /admin/alerts/dispatch`) and
the admin-console UI that reads/acknowledges these docs are later beads.

## What shipped

New `backend/services/alerts.py`, the sole writer of the `alerts` collection,
with two public entry points routed through one private `_write` helper:

- `record_link_exhausted(jti, firm_id, spend_usd, ceiling_usd)`, called from
  `backend/services/link_spend.py`'s `check_budget()` in its
  `LinkBudgetExhausted` refusal branch. Doc id `link_exhausted_{jti}`.
  `check_budget` gained an optional `firm_id` keyword purely to label this
  doc (never consulted by the budget decision itself); the one call site
  (`backend/routes/websocket_routes.py`) now passes
  `claims.get("firm_id")`.
- `record_credit_threshold(firm_id, balance, threshold)`, called from
  `backend/services/credit_ledger.py`'s `append_entry()` after a
  `mint_debit` commits (gated on `entry_type`, not on the sign of the
  balance, so a grant/adjustment/refund landing while a firm is still low
  fires nothing new). Two day-keyed doc ids,
  `{firm_id}_credit_low_{YYYY-MM-DD}` and
  `{firm_id}_credit_exhausted_{YYYY-MM-DD}` (UTC calendar day) -- both fire
  when the balance is exactly zero (zero is also at-or-below any positive
  threshold). The threshold is the new runtime-config key
  `CREDIT_LOW_THRESHOLD` (`runtime_config.credit_low_threshold()`, compiled
  default 10, no env fallback -- the same shape as `CREDITS_ENFORCED`).

Design points:

- **Idempotency is a deterministic id plus `set(merge=True)`, not a
  transaction.** This is best-effort telemetry, not money, so the doc's
  existence-check read and its write are two separate Firestore calls: a
  rare same-second lost update on a double-trigger degrades to "the doc
  reflects an earlier crossing instead of the latest one," never a wrong
  balance.
- **Acknowledged/emailed fields are seeded to `None` only on first
  creation.** A read decides whether the doc already exists; if so, the
  three operator/dispatcher-owned fields (`acknowledged_by`,
  `acknowledged_at`, `emailed_at`) are simply omitted from the repeat
  write's payload, so `merge=True` leaves them untouched -- a re-trigger of
  an already-acknowledged alert cannot silently revive it.
- **Never raises into the caller.** `_write`'s whole Firestore path,
  including the `_collection()` call itself, is inside one
  `try/except Exception`. This mattered concretely: the first draft called
  `_collection()` *before* the try block, and the full `test_credit_ledger.py`
  suite caught it -- `get_db()` can raise (a broken firebase_admin app)
  rather than merely return `None`, and that exception propagated straight
  through `append_entry()`. Fixed by moving the call inside the guard, with
  a dedicated regression test (`test_get_db_itself_RAISING_never_propagates`)
  pinning it.
- **Fields carry metadata only** -- `context` holds `jti`/`spend_usd`/
  `ceiling_usd` or `balance`/`threshold`, never a form field value, per
  `docs/standards/hipaa-pii-policy.md` and
  `docs/standards/stateless-architecture.md`.

`firestore.rules` gains a client deny block for `alerts/{alertId}`, folded
into `ADMIN_SDK_ONLY_COLLECTIONS` in the existing set-derived rules test
(`test_firestore_rules_text.py`).

## Fresh-eyes round 1 (post-review fix)

The Opus cross-surface reviewer found a real doc/code mismatch and one
low-severity doc miscount; both fixed, no other findings changed code:

- **Adopted -- `threshold=0` did not behave as its own doc claimed.**
  `record_credit_threshold`'s low-alert branch (`if balance <= threshold`)
  fired even when `threshold == 0`, so an operator who set the threshold to
  zero explicitly to get "only the exhausted alert, no separate low
  warning" (the documented intent in `runtime_config.py`'s
  `KEY_CREDIT_LOW_THRESHOLD` coercion comment and
  `test_credit_low_threshold_accepts_zero`) got BOTH docs anyway, since
  `balance<=0` and `balance<=0` are the same boundary at threshold zero.
  Fixed by gating the low branch on `threshold > 0 and balance <= threshold`
  in `backend/services/alerts.py`; new mutation-verified test
  `test_threshold_ZERO_writes_ONLY_the_EXHAUSTED_doc` in
  `test_alerts_dedup.py` pins it. Docstrings in `alerts.py` updated to state
  the threshold=0 carve-out explicitly instead of the blanket ("threshold is
  a positive credit count") claim the coercion code no longer matched.
- **Adopted -- `docs/technical_guide.md` miscounted the never-had-an-env-var
  keys.** Surface contract 21 called `CREDIT_LOW_THRESHOLD` the "THIRD"
  such key; only `CREDITS_ENFORCED` and `CREDIT_LOW_THRESHOLD` skip
  `_legacy_env_default`'s os.getenv reads (`LINK_MINTING_ENABLED`,
  `LINK_COST_CEILING_USD`, and `LINK_FIRM_CAP` all read env). Corrected to
  "SECOND" and added a one-line pointer to the threshold=0 gating above.
- **Not adopted (observation, not a gap) -- `_alert_on_low_balance`'s
  `TYPE_MINT_DEBIT`-only gating** (a negative `adjustment` entry draining a
  firm to zero fires no alert). This is documented, deliberate design
  matching the bead's stated scope ("after a `mint_debit` commits"); the
  reviewer explicitly declined to file it as a gap, and it is left as-is.

## Outer cross-surface review (post-review fix)

The Opus cross-surface reviewer found one rubric-fail, both halves rooted in
the same gap; two other findings were informational (not adopted as code
changes) and are recorded here for the audit trail:

- **Adopted -- `append_entry`'s alert wiring (`credit_ledger.py:435`) was
  completely unexercised through its real call site.** Every test proving
  the dedup/never-raises properties for the credit-threshold side
  (`test_alerts_dedup.py`) called `alerts.record_credit_threshold(...)`
  directly; `test_credit_ledger.py` had zero references to alerts at all.
  This was the mirror-image gap of the link-budget side, which already had
  three wiring tests through the real `check_budget` caller. Deleting the
  `_alert_on_low_balance(...)` call at `credit_ledger.py:435` left every
  test in the diff green. Fixed by adding three tests to
  `test_credit_ledger.py`, calling the REAL `credit_ledger.append_entry()`
  (not `alerts.record_credit_threshold` in isolation):
  `test_append_entry_fires_the_alert_on_a_LOW_MINT_DEBIT` (a low mint_debit
  through append_entry calls record_credit_threshold with the post-commit
  balance and the configured threshold), `test_append_entry_writes_no_alert_
  doc_when_balance_stays_ABOVE_threshold` (a real fake Firestore store stays
  empty on a debit that stays comfortably above threshold), and
  `test_append_entry_STILL_COMMITS_when_the_alert_write_fails` (the
  check_budget-side "STILL_RAISES" test's mirror -- a broken alert STORE,
  not the public function mocked to raise, must not stop the debit from
  committing or make append_entry raise). All three mutation-verified: the
  first two redden against the two mutations above (dropping the call;
  making the low branch unconditional), the third reddens when alerts.py's
  own `try/except` around the Firestore write in `_write()` is removed.
- **Not adopted -- `credit_low_threshold()` is channel-scoped, but
  `CREDIT_LOW_THRESHOLD` gates a firm-scoped value.** An operator setting
  the threshold for "demo" does not affect "staging". This exactly mirrors
  the pre-existing `credits_enforced(channel=None)` shape this diff did not
  introduce, and is flagged for a later admin-console UI bead to make the
  channel-scoping visible (or reconsider it), not a bug in this diff.
- **Not adopted (same root cause as the first finding, not separate) --
  `alerts.py`'s "safe by construction" claim for `append_entry`'s side was
  asserted-by-inspection rather than integration-tested.** Resolved by the
  same three tests above; no additional code change needed.

## Lessons

A best-effort helper's "never raises" contract must wrap the ENTIRE call
chain to the external resource, not just the calls that look like they can
fail. `_collection()` looked like a cheap accessor (it is, in every sibling
module -- `link_redemptions._collection`, `links_store._collection`) but its
`get_db()` dependency can itself raise rather than degrade to `None`, and a
first draft left exactly that call outside the try block. The bug was
invisible to `test_alerts_dedup.py`'s own fixtures (which mock `_collection`
directly) and surfaced only when the FULL backend suite ran
`test_credit_ledger.py`'s fake-firestore fixture, which does not implement
`firestore.client()`. Lesson for future best-effort wrappers in this family:
put the try block around the resource-acquisition call, not just the
read/write calls that follow it, and verify with a test that makes
`get_db()` itself raise -- not just a test where `_collection()`'s return
value misbehaves.

## Doc freshness

- `docs/components/auth.md` -- Tracks line gained `link_spend.py`,
  `alerts.py`, `runtime_config.py`; changelog entry added, `Last updated`
  bumped to 2026-09-09 (already the correct date).
- `docs/technical_guide.md` -- new Surface contract 21 (telemetry alert
  docs); changelog entry added.
- `docs/components/admin-service.md` and `docs/components/config-deployment.md`
  reviewed -- neither's Tracks line covers the changed backend/services files
  directly, left as-is.

## Files touched

- `backend/services/alerts.py` -- new module, the alerts collection writer.
- `backend/services/link_spend.py` -- `check_budget` gains `firm_id` kwarg
  and calls `alerts.record_link_exhausted` on refusal.
- `backend/services/credit_ledger.py` -- `append_entry` calls
  `alerts.record_credit_threshold` after a `mint_debit` commits, via new
  `_alert_on_low_balance` helper.
- `backend/services/runtime_config.py` -- new `CREDIT_LOW_THRESHOLD` key
  (`RUNTIME_CONFIG_KEYS`, `_ENV_DEFAULTS`, `_coerce`, `credit_low_threshold()`).
- `backend/routes/websocket_routes.py` -- passes `firm_id=claims.get("firm_id")`
  to `check_budget`.
- `firestore.rules` -- deny block for `alerts/{alertId}`.
- `backend/tests/unit/test_alerts_dedup.py` -- new, 18 tests (17 initial +
  1 added in the fresh-eyes fix round, `threshold=0` gating).
- `backend/tests/unit/test_credit_ledger.py` -- 3 new tests added in the
  outer-review fix round, proving `append_entry`'s alert wiring through the
  real call site (see "Outer cross-surface review" above).
- `backend/tests/unit/test_firestore_rules_text.py` -- `alerts` added to
  `ADMIN_SDK_ONLY_COLLECTIONS`.
- `backend/tests/unit/test_runtime_config.py` -- `CREDIT_LOW_THRESHOLD`
  folded into the existing set-derived env-fallback tests, plus dedicated
  default/settable/coercion tests.
- `backend/tests/unit/test_websocket_link_budget.py` -- spy signatures
  updated for the new `firm_id` kwarg, plus an assertion it is passed
  through.
- `docs/components/auth.md`, `docs/technical_guide.md` -- doc updates above.

Review outcomes recorded in the closeout ping.
