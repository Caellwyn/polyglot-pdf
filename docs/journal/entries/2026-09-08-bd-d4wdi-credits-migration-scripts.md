---
date: 2026-09-08
bead: polyglot-pdf-d4wdi
title: "chore(credits): A6 migration -- backfill firm kind + balance, seed kits commercial docs"
sprint: 22
tags: [testing, conventions]
---

## Trigger

Epic 2 Track A bead A6 of the admin-console program
([plan](../../sprint_22_admin-console_plan.md), "Migration"). Bead A1 added
`kind`/`balance_credits` to `firms/{firm_id}` and bead A2 shipped the
transactional ledger helper, but neither bead touched the firm docs that
predate them: any `firms/{firm_id}` created before A1 still has no `kind`
and no `balance_credits` key at all, and no `kits/{kit_id}` commercial doc
has ever existed (nothing writes that collection until the admin console's
future `PUT /admin/kits/{kit_id}/commercial` route, several beads away).
`CREDITS_ENFORCED` (bead A3) cannot be switched on for any channel while
either gap exists -- a firm with no ledger history would be enforced
against a phantom balance, and the mint route has no price to debit. This
bead is the one-time sweep that closes both gaps.

## What shipped

**`scripts/backfill_firm_kind.py`.** Every `firms/{firm_id}` doc gets
`kind=live` unless its id is named in an explicit `--mock` comma-separated
allowlist -- the plan's deliberate direction: an operator names every
test/staging fixture, and everything unnamed is treated as a real paying
customer (the safe default, since a live firm wrongly marked mock merely
fails to bill, while a mock firm wrongly marked live mints for free once
enforcement is on). `kind` and `balance_credits`/`balance_updated_at` are
each written ONLY when the firm doc lacks that key -- a firm that already
carries a `kind` (from `bootstrap_firm.py`'s required `--kind`, or a
previous run of this script) is never overwritten. An optional
`--seed-credits N` grants a one-time `promo_grant` through
`credit_ledger.append_entry` (the same A2 helper `grant_credits.py` uses,
never a second balance writer), scoped to firms this run is FIRST assigning
a kind to -- a firm that already had a stored kind is skipped for seeding
too, even on its first encounter with this script, so a later credit
decision for it belongs to `grant_credits.py`, not a silent re-seed here.
The combination makes a second run of the identical command a true no-op:
zero Firestore writes attempted at all, not just zero net change.

**`scripts/seed_kit_commercials.py`.** For every kit directory under
`--kits-root` (default the repo's `form-kits/`, walked directly with
`Path.iterdir()` -- the same convention `scripts/translation_lint.py`
already uses for a filesystem sweep, rather than the async `FormKitStore`
interface, which would need an event loop and `backend.config`'s
`FORM_KITS_MODE` resolution for no benefit here), it writes
`kits/{kit_id}` with `credit_cost` from a REQUIRED `--default-credit-cost
N` (no pricing signal exists to derive one per-kit -- the plan is explicit
that this is a maintainer call), `burn_cap_usd` from the kit's own
`metadata.json` `link_cost_ceiling_usd` where present and a valid positive
number (today that is w7 and i-90 at $3 each) else `--default-burn-cap-usd`
(itself defaulting to `link_budget.DEFAULT_LINK_COST_CEILING_USD`, so an
un-overridden kit's seeded ceiling matches what the runtime would already
resolve), and `display.label` from the kit's own label or its kit_id as a
fallback. The metadata key is deliberately left in place -- vestigial after
this bead, per the plan's "stop reading it, do not delete it from published
kits." Unlike the firm backfill, this is a re-runnable SEED, not a
write-once migration: a re-run with the same flags overwrites the doc again
(same effective content), and a re-run with a CHANGED default takes effect
immediately, because there is no console yet to own per-kit pricing.

Both scripts follow the existing operator-CLI shape exactly
(`scripts/bootstrap_firm.py`, `scripts/grant_credits.py`): `main(argv)` for
direct test invocation with no module-reload fixture, a required
`--project` whose resolved `firebase_admin` project is asserted before any
write, the shared `DEAD_PROJECTS` refusal of the dead former-prod project,
`--dry-run` that reads/computes but writes nothing, and literals mirroring
the relevant service-layer constants (`backend.services.firms.KIND_*`,
`backend.services.link_budget.KIT_COST_CEILING_KEY` /
`DEFAULT_LINK_COST_CEILING_USD`) rather than an early `backend.*` import
that could race `firebase_admin.initialize_app`'s ordering -- pinned
against drift by dedicated tests in each new suite.

