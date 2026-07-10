---
date: 2026-07-10
bead: polyglot-pdf-c3y6
title: "schema_repair mirrors controls_fields into targets' show_if/require_if; extractor contract forbids the key"
tags: [hotfix, testing]
---

## Trigger

Split from bd polyglot-pdf-6s71 (overnight session decision): the extractor
LLM emits controls_fields (removed at the P6.2 v2 flip, bd h76m.16) -- the
aw1u paid i-90 re-extraction hit it on 12 fields. schema_repair.py
deliberately declined to convert it, so v2-stamped drafts lint ERROR
legacy-trigger-side-logic and land RED; a contractor onboarding any new form
with conditional logic had to hand-convert every edge. 6s71's remaining exit
criterion (a FRESH paid extraction produces 0 such errors) needs a
maintainer-sanctioned Vertex run, so the code shipped under this new bead
and 6s71 is now blocked by it.

## What shipped

- New shared module backend/services/controls_fields_mirror.py holding the
  proven migrate_schema_v2 Pass-4 helpers (control_condition /
  target_has_condition / add_target_condition + a mirror_controls_fields
  orchestrator), extracted verbatim: key-specific already-mirrored
  suppression, pure-any_of append vs whole-condition any_of wrap, dangling
  targets and the four unconvertible actions (hides/locks/unlocks/
  makes_optional) reported rather than silently dropped.
- scripts/migrate_schema_v2.py Pass 4 now delegates to the shared module;
  behavior unchanged (its 21 tests pass untouched). Import direction is
  scripts -> backend, the existing safe one.
- backend/services/schema_repair.py gained the mirroring step in its
  per-field loop: each mirrored atom is routed through repair's OWN
  _rewrite_atom machinery (the resolution/alias map) so it gets identical
  slug/operator aliasing to every other repaired atom; repairs-list entries
  log mirror / dangling (error: True) / unmirrored / drop events.
  conditional_fields (a plain legacy id list with nothing to mirror into)
  is dropped + logged. Both keys popped unconditionally.
- Prompt side: scripts/bakeoff/schema_contract.py stops documenting
  controls_fields as emittable and explicitly forbids it (teach target-side
  show_if/require_if); arm_llm_native.py build_fewshot rel_keys no longer
  showcases a controls_fields exemplar.
- Notable subtleties (implementer-reported, orchestrator-verified in the
  diff): the raw mirrored atom always carries the "value" key (even None)
  because _rewrite_atom_value's emptiness check distinguishes key-absent
  from present-as-None; the standalone-checkbox equals->is_checked fixup
  lives in the shared core; repair's mirroring is not v2-gated (matches
  Pass 4) which also improved the w7_broken_draft fixture (4 dependent
  show_ifs now correctly gain mirrored edges).
- Implementation delegated to a Sonnet subagent (model-tiering); diff
  reviewed by the orchestrator.
- 12 new repair tests incl. cross-checking mirrored output against
  migrate_schema_v2 on identical input, and idempotency. Suites: repair
  27/27, migrate 21/21 unchanged, contract-sync 11/11, harness tests/
  798 passed / 1 skipped, backend/tests 982 passed / 2 skipped.
- Fresh-eyes triage: (filled at closeout -- see below)

## Lessons

- When a migration owns the only proven implementation of a transform,
  extract-and-share beats reimplement-in-repair: the repair step inherited
  every hard-won edge case (key-specific suppression, any_of wrap,
  unconvertible-action reporting) for free, and the migration's own tests
  pin the extraction did not drift.

## Doc freshness

- No component doc tracks schema repair internals; nothing to bump.
  Pre-existing stale standards docs (tracking files this branch did not
  touch) reviewed and left per the "already stale before you" rule.

## Files touched

- backend/services/controls_fields_mirror.py (new)
- backend/services/schema_repair.py
- scripts/migrate_schema_v2.py
- scripts/bakeoff/schema_contract.py
- scripts/bakeoff/arm_llm_native.py
- tests/test_schema_repair.py
- docs/journal/entries/2026-07-10-bd-c3y6-controls-fields-repair.md
