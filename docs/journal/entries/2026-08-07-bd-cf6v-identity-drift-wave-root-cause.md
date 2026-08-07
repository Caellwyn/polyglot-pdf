---
date: 2026-08-07
beads: [polyglot-pdf-cf6v]
tags: [schema-editor, lint, guidance, provenance, root-cause]
surfaces:
  - backend/services/schema_lint.py
  - backend/services/guidance_contract.py (tests only)
  - schema-editor/src/utils/lintFindings.ts
---

# bd cf6v: the W-7 whole-kit identity-drift wave -- root cause + containment

Sprint-18 C6 (epic polyglot-pdf-4qul). The question: which bulk pipeline step
changed EVERY W-7 field's identity hash after the enrichment bake, ambering
the whole kit at once and eroding the confirm gate's credibility.

## Root cause (measured, not inferred)

The wave was NOT a data sweep. None of the bead's suspects (rename sweep /
spoken_name strip / option re-bake) caused it. Two mechanical causes, both
reproduced by recomputation against the shipped kit:

1. **A hash-formula change shipped 25 minutes after the stamps were written,
   with no re-stamp.** W-7's 52 identity stamps were written by the PR #519
   gold-schema bake (2026-07-31 20:19) under the then-current 3-element
   payload `[name, spoken_name, sorted option triples]`. PR #518 (bd
   polyglot-pdf-stkz + the follow-up normalization) merged at 20:44 and
   appended the type token as a 4th element. Every stamp mismatched at once:
   51 of 51 guidance-carrying fields read stale today; recomputing under the
   pre-#518 3-element payload makes 35 of them match again, with zero author
   edits in between. The append was self-justified by an inline "no shipped
   kit carries a baked identity_sha1 yet (0 of 44 provenance records)" check
   -- true on #518's own base, false at merge time because #519 landed first.
   Nothing made the collision visible.

2. **Bake-time fossils under that: 14 stamps were already stale the moment
   #519 was committed.** Recomputing the 3-element hash against #519's own
   field data shows 14 mismatches at commit time: several stamps describe the
   field ONE POSITION OVER (`reason_h_details`'s stamp hashes
   `treaty_country`; `treaty_country`'s hashes `treaty_article_number` -- the
   ivh9 off-by-one fossilized in bake metadata), and the rest describe a
   pre-hand-verify identity (names/spoken_names edited after the bake ran,
   before the commit). Three more spoken_name edits and one new field landed
   after #519. These 14+4 are the "14" in the previously-pinned 14 -> 51
   jump; the formula change lit up the other 37.

## The fix: mass waves collapse to ONE legible kit-level finding

The bead offered two remedies (re-stamp the causing step, or one kit-level
flag instead of N field flags). The causing "step" was a code change, not a
pipeline stage, so there is nothing to make re-stamp itself; the kit-level
flag is the shipped fix, plus a tripwire so the next formula change cannot be
silent:

- `_check_guidance_identity_drift` (schema_lint.py) now buffers per-field
  findings and counts matches. When >= 3 fields were compared and EVERY one
  mismatched, it emits ONE kit-level `guidance-identity-mass-drift` WARNING
  (path `$`, no field anchor -- renders on the pinned Form row) carrying the
  count and the re-bake remedy, and suppresses the per-field flags: 51
  identical acknowledgment clicks confirm nothing and train editors to click
  through the gate. Any single surviving match keeps the normal per-field
  flags (real hand edits leave survivors). Accepted tradeoff, stated in the
  docstring: a deliberate every-field rename sweep also collapses -- a sweep
  that big warrants a kit-level re-verify anyway.
- Because publish_readiness's ack gate and the client's staleness gate both
  key on the per-field finding, the collapse flows through both one-truth
  mirrors with no readiness/client change. The kit-level WARNING informs; it
  does not block publish (blocking would rebuild the 51-click wall as one
  unremovable lump; the maintainer can re-bake to clear it).
- `test_identity_payload_golden_pin_forces_a_migration_decision`
  (unit/test_guidance_contract.py) pins the exact payload serialization, so
  the next formula edit fails a test whose docstring explains the blast
  radius and demands a same-commit migration decision.
- The old `_W7_EXPECTED_STALE` 51-id pin is replaced by
  `test_w7_wave_is_pinned_as_one_mass_drift_finding` (exactly one kit-level
  finding, zero per-field), keeping the went-dark / came-back tripwire.

Mutation-verified: disabling the collapse, dropping the `matched == 0` guard,
dropping the `>= 3` threshold, and reverting the type token each turn the
suite red (2 / 1 / 10 / 1 failures respectively).

## Clearing W-7 for real

The wave is now one finding, but clearing it still means re-baking the
guidance against the current fields -- maintainer work already tracked (bd
polyglot-pdf-im2u criterion 2, bd polyglot-pdf-aliu). This bead deliberately
does not touch the gold kit (never edit a gold kit without permission).
