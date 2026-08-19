---
date: 2026-08-18
bead: polyglot-pdf-teizj
title: "docs+test(freshness): fix TRACKS_RE comment accuracy + add teizj/lm2oq coverage"
tags: [review, doctrine]
---

## Trigger

Following up on the review-flow wording sweep (bd r8d9r and siblings, PR
#604), the Opus outer reviewer on that PR filed two non-blocking beads
(polyglot-pdf-675f8, polyglot-pdf-lm2oq) about comment accuracy and missing
test coverage in `scripts/check_doc_freshness.py`. Scanning the backlog for
more low-complication work turned up two more beads in the same file/domain
(`polyglot-pdf-09e35`, a docstring overstatement; `polyglot-pdf-teizj`, a
doc silently exempt from the freshness scan) plus a fifth
(`polyglot-pdf-gz7dv`) that turned out to already be resolved. All five were
claimed together as one small, same-file, no-cross-surface batch.

## What shipped

- **bd 675f8**: fixed three sites that misdescribed which `**Tracks:**` text
  `TRACKS_RE.search()` actually matches in `docs/doc-architecture.md`.
  `parse_tracks()` uses `.search()` (first match only); the comments claimed
  it hits the file's fenced `**Tracks:**` example, but the real first match
  is the file's own intro prose mentioning the token. Verified by executing
  `parse_tracks()` against the real file (`['line', 'because', 'it', 'owns',
  'no']`), not just reading the code.
- **bd 09e35**: fixed `check_doc_conventions()`'s docstring, which claimed
  the tier-1 scan covers "docs/*.md top-level files" when `TIER1_DOCS` is
  exactly three named entries. Added a direct pin
  (`test_tier1_docs_is_exactly_the_three_named_entries`) asserting the list
  value itself, not just a paraphrase of it.
- **bd lm2oq**: `CONVENTION_ONLY_DOCS` (added by bd r8d9r) was a second
  membership list feeding `check_doc_conventions()`'s target union, with no
  prose pin -- unlike `DOC_DIRS`, which has a hard-won 5-site `_SITE_ANCHORS`
  battery from an earlier 6-round review saga. Added two tests pinning the
  two sites that enumerate the convention-scanned set.
- **bd teizj**: `docs/standards/schema-key-visibility.md` had no
  `**Tracks:**` line, so the freshness scan silently skipped it (treated as
  "no dependencies," never flagged STALE) instead of reporting OK/STALE.
  Added a real `**Tracks:**` line naming six source files, and a new test
  class (`TestEveryTier2DocHasTracksOrIsExempt`) pinning that every doc under
  `docs/standards/` and `docs/components/` has a Tracks line or is on an
  explicit exemption list.
- **bd gz7dv**: found already resolved on `dev` tip before this batch was
  claimed -- closed with no code change (see "What was already done" below).

## Lessons

Two mutation-verify traps surfaced in this batch, both worth generalizing:

1. **A fresh-eyes review found a real gap in my own claimed coverage.** My
   first pass reused `lm2oq`'s `CONVENTION_ONLY_DOCS`-focused tests to also
   claim `09e35`'s exit criterion 2 (pin the scanned-doc set) was satisfied.
   It wasn't -- those tests check a *different* assertion (that a docstring
   mentions a token), not that `TIER1_DOCS`'s membership itself is pinned.
   Reverting the corrected docstring wording left all tests green. The fix:
   a test must assert the actual claim the exit criterion names, not an
   adjacent one that happens to live in the same commit. "I added tests
   nearby" is not the same as "I pinned this specific criterion."
2. **My own stamp wording defeated its own mutation test.** The first draft
   of `teizj`'s new stamp read "added the `**Tracks:**` line above" -- which
   contains a literal `**Tracks:**` token, so `TRACKS_RE` matched the
   STAMP's own prose even after I deleted the real Tracks line in the
   mutation test, making the test pass when it should have failed. This is
   the same self-collision class that bit `docs/doc-architecture.md` in bd
   r8d9r (the file that defines the `**Tracks:**` convention keeps
   accidentally demonstrating it in prose). Generalizable rule: writing
   ABOUT a marker syntax in a doc that syntax also governs is a landmine;
   describe it without the literal token (e.g. "a tracked-source
   declaration" instead of "a `**Tracks:**` line") whenever the doc itself
   is subject to the check that parses for it.

## What was already done (bd gz7dv)

`PREVIOUSLY_CHAIN_RE`'s bare-`bd`-word false positive (`"earlier, bd is the
tracker"`) was already fixed and pinned
(`test_bare_bd_word_NOT_flagged_as_bead_id`) before this bead was claimed --
an earlier regex-tightening pass (bd 6dn2n/riffn era) evidently covered it
as a side effect. The residual `same day`/`Sprint N` false-positive gap
(`"prior: same day we shipped"`) is documented as a KNOWN ACCEPTED RISK in
the regex's own code comment (citing this bead by id) and pinned by
`test_same_day_sprint_residual_false_positive_documented`. Both of bd
gz7dv's exit criteria were satisfied on `dev` tip; closed directly rather
than doing redundant work.

## Doc freshness

- `docs/standards/schema-key-visibility.md` -- gained a real `**Tracks:**`
  line (6 files); now reports OK instead of being silently skipped.
- `scripts/check_doc_freshness.py` -- three comment sites and one docstring
  fixed for factual accuracy against the real code (no behavior change).
- `tests/test_doc_freshness.py` -- 5 new tests (105 total, up from 101),
  all mutation-verified non-vacuous.
- The outer cross-surface review filed two further, non-blocking, correctly
  out-of-scope findings during its trace: `polyglot-pdf-om8q6` (the doc's
  "Known gap" section misattributes a `Progress: N/M` template to
  `ai_context.py` when it actually lives in `backend/config.py` --
  pre-existing on `dev`, now surfaced because the doc is freshness-checked
  for the first time) and `polyglot-pdf-yznuk` (the new
  `TestEveryTier2DocHasTracksOrIsExempt` gate is presence-only -- it doesn't
  verify a Tracks line covers every file a doc actually makes claims about).
  Both filed as separate beads rather than folded into this PR.

## Files touched

- `docs/standards/schema-key-visibility.md` -- added `**Tracks:**` line +
  stamp bump (bd teizj)
- `scripts/check_doc_freshness.py` -- 3 comment sites fixed (bd 675f8) + 1
  docstring fixed (bd 09e35)
- `tests/test_doc_freshness.py` -- 5 new tests: TIER1_DOCS pin (bd 09e35),
  2 CONVENTION_ONLY_DOCS enumeration pins (bd lm2oq), 1 test class with 1
  test for the Tracks-line-or-exempt gate (bd teizj)
