---
date: 2026-07-10
bead: polyglot-pdf-v76t
title: "Bundled review-nit cleanup: v76t + 715i + pofh"
tags: [hotfix, testing]
---

## Trigger

Three tiny beads filed by today's review rounds, bundled into one PR per the
deferred-nit convention (several nit beads = prime candidates for one
cleanup PR): v76t (three notes from n3mn's outer review), 715i (one note
from dr1l's Opus round), and pofh (filed by the n3mn Opus reviewer itself).

## What shipped

- v76t.1: `_retarget_unwrapped_conditions` now also walks SECTION-level
  show_if -- a section condition referencing an unwrapped lone-option
  checkbox by its old option value stayed model-valid but semantically dead
  (a boolean trigger never equals the vanished value).
- v76t.2: the contract-sync test's old-shape guard asserted the
  double-brace spelling (`"label": str}}`) which can never appear in
  RENDERED output (the source's f-string braces collapse) -- a dead
  assertion, now the single-brace form that actually bites.
- v76t.3: synthesized supplement ids de-duplicate (suffix _2, _3 ...)
  against both other synthesized ids and explicit ones.
- 715i: PdfPreviewFallback drops its pdf-preview-modal* secondary-hook
  classNames; the inline styles are the whole contract, and a stale
  chunk-CSS height:100% rule could otherwise bind in the
  opened-once-then-failed scenario and stretch the notice full-height.
- pofh: `_repair_overflow_supplement` now also runs on the multi_entry
  sub-config (the same SupplementType enum lives there); an invented value
  aliases/drops exactly like the field-level key.
- 3 new tests; repair/contract-sync/migrate suites 77 green; schema-forms +
  pdf-view 25 files / 601 green.
- Fresh-eyes triage: round 1 (sonnet) cleared all five criteria with two
  informational notes -- the sibling pane fallback's harmless className
  (left; its CSS rule carries no risky properties) and a PRE-EXISTING
  latent gap (section show_if never goes through slug-mint alias
  resolution), which the orchestrator filed as bd polyglot-pdf-ei8b.
  Required Opus final round NO-GAPS. Outer review (Step 5.6): two
  independent Opus NO-GAPS on the identical final diff.

## Lessons

- A guard assertion that can never match is worse than none -- it reads as
  coverage. When pinning rendered output, assert against the RENDERED form,
  not the source spelling.

## Doc freshness

- Nothing tracks these internals; pre-existing stale standards docs
  (tracking files this branch did not touch) reviewed and left per the
  "already stale before you" rule.

## Files touched

- backend/services/schema_repair.py
- tests/test_schema_repair.py
- tests/test_schema_contract_sync.py
- frontend/src/schema-forms/components/PdfPreviewFallback.tsx
- docs/journal/entries/2026-07-10-bd-v76t-bundled-nit-cleanup.md
