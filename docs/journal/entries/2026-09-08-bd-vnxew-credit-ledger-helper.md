---
date: 2026-09-08
bead: polyglot-pdf-vnxew
title: "feat(credits): A2 credit_ledger transactional helper + typed entries + grant_credits.py CLI"
sprint: 22
tags: [security, testing]
---

## Trigger

Epic 2 Track A bead A2 of the admin-console program
([plan](../../sprint_22_admin-console_plan.md), "Mint transaction"). Bead A1
laid the schema -- `firms/{firm_id}` gained `kind` and `balance_credits`, the
`links[_<channel>]/{jti}` mint record store shipped, and `firestore.rules`
gained a deny block for the nested `firms/{firmId}/ledger` -- but nothing
wrote a ledger row or moved a balance. A3 starts debiting credits at mint
time, and it cannot be written until the transaction it debits through
exists. This bead is that transaction, plus the operator CLI that lets
credits be put in and taken back out before any console exists to do it.

## What shipped

**`backend/services/credit_ledger.py`.** One `@firestore.transactional`
helper, `append_entry()`, is now the only code that writes
`firms/{firm_id}.balance_credits` after the firm is created, and the only
producer of `firms/{firm_id}/ledger/{auto}`. All six entry types --
`subscription_grant`, `purchase`, `promo_grant`, `mint_debit`,
`expiry_refund`, `adjustment` -- go through it, so the invariant
`balance_credits == sum(amount)` holds by construction rather than by six
call sites each remembering to update the balance. Nothing recomputes the
balance from the ledger on a read, which is precisely why a second writer
would break it silently.

Entries carry a signed `amount`, a nullable `usd_amount`, a snapshotted
`firm_kind`, a nullable `channel`, `balance_after`, a never-blank `actor`, a
`reason`, `link_jti`, `kit_id` and `ts`. Three rules are enforced at the
write and each runs in both directions:

- `purchase` and `subscription_grant` REQUIRE `usd_amount`; the other four
  REFUSE it. "Forgot to pass it" loses revenue; "passed it where it does not
  belong" double-counts a promo grant or a debit as income in a view that
  sums the column. Both are caller bugs, so both are refused.
- The four credit-adding types refuse a negative amount and `mint_debit`
  refuses a positive one. `adjustment` is the one signed escape hatch, and
  is the one type that requires a non-blank `reason` -- the control that
  replaces the sign rule.
- `actor` is required and never blank. An unattributable credit movement is
  the single thing a ledger exists to make impossible.

**Reads before writes, and nothing hoisted.** This is the shape the bead
called out: Firestore requires every transactional read to precede every
write, and RE-RUNS the whole body on contention. So the balance, the kind
snapshot, the sufficiency verdict and `balance_after` are all computed
inside the body from the same snapshot, on every run. A value read before
the transaction would be stale on the retry -- and that retry IS the
double-mint race. The helper is sync on the Admin SDK; async callers wrap it
in `asyncio.to_thread`, and the docstring carries the rule.

**Enforcement is a caller's switch, not a default.**
`require_sufficient_balance=False` (the default) writes a debit past zero and
lets the balance go negative -- the metered soft-launch mode the plan wants
until A6 seeds balances. `True` raises `InsufficientCredits` with nothing
committed; A3's mint route passes it from the `CREDITS_ENFORCED` runtime-config
flag and maps the refusal to `402`. `extra_writes(tx, firm_snapshot)` joins a
caller's documents to the same transaction, which is how A3 will make the
debit, the ledger entry and the `links/{jti}` mint record commit together or
not at all.

**The `ledger_export` line.** Every committed write emits one structured log
line carrying `event_type`, `type`, `amount`, `usd_amount`, `firm_id`,
`firm_kind`, `channel`, `link_jti` -- the income and spend feed Epic 3's
Cloud Logging -> BigQuery sink filters on (`jsonPayload.event_type`; this
repo's structlog `JSONRenderer` puts every bound key at the JSON line's top
level, which is what makes that filter match). It is emitted AFTER the
commit, so an aborted transaction leaves no line to inflate the income view,
and it carries no field values, PII or PHI: `reason` is operator free text
and deliberately stays out of the log while being stored on the entry.

