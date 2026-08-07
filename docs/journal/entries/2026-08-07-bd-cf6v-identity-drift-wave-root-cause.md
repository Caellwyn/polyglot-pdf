---
date: 2026-08-07
bead: polyglot-pdf-cf6v
title: "s18 C6: the W-7 identity-drift wave -- root cause + mass-drift collapse"
sprint: 18
tags: [schema-editor, postmortem, testing]
---

## Trigger

Sprint-18 C6 (epic polyglot-pdf-4qul): after the enrichment bake, EVERY W-7
field's guidance-identity hash read stale at once, ambering the whole kit and
eroding the confirm gate's credibility. The bead asked which bulk pipeline
step caused it (suspects: rename sweep / spoken_name strip / option re-bake)
and for either a re-stamping step or one kit-level re-check flag.

## What shipped

**Root cause (measured by recomputation against the shipped kit, not
inferred).** The wave was NOT a data sweep; none of the bead's suspects
caused it. Two mechanical causes:

1. **A hash-formula change shipped 25 minutes after the stamps were written,
   with no re-stamp.** W-7's 52 identity stamps were written by the PR #519
   gold-schema bake (2026-07-31 20:19) under the then-current 3-element
   payload `[name, spoken_name, sorted option triples]`. PR #518 (bd
   polyglot-pdf-stkz + its normalization follow-up) merged at 20:44 and
   appended the type token as a 4th element. Every stamp mismatched at once:
   51 of 51 guidance-carrying fields read stale; recomputing under the
   pre-#518 3-element payload makes 35 match again, with zero author edits in
   between. The append was self-justified by an inline "no shipped kit
   carries a baked identity_sha1 yet (0 of 44 provenance records)" check --
   true on #518's own base, false at merge time because #519 landed first.
   Nothing made the collision visible.
2. **Bake-time fossils underneath: 14 stamps were already stale the moment
   #519 was committed.** Recomputing the 3-element hash against #519's own
   field data shows 14 mismatches at commit time: several stamps describe the
   field ONE POSITION OVER (reason_h_details's stamp hashes treaty_country;
   treaty_country's hashes treaty_article_number -- the ivh9 off-by-one
   fossilized in bake metadata), the rest a pre-hand-verify identity (names /
   spoken_names edited after the bake ran, before the commit). Three more
   spoken_name edits and one new field landed after #519. These are the "14"
   in the previously-pinned 14 -> 51 jump; the formula change lit the rest.

**The fix (the bead's kit-level-flag option).** The causing "step" was a code
change, not a pipeline stage, so there is nothing to make re-stamp itself:

- `_check_guidance_identity_drift` (backend/services/schema_lint.py) now
  buffers per-field findings and counts matches. When >= 3 fields compared
  and EVERY one mismatched, it emits ONE kit-level
  `guidance-identity-mass-drift` WARNING (path `$`, no field anchor -- the
  pinned Form row) carrying the count and the re-bake remedy, and suppresses
  the per-field flags: 51 identical acknowledgment clicks confirm nothing and
  train editors to click through the gate. Any surviving match keeps the
  normal per-field flags (real hand edits leave survivors). Because
  publish_readiness's ack gate and the client staleness gate both key on the
  per-field finding, the collapse flows through both mirrors with no
  readiness or client logic change; the new rule got its label + remedy in
  schema-editor/src/utils/lintFindings.ts.
- `test_identity_payload_golden_pin_forces_a_migration_decision`
  (backend/tests/unit/test_guidance_contract.py) pins the exact payload
  serialization so the next formula edit fails a test whose docstring
  explains the blast radius and demands a same-commit migration decision.
- The old `_W7_EXPECTED_STALE` 51-id pin is replaced by
  `test_w7_wave_is_pinned_as_one_mass_drift_finding` (exactly one kit-level
  finding, zero per-field), keeping the went-dark / came-back tripwire.

Mutation-verified: collapse disabled, `matched == 0` guard dropped, `>= 3`
threshold dropped, and type token reverted each redden the suite
(2 / 1 / 10 / 1 failures). Full backend suite green (1774 passed) and
schema-editor lintFindings tests + tsc clean.

Clearing W-7 for real still means re-baking the guidance against the current
fields -- maintainer work already tracked (bd polyglot-pdf-im2u criterion 2,
bd polyglot-pdf-aliu). This bead deliberately does not touch the gold kit.

(Fresh-eyes triage breakdown filled at closeout.)

## Lessons

- A hash formula with persisted outputs is a wire contract with its own past:
  changing it invalidates every stored value, and a "no records exist yet"
  justification must be re-checked at MERGE time, not authoring time. The
  golden pin turns that re-check into a failing test.
- When every member of a set flips at once, per-member confirmation is
  noise; the legible unit is the set. (The same shape as the epic's
  one-truth thesis.)

## Doc freshness

No tier-1/2 doc tracks the lint rule inventory in prose beyond
schema_lint.py's own module docstring (updated in-file). No doc bumps owed.

## Files touched

- backend/services/schema_lint.py -- mass-drift collapse + rule docs
- backend/tests/test_schema_lint.py -- collapse/partial/small-kit tests; W-7
  pin reworked
- backend/tests/unit/test_guidance_contract.py -- golden payload pin
- schema-editor/src/utils/lintFindings.ts -- label + remedy for the new rule
- docs/journal/entries/2026-08-07-bd-cf6v-identity-drift-wave-root-cause.md
