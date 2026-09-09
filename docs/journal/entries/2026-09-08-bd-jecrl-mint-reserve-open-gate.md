---
date: 2026-09-08
bead: polyglot-pdf-jecrl
title: "feat(links): A3 mint reserves the credit before signing; open requires a mint record; live firms only on demo"
sprint: 22
tags: [security, testing]
---

## Trigger

Epic 2 Track A bead A3 of the admin-console program
([`docs/sprint_22_admin-console_plan.md`](../../sprint_22_admin-console_plan.md),
sections "Mint transaction" and "Open requires a mint record"). A1 laid the
`links[_<channel>]/{jti}` mint-record collection and the firm `kind`/balance
schema, A2 landed the one transactional ledger helper, A4 taught the token to
carry `cap_usd`. All three were unwired: nothing called `record_mint()` from a
route, nothing debited a firm, and `cost_ceiling_usd_for_claims` documented a
safety property ("every token that CAN open already carries `cap_usd`") that
depended on a gate this bead had to build.

The maintainer's revision of the plan (same day it was approved) set the
ordering constraint that shapes everything here: **reserve the credit BEFORE
signing the token**, because a refused mint that still returns a signed token
hands out a paid Gemini session nobody was charged for.

## What shipped

**Mint: `new_jti()` -> one transaction -> sign.** The transaction is A2's
`credit_ledger.append_entry()` -- the repo's one writer of `balance_credits` --
with the `links/{jti}` mint record passed through its `extra_writes` hook, so
the balance, the `mint_debit` entry and the record commit together or not at
all. A refusal leaves no token, no entry, no record.

**Two staff-facing refusals, deliberately not the uniform 404.** The
uniform-refusal rule exists so the UNAUTHENTICATED `/open` cannot be used as an
oracle for which links and firms exist. The mint door is authenticated staff and
already knows which firm is calling, so hiding the reason only costs the console
a useful message. `403` for a live (or kindless) firm off the demo channel;
`402` for insufficient credits under `CREDITS_ENFORCED`; `503` for a deployment
fault.

**The channel gate reads `os.environ["LINK_CHANNEL"]` raw, not
`link_tokens.link_channel()`.** This is the subtlest decision in the bead and it
comes straight from the plan. `link_channel()` defaults to `demo` so an
unconfigured deploy keeps minting and opening the links it already has -- which
means asking it would make an *unset* channel (a laptop, a one-off container, a
misconfigured revision) look like the demo and let it debit a paying firm.
Reading the env var raw means `demo` has to be written down somewhere before
real money moves. Both halves are load-bearing: an unset channel still mints
`aud=demo` tokens for **mock** firms, while refusing live ones. A firm with no
`kind` at all counts as live, the same fail-closed polarity `firms.firm_kind()`
already uses.

The gate runs INSIDE the transaction, off the same firm snapshot the balance
comes from, so a firm flipped mock -> live between two separate reads cannot slip
one mint through.

**New `backend/services/kit_commercials.py`** reads the `kits/{kit_id}`
commercial doc for `credit_cost` and `burn_cap_usd`. Fail-soft in ONE direction:
a missing doc, an unreachable store or a malformed value resolves to the global
defaults, never to "free" and never to "no ceiling". `burn_cap_usd` funnels
through `link_budget.cost_ceiling_usd_for_kit()` so a bad commercial value fails
exactly the way a bad kit-metadata value does -- one parsing rule for "a spend
ceiling read from outside `link_budget`", not two that could drift. The read
sits deliberately OUTSIDE the transaction: both numbers have safe defaults, and
refusing every demo mint because one pricing doc was slow would trade a real
outage for a rounding error.

**Open requires the record, and the check lives in the shared gate.**
`link_redemptions.enforce_link_redemption` is the one helper every door that
SPENDS already calls, so `/api/links/open`, `/ws/fill` and
`require_paid_client_work` inherit the refusal from one place. It reads
`links[_<channel>]/{jti}` and raises the new `LinkNotMinted` for a missing
record or one whose status is `revoked`/`refunded`; every other status falls
through to the existing redemption gate, so reopening an unfinished link still
works.

Three details there carry weight, and each was chosen against a specific
failure:

- **It runs FIRST, before `open_link()`** creates the redemption doc. Checking
  after would stamp `opened_at` on a link about to be refused.
- **`LinkNotMinted` subclasses `RedemptionUnavailable`.** The socket gate and
  `require_paid_client_work` both catch a tuple that already names the base
  class, so a door someone adds later, catching only that, still fails closed. A
  brand-new exception type would have sailed past those handlers as an unhandled
  error.
- **An unreachable links store RAISES** rather than reading as "no record". Both
  refuse, but the raise keeps the two causes distinguishable in the log.

A successful open then best-effort mirrors the record to `opened` for the
console's link table. That mirror never raises and only ever moves `minted` ->
`opened` -- it is a derived cache, and the authoritative answer to "was this
opened" stays the redemption doc, which is what A5's refund transaction will
read.

**Cutover, deliberate:** tokens minted before the record existed cannot open.
The maintainer re-mints any outstanding link (listed in the plan's maintainer
calls).

**Deferred, unchanged:** `record_mint` (the monthly per-firm counter) keeps
running after commit -- it answers a different question and the plan explicitly
does not delete it in this epic. The refund/revoke/sweep writers that transition
`status` are A5's.