**`scripts/grant_credits.py`.** The operator CLI on the same helper. Two
subcommands rather than one signed flag: `grant` adds credits and refuses a
negative `--credits`; `adjust` takes either sign and requires `--reason`. The
dangerous operation -- an arbitrary signed correction to a paying firm's
balance -- needs a different verb AND a justification, so it cannot be
reached by fat-fingering a minus sign into the everyday command. `--dry-run`
reads the balance and prints the entry, and distinguishes "firm has no
document" (a `read_balance` of `None`) from "firm has zero credits", because
the first is a write the real run will refuse. `--project` is required and
its resolved firebase_admin project asserted before any write, the dead
project is refused, and `actor` is stamped
`system:grant_credits_cli:<operator>` -- deliberately distinguishable from a
console grant's Firebase uid, because "a human ran a script" and "a human
clicked a button behind the admin auth gate" are different provenance.

**Deliberately NOT in this bead** (they belong to A3/A5, and the surfaces
list says so): the mint route rewrite, the open-requires-a-mint-record gate,
the expiry refund and its sweep, and the alert docs the plan wants written
"by the Epic 2 ledger debit helper after the balance changes" -- that last
one needs the `alerts` collection and its thresholds, which are Epic 3's.

## Lessons

**A fake Firestore must copy on read, or every stale-read test is vacuous.**
The first version of the test fake stored a reference to the live store dict
in its snapshot object. A real Firestore snapshot is a point-in-time copy,
and the difference is not cosmetic: with the reference, a snapshot taken
BEFORE a competing commit silently observed that commit's values. The
consequence was concrete and would have shipped -- I mutated the helper to
hoist the firm read OUT of the transaction body (the exact bug the race test
claims to catch) and `test_mint_transaction_double_mint_race_is_safe`
**still passed**. Only the reads-before-writes test went red, and for a
different reason. One line (`dict(data)` in the snapshot constructor) turned
the race test from decorative into load-bearing. The general form: when a
test double stands in for something whose whole value is ISOLATION, the
double has to model the isolation, or the test measures the double.

**Redundant guards hide each other from mutation testing.** Deleting the
`usd_amount is None` check left the suite green -- not because the property
was unpinned, but because the `isinstance(usd_amount, (int, float))` check
one line below also rejects `None`. Three stacked guards (missing,
non-numeric, negative) were pinned by one test that only exercised the first.
Deleting either of the other two was a free, silent removal. The fix was a
test per guard, each verified to redden ONLY its own layer -- which is the
repo's existing "redundant guards need per-layer tests" scar, met again in a
new place. The tell is generic: if a mutation you expected to be red comes
back green, the guard you deleted probably was not the one doing the work.

**Write the mutation you actually ran into the docstring.** Two of my test
docstrings named a mutation that turns out not to change behaviour --
moving the sufficiency check below the two `tx.set` calls, for instance,
aborts identically, because the buffered writes are discarded either way.
That is the property, not a gap, but a docstring asserting a red that never
happens is a false record the next reviewer has to re-derive. Both were
rewritten to name the mutation that genuinely reddens, with a note about the
one that does not and why.

## Doc freshness

