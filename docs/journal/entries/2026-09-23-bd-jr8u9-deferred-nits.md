---
date: 2026-09-23
bead: polyglot-pdf-jr8u9
title: "chore(nits): deferred review nits from polyglot-pdf-k5w16"
sprint: 22
tags: [conventions, testing]
---

## Trigger

bd polyglot-pdf-jr8u9 collects three nits the outer cross-surface review of
bd polyglot-pdf-k5w16 (fix/k5w16-telemetry-grant-prefix) surfaced but
deferred, since none changed behavior and they were pre-existing or
cosmetic: (1) a stale comment in `scripts/setup-telemetry.sh` claiming
BigQuery views are late-bound, (2) a missing PEP8 blank line in
`tests/test_setup_telemetry_script.py`, and (3) a hardcoded `"true"` gate
in an `_apply_view` call that makes its `skip_reason` argument dead text.

## What shipped

Investigated all three items against the current worktree (branched from a
later `origin/dev` than the review that filed the bead) before touching
anything:

- **Item 1 (stale "late-bound" comment) is moot.** A later, already-merged
  PR (bd polyglot-pdf-vm2fu, "sink-table detection via python client, not
  bq ls") rewrote the entire comment block that used to contain the
  cited line 361. Confirmed by grep across the repo: the exact stale
  sentence ("BigQuery views are late-bound, so applying a view against a
  not-yet-existent table is fine") no longer exists anywhere. No code
  change needed.
- **Item 2 (missing blank line) is already fixed.** Wrote a small script
  to enumerate every top-level `def`/`class` in
  `tests/test_setup_telemetry_script.py` and check the blank-line count
  immediately before it (PEP8's two-blank-line rule) -- zero violations
  found across all 36 (now 37) top-level defs. Matches the bead's own
  note that this was "already fixed as a side effect" of a later commit
  in the same PR round.
- **Item 3 (dead skip_reason) fixed.** `hosting_cost_by_service_month`'s
  `_apply_view` call in `scripts/setup-telemetry.sh` is gated `"true"`
  unconditionally (`BILLING_EXPORT_TABLE` is already guaranteed non-empty
  by an earlier `exit 0` check), so its `skip_reason` string
  `"BILLING_EXPORT_TABLE not given"` could never print and misleadingly
  implied the gate was still live. Reworded it to
  `"unreachable -- BILLING_EXPORT_TABLE is already guaranteed non-empty
  here"` so the call site documents its own dead branch honestly.
  Confirmed (via grep across `scripts/`) this is the only `_apply_view`
  call using a hardcoded `"true"` gate -- the other four all read a real
  `$STDOUT_OK`/`$STDERR_OK` variable, so this was a single, fully
  enumerated instance, not a pattern needing a wider sweep.

Added a new pinning test,
`test_hosting_cost_view_skip_reason_does_not_restate_the_removed_gate`,
asserting the skip_reason string is not the old misleading text and does
say "unreachable". Mutation-verified: reverted the production string back
to `"BILLING_EXPORT_TABLE not given"` and watched the new test fail with a
clear assertion message, then restored the fix and re-ran the full
36-test (now 37) file green.

## Lessons

A deferred-nits bead is worth re-verifying against the current tree before
fixing anything -- two of the three items here had already been resolved
by unrelated, already-merged work between when the bead was filed
(2026-09-18) and when it was picked up (2026-09-23). Fixing a nit that no
longer exists, or "fixing" one that's already fixed, would have been
wasted diff and a false completion signal. Confirmed each item's current
state mechanically (grep for the exact stale string; a script enumerating
blank-line gaps) rather than trusting the bead's line-number citations,
which had already drifted from a later file rewrite.

## Doc freshness

`docs/standards/logging-and-cost.md` tracks `scripts/setup-telemetry.sh`
but was left untouched: it was already flagged STALE by
`scripts/check_doc_freshness.py` before this bead (two files it also
tracks, `backend/services/credit_ledger.py` and `backend/utils/logging.py`,
were touched 2026-09-23 by an unrelated, already-merged bead,
polyglot-pdf-65jeu) and already carries a pre-existing 6-stacked
`*Last updated:*` violation the checker itself flags. This bead's change
is a single cosmetic string edit that adds no new documented behavioral
fact, so bumping the stamp would add a 7th stacked line to an
already-broken doc without fixing the underlying violation -- left for a
dedicated doc-cleanup pass instead. No other docs/components or
docs/standards file tracks `scripts/setup-telemetry.sh` or
`tests/test_setup_telemetry_script.py`.

## Files touched

- `scripts/setup-telemetry.sh` -- reworded the dead `skip_reason` string
  on `hosting_cost_by_service_month`'s `_apply_view` call.
- `tests/test_setup_telemetry_script.py` -- added
  `test_hosting_cost_view_skip_reason_does_not_restate_the_removed_gate`.
