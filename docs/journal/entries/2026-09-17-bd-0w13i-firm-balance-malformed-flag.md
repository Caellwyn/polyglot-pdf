---
date: 2026-09-17
bead: polyglot-pdf-0w13i
title: "chore(nits): deferred review nits from polyglot-pdf-zopqq"
sprint: 22
tags: [review, testing]
---

## Trigger

Two nits deferred from the polyglot-pdf-zopqq fresh-eyes review (firm CRUD +
credit grant/adjust routes on the admin service): low-confidence/small-scale
tradeoffs, not blockers, filed as their own bead rather than fixed inline.

1. `_public_firm_view`'s `balance_credits` fallback silently reported 0 for
   any non-int stored value -- a corrupted doc looked identical to a real
   "$0 firm" in the console, with no signal telling the two apart.
2. `get_firm` read a firm's entire ledger history into memory
   (`read_entries(db, firm_id, limit=None)`) on every profile view, an
   unbounded read on a hot admin page.

## What shipped

Nit 1 (observability): `_public_firm_view` now also returns
`balance_credits_malformed: true` only when the stored value is PRESENT but
not a plain int (a corrupted doc) -- `false` for both a real zero balance
and a firm whose balance was never written yet (the pre-first-grant state),
so it never over-reports corruption. Both `GET /admin/firms` and
`GET /admin/firms/{firm_id}` share this view and both carry the field. The
admin console surfaces it as a small "unreadable" badge next to the balance
on both the firms list and the firm detail page. Four new parametrized
backend tests pin the false/false/true/true shape (a valid int, the
never-written case, five non-int junk shapes, and the detail route), each
mutation-verified; one new frontend test pins the badge rendering (and its
absence on an unflagged row in the same table).

Nit 2 (unbounded ledger read): already resolved, independently, by bd
polyglot-pdf-y1t68 ("GET /admin/firms/{id} reads the whole unbounded ledger
to serve a 50-row page", PR #809, closed 2026-09-15) -- `get_firm` now calls
`credit_ledger.read_recent_entries(db, firm_id, ledger_limit)`, which reads
at most `ledger_limit + 1` docs regardless of ledger size, with
`ledger_limit` a query param bounded 1-200 (default 50) and a
`ledger_truncated` flag on the response. That fix landed on `dev` before
this bead started work, so no further change was needed here -- confirmed
by reading the merged commit history rather than assuming from the bead's
original (now-stale) description.

## Lessons

A deferred-nit bead's description is a snapshot at filing time; by the time
the bead is picked up, part of its scope may already be resolved by
unrelated work that happened to touch the same code. Worth a quick
`git log`/`bd show` check on the cited symbols before assuming both nits are
still open -- confirmed by evidence (the commit that introduced
`read_recent_entries` and closed `y1t68`), not by re-deriving the fix from
scratch.

Also: this bead's worktree already had substantial uncommitted work from an
earlier session whose lease had expired (`bd_safe.py claim` correctly
refused a re-claim and pointed at the existing branch). Continuing in that
worktree rather than creating a duplicate avoided redoing the same fix
twice; git history and diffs (not just skimming) confirmed which parts of
the uncommitted diff belonged to this bead versus pre-existing merged work.

## Doc freshness

- `docs/components/admin-service.md`: Routes table updated for both firm GET
  routes; the single `*Last updated:*` stamp replaced in place (not
  stacked), per the stacked-stamp convention retired the same day in bd
  polyglot-pdf-e1l5f.
- `docs/technical_guide.md`: Surface contract 18 gains a bullet for the new
  field; the `GET /admin/firms` route-table row updated. No stamp, by
  design (this file predates/exceeds the single-stamp convention and is not
  gated on one).

## Files touched

- `admin_backend/routes/firm_routes.py` -- `_public_firm_view` gains
  `balance_credits_malformed`.
- `admin_backend/tests/unit/test_firm_routes.py` -- four new parametrized
  tests.
- `admin-console/src/utils/adminApi.ts` -- `FirmRow`/`FirmDetail` gain
  `balance_credits_malformed: boolean`.
- `admin-console/src/pages/FirmsPage.tsx`, `FirmDetailPage.tsx` -- render
  the "unreadable" badge.
- `admin-console/src/pages/FirmsPage.test.tsx` -- new badge-rendering test;
  fixture update.
- `admin-console/src/pages/FirmDetailPage.test.tsx`,
  `UsagePage.test.tsx`, `UsersPage.test.tsx`, `pageIntroCoverage.test.tsx`
  -- fixture updates for the new required field.
- `docs/components/admin-service.md`, `docs/technical_guide.md` -- doc
  updates described above.

Review outcomes recorded in the closeout ping.
