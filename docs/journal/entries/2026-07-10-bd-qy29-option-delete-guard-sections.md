---
date: 2026-07-10
bead: polyglot-pdf-qy29
title: "schema-editor: option-delete guard now scans section-level show_if"
tags: [hotfix, testing]
---

## Trigger

Filed by the fresh-eyes reviewer during bd 6b7z: that bead gave FormSection a
typed show_if the group mutations actively rewrite, but the option-DELETE
guard (optionValueReferencedBy, consumed by FieldEditor's Remove button)
still scanned only schema.fields. Deleting an option that ONLY a section's
show_if referenced was silently allowed, stranding the section condition --
the same dangling-reference class 6b7z fixed for merge/ungroup/kind-flip/
retarget, on the delete path (out of 6b7z's scope by its own criterion).

## What shipped

- optionValueReferencedBy also scans schema.sections' show_if for a
  reference to (triggerFieldId, optionSlug). Sections report as
  human-readable `section "<label>"` entries (fields stay bare ids, the
  existing pinned behavior), so FieldEditor's blocked-reason message reads
  naturally with zero changes to the consumer.
- 4 new tests: section-only reference blocks the delete (incl. the
  wrong-slug-unblocked assertion); combined field+section listing;
  no-show_if sections never block; empty-label sections fall back to the
  section id in the message. Editor suite green; tsc clean.
- Fresh-eyes triage: round 1 (sonnet) NO-GAPS with two nits, both adopted
  (journal test-count corrected; empty-label fallback test added). Required
  Opus final round NO-GAPS. Outer review (Step 5.6): primary Opus NO-GAPS +
  second independent Opus NO-GAPS on the identical final diff. No beads
  filed.

## Lessons

- (Process) A compound Bash command chaining vitest into `npx tsc` hung
  silently for an hour -- npx can sit on an install prompt on Windows, and
  piping hid it. Run test/typecheck steps as separate commands with explicit
  ./node_modules/.bin binaries and timeouts.

## Doc freshness

- No component doc covers the editor's delete guard; nothing to bump.
  Pre-existing stale standards docs (tracking files this branch did not
  touch) reviewed and left per the "already stale before you" rule.

## Files touched

- schema-editor/src/utils/fieldGrouping.ts
- schema-editor/src/utils/fieldGrouping.test.ts
- docs/journal/entries/2026-07-10-bd-qy29-option-delete-guard-sections.md