## Lessons

**A malformed-metadata parametrization catches exactly the guard
responsible, and nothing else.** `_positive_number`'s three guards
(non-positive, NaN/inf, bool) are stacked the same way
`credit_ledger.append_entry`'s `usd_amount` checks are (a pattern this
sprint's A2 journal entry already names as a recurring shape in this repo).
Mutation-testing by removing the `value <= 0` clause and re-running the
six-value parametrization (`None, "free", -4, 0, True, []`) turned red
ONLY the `-4` and `0` cases -- the other four stayed green because a
different guard (type coercion failure, or the bool check) already caught
them. That is the expected, correct signature of a per-parametrization
mutation check: if removing one guard had turned every case red, the other
guards would not actually be load-bearing, and the parametrization would be
one test wearing six labels.

**A false claim collision is a real trap in the exact worktree-creation
sequence this project's process requires.** Claiming a bead immediately
after creating its own worktree and branch (as CLAUDE.md's collision-guard
mechanics assume) failed on the first attempt with "appears to be
mid-flight already" -- the branch I had just created for THIS bead matched
its own collision pattern. The guard's exclusion of "the branch checked out
in the CURRENT worktree" depends on `git rev-parse --abbrev-ref HEAD`
resolving inside that worktree; running `bd_safe.py claim` from a shell
whose cwd had reset to a different directory (the documented Bash-tool cwd
trap) made the exclusion silently fail to apply. Re-running the exact same
claim command with `cd` into the worktree in the same command succeeded
immediately. No code changed -- this is a note for the next session hitting
the same shape, since the error message ("switch to that worker's branch")
reads as a real collision when it is actually a cwd artifact of the shell
tool, not the bead-claim tool.

## Doc freshness

- `docs/components/auth.md` -- `**Tracks:**` gained
  `scripts/backfill_firm_kind.py` and `scripts/seed_kit_commercials.py`;
  the *Last updated* note gained a parenthetical describing both scripts'
  write rules (never-overwrite backfill, seed-scoped-to-new-kind,
  filesystem walk for the kit seed) and the `CREDITS_ENFORCED` per-channel
  switch-on precondition. Stamp bumped to 2026-09-08 -- but
  `closeout_prep.py`'s doc-freshness pass still flags it STALE against the
  two new scripts. This is a UTC-boundary false positive, not a real gap:
  `check_doc_freshness.py` compares the doc's date stamp (parsed as
  23:59:59 UTC on that calendar day) against each tracked file's last
  COMMIT timestamp, and every commit in this PR landed after 17:00 PDT,
  which is already past midnight UTC (`2026-09-09`). The doc commit itself
  (17:09:00 PDT) is genuinely LATER than the scripts' commit (17:08:36
  PDT) -- the content is current -- the check just sees a same-local-day
  edit as spilling into the next UTC day. `check_doc_freshness.py` is not
  one of this bead's surfaces; left as-is rather than patched here.
- `docs/technical_guide.md` -- no Surface contract change: this bead adds
  two scripts on top of contracts (the ledger helper, the `kits/{kit_id}`
  doc shape, the firm doc shape) that beads A1/A2 already documented there;
  nothing new to enumerate.
- All other tier-2 docs flagged STALE by `check_doc_freshness.py` are
  pre-existing and driven by other branches' timestamps on
  `websocket_routes.py`, `config.py`, `live_ai_gemini.py` and frontend
  files this bead never touched. Reviewed and left alone.
- No CLAUDE.md change.

## Files touched

- `scripts/backfill_firm_kind.py` (new) -- the firm kind/balance backfill +
  optional seed grant.
- `scripts/seed_kit_commercials.py` (new) -- the `kits/{kit_id}` commercial
  doc seed.
- `backend/tests/unit/test_backfill_firm_kind_cli.py` (new) -- the CLI
  contract: mock allowlist, never-overwrite, true-no-op re-run, seed
  scoping, dry-run, dead/mismatched project, one-bad-firm resilience.
- `backend/tests/unit/test_seed_kit_commercials_cli.py` (new) -- the CLI
  contract: required `--default-credit-cost`, burn_cap_usd resolution
  (metadata vs default, parametrized over every malformed value), display
  label fallback, dry-run, idempotent re-run, one-bad-kit resilience.
- `docs/components/auth.md` -- Tracks line + Last-updated note, as above.

Review outcomes recorded in the closeout ping.
