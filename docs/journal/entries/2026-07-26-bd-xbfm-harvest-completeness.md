---
date: 2026-07-26
bead: polyglot-pdf-xbfm
title: "R4: harvest completeness -- unlocks/hides convert, locks/makes_optional retained loud (sprint 15)"
tags: [extraction, conventions]
---

## Trigger

Sprint-15 R4 (epic o2bs crit 4, zero silent drops): the repair mirror
converted only shows/makes_required; the four remaining trigger-side actions
(hides/locks/unlocks/makes_optional) were dropped with a report entry a human
would only see in the repair log -- invisible to lint.

## What shipped

- **`backend/services/controls_fields_mirror.py`** (pure, additive): new
  `REPAIR_CONVERTIBLE_ACTIONS` contract + helpers -- `unlock_descriptor()`
  (the gold i-90 shape), `negated_atom_present()` (polarity-aware none_of
  check; `target_has_condition` flattens all buckets so it cannot tell a
  positive occurrence from a negated one), `add_target_negated_condition()`
  (AND-NOT composition: none_of on a bare target, append into a pure AND
  composite, else wrap `{all_of:[existing], none_of:[atom]}`).
  `MIRRORABLE_ACTIONS` / `UNCONVERTIBLE_ACTIONS` are deliberately UNTOUCHED:
  they are the pinned migrate contract (proven v1->v2 migration, unchanged --
  its 35 tests pass unmodified) and the merged scorer sync test compares
  against them.
- **`backend/services/schema_repair.py`**: after the shows/makes_required
  mirror, a repair-time conversion pass:
  - `unlocks` -> the COMPLETE gold unlock descriptor on the target
    (`conditional_behavior {unlock_method: flip_readonly_bit,
    pdf_field_flag_change: {bit 0, 1 -> 0}}`) + the trigger condition as a
    show_if alternative. Fresh-eyes round 1 caught the first draft
    synthesizing unlock_method ALONE -- which lints clean and looks unlocked
    in the editor while the PDF filler's apply_field_flag_changes
    early-returns without pdf_field_flag_change, silently leaving the field
    locked in the filled PDF. Fixed (full descriptor synthesized) AND the
    failure mode got its own lint rule: `unlock-missing-flag-change` WARNING
    for any pre-existing unlock_method lacking the flag change. Never
    overwrites an existing unlock_method.
  - `hides` -> the trigger condition NEGATED into the target's show_if
    (none_of; "shown when NOT ...").
  - `locks` / `makes_optional` (genuinely unconvertible: no gold-attested
    encoding; makes_optional collides with the static validation.required
    short-circuit in isFieldRequired) -> the control is RETAINED as a reduced
    controls_fields rump, so schema_lint's existing legacy-trigger-side-logic
    ERROR flags it for a human. Loud in the repair report AND the lint --
    never a silent pop. (FormField is extra="ignore" and extract_form's
    validate discards the model, so the rump survives the pipeline to lint.)
  - Conversion entries reuse the `mirror-controls-fields` action name and the
    rump entry reuses `controls-fields-unmirrored`, so eval_extraction's
    harvest counters keep working unchanged.
  - Outer review seat B caught a model-invalidity bug: v2 conditions are
    DEPTH-1 (bucket members must be ATOMS), and both composition wrap paths
    -- the new hides AND-NOT wrap and the pre-existing c3y6 OR wrap that
    unlocks newly reached -- emitted nested groups the model rejects and the
    frontend fails open on. Fixed centrally: add_target_condition /
    add_target_negated_condition now return False when the combination is
    inexpressible at depth 1 (existing composite that cannot absorb the atom),
    and every caller routes the failed edge to the LOUD rump instead of
    emitting invalid schema (the mirror core reports them via the unconverted
    channel). Depth-1 is now structurally asserted in tests; the unlocks edge
    is all-or-nothing (no half-paired descriptor when its visibility pairing
    cannot compose). The final outer round then caught that MIGRATE's caller
    ignored the new False return (silent drop + false "mirrored" count on a
    composite-conditioned target) -- so migrate's Pass 4 now honors it too,
    surfacing the edge through its unmirrored_controls channel (bd urrt,
    resolved here; migrate is otherwise behavior-identical and its prior
    behavior on that input was an invalid nested group). One latent depth-1
    migrate caveat is thereby FIXED, not just avoided.
  - Outer review caught the conversion pass double-logging: it re-normalized
    every control loudly, duplicating alias-operator entries and doubling
    alias_hit_count (the P6 decay metric) even on plain shows edges. Fixed:
    the pass skips controls with nothing to convert and re-normalizes
    unlocks/hides-bearing controls QUIETLY (identical rewrites, no report
    side-effects); exact-once cardinality is now test-pinned.
- **`tests/test_schema_repair.py`**: the old unlocks-drop pin REPLACED by the
  new contract (that behavior change IS the bead), plus: hides->none_of,
  rump+lint loudness, the all-six-actions end-to-end criterion test,
  idempotent re-repair, and the hides polarity guard.

## Notes

- 58 repair + 35 migrate/scorer-dialect + 4 i90-migrated-baseline tests green;
  full backend suite green with the change in place: 1280 passed, 1 skipped
  (closeout_prep, 2026-07-26). ASCII clean.
- closeout_prep's STALE tier-2 doc flags reviewed: all cite code changed by
  other already-merged branches; this branch touches the repair/mirror
  services, their tests, and this entry. Pre-existing drift, not caused here.
- Scorer alignment note: scripts/schema_score.py's residue split (mirrorable
  2 / unconvertible 4) now under-states what repair converts; post-repair
  drafts carry only locks/makes_optional residue so the split is vacuous in
  practice. Aligning the constants touches files owned by open PR #485 --
  logged on bd btbi to fold in after that merges.