- `docs/technical_guide.md` -- new **Surface contract 18** (the credit
  ledger): the one-writer rule and its single deliberate exception
  (`firms.upsert_firm`'s 0-initialization), the entry field set and the
  two-way type rules, the reads-before-writes discipline, the enforcement
  switch and the `extra_writes` hook A3 consumes, the `ledger_export` line
  Epic 3 consumes, the two readers, and the CLI. Header stamp bumped.
- `docs/components/auth.md` -- new "The credit ledger" section, `**Tracks:**`
  extended with `backend/services/credit_ledger.py` and
  `scripts/grant_credits.py`, stamp bumped. Two forward-looking phrases went
  current-state: the `firms/{firm_id}` bullet no longer says the helper is
  "landing in Epic 2 bead A2", and the mint-record section's list of later
  beads drops A2.
- 19 other tier-2 docs are flagged STALE by `check_doc_freshness.py`. None
  tracks a file this branch changed -- they are pre-existing, driven by other
  branches' timestamps on `live_ai_gemini.py`, `config.py` and the frontend.
  Reviewed and left alone.
- No CLAUDE.md change.

## Files touched

- `backend/services/credit_ledger.py` (new) -- the transactional helper,
  entry-type rules, `read_balance`, `read_entries`, the `ledger_export` line.
- `scripts/grant_credits.py` (new) -- the `grant`/`adjust` operator CLI.
- `backend/tests/unit/test_credit_ledger.py` (new) -- the replay invariant,
  the double-mint race, the entry-shape and type rules, the firm_kind
  snapshot, the export line, and the set-derived one-writer guard.
- `backend/tests/unit/test_grant_credits_cli.py` (new) -- the CLI contract.
- `docs/technical_guide.md`, `docs/components/auth.md` -- as above.

## Fresh-eyes round 1 -- adopt / reject / defer

The reviewer scored all three exit criteria PASS and returned GAPS-FOUND with
three findings. Two adopted, one deferred.

**Adopted -- the one-writer guard was pinning a spelling, not the set.**
`test_credit_ledger_is_the_only_module_that_writes_balance_credits` detected
offenders with the literal substring `"balance_credits":`, so a second writer
using single quotes, a `payload["balance_credits"] = n` subscript assignment,
or an `update(balance_credits=n)` kwarg would not be caught. This was worse
than the reviewer's read: `firms.upsert_firm()` -- the one legitimate second
writer the test's own docstring names -- writes the field as
`payload["balance_credits"] = 0`, which that substring never matched, so the
allowlist entry for `firms.py` was dead weight and the repo's actual write
idiom was already invisible to the guard. Detection is now an AST walk over
subscript assignments, dict-literal keys and call kwargs, and the allowlist is
pinned in both directions so a stale exemption fails too. Mutation-verified by
injecting each of the four write shapes into `links_store.py` one at a time:
all four now red, where the old pattern caught only one. This is scar #8's
own failure mode, in the test that cites scar #8.

**Adopted -- a whitespace-only `--actor` stamped an unattributable entry.**
`_actor()` treated any truthy string as an explicit actor, and the helper's
blank-actor guard tests `actor.strip()` on the whole stamped string, which is
non-empty for any prefix at all. So `--actor "   "` committed an entry whose
operator segment -- the half naming who moved the credits -- was blank, which
is exactly what this module's docstring calls the one thing the ledger exists
to make impossible. `_actor()` now strips before the truthiness test, so
whitespace takes the same fallback path as an omitted flag. Pinned by a new
test parametrized over the whole blank dimension (spaces, tab, newline, mixed,
empty) rather than one sample; mutation-verified per parametrization -- the
four whitespace cases go red without the strip, and `""` stays green because
argparse's default already covers it.

**Deferred -- dry-run conflates "no such firm" with "could not read".**
Filed as bd `polyglot-pdf-73ze5`. The `--dry-run` path prints "a real run
would be REFUSED" and exits 0 both when the firm document is genuinely absent
and when the balance read raised. The message already hedges with "(or could
not be read)" and the blast radius is operator confusion in an internal CLI
run under the operator's own credentials -- no ledger-integrity impact -- so
it was carried out of this PR as a nit rather than fixed here.

Suite after the round: 3389 backend passed / 72 skipped, 1397 root passed /
46 skipped. The two changed test files went 89 -> 94 tests (+5 from the new
parametrization).

Review outcomes recorded in the closeout ping.
