---
date: 2026-08-28
bead: polyglot-pdf-uat6s, polyglot-pdf-hkce6
title: "docs(technical_guide): re-anchor 6 more drifted citations to symbol names"
tags: [doc-freshness, citations]
---

## Trigger

Two more bead-catcher findings from this session's own review chain: bd
`uat6s` (filed by the Opus cross-surface reviewer during bd `qt02i`/`a1g6f`'s
review) named 4 drifted `editor_kit_routes.py` citations in
`docs/technical_guide.md`; bd `hkce6` (filed during bd `6o2xn`/`31byq`/`n9uu9`'s
review) named 2 drifted `callback_handler.py` citations in the same file's
confirmation-audit section. Both pre-existing on `origin/dev`, unrelated to
any PR in this session's chain.

## What shipped

Re-anchored all 6 citations to symbol names (function names, or a nearby
comment/log-line quote) instead of bare line numbers, following the pattern
established earlier this session: `save_editor_kit_schema`,
`set_editor_kit_status` (containing both `FormSchema.model_validate` and its
`lint_schema` gate check), `get_editor_kit_schema` (the unvalidated-read
path), the `form_updated` send site, and the "Recorded" guard inside
`_handle_confirm_field_tool`. One citation (`request_coordinator.py:279` for
`request_confirm_field`) turned out to still be numerically accurate --
re-anchored to the symbol anyway, for the same durability reason as the rest.

## Lessons

Nothing novel -- the same citation-drift pattern this session has now fixed
several times over: a tier-2 doc's line-number citations rot on every
unrelated edit above them, `check_doc_freshness.py`'s citation checker can't
catch a citation landing on real-but-wrong code by design, and symbol-name
anchors are the only fix that doesn't need re-doing on the next edit.

## Files touched

- `docs/technical_guide.md` -- 6 citations re-anchored to symbol names across
  the schema-validation and confirmation-audit sections.
