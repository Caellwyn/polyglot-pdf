---
date: 2026-07-10
bead: polyglot-pdf-6b7z
title: "schema-editor: group merge/ungroup/kind-flip now rewrite section-level show_if"
tags: [hotfix, testing]
---

## Trigger

Editor-wide limitation surfaced by the Opus outer review during bd 8qfj (the
group-kind flip): the editor's group mutations rewrote dependent FIELD
show_if/require_if across a group change but never a SECTION-level show_if.
The backend validates a section's show_if with the same operator/trigger
matrix as a field's, so a loaded kit whose section is gated on a group would
strand a checkbox_group-only `includes` on a radio (or the reverse) after a
kind flip / merge / ungroup and be rejected at promotion. Latent for
editor-authored kits (the editor never authors section show_if); live for
onboarded kits, whose section show_if survives the editor only by raw-JSON
passthrough (verified: loadSchema/loadRemoteSchema cast response.json()
directly; sections are only ever shallow-spread; stripEditorState touches
only fields).

## What shipped

The bead's exit criterion offered rewrite-or-document; REWRITE was chosen
(the passthrough means real kits carry section conditions the editor could
strand -- documenting the hole would leave a live promotion-rejection path).

- FormSection gains a typed `show_if?: FieldCondition`, commented with the
  backend truth (sections accept only the legacy single-atom shape,
  form_models.py:627; union typing so a hand-edited composite is handled
  defensively rather than crashing).
- All four group mutations now treat a section's show_if exactly like a
  dependent field's: mergeFields rewrites + stashes originals (new
  `sections` entry in the _ungroup stash, same had_* sentinel convention);
  ungroupField restores stashed originals verbatim (lossless path) or
  remaps atoms (fallback path, via remapFallbackCondition extracted from
  remapFallbackDependent so the composite-vs-legacy dispatch is shared);
  changeGroupKind flips section atoms; retargetOptionValueReferences takes
  an optional sections param and returns {fields, sections}.
- One production call-site chain updated for the new retarget signature
  (FieldEditor -> App onUpdateFields widened to optionally carry sections).
- A `?? []` guard on the stash's sections entry (readStash is an
  unvalidated cast; the stash is session-only but the guard is free).
- Implementation delegated to a Sonnet subagent (model-tiering); diff
  reviewed by the orchestrator, which added the stash guard.
- 10 new tests; editor suite 37 files / 658 tests green (648 baseline);
  tsc clean.
- Fresh-eyes triage: round 1 (sonnet) cleared the rubric, filed one
  out-of-scope bug itself (bd polyglot-pdf-qy29: the option-delete guard
  optionValueReferencedBy never scans sections) and noted one test nit
  (adopted: the round-trip test now pins membership + show_if restore
  together). Opus clearing round 1 found a REAL in-scope gap: a
  radio->checkbox_group flip on a group whose SECTION show_if carried a
  fully-live top-level in/not_in expanded it into an any_of composite the
  backend rejects on sections, and hasUnflippableListMembership never
  scanned sections. Fixed (sections scan blocks ANY list-membership atom on
  the group; fields keep the expandable-list allowance) + a test pinning the
  block. Opus clearing round 2 on the updated diff: NO-GAPS. Outer review
  (Step 5.6): primary Opus NO-GAPS + second independent Opus NO-GAPS on the
  identical final diff (both flagged only this journal's then-stale test
  count, corrected here).

## Lessons

- A "the editor does not support X" gap can still be a live bug when the
  load/save path passively round-trips X: the editor then actively corrupts
  what it silently carries. Passive passthrough + active mutation of
  neighbors is the pattern to look for.

## Doc freshness

- No component doc covers the schema-editor's grouping internals; nothing
  to bump. Pre-existing stale standards docs (tracking files this branch
  did not touch) reviewed and left per the "already stale before you" rule.

## Files touched

- schema-editor/src/types/schema.ts
- schema-editor/src/utils/fieldGrouping.ts (+ .test.ts)
- schema-editor/src/components/FieldEditor.tsx
- schema-editor/src/App.tsx
- docs/journal/entries/2026-07-10-bd-6b7z-section-showif-rewrites.md
