---
date: 2026-07-13
bead: polyglot-pdf-s7gq
title: "cost_matrix_lib.recompute_si_scenarios: pin the legacy full-SI mode explicitly so the USE_DTI default flip stops mislabeling DTI-SI as 'full'"
tags: [cost, testing]
---

## Trigger

`scripts/spikes/cost_matrix_lib.py::recompute_si_scenarios` measures the legacy
full-SI length for the notebook cost-matrix's 'full'/'sections'/'drip' scenarios
by calling `ai_context.build_form_context(...)` and relying on the module-level
`get_settings()` default. bd polyglot-pdf-7872 flipped `USE_DTI` to default ON,
and `build_form_context` (ai_context.py:468) branches to the DTI thin SI whenever
`settings.USE_DTI` -- so the probe silently switched to rendering the DTI SI while
its docstring/comment still claimed it measured the surviving legacy full-SI. The
same el92 mislabeled-data failure class the sibling harness
(`measure_form_session_costs._make_settings`) was hardened against, missed on this
instrument.

## Impact (measured)

On the demo schema the probe consumes (`adult_intake_demo_schema.json`, 174
fields):

- buggy (dev): `full` = **4457** chars (the DTI thin SI)
- fixed: `full` = **26500** chars (the legacy full-SI)

A ~5.9x under-measurement -- the notebook cost-matrix length model was fed DTI-SI
lengths mislabeled as full-SI. Analysis-only (no production/backend-test impact).

## Fix

Pin the legacy SI mode EXPLICITLY inside `recompute_si_scenarios`, mirroring the
`test_ai_context` autouse fixture and `measure_form_session_costs`: construct
`Settings(USE_DTI=False, CONTINUOUS_SESSION=False)` (CONTINUOUS_SESSION must also
be off or config forces `USE_DTI` back on) and patch
`ai_context.get_settings` to return it for the `build_form_context` calls, in a
try/finally that restores the original. A `USE_DTI` default flip can no longer
relabel these lengths. Updated the stale "USE_DTI off, the default" comment.

## Verification

- Before/after on the real consumed schema: `full` 4457 (DTI) -> 26500 (legacy);
  `get_settings` is restored after the call (verified `before is after`).
- The scenario dict keeps its shape (full / jit-frozen / drip / 15 sections);
  `full > drip` holds (legacy full carries all fields, drip is metadata-only).
- `py_compile` clean; ASCII-only. The sole consumer is
  `cost_matrix_analysis.ipynb` (its drift-check now compares against the correct
  legacy value); no test references this lib.

## Files touched

- `scripts/spikes/cost_matrix_lib.py`
