---
title: "check_doc_freshness: scan tier-1 docs + accept comma-separated Tracks lines"
bead: polyglot-pdf-gfb.3
date: 2026-05-30
tags: [docs-reorg, ci, scripts, bugfix, doc-freshness]
bd: gfb.3
---

# gfb.3 — doc-freshness: scan tier-1 docs + accept comma-separated Tracks lines

Two coupled bugs in `scripts/check_doc_freshness.py`, both surfaced while
writing tier-1 `docs/technical_guide.md` (gfb.2).

## Bug 1 — tier-1 freshness never enforced

`main()`'s per-doc **freshness** loop iterated `find_docs()`, which only
globbed `DOC_DIRS` (`docs/components`, `docs/standards`). So a tier-1 doc
with a valid `**Tracks:**` line — `technical_guide.md` tracks
`backend/main.py`, `config.py`, `routes/*.py`, `firebase.json`,
`deploy-*.sh` — was **never** checked for staleness. The module docstring
claimed the scan covered TIER1_DOCS, but only `check_doc_conventions()`
(the `Previously:` / history-heading regexes) actually included them; the
freshness/Tracks half was gapped.

The bead asked to verify whether the convention checks were also gapped —
they were **not**: `check_doc_conventions()` already prepended TIER1_DOCS
explicitly, and `tests/test_doc_freshness.py` covered that. Only freshness
was missing tier-1.

Latent extra: `main()` early-returns "No docs to check" when `find_docs()`
is empty, so when components/ + standards/ were both empty (early in the
docs-reorg) the checker did nothing at all — tier-1 included.

**Fix:** `find_docs()` now prepends `find_tier1_docs()` (the on-disk subset
of TIER1_DOCS) before globbing DOC_DIRS, then dedupes. The freshness loop,
the convention check, and the empty-guard all flow through it.
`check_doc_conventions()` keeps its own explicit TIER1_DOCS prepend + dedup
so an explicit `docs=[...]` test list (which omits tier-1) still applies
conventions to tier-1.

## Bug 2 — comma-separated Tracks tokens matched no files

`parse_tracks()` split on whitespace and stripped backticks but **not**
trailing commas. A comma-separated line (`` `a.py`, `b.py` ``) yielded
tokens like `a.py,` that matched no files → spurious "matched no files"
warnings. `technical_guide.md`'s Tracks line uses commas; the warning was
masked only because bug 1 meant the doc was never scanned. (`terminology.md`
sidestepped this by using space-separated tokens.)

**Fix:** split on `[\s,]+` and `strip("`,")` each token. Both styles now
parse identically — no need to de-comma `technical_guide.md`.

## Verification

- `technical_guide.md` now appears in checker output (`OK`, no spurious
  warnings) where it was previously absent entirely.
- 38 tests (was 32). The two regression tests
  (`TestParseTracks::test_comma_separated_strips_trailing_commas`,
  `TestFreshnessScanCoversTier1::test_stale_tier1_doc_with_tracks_is_flagged`)
  were confirmed to **fail** against the un-fixed code, so they genuinely
  guard the fix. The bead's acceptance criterion — an intentionally-stale
  stamp on a tier-1 doc with a Tracks line gets flagged, with CI coverage —
  is pinned by the latter.
