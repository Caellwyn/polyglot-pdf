---
date: 2026-08-19
bead: polyglot-pdf-lt5il
title: "docs(genai): fix stale compression DEAD END entry"
tags: [review]
---

## Trigger

Continuing the low-complication-bead sweep: `docs/genai_docs/README.md`'s
"Hard-won facts" section carried a "DEAD END: contextWindowCompression is
an unreleased/unsupported stub" entry instructing readers to "keep
CONTEXT_COMPRESSION_ENABLED=False; do not re-investigate" -- the exact
opposite of shipped behavior. `genai_docs/` is CLAUDE.md's cited
authoritative SDK reference for any `google-genai` work, so this was a
tier-2-adjacent doc actively teaching the wrong default to a future agent,
and it directly contradicted `docs/standards/logging-and-cost.md`'s cost
invariant, which explicitly depends on compression being ON.

## What shipped

Verified `backend/config.py:278` defaults `CONTEXT_COMPRESSION_ENABLED`
`true`, and `:496-497` defaults `CONTEXT_COMPRESSION_DERIVE_FROM_SI_FLOOR`
`true`. The original dead-end verdict (bd `l3a.1`, 2026-06-04) was real at
the time -- the SDK type existed ahead of the server implementation and
never evicted -- but a later SDK version bump (1.38.0) shipped real
native-audio eviction, confirmed by re-measurement in
`docs/components/context-compression.md` (3/3 twenty-turn runs, multiple
evictions each, 54-74% below the unbounded baseline).

Rescoped the entry: kept the original dead-end finding as historical
methodology context (what a false-negative compression trace looks like --
still valuable, since the file's very next bullet draws a generalizable
lesson from it: "an SDK type's existence is not evidence the feature is
implemented"), removed the "keep it disabled" instruction, and pointed at
`context-compression.md` for current state.

## Lessons

None of this session's usual mutation-verify or set-enumeration lessons
apply here -- this was a straightforward stale-fact correction. The one
thing worth naming: when correcting a stale claim that's followed by a
lesson DERIVED from that claim (the SDK-introspection-isn't-implementation
bullet), check that the lesson still reads coherently once the claim above
it is reframed -- it did here, since the lesson is about the *shape* of the
mistake (trusting SDK introspection over live verification), not about
compression being permanently broken.

## Doc freshness

- `docs/genai_docs/README.md` -- carries no `*Last updated:*` stamp (not in
  `TIER1_DOCS` or `DOC_DIRS`); no stamp change applicable.

## Files touched

- `docs/genai_docs/README.md` -- rescoped the compression DEAD END entry to
  historical context, removed the stale "keep it disabled" instruction,
  pointed at `docs/components/context-compression.md` for current state
