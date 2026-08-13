---
tags: [bug-hunt, testing, publish-readiness, schema-forms, mutation-verify, pydantic]
beads: [polyglot-pdf-hhwgi, polyglot-pdf-ii6g, polyglot-pdf-36kqn, polyglot-pdf-ukch0, polyglot-pdf-ele9z]
surfaces: [frontend/schema-forms, backend/services]
---

# Bug-hunt round 4: FE min/max coercion, x/x[] field merge, publish-readiness index bucketing

Fourth round of the ongoing bug-hunt bead roundup (rounds 1-3: PRs #573, #576,
#578). Five beads, two independent fixes:

1. **`ValidationRules.min`/`.max` widened to `number | string` on the frontend**
   (bd hhwgi), mirroring the backend model widening from round 3 (bd ondn).
   The type widening alone surfaced a real `tsc` error in
   `validation.ts`'s min/max comparisons, which forced the actual bug fix:
   `numValue < rules.min` was doing JS's implicit `ToNumber()` coercion on
   whatever showed up in `rules.min`, rather than skipping non-numeric bounds.
2. **`reconcileFieldValues` alias-collapse cross-contaminating `x`/`x[]` when
   BOTH are real, distinct schema fields** (bd ii6g) -- the collapse logic
   assumed a bracket suffix always meant "the same field under an alias";
   when the schema genuinely declares both `x` and `x[]` as independent
   fields, collapsing them lost data.
3. **`publish_readiness.py` bucketed lint findings by field ID string**,
   which silently dropped/miscounted findings whose `id` was missing,
   non-string, or duplicated across fields (bd 36kqn, ukch0, ele9z) -- fixed
   by bucketing on the field's positional index instead, with a fallback path
   for findings whose path shape never carries an index at all.

## Scar tissue

### JS numeric coercion defeats an obvious mutation test

The natural mutation-test bound for `typeof rules.min === "number"` is a
non-numeric string, e.g. a stray date string `'01/01/2000'`. That mutation
does **not** redden: `numValue < '01/01/2000'` coerces the string via
`ToNumber`, which returns `NaN` for a non-numeric-looking string, and `x <
NaN` is `false` regardless of whether the type guard is present. Pre-fix and
post-fix code produce the identical (accidentally correct) result, so a test
built on that bound is vacuous and would pass unchanged if the guard were
deleted.

The bound that actually distinguishes the two: an **empty string**.
`ToNumber('') === 0`, so an unguarded `numValue < ''` becomes `numValue < 0`
-- a real, wrong comparison that only the type guard prevents. Confirmed by
reverting the guard and watching the new test go red before restoring it.
General lesson: when constructing a JS coercion-defeating mutation test,
don't reach for "an obviously wrong type" -- reach for the specific value
whose coercion result is silently plausible. `''`, `[]`, and `null` are the
classic landmines (`Number('') === 0`, `Number([]) === 0`, `Number(null) ===
0`); a string that merely *looks* wrong (a date, a word) usually coerces to
`NaN` and won't distinguish anything.

### A fix reopens a narrower version of the same bug -- again

Same pattern as round 1's cache fix and round 3's kit-provenance fix: the
first attempt at the `publish_readiness.py` index-bucketing fix broke a
**pre-existing, deliberately-pinning** test,
`test_mass_drift_wave_disarms_the_ack_gate_by_design`. That test exercises
the `guidance-identity-stale` lint rule, which emits a finding path shaped
`fields (id=fid).help[...]` -- no `fields[N]` bracket at all. The first
`_field_index_of` implementation only recognized the bracketed-index shape,
so this rule's findings silently fell out of every bucket, changing the
"partial drift, gate stays armed" behavior the test pins into "the gate
disarms" -- a regression narrower than, but structurally identical to, the
original bug (findings dropped due to an unindexed path).

This was caught only because the full existing suite was run before
considering the fix complete -- not just the new tests written for this
bead. Fixed with a second regex (`_FIELD_ID_ANCHOR_RE`) that recovers the
index via an `id=` anchor when no bracket is present, and confirmed by
grepping the actual lint-rule source for every path shape that omits the
bracket (three total: `guidance-identity-stale`, `show-if-cycle`, and two
`enrich_instructions.py` flags) rather than trusting the one shape the new
tests happened to cover.

**Restated lesson (CLAUDE.md scar #7, enumerate the set):** a positional or
identity-based bucketing fix is not "done" once the bead's own repro passes
-- grep every emitter of the data shape being rebucketed and confirm each
one's shape is handled, then pin that as the full set, not just the
instance the bead named.

## Process notes

- All four rounds now follow the identical closeout pattern: Explore-agent
  recon of `bd ready`, manual verification against live code, fix +
  mutation-verify, full-suite run, inner fresh-eyes review looped to
  no-gap, outer Opus cross-surface review looped to a single clearing pass,
  journal entry, `closeout_finish.py`, autonomous merge (Opus NO-GAPS +
  green CI + not consequence-bearing).
- The outer review filed one new bead, `polyglot-pdf-w95ln`: this PR's
  backend fix (bucket by positional index) widens a pre-existing frontend/
  backend parity gap, since `schema-editor/src/utils/lintFindings.ts` still
  buckets by string field ID on the frontend side. Correctly left
  out-of-scope rather than pulled into this PR -- closing it symmetrically
  needs a schema-editor change plus extending the shared parity fixture,
  which is a separate unit of work.
- Total across rounds 1-4: 20 beads closed over 4 merged PRs (#573, #576,
  #578, and this one), all via the same bug-hunt process with zero
  maintainer-blocking escalations.
