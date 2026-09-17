---
date: 2026-09-17
bead: polyglot-pdf-hi9tj
title: "Bug-hunt batch 5: a docstring key-count drift, a stale historical clause, an incomplete Readers bullet"
tags: [testing, review]
---

## Trigger

Continuation of the open-ended bug-hunt mandate. Batch 4 (PR #829) had just
merged; this batch picks up ready `sonnet`/`haiku`-tier beads from the pool,
including two the outer cross-surface review filed during batch 4's own
closeout (`hi9tj`) and one carried over from batch 2's review
(`qmdc2`).

## What shipped

Three beads closed with real fixes, one closed as already-satisfied:

- **`hi9tj`** -- `backend/services/runtime_config.py`'s module docstring
  opened "Four keys, moved off deploy-time env..." while enumerating five
  (`LINK_MINTING_ENABLED`, `LINK_COST_CEILING_USD`, `LINK_FIRM_CAP`,
  `CREDITS_ENFORCED`, `CREDIT_LOW_THRESHOLD`). Filed by the batch-4 Opus
  outer reviewer as a concrete example of the exact drift risk `q1s8y`
  (batch 4) had just flagged in a neighboring comment. One-word fix:
  "Four" -> "Five".
- **`mcqc0`** -- `docs/technical_guide.md`'s Surface-contract-32 prose
  carried a "bd polyglot-pdf-l3kqc shortened it from the original
  `admin-monthly-topup-scheduler-sa` (32 chars)" clause -- a "bead X did Y"
  chronological narrative embedded in body prose, the same
  `doc-architecture.md` section 3 violation as a `Previously:` stamp chain,
  just not caught by the mechanical checker (which only regexes for
  stamp-line chains, not narrative embedded in prose). Dropped the
  historical clause, kept the current-state rationale (the 30-char
  service-account-id cap). The excision itself introduced a paren-balance
  defect (the removed clause's closing paren had been reused to close a
  DIFFERENT, still-needed nesting level) -- caught by the outer Opus
  cross-surface review, fixed inline before merge.
- **`qmdc2`** -- `docs/technical_guide.md`'s credit-ledger "Readers" bullet
  enumerated only `read_balance` and `read_entries`, omitting
  `read_recent_entries` (added by bd `polyglot-pdf-y1t68` in batch 2) --
  and worse, `read_entries`'s own contrast clause ("not the console's
  newest-n") actively implied no newest-n reader existed, at the exact
  moment one did. Added `read_recent_entries` to the bullet with its
  signature, ordering, bounding, and return shape, and pointed the
  contrast clause at it by name.
- **`77x20`** -- investigated and found ALREADY SATISFIED on `origin/dev`.
  The bead described the journal entry for bd `ylokf` (batch 3) as
  miscounting `KNOWN_CHANNELS`-carrying route files as "3 of 5" (actual:
  7). Reading the entry as it exists on `origin/dev` today, it already
  says "3 of the 7" and already names all four missed files. The bead's
  premise must have described an earlier draft that was corrected before
  PR #823 merged. Closed with no diff.

Fresh-eyes triage (Sonnet, routed by diff size): no gaps found; no
out-of-scope findings surfaced. Outer review (Opus cross-surface, one
round): GAPS-FOUND (1) -- the mcqc0 excision left an unbalanced
parenthesis in the same bullet (fixed inline, bd `polyglot-pdf-yg7fy`).
Also filed one pre-existing out-of-scope finding (bd `polyglot-pdf-wb1v4`,
a stale `read_entries` comment in `test_firm_routes.py` predating this
branch). Second round: NO-GAPS.

## Lessons

- **Deleting a clause from the MIDDLE of a parenthetical needs a
  paren-balance check, not just a re-read for sense.** Removing "bd
  polyglot-pdf-l3kqc shortened it from the original ... (32 chars)" from
  `technical_guide.md`'s Surface-contract-32 bullet also removed the `(`
  that opened it, but the sentence's LATER closing `)` (for a still-needed
  "SEPARATE identity from BOTH..." clause) survived -- leaving the bullet
  at paren-depth -1. The prose still read as grammatically plausible
  English, which is exactly why a re-read alone missed it; only counting
  parens (or the outer cross-surface reviewer, which did) caught it.

- A "bead X did Y to the old value" clause embedded in tier-1/2 body prose
  is the same current-state-only violation as a `Previously:` stamp chain
  (`doc-architecture.md` section 3), just in a shape the mechanical
  `check_doc_freshness.py` checker cannot catch (its regex only fires on
  stamp-LINE chains, not narrative threaded through a paragraph). Worth a
  grep sweep of `docs/technical_guide.md` and `docs/components/*.md` for
  the pattern `bd polyglot-pdf-[a-z0-9]+ (shortened|changed|fixed|added)`
  if this recurs.
- A bead filed against a doc's PAST state can go stale before it's picked
  up if another PR corrects the same passage first (`77x20`). Always
  re-read the current file before assuming a filed bead's premise still
  holds -- this is the second time this session a bead's exit criteria
  turned out to already be satisfied on `origin/dev`.

## Doc freshness

`docs/technical_guide.md` (both `mcqc0` and `qmdc2` fixes) and
`backend/services/runtime_config.py` (`hi9tj` fix, docstring-only) are
this branch's only touched files. `check_doc_freshness.py` reports
`technical_guide.md: OK` post-fix (its git-commit-time fallback now
reflects this branch's own edit). Doc conventions and code-citations
checks both clean.

## Files touched

- `backend/services/runtime_config.py` -- hi9tj fix
- `docs/technical_guide.md` -- mcqc0 and qmdc2 fixes
