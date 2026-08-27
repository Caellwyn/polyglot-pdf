---
date: 2026-08-27
bead: polyglot-pdf-l2kcp
title: "docs(context-compression): re-derive the tool-declaration count and compression figures"
tags: [context-compression]
---

## Trigger

The spell-back cutover (bd `polyglot-pdf-apkdl`) flipped
`SPELLBACK_TOOL_ENABLED` to default true, so a default continuous-mode
session now ships seven tool declarations, not six. Three sites were
named as still asserting the old count.

## What shipped

Checked all three named sites directly by executing the real builder
rather than assuming: `docs/technical_guide.md` and
`derive_compression_window`'s own docstring were already correct (fixed
by other work earlier this session). Only
`docs/components/context-compression.md` still had the stale count and
stale derived figures. Re-executed `derive_compression_window` against
today's shipped config and updated the doc's derivation paragraph,
parameters table, and stamp.

## Lessons

**Verify every named site before fixing any of them -- some may already
be done.** Two of the bead's three named sites were already correct,
fixed incidentally by unrelated work earlier in the same session. Running
the actual verification command the bead specified (rather than assuming
all three sites needed the same fix) meant the diff stayed narrowly
scoped to the one site that genuinely needed it.

**A doc's own adjacent, unrelated-looking claim can be wrong in the exact
same way the bead is fixing.** While rewriting the tool-declaration-count
paragraph, a separate sentence in the same paragraph ("the raw
settings.TOOL_DECLARATIONS is 6") turned out to also be wrong -- verified
by execution, not assumption. It happened to coincidentally read as
plausible next to the stale numbers it sat beside. Since the paragraph
was already being rewritten, fixing it there was cheaper and safer than
leaving a second wrong number next to the freshly corrected one.

**A reviewer flagging "these numbers look suspiciously unchanged" is a
legitimate question, not a bug -- but it demands an explicit answer in
the doc, not just quiet confidence.** A Haiku pass questioned why two
measurements two days apart produced identical figures. The honest
answer -- the function is deterministic and the inputs hadn't changed --
was already implicitly true, but the doc didn't SAY so. Making that
explicit (rather than dismissing the concern) is what actually resolved
it.

## Files touched

- `docs/components/context-compression.md` -- count, figures, stamp
  corrected
