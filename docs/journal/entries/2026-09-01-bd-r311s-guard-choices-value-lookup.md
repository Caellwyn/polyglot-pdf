---
date: 2026-09-01
bead: polyglot-pdf-r311s
title: "fix(bakeoff): guard choices[].value lookup in both prompt-builder field-list renderers"
tags: [scripts]
---

## Trigger

Both `acroform_field_list` (`scripts/bakeoff/schema_contract.py`) and
`enriched_field_list` (`scripts/bakeoff/structural_enrich.py`) render a
widget's `/Opt` choice sample with `c["value"] for c in choices[:12]` --
direct dict indexing, no `.get()` / `isinstance` guard. A choice dict
missing a `"value"` key (a malformed/hand-edited dump, or a future dump
producer with a different choice shape) raised `KeyError` and crashed
prompt building outright, rather than degrading gracefully like the rest
of the file's defensive `.get()` style.

Not reachable via the current `acroform_dump.py` producer (it always
writes `{"value": ..., "display": ...}`), so this had not fired -- but a
latent crash risk on a hot path.

This IS reachable from the hosted app, not merely offline research
tooling -- correcting an earlier draft of this entry, caught by the Opus
cross-surface review: `POST /api/editor/kits/{kit_id}/extract`
(`backend/routes/editor_kit_routes.py`) runs `scripts/authoring/
extract_form.py` as a subprocess with `scripts/bakeoff` on its `sys.path`,
and `extract_form.py` imports `arm_llm_native`, which imports both
functions this bead touches. The pre-fix `KeyError` would have surfaced
as a failed hosted extraction (a metered LLM call already spent), and the
count bug (see Fix below) would have quietly degraded that same metered
call -- which raises the value of the fix, not just its tidiness.

## Fix

Both functions filter their choices to `isinstance(c, dict) and "value" in
c` -- a value-less entry is skipped from the sample rather than crashing
or being substituted with a placeholder that could be mistaken for a real
option value.

Filtering happens BEFORE slicing to 12, not after. My first version
filtered the already-sliced `choices[:12]`, which the Opus cross-surface
review caught as a real, if narrow, second bug: it would shrink the
rendered sample below 12 whenever a value-less dict fell within the first
12 slots, while the `"... and N more"` count still only counted entries
past index 12 -- silently undercounting how many usable values actually
exist. That is exactly the unmarked-truncation failure bd `polyglot-pdf-
hmkas` exists to prevent, and this diff is what made the scenario
reachable at all (previously it crashed before the count was ever
computed). Fixed by filtering the full `choices` list first, THEN
slicing the filtered result to 12 -- `shown + more` now always sums to
the true count of usable values, unaffected by where a value-less entry
happens to sit.

## Testing

New file `tests/test_prompt_choice_value_guard.py`, mirroring the sibling
`test_prompt_choice_truncation.py`'s (bd `polyglot-pdf-hmkas`) fixture
pattern exactly (`_load()`/dynamic module loading, both builders
parametrized together so a fix applied to one and not the other fails).
Five cases: a single value-less choice doesn't crash; a mix of valid and
value-less choices renders only the valid ones; all choices value-less
still degrades to an EXACT empty `choices=[]` clause (not a weaker
"contains 'choices='" check -- an earlier version of this assertion was
vacuous, satisfied by any rendered clause regardless of content, caught
during review); a value-less choice landing WITHIN the first 12 slots
does not undercount `"... and N more"`; a non-dict entry (bare string,
`None`) in the choices list does not crash either (the `isinstance`
half of the guard, pinned separately from the `"value" in c` half, which
an earlier version of the test suite never actually exercised).

Mutation-verified: reverting the guard back to direct indexing reddens
the crash-avoidance cases with the exact `KeyError: 'value'` the bead's
repro predicted, for both builders. Separately reverting to
filter-after-slice (keeping the crash guard, dropping only the count
fix) reddens exactly the mid-sample undercount test, for both builders,
while every other case stays green. Restored both; ran alongside the
sibling truncation test file (27 tests total), all green.

## Review

Two rounds. The inner fresh-eyes pass was `NO-GAPS` on the bead's stated
exit criteria, but reported `GAPS-FOUND (1)` overall: the filter-after-
slice undercount above, plus two test-quality nits (the vacuous empty-
bracket assertion; missing non-dict-entry coverage) -- all three fixed
in this same diff before the outer pass, since they were genuine defects
in my own work, not out-of-scope findings to file separately.

The Opus cross-surface pass was `NO-GAPS`, independently re-derived the
count-fix boundary math across 9 cases (0/1/11/12/13 usable, scattered
value-less entries, non-dict entries), confirmed no third copy of this
pattern exists anywhere else in the repo, and corrected the offline-only
premise above. It filed two non-blocking, pre-existing follow-ups rather
than folding them into this bead's scope: `polyglot-pdf-frrdh` (the
neighboring `on=` clause three lines below `choices=` has the identical
unmarked-truncation gap this bead just fixed for `choices=`, still
present) and `polyglot-pdf-skkps` (`structural_enrich.py`'s "Throwaway
research tool" module docstring is false now that the module runs inside
the hosted extract endpoint).