## Lessons

**A shared fake with real semantics belongs in one file the moment it has two
callers.** `test_credit_ledger.py`'s fake Firestore models the two things a dict
does not -- writes buffered until commit, and a body re-run on contention -- and
those semantics are exactly what makes "nothing was committed" a real assertion
rather than a tautology. When the mint route became a second driver of the same
transaction, copying it would have let one caller's tests pass against semantics
the other did not have. Extracted to `backend/tests/unit/_fake_firestore.py`
instead.

Two gaps the extraction exposed, both real: the fake had no `update()` (the
opened mirror relies on the real client's refusal to conjure a missing doc) and
no `Increment` (so the per-firm mint counter had been silently landing in its own
fail-soft except branch in every test that ran it -- asserting against a code
path production never takes).

**A test that stubs the shared helper reintroduces the bug the file was written
to catch.** `test_link_redemptions.py` exists because every earlier test
monkeypatched `open_link` at its call site, so the real function never ran.
Adding the mint-record gate to the same helper created the identical temptation
one layer up -- stub `_require_mint_record` and the tests go green. Stubbing
`links_store.get_link` instead keeps the gate itself executing.

**Injecting a failure at a shared helper tests the wrong thing.** The first
version of "a failed mirror write must not refuse the client" patched
`links_store._collection`, which also broke the gate's read -- so the 404 it saw
was the gate failing closed (correct) rather than the mirror leaking (the bug
being pinned). The test passed for the wrong reason until the failure was moved
to the write itself.

**Verify the mutation actually bites.** Of 28 mutations run against the new
tests, 27 came back red immediately. The one green was `amount=-int(credit_cost)`
-> `amount=-1` on a journey whose kit costs exactly 1 credit -- a no-op edit, not
a vacuous test. Re-running at `-2` reddened 9 tests. A green mutation result is a
question, not a verdict.

## Doc freshness

- [`docs/doctrine/promotion-tiers.md`](../../doctrine/promotion-tiers.md) --
  bumped. Its claim that firm-billing isolation "rests on staging using its own
  mock firm, not on code" is now false; the channel gate makes it a code
  property. Rewritten with the raw-env-var reasoning and the unset-channel case.
- [`docs/components/auth.md`](../../components/auth.md) -- bumped. New section
  for the mint order, the refusal codes, the channel gate and the open gate;
  corrected the A4 and A1 paragraphs, which described this bead in the future
  tense; added `kit_commercials.py` and `link_routes.py` to **Tracks:**.
- [`docs/technical_guide.md`](../../technical_guide.md) -- new Surface contract
  19 (producer/consumer for the whole path), plus the two contracts this bead
  made stale: 16's "not wired to anything yet" and 9's description of what the
  shared redemption helper checks.
- Reviewed and left as-is: `websocket-routing.md`, `ws-protocol.md`,
  `hipaa-pii-policy.md`, `stateless-architecture.md`, `risk-rating.md`,
  `voice-and-vad.md`, `admin-service.md`, `config-deployment.md`. They track
  `websocket_routes.py` / `auth.py`, whose changes here are comment-only.
- No CLAUDE.md change.

Review outcomes recorded in the closeout ping.

## Files touched

- `backend/services/kit_commercials.py` (NEW) -- the `kits/{kit_id}` commercial
  reader, fail-soft to the global defaults in one direction only.
- `backend/services/links_store.py` -- split `record_mint()` into
  `build_mint_record()` + the plain write; added `mint_record_ref()` for the
  transaction, `OPEN_BLOCKING_STATUSES`, and `mark_opened()`.
- `backend/routes/link_routes.py` -- reserve-then-sign in `mint_link`,
  `_reserve_mint`, `_live_firm_channel_ok`, `MintRefused`; the `LinkNotMinted`
  branch and the opened mirror in `open_client_link`.
- `backend/services/link_redemptions.py` -- `LinkNotMinted`,
  `_require_mint_record`, and its call at the top of
  `enforce_link_redemption`.
- `backend/services/auth.py`, `backend/routes/websocket_routes.py` -- comments
  only: why the existing except-tuples already catch the new refusal.
- `backend/tests/unit/_fake_firestore.py` (NEW) -- the shared buffer-and-retry
  fake, extracted from `test_credit_ledger.py`, plus `update()` and
  `Increment`.
- `backend/tests/unit/test_link_routes.py` -- a real fake Firestore in the
  fixture; the reservation and open-gate suites.
- `backend/tests/unit/test_link_redemptions.py` -- the `minted` fixture and the
  gate's own refusals.
- `backend/tests/integration/test_websocket_ephemeral.py` -- one
  `_stub_link_gates` helper replacing six inline copies; the socket's own
  no-mint-record refusal test.
- `backend/tests/integration/test_client_link_journey.py` -- a real-HTTP mint ->
  open walk, the only test that proves the record the mint writes is the record
  the gate reads.
- `backend/tests/unit/test_credit_ledger.py`,
  `backend/tests/unit/test_websocket_link_budget.py` -- rewired to the shared
  fake / the new gate.
- `docs/doctrine/promotion-tiers.md`, `docs/components/auth.md`,
  `docs/technical_guide.md`.
