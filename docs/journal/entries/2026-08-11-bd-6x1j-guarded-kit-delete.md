---
date: 2026-08-11
bead: polyglot-pdf-6x1j
title: "Guarded hard delete -- refusing when the record cannot be checked"
sprint: 19
tags: [testing, conventions, audit]
---

## Trigger

Sprint 19 (docs/sprint_19_firm-tier-kit-lifecycle_plan.md), epic
polyglot-pdf-7jmy child 4 of 4 -- the last implementation child, unblocked by
bd polyglot-pdf-xzw5.

Kits accumulated: a mistaken upload, a junk draft, a superseded revision nobody
will republish. There was no way to remove one. But deletion is the only
operation in this system that can destroy the evidence the previous three beads
(w3zw, 6dz0, xzw5) built the revision archive to preserve -- so the feature is
the GUARD, not the delete.

## What shipped

`DELETE /api/editor/kits/{kit_id}`, author-only, plus a type-the-kit-id dialog
and the store's first destructive primitive (`FormKitStore.delete_kit`, both
impls).

**The guard has FOUR refusal cases, and only one of them is "records exist".**
The other three are all forms of "I could not verify":

1. Records name the kit -> 409, offering unpublish.
2. The sink is disabled (`CONFIRMATION_FIRESTORE_ENABLED` defaults false) --
   the local JSONL fallback dies with the instance, so its silence is not
   evidence.
3. A record stores `kit_id: null` -- Firestore equality cannot match a stored
   null, so a kit-scoped query is blind to it.
4. A legacy record omits `kit_id` entirely -- `IS_NULL` matches a stored null
   but not a missing key.

Maintainer decisions: "cannot verify" reads as NO, and deletion is AUTHOR ONLY
-- "editors should not ever be able to make destructive actions; their work
should always be recoverable."

## Scar tissue

**1. A fail-open guard has more than one "absent".** Cases 3 and 4 above are
the SAME bug found twice, in two different representations. I fixed the
stored-null blindness in review round 2, declared it closed, and the outer
cross-surface review then found the missing-key shape -- reachable against real
data written in a two-day window (2026-08-03 to 2026-08-05, verified against
the pre-47r3 event literal in git, not assumed). **When a query is blind to one
representation of absent, enumerate every representation before calling it
fixed.**

The discriminator that made case 4 fixable rather than deferrable:
`event == "field_confirmed"`. Session-lifecycle records share the missing-key
shape, so sweeping on the shape alone would have made every kit permanently
undeletable the moment one session was logged. Scoping on the event value
separates the populations AND keeps it a single-field equality query -- no
composite index, which the repo has no artifact for.

**2. The implementation that ships is the one to test.** `LocalFormKitStore` is
the dev fallback; GCS is production. My sibling-prefix test exercised the LOCAL
store, where a directory delete makes prefix collision structurally impossible
-- so it passed for a reason unrelated to what its docstring claimed. Removing
the "load-bearing" trailing slash left the FULL 1903-test suite green while
turning `delete w7` into "also delete w7-2024, w7-old, and every archived
revision under them".

**3. Four tests on this bead passed for the wrong reason, all mine, all in a
fake I also wrote.** The pattern: my assumptions got encoded twice (once in the
code, once in the fake) and validated zero times.

- The disabled-sink test's stub raised `AssertionError`, which the function's
  broad `except Exception` caught and re-raised as exactly the exception being
  asserted -- so deleting the guard left it green.
- The fake DISCARDED the query operator, so inverting the null sweep to `!=`
  (which resolves to `IS_NOT_NULL` and would make every kit permanently
  undeletable) kept all 31 tests green.
- A `limit(1)` test wrapped `stream()` after the query was already built,
  measuring nothing.
- A telemetry test was vacuous twice: `caplog` does not see structlog events,
  then `structlog.configure` did not reach a logger bound at import.

Every one was caught by RE-RUNNING THE MUTATION rather than trusting the pass.
A detail that nearly defeated the fix: `str()` on a resolved Firestore operator
enum yields `'3'`, not `'IS_NULL'` -- record `.name`, or the assertion can
never match.

**4. Editing one of a pair without checking for the pair.** Moving the Delete
button, I brace-matched to the first `isAuthor && !kit.hasSchema` block and
landed it in the compact STRIP instead of the card grid. Two identical blocks
exist in that file. Five tests caught it immediately -- but it is the same
twin-surface shape that has run through this entire epic.

## Review record

Four inner rounds (4, 1, 5, 4 findings) then two outer cross-surface passes
(1, 0). The outer re-ran because I fixed its finding in-branch rather than
accepting the filing -- a guard that fails open is not follow-up work.

The outer pass settled two things I could not settle myself: it verified
Firestore's null-equality semantics against the installed SDK source (`==` with
`None` resolves to `UnaryFilter(IS_NULL)`), and it enumerated every `event`
value ever written across all 19 historical revisions of the logger to confirm
the discriminator is exhaustive.
