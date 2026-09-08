---
date: 2026-09-08
bead: polyglot-pdf-li9x0
title: "feat(admin): 1.4 append-only audit log (in-transaction + pending forms), config/audit routes, rules set test"
sprint: 22
tags: [security, testing, conventions]
---

## Trigger

Epic 1 child 1.4 of the admin-console program
([plan](../../sprint_22_admin-console_plan.md), "Append-only audit log"). The
admin service now has a gate (bd `polyglot-pdf-7w17m`) and a deploy bridge (bd
`polyglot-pdf-3l2vp`), but nothing yet records what an operator actually *did*
with it. The plan is explicit about *why* that record has to exist before the
first mutating route rather than after: the failure it prevents is a **double
apply**. An operator who sees a 500 retries, and without an audit row bound to
the mutation there is no way to tell a first attempt from a second — which for
a credit grant means real money applied twice.

Filed with its first consumers deliberately ("so the forms are proven against
real routes"), because a helper validated only against a test double proves
nothing about the shape a route needs.

## What shipped

**`admin_backend/services/audit_log.py`** — one row in `admin_audit_log/{auto}`
per privileged mutation, in two forms that are *not* interchangeable:

- **`record_in_transaction(tx, db, ...)`** for Firestore mutations. The row is
  written with `tx.set` inside the **caller's** transaction, so either both
  commit or neither does. The helper takes the transaction rather than opening
  one — a helper that opened its own would produce two independent commits and
  exactly the window it exists to close — and deliberately carries **no
  `try/except`**: swallowing an audit failure would let the mutation commit
  unaudited, which is the one outcome this form makes impossible.
- **`record_pending` → `mark_committed` / `mark_failed`** for mutations
  Firestore cannot wrap (Auth user create/disable, claim stamps, Cloud Build
  triggers — Epic 1's user routes and Epic 4's build triggers are the first
  consumers). Note the deliberate **asymmetry**: `record_pending` *raises* (if
  the intent cannot be recorded, the action must not happen), while both
  closeouts are *best-effort*. That is not laxness — the action has already
  happened by then, so raising would surface an error for a success, and a
  caller retrying on it would double-apply. A row stuck at `pending` reads as
  "this may have taken effect", which is true.

`build_row` is the single producer of the payload, so the two forms cannot
drift into carrying different field sets — the drift that makes an audit query
mean two different things for two eras of rows. `ROW_FIELDS` pins the shape.

**The first consumers.** `PUT /admin/config/{channel}` is the audited producer
for `app_config/{channel}` that Surface contract 14 had named as future work.
It reads the current value, writes the new one with `merge=True`, and writes
the audit row all inside one `@firestore.transactional` body. `GET
/admin/config/{channel}` returns the **raw** stored values, and `GET
/admin/audit` is the cursor-paginated read half.

**`firestore.rules`** gains deny blocks for `admin_audit_log` and `app_config`,
and `backend/tests/unit/test_firestore_rules_text.py` becomes **one set-derived
test** over every Admin-SDK-only collection.

**No new IAM.** The writes need `roles/datastore.user`, which `admin-backend-sa`
already holds and whose pin in `test_admin_sa_iam_envelope.py` already names
`admin_audit_log` and `app_config` in its justification. Asking the question
was the point (CLAUDE.md scar #7); the answer happened to be "already covered".

### Cross-surface review round 1 — adopt 2, defer 2

**Adopted (blockers, both one root cause).** The reviewer traced the *query
shape* out to the deploy surface — a contract the handoff list had not named —
and found that every filtered `GET /admin/audit` query is an equality filter
plus an `order_by` on a different field, the one shape Firestore serves only
from a **composite index**. This repo shipped no `firestore.indexes.json` at
all (`git log --all` on the path is empty), `firebase.json` declared only
rules, and no deploy script ran `firebase deploy --only firestore:indexes`. So
three of the four filters plus every state-filtered query would have failed in
production with `FAILED_PRECONDITION` while all 135 local tests stayed green —
because `test_audit_log.py` substitutes an in-memory `_Query` that filters and
sorts in Python. That is **CLAUDE.md scar #7 with indexes in place of IAM**: a
fake proves the code *makes* the query, never that the datastore will *accept*
it. The second finding was the tell rather than a separate defect — the module
docstring called the requirement "a simple composite index", documenting as
solved the very thing that was missing.

The fix ships the artifact rather than removing the ordering: a new
`firestore.indexes.json` with the four `(<field> ASC, ts DESC, __name__ DESC)`
composites, wired through `firebase.json`, and deployed by `deploy-demo.sh`
beside the rules — indexes are project-wide exactly as rules are, so they
belong to the protected channel and not to disposable staging. The docstring,
Surface contract 15, and the route table now all state the prerequisite.

The guard is **set-derived, not four hand-written assertions** (CLAUDE.md scar
#8). `test_firestore_indexes.py` reads the filter field names out of the
route's **AST** — the literal tuple the route iterates to build its filters —
so the test tracks the route instead of a copy of it. Mutation-verified five
ways: dropping the `state` index reddens three assertions including
`[state]` specifically; flipping one index's `ts` direction to ASCENDING
reddens only `[channel]`; unwiring `firebase.json` and deleting the deploy line
each redden their own guard; and adding a **fifth filter to the route** made
the parametrization expand to `[target]` on its own and fail — which is the
regression that actually matters, and the proof the derivation is real.

**Deferred (already filed by the reviewer, not fixed here).** The 503 that
masks `FAILED_PRECONDITION` and `INVALID_ARGUMENT` as "audit store
unavailable" is a diagnosability defect independent of the correctness one —
`polyglot-pdf-xdbqm`. And `scripts/set_runtime_config.py` accepting any
channel string while the new route rejects one outside `KNOWN_CHANNELS`
reproduces unchanged on `origin/dev`, so it is pre-existing —
`polyglot-pdf-3rvwm`.

**Nothing refuted.** Both blockers were independently confirmed here before
fixing: the missing artifact by `git log --all -- firestore.indexes.json`
returning empty, and the constraint itself by this repo's own two prior
records of it (`backend/utils/confirmation_logger.py:934-937`, which avoids
`order_by` entirely for this reason, and
`docs/standards/confirmation-and-audit.md:204-205`).

## Lessons

**A fake that is more helpful than the real dependency hides the bug.** Twenty
mutations were run against the real production paths; nineteen reddened their
guard. The twentieth did not: dropping the `__name__` tiebreaker from the audit
query's `order_by` left **every test green**, including one whose docstring
claimed to catch exactly that. The cause was the fake query object — its
`order_by` ignored its arguments and always sorted by `(ts, doc_id)`, so it
*supplied the tiebreaker the route had just dropped*. The fix was two-part, and
both halves were needed: the fake now honours the order the route actually
requests, **and** the fixture gives three pairs of rows a *shared* `ts` so the
tiebreaker is observable at all. With distinct timestamps everywhere, a route
that dropped the tiebreaker would be indistinguishable from one that kept it
however faithful the fake. This generalizes past this file: when a test double
normalizes, sorts, defaults, or otherwise tidies up on the real dependency's
behalf, it can only make the code under test look better than it is — and the
mutation test is the only thing that finds it.

**"Some audit call is present" would have been a vacuous coverage test.** The
plan called for asserting the *required form*, not mere presence, and building
it made clear why: the regression that matters is not a deleted audit call
(loud, obvious) but an audit call that drifts **outside** the transaction — a
diff that reads fine and passes any presence check. `test_admin_audit_coverage.py`
therefore checks the *position* of the call (inside a `@firestore.transactional`
body) and that the mutation is in that body with it, since a transactional body
carrying only the audit row would otherwise pass.

**Enumerating the set beat the next three review rounds** (scar #8).
`test_firestore_rules_text.py` asserted one deny block, for `firms/{firmId}`.
This bead added two collections; the path of least resistance was two more
copies of the same assertion, and Epic 2's ledger would have made a fourth. It
is now one list plus a parametrized assertion, failing in **both** directions —
a listed collection with no block, *and* a block for a collection nobody listed
(the second is what stops a collection silently dropping out of the guard when
someone tidies the rules file). It also rejects a **weakened** block, not only
a deleted one: adding `allow read: if request.auth != null;` next to the deny is
the far likelier regression, and a substring check for `if false` would wave it
straight through.

## Doc freshness

- **`docs/technical_guide.md`** — new Surface contract 15 (the audit log); three
  new rows in the Admin service routes table; contract 14's "Producer (future)"
  rewritten as the two real producers, naming which audits and which is
  break-glass, and its forward reference to the rules blocks replaced with the
  shipped set. *Last updated* bumped.
- **`docs/components/auth.md`** — the rules-deploy note names all three
  Admin-SDK-only collections and flags that `firestore.rules` is project-wide
  (a demo action whichever channel you ran it from); the testing section
  describes the set-derived test that replaced the single `firms` assertion.
  *Last updated* bumped.
- **`docs/components/config-deployment.md`** — the inert `LINK_MINTING_ENABLED`
  note names the audited route as the operational seeding path; the admin-gate
  paragraph is no longer "its first route is whoami"; the **Tracks:** line picks
  up the three new `admin_backend/` files. *Last updated* bumped.
- Reviewed and left as-is: `docs/standards/confirmation-and-audit.md`. It tracks
  the *client confirmation* sink, a different trail with the opposite
  (fire-and-forget) polarity; the contrast is documented in `audit_log.py`'s
  module docstring and in contract 15 rather than mixed into that doc.
- No CLAUDE.md change. Other docs flagged stale by `check_doc_freshness.py`
  track files this branch does not touch and were left alone.

## Files touched

- `admin_backend/services/audit_log.py` — new; the log's two write forms.
- `admin_backend/routes/config_routes.py` — new; `GET`/`PUT
  /admin/config/{channel}`, the in-transaction form's first consumer.
- `admin_backend/routes/audit_routes.py` — new; `GET /admin/audit`, cursor-paginated.
- `admin_backend/main.py` — registers the two new routers; docstring updated.
- `admin_backend/tests/unit/test_admin_audit_coverage.py` — new; the required-form pin.
- `admin_backend/tests/unit/test_config_routes.py` — new; exit criterion 1.
- `admin_backend/tests/unit/test_audit_log.py` — new; the helper's own contract
  and the read route's pagination.
- `admin_backend/tests/unit/test_admin_route_auth.py` — route-set pin extended
  to the three new routes.
- `backend/tests/unit/test_firestore_rules_text.py` — rewritten as one
  set-derived test over `ADMIN_SDK_ONLY_COLLECTIONS`.
- `firestore.rules` — deny blocks for `admin_audit_log` and `app_config`.
- `firestore.indexes.json` — **new** (review round 1); the repo's first index
  artifact. The four composites `GET /admin/audit`'s filters require.
- `firebase.json` — wires `firestore.indexes` alongside `firestore.rules`.
- `deploy-demo.sh` — ships `firestore:indexes` beside the rules (both are
  project-wide, so both belong to the protected channel).
- `admin_backend/tests/unit/test_firestore_indexes.py` — **new** (review round
  1); the set-derived index guard, filter names read from the route's AST.
- `docs/technical_guide.md`, `docs/components/auth.md`,
  `docs/components/config-deployment.md` — see Doc freshness.

Review outcomes recorded in the closeout ping.
