---
date: 2026-08-19
bead: polyglot-pdf-om8q6
title: "docs(schema-key-visibility): fix Progress: N/M misattribution"
tags: [review]
---

## Trigger

Filed by the Opus outer cross-surface reviewer on PR #606 (the doc-freshness
Tracks-coverage batch) as a pre-existing, out-of-scope finding: bd teizj
gave `docs/standards/schema-key-visibility.md` a real `**Tracks:**` line for
the first time, which made the doc freshness-checked for the first time --
surfacing an existing misattribution in its "Known gap" section that had
been invisible while the doc was silently skipped.

## What shipped

`docs/standards/schema-key-visibility.md`'s "Known gap" section claimed the
backend's unfiltered `Progress: N/M` SI render lives in `ai_context.py`.
Verified directly: `grep -n "Progress:" backend/config.py` finds the
template string at line 993; the same grep against `ai_context.py` finds
nothing. Corrected the citation to `backend/config.py` and added that file
to the doc's `**Tracks:**` declaration, so an edit to the real template file
now flags this doc STALE instead of staying silently unwatched.

## Lessons

This is a small instance of a pattern worth naming: a doc that's been
silently exempt from freshness checking (no `**Tracks:**` line) can
accumulate factual drift invisibly, because nothing ever forces a review of
it. The moment a doc like that gets a Tracks line for the first time (as bd
teizj did for this file), it's worth expecting -- not just hoping -- that
the outer review will surface pre-existing content bugs the silent-skip had
been hiding. That happened here exactly as expected.

## Doc freshness

- `docs/standards/schema-key-visibility.md` -- stamp bumped; `**Tracks:**`
  line now includes `backend/config.py` alongside its existing five entries.
  Live checker confirms `OK` (not STALE, not skipped).

## Files touched

- `docs/standards/schema-key-visibility.md` -- corrected citation + Tracks
  line + stamp bump
