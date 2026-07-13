---
date: 2026-07-13
bead: polyglot-pdf-2wod
title: "Remove the dead get_field_value recall scaffolding from measure_form_session_costs.py (the tool was retired in p5h2)"
tags: [testing, cost]
---

## Trigger

The G3 cost-measurement spike `scripts/spikes/measure_form_session_costs.py`
still carried an inbound `get_field_value` message handler that called
`self.service.handle_field_value_response(...)` -- a method removed from
FormFillingService when the `get_field_value` tool was retired (bd
polyglot-pdf-p5h2, single recall path is now `ask_secretary`). The branch is
dead in practice (the model no longer declares or emits the tool), but it would
AttributeError if the harness were ever run against an old transcript or a model
that hallucinated the call.

## What was removed

The whole recall-measurement scaffolding for the retired tool:

- the `elif mtype == "get_field_value"` handler (the only caller of the removed
  `handle_field_value_response`);
- the `spoken_to_fids` map built in `FakeClient.__init__` (used ONLY by that
  handler);
- the `field_value_lookups` instrumentation list, its `meta["field_value_lookups"]`
  emission, and the "get_field_value lookups: N" line of the run summary print;
- the docstring + inline comments that described the recall-lookup arm (updated
  to note it was removed with the tool, rather than deleted silently).

The fill-correctness score (`meta["fill_accuracy"]` via `score_fill_accuracy`)
is untouched -- that is the surviving, still-valid G3 instrument.

## Downstream safety

`scripts/spikes/analyze_continuous_window.py` reads `field_value_lookups` from
meta files, but via `meta.get("field_value_lookups") or []` and only uses
`len(...)` for an `n_lookups` output metric -- so a meta file without the key
degrades to `n_lookups: 0` (accurate now that the tool is gone). Historical meta
JSONs keep their recorded key; new runs simply omit it. One inline comment
elsewhere (the callback-tap timing note) that used `get_field_value` as its
example was repointed at `ask_secretary` (the surviving recall tool).

## Verification

- Exit criterion (grep-clean): 0 references to `handle_field_value_response`, 0
  inbound `get_field_value` handlers, 0 `field_value_lookups`/`spoken_to_fids`.
  The 2 remaining `get_field_value` mentions are explanatory comments documenting
  the removal.
- `py_compile` clean on the spike and the analyzer; ASCII-only.
- `tests/test_measure_cost_debug.py` green (6 passed) -- it imports the spike, so
  the import path still resolves.

## Files touched

- `scripts/spikes/measure_form_session_costs.py`
