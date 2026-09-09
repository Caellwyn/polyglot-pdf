---
date: 2026-09-08
bead: polyglot-pdf-1op3g
title: "feat(credits): A5 refund on unopened expiry keyed on the redemption doc; lazy reconciliation on balance reads"
sprint: 22
tags: [security, testing]
---

## Trigger

Epic 2 Track A bead A5 of the admin-console program
([plan](../../sprint_22_admin-console_plan.md), "Refund on unopened
expiry"). A firm's credit is debited at MINT time (the future A3), before
any client opens the link -- so a link that expires unopened must give the
credit back, or firms pay for links nobody ever touched. This bead is that
refund path: one transactional helper plus the lazy per-firm catch-up a
balance read runs before showing a number that might be stale because the
hourly sweep (Track B bead B5) has not run yet.

## What shipped

**`credit_ledger.refund_expired_link(db, jti, *, actor, channel=None,
now=None)`.** One transaction, reads-before-writes: first
`link_redemptions[_<channel>]/{jti}` -- the AUTHORITATIVE record a client's
first open writes -- and refuses on its existence ALONE, regardless of what
the doc contains. This is the bead's central design point: `links/{jti}`
also carries a `status` field that the open route best-effort-MIRRORS to
`"opened"`, and that write can fail even though the real open succeeded. If
the refund gate trusted the mirror, a failed mirror write would refund a
link a client is actively filling out. So the gate reads the doc a client's
open ACTUALLY writes, never the label that merely reflects it. Second read
is `links[_<channel>]/{jti}`, proceeding only from `status == "minted"` --
every other status (including `refunded`) refuses, which is what makes a
second run, or a sweep and a lazy reconcile racing on the same jti, a no-op
rather than a double credit.

The write half is NOT a new implementation: `append_entry()`'s body was
split into a new `_apply_entry_writes()` helper that both `append_entry`
and `refund_expired_link` call, so a refund's ledger entry
(`type=expiry_refund`, `amount=+credit_cost` reversing the exact snapshot
taken at mint) is bit-for-bit the same shape as a grant, a purchase, or a
debit. The links record's `status=refunded` flip joins the SAME
transaction via the existing `extra_writes` hook, so a refund can never
credit the firm while leaving `status=minted` for the next sweep pass to
hit again.

**`reconcile_expired_for_firm(firm_id, channel=None, now=None)`.** The lazy
half: queries `links[_<channel>]` for one firm's `status == "minted"` and
`open_deadline < now` (using `FieldFilter`, matching the one other query
call site in this repo, `confirmation_logger.py`, rather than the
deprecated positional `.where()`), and calls `refund_expired_link()` once
per hit. A per-link `LinkNotRefundable` (a race the sweep already won) is
logged and skipped, never raised past the loop -- a lazy pass riding a
balance read must not turn "one link had a race" into a 500 on that
balance page. Not wired into an admin-service route in this bead (Track B
owns those routes); the plan is explicit that it must NEVER be called from
the mint transaction, which does not exist as production code yet either
(A3 is still open) -- so exit criterion 3 is pinned against `append_entry()`
itself, the shared helper A3 will compose its mint transaction on: one test
asserts its transaction's read set is exactly the firm doc, and a second,
AST-walk test asserts neither `append_entry` nor `_apply_entry_writes` ever
calls `reconcile_expired_for_firm`. Together these hold regardless of what
shape A3's own mint route eventually takes.

**Socket teardown mirror.** `LinkBudgetExhausted`'s except block in
`websocket_routes.py` now writes a best-effort, never-raising
`links[_<channel>]/{jti}.status = "budget_exhausted"` via
`links_store._collection()`, off the event loop. Telemetry only -- no
ledger entry -- because whether a budget-exhausted link earns a refund,
and whether a replacement link (bd `polyglot-pdf-1uyof`) costs a fresh
credit, are both maintainer pricing calls the plan lists as undecided.

**Deliberately NOT in this bead:** the hourly sweep endpoint
(`POST /admin/links/sweep-expired`, Track B bead B5) and its Cloud
Scheduler wiring; wiring `reconcile_expired_for_firm` into an actual
admin-service or firm-console route (also Track B/C); any decision on
budget-exhausted or opened-but-abandoned refunds (both maintainer calls,
assumed "no" per the plan).

**Fresh-eyes review round -- adopt/reject/defer.** All three exit criteria
were confirmed PASS (mutation-verified independently by the reviewer). Two
blockers, adopted:

- ADOPTED: `refund_expired_link` never called `_validate()` -- unlike every
  other ledger entry path, a blank or malformed `actor` would silently
  commit an unattributable ledger entry. Fixed by calling `_validate()`
  inside the transaction body once `credit_cost` (the entry's `amount`) is
  known from the links record, still before any write. New pinning test:
  `test_refund_refuses_a_blank_actor`. Mutation-verified (deleting the
  `_validate` call reddens it).
- ADOPTED: the second `ledger_export` producer (`refund_expired_link`'s own
  `_log.info` call) was not pinned against `LEDGER_EXPORT_FIELDS` --
  `append_entry`'s producer was pinned, this one was not, which is exactly
  the "enumerate the set" trap CLAUDE.md's scar tissue #8 names. New
  pinning test: `test_refund_export_line_carries_exactly_LEDGER_EXPORT_FIELDS`.
  Mutation-verified (dropping `usd_amount` from the call reddens it).

Two nits, deferred (filed as `bd polyglot-pdf-sw2lv`, not fixed in this
diff per the closeout rule that nits are not fixed inline):

- DEFERRED: `test_the_refund_and_the_status_flip_commit_ATOMICALLY`'s
  docstring claims a negative-injection proof ("making the joined write
  explode") the test body does not perform (it asserts only the positive
  case). The test still correctly catches the mutation it names; this is a
  stale docstring, not a coverage gap.
- DEFERRED (not this bead's own finding, but surfaced by the reviewer and
  carried into the same nits bead for one-place tracking): the pre-existing
  `bd polyglot-pdf-o4h98` (the doc-freshness ack-counting test bug this
  branch's `--ack` usage exposed, filed before this review round) is itself
  missing its required `## Exit criteria` section and `metadata` block.

One pre-existing, out-of-scope failure noted and left alone: the root-level
`tests/test_doc_freshness.py::TestFreshnessAcks::
test_bulk_ack_hint_counts_this_branch_not_the_whole_corpus` fails on this
branch (and on a clean stash of it) because it globs every `.ack` file in
the working tree rather than comparing against the branch's merge-base --
exactly the bug `bd polyglot-pdf-o4h98` already describes. Re-confirmed via
`git stash` that it fails identically with none of this bead's changes
present.

**Cross-surface review round -- adopt/reject/defer.** The Opus outer
reviewer traced every new contract into its consumers and returned
GAPS-FOUND (2 blockers). One blocker adopted (fixed in this round); one
blocker the reviewer itself filed as a bead rather than blocking on
(explained below); four nits, all already filed as beads by the reviewer.

- ADOPTED (blocker): `reconcile_expired_for_firm`'s Firestore query
  (`firm_id ==`, `status ==`, `open_deadline <`) needs a composite index
  that `firestore.indexes.json` did not ship. Unlike the all-equality
  audit-log queries `confirmation_logger.py` and `audit_routes.py` run
  (which Firestore serves via automatic single-field index merging, no
  composite index needed), this query adds a RANGE filter on top of two
  equality filters -- a shape Firestore serves ONLY from a composite index.
  Without one, every call fails in production with `FAILED_PRECONDITION`
  while the local suite (which fakes Firestore with an in-Python filter)
  stays green -- CLAUDE.md scar #7's "a mock cannot tell you the real
  dependency is forbidden" applied to indexes instead of IAM. Fixed by
  adding `(firm_id ASC, status ASC, open_deadline ASC)` composite indexes
  for both `links` (demo channel) and `links_staging` (staging channel) to
  `firestore.indexes.json`, and extending
  `admin_backend/tests/unit/test_firestore_indexes.py` with a new
  AST-derived guard block (mirrors the existing audit-log guard's
  read-the-real-query-from-source pattern, generalized to a second
  collection family and a range-filter shape) that fails if either index
  goes missing, has the wrong field order, or the range field is not last.
  Mutation-verified: removing the two new indexes from
  `firestore.indexes.json` reddens exactly the three new tests
  (`test_reconcile_query_has_a_composite_index[links]`,
  `[links_staging]`, `test_no_unused_links_indexes`) and nothing else.
- NOT BLOCKED HERE (blocker, filed as `bd polyglot-pdf-cppkx`): the socket
  teardown's `_mirror_budget_exhausted` uses `set(..., merge=True))`, which
  CREATES an orphan `links/{jti}` doc (status-only, no `expire_at`) on any
  jti with no prior mint record -- and since A3 (the mint route) has not
  landed, every jti reaching this line today IS such a case, so the TTL
  policy can never reap what accumulates. Money-path correctness is
  unaffected (`refund_expired_link` refuses `not_pending`;
  `reconcile_expired_for_firm` filters on `firm_id`, which an orphan
  lacks) -- this is unbounded doc growth plus a schema violation, not a
  mis-refund, and its own fix is a genuine two-way judgment call (`update()`
  vs. `set(merge=True)` + `expire_at`) the reviewer deliberately left
  unresolved rather than picking for the next bead. Filed with exit
  criteria rather than fixed inline in this round.
- DEFERRED (nit, filed as `bd polyglot-pdf-h9584`): the mirror write's
  docstring and call-site comment both claim it "never blocks the close it
  runs alongside," but `await asyncio.to_thread(...)` does block until the
  thread returns -- the "never raises" half is true, "never blocks" is not.
- DEFERRED (nit, filed as `bd polyglot-pdf-beq0n`): `refund_expired_link`
  and `reconcile_expired_for_firm` default `channel=None` to
  `os.getenv("LINK_CHANNEL", "") or "demo"`, but their documented callers
  are the admin service, which sets no `LINK_CHANNEL` by design -- an
  admin-side caller who omits `channel=` would silently act on the
  protected demo collections. No caller exists yet (Track B/B5), so nothing
  is broken today; flagged to settle before B5 wires it.
- DEFERRED (nit, filed as `bd polyglot-pdf-jkeqk`): the reconcile query's
  fallback comment cites `confirmation_logger.py`'s "no composite index
  needed" reasoning as precedent for the SAME fallback-shape choice, but
  that reasoning does not transfer (the cited query is all-equality; this
  one adds a range filter) -- and separately restates a stale "two query
  call sites" count (there are at least four). Comment-only, no behavior
  change; left for a follow-up chore pass.

**Fix-up round -- GAPS-FOUND (1), fixed.** A second cross-surface pass
re-traced the same diff and confirmed exit criterion 3's "firm + kit"
wording is satisfied (the test's tighter "exactly the firm doc" pin is
what GUARANTEES A3's eventual composed transaction is `{firm, kit}`, not a
rubric-fail), then re-raised the blocker the prior round had deliberately
left filed-not-fixed:

- ADOPTED (blocker, closes `bd polyglot-pdf-cppkx`): `_mirror_budget_exhausted`
  now reads the doc before writing it -- `doc_ref.get()`, return silently
  when `not snap.exists` -- so `set(..., merge=True)` only ever runs
  against a links doc that already exists. Since A3 (the mint route,
  `bd polyglot-pdf-jecrl`) has not landed, every jti reaching this teardown
  today has no such doc, so before this fix EVERY budget-exhausted close
  created a schema-violating, TTL-immune orphan; after it, none do (missing
  doc: no-op; real mint record: status flips as before). New pinning test
  `test_websocket_budget_exhausted_mirror_does_not_create_an_orphan_doc`
  asserts `set()` is never called against a fake whose `get()` reports a
  missing doc; mutation-verified by deleting the `if not snap.exists:
  return` guard and confirming the test reddens (`assert 1 == 0`), then
  restoring it green. The pre-existing
  `test_websocket_budget_exhausted_writes_the_telemetry_mirror` test was
  updated so its fake's `get()` reports an EXISTING doc, so the new guard
  does not also swallow the real-mint-record case it pins (`bd
  polyglot-pdf-cppkx`'s exit criterion 2). `docs(nits)` findings 2 and 3
  from this round were both already filed by the reviewer (`bd
  polyglot-pdf-yl1ln`, `bd polyglot-pdf-alziy`) -- no new nits bead needed.
  Full backend suite (3457 passed, 72 skipped, 3 deselected) plus
  `admin_backend` (115 passed) green after the fix; the pre-existing,
  out-of-scope `tests/test_doc_freshness.py` failure (see below) still
  reproduces identically with this round's diff stashed out.

## Lessons

**A criterion can name a transaction that does not exist yet as code.**
Exit criterion 3 says "the mint transaction has no reconciliation read,"
but the mint route (`link_routes.py`'s `mint_link`) does not call
`credit_ledger` at all in this branch -- A3 is a sibling bead, still open,
and not even a dependency of A5. Pinning the criterion against the literal
mint route would have meant leaving it PENDING or inventing route code out
of scope. Instead it is pinned against the shared helper (`append_entry`)
both the future mint route and this bead's own refund path build on:
proving THAT transaction's read set stays `{firm}` alone is the actual
load-bearing property (a mint route composed on top of it will read
`{firm, kit}`, never `{firm, kit, redemption, links}`), and it holds
independent of when or how A3 lands. The general form: when a criterion is
phrased against a future surface, look for the shared primitive the future
surface will be built FROM, and pin the property there instead of blocking
on code that has not shipped.

**Reads-before-writes forces write-logic extraction, not just read
composition.** `append_entry`'s `extra_writes` hook exists for a caller
that wants to join a write to the SAME transaction, but it explicitly may
not read (it runs after the firm write is already queued). A refund needs
TWO extra reads (the redemption doc, the links record) before it can even
look at the firm balance -- reads `append_entry` itself does not know
about and cannot be handed through `extra_writes`. The fix was not a new
parameter on `append_entry`; it was splitting its write half into
`_apply_entry_writes(tx, firm_ref, entry_ref, firm, ...)`, callable once a
caller has already done ALL of its own reads (including the firm read) in
its own transaction body. Two transactional writers of one balance field
sharing one write implementation, rather than one writer stretched to
cover a shape it was not built for.

## Doc freshness

- `docs/components/auth.md` -- new "Expiry refund" section under the
  credit ledger; stamp bumped to 2026-09-08 with this bead's entry.
- `docs/technical_guide.md` -- Surface contract 18 (Credit ledger) gains a
  bullet for `refund_expired_link`/`reconcile_expired_for_firm`; header
  stamp gains this bead's entry.
- `docs/freshness/components~auth.md.ack` -- acked (bd polyglot-pdf-1op3g):
  the freshness checker's Last-updated stamp is date-only and cannot
  express that `auth.md`'s edit landed AFTER `websocket_routes.py`'s
  same-day commit within this session, so it flagged a same-day false
  stale without the ack.
- Several other tier-2 docs (`stateless-architecture.md`,
  `terminology.md`, `validation-delegation.md`, `voice-and-vad.md`,
  `ws-protocol.md`, and others) are flagged STALE by
  `check_doc_freshness.py` because they also track `websocket_routes.py`.
  None tracks the actual subject matter this branch touched (a telemetry
  mirror write in one except block); reviewed and left alone.
- No CLAUDE.md change. No `firestore.rules` change (the `links` and
  `link_redemptions` deny blocks already exist from bead A1).

## Files touched

- `backend/services/credit_ledger.py` -- `_apply_entry_writes()` (the
  write half extracted from `append_entry`), `refund_expired_link()`,
  `reconcile_expired_for_firm()`, `LinkNotRefundable`.
- `backend/routes/websocket_routes.py` -- `_mirror_budget_exhausted()` and
  its call from the `LinkBudgetExhausted` except block.
- `backend/tests/unit/test_credit_refunds.py` (new) -- the three exit
  criteria, every-non-minted-status coverage, the sweep-vs-lazy race,
  reconcile's firm-scoping and skip-don't-abort behavior, and the socket
  mirror's write/never-raise/missing-jti behavior.
- `docs/components/auth.md`, `docs/technical_guide.md` -- as above.
- `docs/freshness/components~auth.md.ack` (new) -- the same-day freshness
  ack.
- `firestore.indexes.json` -- two new composite indexes
  (`firm_id ASC, status ASC, open_deadline ASC`) for `links` and
  `links_staging`, added in the cross-surface review round above.
- `admin_backend/tests/unit/test_firestore_indexes.py` -- new AST-derived
  guard block for the links composite index (same round).

Review outcomes recorded in the closeout ping.
