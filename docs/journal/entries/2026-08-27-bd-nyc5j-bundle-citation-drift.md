---
date: 2026-08-27
bead: polyglot-pdf-nyc5j
title: "docs(technical_guide): re-anchor drifted config/service citations across 4 contracts"
tags: [doc-freshness]
---

## Trigger

Four narrow citation-drift beads (`nyc5j`, `eev3n`, `qn8wv`, `x6dq1`), each
found during earlier review passes this session, all pointed at the same
small set of drifted `<file>.py:<line>` citations in
`docs/technical_guide.md` and `docs/components/context-compression.md`.
Bundled into one PR since each is too small to warrant its own cycle.

## What shipped

Every named citation re-anchored to a symbol name. While enumerating the
same sections (CLAUDE.md scar #7), found and fixed several more drifted
citations not covered by any existing bead.

## Lessons

**This doc has now drifted the same way three times in three days**
(`x82ii` on 2026-08-17, `vdcm4` on 2026-08-27 for a different citation set,
and this bead redoing contract 2's citations `vdcm4` had also touched).
Line numbers in a doc describing actively-changing code are not a
maintenance cost that gets paid once -- they recur on a cadence set by how
often the underlying file changes, not by how carefully the last fix was
done. Symbol anchors don't eliminate the maintenance burden, but they
change its failure mode from silent-and-wrong to loud-and-missing (a
renamed symbol is a clear grep miss; a shifted line number is a citation
that still "resolves," just to the wrong thing).

**Fixing one citation next to a stale one can introduce a fresh
contradiction, not just leave an old one standing.** A review round caught
that a citation I'd just fixed directly contradicted an adjacent,
unfixed sentence describing the same variable -- both existed in the same
paragraph, and only one had been corrected. Enumerate-the-set discipline
needs to include immediate neighbors of anything already being touched,
not just the named targets.

**A stamp claiming "this fix covers contracts X" is itself a testable
claim, and got it wrong twice before landing on the right answer.**
Verifying it precisely -- mapping every diff hunk's line number to the
section it falls in via the document's own headers -- took an explicit,
mechanical cross-check rather than eyeballing which paragraphs "felt"
touched.

## Files touched

- `docs/technical_guide.md` -- citations re-anchored across contracts
  1, 2, 4, 11
- `docs/components/context-compression.md` -- injection-budget citation
  re-anchored
