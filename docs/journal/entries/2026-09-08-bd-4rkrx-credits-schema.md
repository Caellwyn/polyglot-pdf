---
date: 2026-09-08
bead: polyglot-pdf-4rkrx
title: "feat(credits): A1 schema -- firm kind/balance, links mint record, explicit channel on link helpers, rules + TTL"
sprint: 22
tags: [security, testing, conventions]
---

## Trigger

Epic 2 Track A bead A1 (plan: `docs/sprint_22_admin-console_plan.md`, "Data
model" section), the first bead of the admin-console program's credits
ledger track. Track A runs in the PUBLIC backend and has no dependency on
the admin service beyond bead 1.5 (runtime config), so it starts
immediately once bead 1.4 (the audit log + set-derived rules test) is
merged. This bead is schema and plumbing ONLY, deliberately no route
behavior change: it lays the data model the later beads (A2 ledger
transaction, A3 mint route rewrite, A5 refund/revoke) compose against,
so those beads write to an already-agreed shape instead of each
inventing one under review pressure.

## What shipped

**`firms/{firm_id}` gains `kind` and a materialized balance.**
`kind: "mock" | "live"` is required on `upsert_firm()` (no default in
either direction) so an operator bootstrapping a firm must consciously
decide which it is. `firm_kind(firm_id)` is the new reader, and it fails
closed to `"live"` -- the OPPOSITE polarity from the module's existing
`get_allowed_kits()`, which fails closed to `[]`. The two readers guard
different risks: widening kit visibility on a broken read is the danger
for `get_allowed_kits`, while widening who can mint without the
demo-channel-only gate (Epic 2 bead A3) is the danger for `firm_kind`, so
"live" -- the value that SUBJECTS a firm to that gate -- is the safe
default there, including for a doc with no `kind` key at all (the window
between this bead's deploy and the backfill migration, bead A6).
`balance_credits`/`balance_updated_at` are 0-initialized on first create
only and never touched by a re-bootstrap, since only the transactional
ledger helper (bead A2) may write them thereafter. `scripts/bootstrap_firm.py`
gains a required `--kind` flag; its positional call into `upsert_firm`
shifted (`kind` is the 5th positional argument, `status` moved to a
keyword) since the write-layer guard needed a required parameter, not an
optional one with a dangerous default.

**New `backend/services/links_store.py` -- the mint record.** A collection
SEPARATE from `link_redemptions` on purpose: `link_redemptions` answers
"has this link been opened/completed" (written on the client's FIRST
open); `links_store` answers "was this link ever legitimately minted, by
whom, for how much, and is it still good to open" (written at MINT time,
by staff, before the client ever sees the link). Folding the two together
would put a doc in existence before the client's first open, which is
exactly the state `link_redemptions`'s callers currently treat as proof
of a real open. The doc carries the firm/kit/employee identity,
`credit_cost` and `cap_usd` snapshots (the latter closes the long-open
bead `polyglot-pdf-4tjt7`), `minted_at`/`open_deadline`, a `status` field
that is explicitly a DERIVED CACHE for listing (never the money
decision -- any transaction that moves real credits reads the
authoritative record directly), and an `expire_at` TTL field. This bead
writes ONLY `record_mint()`, a plain non-transactional write with input
guards (positive `credit_cost`/`cap_usd`, non-blank identity fields); the
atomic reserve-credit + ledger-entry + record transaction is bead A2/A3's
job, and nothing here is wired into a route yet.

**Channel becomes an explicit argument.** `link_redemptions.py`'s
`_collection_name()` and `_collection()` now take `channel` explicitly
instead of reading `LINK_CHANNEL` internally -- the admin service acts on
a channel it names itself and sets no `LINK_CHANNEL` of its own, so an
env-reading helper would silently resolve to the wrong channel for every
admin-service caller. The public backend's existing callers
(`open_link`/`complete_link`/`enforce_link_redemption`) are UNCHANGED:
they call `_collection()` with no argument, which still defaults to
`link_channel()`, so this bead makes no route-behavior change despite
the signature widening. `links_store.py`'s own `_collection_name()`/
`_collection()` mirror this exact convention from the start.

**`firestore.rules` gains six new deny blocks plus a two-collection
fold-in.** New: `kits/{kitId}` (kit commercial docs, a later Track B
consumer), `links/{jti}` + `links_staging/{jti}`, and the nested
`firms/{firmId}/ledger/{entryId}` (bead A2's per-firm ledger rows -- a
parent's deny does not cascade to a subcollection in Firestore's rules
language, so this needed its own block even though `firms/{firmId}` was
already denied). Fold-in: `link_redemptions/{jti}` +
`link_redemptions_staging/{jti}` had NO deny block until now, despite
being Admin-SDK-only by access pattern since it shipped -- closed
opportunistically while the rules-set test was already being extended.
The set-derived test (`test_firestore_rules_text.py`) grows to 6 new
entries, and its file-wide both-directions scan regex was widened to
recognize one extra `/{wildcard}/segment` hop so the nested ledger
collection round-trips against the file in both directions -- without
that widening, a collection path containing a `/` is invisible to the
"every full-deny block in the file has a listed entry" half of the
guard. Mutation-verified: stripping the ledger's block reddens all three
tests that reference it (the per-collection test, the removal-proof
test, and the both-directions test).

**New `scripts/setup-firestore-ttl.sh`.** Declares a Firestore TTL policy
on `expire_at` for `links`, `links_staging`, and (ahead of Epic 3, since
this is the one script that owns TTL declarations) `alerts` --
deliberately NOT `admin_audit_log` or `deployments` (must be retained)
or either `link_redemptions` collection (a separate, deliberate retention
decision this bead does not touch). Idempotent, and not run by any deploy
script -- an operator runs it by hand once per project, same shape as
`setup-gcp-project.sh` and `setup-admin-service.sh`. A new
`tests/test_setup_firestore_ttl_script.py` pins the shipped script text
(field name, the declared collection set exactly, the retained
collections never appearing, the gcloud invocation using the loop
variable rather than a hardcoded literal). One of the first assertions
attempted -- checking the file's executable bit via Python `stat()` --
turned out to be untestable in this repo's environment: `git ls-files -s`
shows the two precedent setup scripts are themselves tracked as mode
`100644`, and Windows filesystem `stat()` never reports `S_IXUSR`
regardless of `chmod`, so that check would have failed for every script
in the repo, not just a real regression. Replaced with a shebang-text
check, which is what actually governs how the script runs.

Deferred to later Epic 2 beads, named explicitly so review does not
mistake the absence for an oversight: the atomic mint transaction
(`credit_ledger.py`, A2), the mint route rewrite and live-firm-demo-gate
(A3), the open-requires-a-mint-record check and revoke route (A3), the
refund helper and sweep (A5), and the backfill/seed migration (A6).

**Fresh-eyes + cross-surface review round.** Both review layers (fresh-eyes
rubric, then the Opus outer cross-surface pass) returned clean: all 3 exit
criteria scored PASS with verified evidence, and the outer review's final
verdict was `NO-GAPS`. Breakdown of the round's findings:

- Adopt (none) -- no rubric-fail or blocker was found, so no inline code
  change was needed this round.
- Reject (none) -- no finding was refuted against the code; both raised
  findings held up as real, just not in-scope for an inline fix.
- Defer (2, both filed as beads rather than fixed inline, per the
  finding's own classification):
  - `polyglot-pdf-o3l5z` (out-of-scope) -- `links_store.record_mint()`
    (this bead) and the pre-existing `link_metering.record_mint()` share a
    bare function name; a future route importing both under the plain name
    would get a silent shadow rather than an ImportError. Real, but nothing
    in this bead's diff wires the two together yet -- filed against the
    future mint-route bead (A2/A3) that will.
  - `polyglot-pdf-rrz0t` (nit) -- `link_redemptions.py`'s and
    `links_store.py`'s `_collection()` both resolve channel via
    `channel or link_channel()`, which treats an explicitly-passed empty
    string the same as "omitted" and silently falls through to the
    process's own channel. Low confidence (no current caller passes `""`)
    and not a regression from `origin/dev` (the function didn't exist
    there), so filed rather than fixed inline.

**Second cross-surface round (GAPS-FOUND 1, fixed).** A follow-up outer
review traced every new/changed contract (`upsert_firm`'s new `kind`
positional, the `FIRM_KIND_*` constants, `firm_kind()`, the Firestore
schema additions, `bootstrap_firm.py --kind`, `_collection_name`/
`_collection`'s channel argument, `links_store.py`'s public API,
the six `firestore.rules` blocks, the widened `ADMIN_SDK_ONLY_COLLECTIONS`
regex, and the IAM envelope) out into every consumer and found no
production caller broken and no new permission needed. Breakdown:

- Adopt (1) -- `docs/technical_guide.md:1184` claimed "All eight are added
  to `ADMIN_SDK_ONLY_COLLECTIONS`"; the diff adds six new deny blocks and
  the constant holds nine tuples total (three pre-existing + six new).
  Neither number is eight. Fixed to "All six" (matching the diff's new-block
  count, which is what the sentence is counting). Verified:
  `git diff origin/dev...HEAD -- firestore.rules | grep -c "^+    match /"`
  returns 6; `ADMIN_SDK_ONLY_COLLECTIONS` has 9 tuples.
- Reject (none).
- Defer (3, all filed as beads, none a blocker for this bead since nothing
  reads the affected records/collections yet):
  - `polyglot-pdf-s0g69` (nit, forward-facing) -- the mint record's 30-day
    TTL retention margin (`links_store.py:108`) exactly equals the maximum
    staff-requestable `complete_window_s` (`link_routes.py:69`), so a link
    minted with the maximum window and opened near its deadline can have
    its mint record reaped while still legitimately reopenable. Matters
    once Epic 2 bead A3 wires an "open requires a mint record" gate, not
    today.
  - `polyglot-pdf-yz5cp` (pre-existing) -- the Admin-SDK-only collection
    enumeration missed two collections that predate this bead:
    `firms/{firm_id}/link_usage/{period}` (`link_metering.py`) and
    `confirmation_events` (`confirmation_logger.py`). Same nested-subcollection
    shape as the `firms/{firmId}/ledger` block this bead already added, and
    the same scar-#8 lesson (enumerate the set mechanically, not by eye)
    this bead was already applying to `link_redemptions`.
  - `polyglot-pdf-5vi67` (nit, combined) -- two small hardening items: the
    `link_minted` structured-log event name is now emitted from two places
    (`link_routes.py:207`, `links_store.py:210`) with different field sets,
    a schema hazard once A3 wires both into one path; and
    `channel or link_channel()` in both `links_store.py` and
    `link_redemptions.py` treats an empty-string channel the same as
    "omitted," which the docstrings claim explicit-channel prevents.

## Lessons

The "both-directions" rules-text scan in `test_firestore_rules_text.py`
was written assuming every Admin-SDK-only collection is a single flat
path segment. The first nested subcollection (`firms/{firmId}/ledger`)
broke that assumption silently -- the per-collection test still worked
(its regex takes the collection string literally via `re.escape`), but
the file-wide scan's `[A-Za-z0-9_]+` collection-name group cannot match
a path containing `/`, so a nested collection would sit outside the
"reverse direction" half of the guard forever without a deliberate
widening. Generalizes: a set-derived test built against today's shapes
should get a fresh look, not just a new list entry, the first time a
genuinely different shape (nesting, in this case) joins the set.

The executable-bit test attempt is worth naming as a repo-specific trap:
`ls -la` in this Windows/git-bash environment shows scripts as
`-rwxr-xr-x`, which looks like a real executable-bit convention worth
pinning -- but `git ls-files -s` (what actually ships) shows `100644` for
the precedent scripts, and Python's own `stat()` never reports `S_IXUSR`
on this filesystem regardless of `chmod +x`. A mode-based test here would
have been testing a filesystem artifact, not a repo convention; checking
against `git ls-files -s` output (or, as done here, dropping the
mode check for a shebang-text check that reflects how the script
actually runs) is the correct pin.

## Doc freshness

`docs/components/auth.md` -- Tracks line gains `link_redemptions.py` and
the new `links_store.py`; the Firm identity section gains `kind`/balance
schema and `firm_kind()`'s fail-closed contract; the bootstrap usage
example gains `--kind`; the rules-collections list and Testing section
are updated for the six new blocks and two new test files.
`docs/technical_guide.md` -- Surface contract 9 (client magic links)
gains a bullet on `link_redemptions`'s channel-explicit argument; new
Surface contract 16 documents the full credits data model this bead
lays. `docs/sprint_22_admin-console_plan.md` was read but not edited --
its A1 section already matched what shipped.

## Files touched

- `backend/services/firms.py` -- `kind`/balance fields, `firm_kind()` reader.
- `scripts/bootstrap_firm.py` -- required `--kind` flag.
- `backend/services/links_store.py` -- NEW, the mint record store.
- `backend/services/link_redemptions.py` -- channel becomes an explicit argument.
- `firestore.rules` -- six new deny blocks + two fold-ins.
- `scripts/setup-firestore-ttl.sh` -- NEW, TTL policy declaration script.
- `backend/tests/unit/test_firms_service.py`, `test_bootstrap_firm_cli.py`,
  `test_links_store.py` (NEW), `test_link_redemptions.py`,
  `test_firestore_rules_text.py` -- test coverage for all of the above.
- `tests/test_setup_firestore_ttl_script.py` -- NEW, script-text pins.
- `docs/components/auth.md`, `docs/technical_guide.md` -- doc updates.

Review outcomes recorded in the closeout ping.
