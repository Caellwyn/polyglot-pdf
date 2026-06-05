---
date: 2026-06-04
bead: polyglot-pdf-ayk
tags: [conventions]
---

## Trigger

`ayk`: PR #81 (bd bmz) merged early at `c75814d`, before two later commits on
`claude/bmz-firestore-authorized-emails` were merged, so `origin/dev` was missing both.
Picked up as small, non-overlapping work.

## What shipped

Cherry-picked the two stranded commits onto a fresh branch off dev (preserving original
authorship), after verifying both were still absent from dev and the bug was live:

- `ef15eda` -- removes the stale duplicate `*Last updated: 2026-06-01*` footer at
  `docs/components/auth.md:121`, which contradicted the canonical 2026-06-04 header stamp
  (line 5) and could mis-flag the doc-freshness checker. Confirmed: after the cherry-pick
  the checker reports `auth.md: OK`.
- `04e6997` -- re-adds the missing PR #81 telemetry row to
  `docs/journal/harness_ledger.jsonl` (the ledger auto-merged with no conflict).

Both commits were already reviewed on #81's branch; this is a mechanical re-land, not new
work. Net diff: 2 files, +1/-2.

## Lessons

- **Merging a PR before its branch's later commits are pushed strands them.** They live
  on the feature branch but never reach dev; a follow-up cherry-pick is the clean
  recovery. Worth a glance at "are there commits ahead of the merge point?" before
  merging.

## Doc freshness

- `docs/components/auth.md` -- fixed (duplicate footer removed); checker now `OK`. Other
  freshness flags this session are stale-by-mtime from unrelated dev merges, untouched
  here.

## Files touched

- `docs/components/auth.md` -- removed duplicate Last-updated footer.
- `docs/journal/harness_ledger.jsonl` -- re-added PR #81 telemetry row.
