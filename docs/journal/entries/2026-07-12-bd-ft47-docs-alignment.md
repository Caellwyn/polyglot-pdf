---
date: 2026-07-12
bead: polyglot-pdf-ft47
title: "Tier-2 docs state continuous-DTI as the law + section-reset as the deprecated fallback"
sprint: 11
tags: [conventions, doctrine]
---

## Trigger

Sprint-11 epic polyglot-pdf-fc7t child C8 (the epic finale). Several tier-2/1
docs still framed section-reset as "the default" and continuous-DTI as an
"opt-in / unvalidated candidate", with three outright-false "flag defaults
false" claims contradicting config.py (all three default TRUE since bd 7872).

## What shipped

Scope adjusted for the deprecate-not-delete decision (C7/55jg deprecated
section-reset in place rather than deleting): docs state continuous-DTI as the
law/default AND section-reset as a DEPRECATED-but-LIVE fallback (not "gone"),
all pointing at docs/standards/section-reset-deprecation.md.

Eight docs aligned:
- context-compression.md (the heaviest -- an entire "should we enable
  compression? epic hcsl decides, don't assume the answer" investigation
  framing, now the shipped-default record: STATUS block, the section-reset-as-
  current comparison table, the flag-table row, and the "success criteria for
  ENABLING (owned by hcsl)" section all rewritten to state the resolved
  outcome).
- si-reduction.md + technical_guide.md: the USE_DTI "default false / demo sets
  it" claims -> default TRUE; technical_guide gained CONTINUOUS_SESSION +
  CONTEXT_COMPRESSION_ENABLED env-table rows (were omitted).
- terminology.md: Section is a DISPLAY division, not the conversation/navigation
  unit; the switch_section/currentSectionId/completedSections vocabulary is the
  deprecated fallback.
- voice-ai.md + tool-call-flow.md: switch_section marked DEPRECATED (dropped in
  continuous mode); the "delivers its response on the OLD session" mechanic
  noted as fallback-only.
- schema-forms.md: currentSectionId/completedSections inert in continuous mode,
  manual prev/next suppressed (sections still page the UI).
- websocket-routing.md: the whole Section-switch-flow section headed as the
  DEPRECATED fallback with a continuous_session_enabled note.

Last updated bumped on all eight (Prior: inline stamps, no history chains --
doc-conventions check clean). ws-protocol.md was already correct (the reference
the others aligned to). INDEX already discoverable (sprint-11 plan row +
context-compression component + section-reset-deprecation standard).

## Lessons

- A docs-alignment pass that follows a design REVERSAL (deprecate, not delete)
  differs from the originally-planned "post-deletion truth": docs must describe
  the fallback as LIVE-but-deprecated, not absent -- getting this wrong would
  document code as gone while it still runs.
- The doc-freshness checker's STALE flag is an mtime-vs-timestamp compare, not a
  content judgment: same-day source edits (this session's schemaFormState.ts
  deprecation markers) re-flag a doc even after a same-day bump. The
  content-bearing gate is the conventions + sprint-archive check.

## Doc freshness

The eight target docs bumped + verified content-current. The checker still
flags them STALE against schemaFormState.ts (edited 19:14 this session, already
merged) -- a same-day mtime artifact, content is current. Other STALE flags
(auth, ai-models, config-deployment, jit-schema, etc.) track files this branch
never touched -- pre-existing, out of scope.

## Files touched

- docs/components/{context-compression,schema-forms,tool-call-flow,voice-ai,websocket-routing}.md
- docs/standards/{si-reduction,terminology}.md
- docs/technical_guide.md
- docs/journal/entries/2026-07-12-bd-ft47-docs-alignment.md (this)
