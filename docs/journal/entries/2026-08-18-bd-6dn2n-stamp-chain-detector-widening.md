---
date: 2026-08-18
bead: polyglot-pdf-6dn2n
title: "docs+test(freshness): widen the stamp-chain detector to Prior:/Earlier: + docs/doctrine"
tags: [conventions, testing]
---

## Trigger

Picking up another batch of low-complication ready beads, found a cluster of
four filed around the same underlying gap: `scripts/check_doc_freshness.py`'s
stamp-chain checker only matched the literal `Previously:` spelling, so a
chain written as `Earlier:` or `Prior,` passed it silently, even though
`doc-architecture.md` section 3 is explicit the rule bans the pattern, not
the keyword. Two of the four filed beads (`cqyke`, `f6wb6`) turned out to
already be resolved by an unrelated later PR (#593) -- verified against
current `dev` before touching anything, not assumed from the bead text.

## What shipped

- Enumerated every tier-1/2 doc against the real pattern (not just the
  individually-named files) and found the complete current set was 4 files,
  not the 2-3 each surviving bead separately claimed: `validation-delegation.md`,
  `context-compression.md`, `pdf-filling.md` (found during this enumeration,
  named by no bead), and `review-flow.md` (also never convention-scanned at
  all, since `DOC_DIRS` excluded `docs/doctrine` entirely despite the closeout
  skill already treating it as tier 2).
- Widened `PREVIOUSLY_CHAIN_RE` to catch `Prior:`/`Prior,`/`Earlier:`/`Earlier,`
  followed by a date, `Sprint NN`, "same day/week", or a bead-id reference,
  and added `docs/doctrine` to `DOC_DIRS`.
- Pruned all 4 real chains to single current-state stamps, moving any
  still-load-bearing fact into body prose (verified each was already
  duplicated there before pruning).
- **Fresh-eyes round 1** found two gaps: the finding message still hardcoded
  `'Previously:' chain detected` even for an `Earlier:` match, and the new
  `docs/doctrine` DOC_DIRS membership was unpinned by any test (mutation-
  verified: reverting it left the suite green). Both fixed inline.
- **Outer Opus review round 1** found something more consequential: bumping
  two of the four stamps to today's date had silently cleared a REAL
  pre-existing STALE warning against backend files (`config.py` etc.) that
  had moved ~10 days after the original 2026-08-08 stamp -- exactly the trap
  `.claude/skills/closeout/SKILL.md:183` names ("if a stale doc tracks files
  your branch did NOT touch, leave it"). A prose-only chain-prune is not a
  content re-verification, so the date bump was unearned. Reverted both
  dates, added a NOTE explaining why the date stays put, and left the
  genuinely-stale content flagged for a real follow-up. Also found a second,
  smaller bug the review itself surfaced: the widened bead-id alternative
  false-positived on ordinary prose containing the bare word "bd" (e.g.
  "earlier, bd is the tracker") -- tightened to require the actual bead-id
  shape (backtick-quoted or hyphenated token). Two residual false-positive
  shapes ("Prior: same day...", "Earlier, Sprint N...") are accepted as a
  documented, zero-current-occurrence risk.
- **Outer Opus review round 2** (after both fixes) returned NO-GAPS,
  independently re-executing the checker against both branches rather than
  trusting the diff's own claims, and filed one more non-blocking nit
  (3 sibling comment/docstring sites in `check_doc_freshness.py` still
  enumerate the pre-widening `DOC_DIRS` set -- `polyglot-pdf-3t190`).
- Fixed a missing `import pytest` the new `@pytest.mark.parametrize`
  decorators exposed (the file previously only used `pytest.skip` inside a
  function body, so the absent import never surfaced at collection time).

## Lessons

- **A checker widening that fixes real drift can itself create new drift, in
  the same commit, in the same file.** Widening `DOC_DIRS` made
  `doc-architecture.md`'s own description of the scanned set false; the outer
  reviewer caught it. A widening PR should grep its OWN file for every
  sibling mention of the thing it just changed, not just the primary
  docstring -- three more sites survived a first pass and needed a second
  outer round to surface (`polyglot-pdf-3t190`).
- **A stamp-chain PRUNE and a stamp-date BUMP are two different claims, and
  conflating them silently defeats the staleness gate.** Removing chain
  prose from a stamp is a pure formatting fix; moving the date forward
  asserts "I re-verified this content is current," which a formatting-only
  pass has not earned. The checker cannot tell the difference -- it trusts
  whatever date is on the line -- so the discipline has to be the author's:
  bump the date only when the content claims were actually re-checked
  against the tracked code, not whenever the stamp text changes for any
  reason.
- **Mutation-verifying a REGEX false-positive fix needs the false-positive
  case as a test, not just the true-positive case.** The first widening
  round proved the new alternatives caught real violations; it never asked
  whether they ALSO caught things that shouldn't match. The outer reviewer
  found that gap by generating adversarial inputs the diff's own tests never
  tried -- exactly the value the outer/inner split is designed to add.

## Doc freshness

- **Bumped (genuinely current):** `docs/components/pdf-filling.md`,
  `docs/doctrine/review-flow.md`, `docs/doc-architecture.md`.
- **Deliberately NOT bumped, chain pruned but date kept at 2026-08-08:**
  `docs/components/context-compression.md`, `docs/standards/validation-delegation.md`
  -- both genuinely stale against tracked backend files; a NOTE in each
  stamp explains why the date is unchanged. Left for a real re-derivation
  pass (out of this bead's scope).

## Files touched

- `docs/standards/validation-delegation.md`
- `docs/components/context-compression.md`
- `docs/components/pdf-filling.md`
- `docs/doctrine/review-flow.md`
- `docs/doc-architecture.md`
- `scripts/check_doc_freshness.py`
- `tests/test_doc_freshness.py`
