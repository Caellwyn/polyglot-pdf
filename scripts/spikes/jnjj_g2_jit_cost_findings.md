# G2: rendered-SI cost -- JIT-SI vs per-section-reset baseline (bd polyglot-pdf-jnjj.6)

*Date: 2026-06-15. Epic: polyglot-pdf-jnjj (SI reduction via task delegation).
Instrument: bd polyglot-pdf-4loz (`measure_form_session_costs.py`), with the new
`section-reset-jit` arm added under this bead (commit cb940218 here, originally
f4e16f4b on `claude/competent-diffie-05dc08`). Data:
`scripts/spikes/data/costs_2.5_<arm>_<path>_20260615T*.csv` + `.meta.json`. Model
2.5 (`gemini-2.5-flash-native-audio-preview-12-2025`), GEMINI_API_KEY /
VERTEXAI=false. 4/4 live cells ran.*

## Verdict: NO-GO on the manifest swap as currently implemented

The cost arm of A5's flip is **NO-GO**. Two independent reasons, either of which
is disqualifying:

1. **Cost inverted.** The JIT manifest swap, despite a smaller per-turn system
   instruction (SI), produced HIGHER real-dollar run cost than today's shipped
   full-SI baseline on both paths.
2. **Correctness collapse exposed a real production defect.** The live JIT runs
   confirmed only 2/20 (happy) and 1/20 (unhappy) fields, versus 17/20 and 20/20
   for the baseline. Root cause is a genuine bug in the production JIT
   next-field drip (see "Root cause" below), not a harness artifact -- the
   harness faithfully reproduced it. The smaller SI is real, but it is not
   reachable for cost benefit until the drip is fixed.

The manifest swap CANNOT ship (A5 default-flip USE_JIT_SCHEMA) until the JIT
next-field drip defect is fixed and re-measured. Filed as a new bead (see below).

## The live 4-cell matrix (20 questions/run; happy = 2 turns/q, unhappy = 4)

| arm | path | SI chars (1st section) | run $ | total tokens | confirmed | evictions |
|---|---|---:|---:|---:|---:|---:|
| section-reset (full-SI, baseline) | happy | 4587 | **$0.156** | 195,650 | 17/20 | 3 |
| section-reset (full-SI, baseline) | unhappy | 4587 | **$0.363** | 497,961 | 20/20 | 3 |
| section-reset-jit (manifest SI) | happy | 3698 | **$0.192** | 207,743 | 2/20 | 2 |
| section-reset-jit (manifest SI) | unhappy | 3698 | **$0.448** | 565,829 | 1/20 | 1 |

Files (under `scripts/spikes/data/`):
`costs_2.5_section-reset_happy_20260615T225231Z.csv`,
`costs_2.5_section-reset_unhappy_20260615T225236Z.csv`,
`costs_2.5_section-reset-jit_happy_20260615T225238Z.csv`,
`costs_2.5_section-reset-jit_unhappy_20260615T225239Z.csv` (+ `.meta.json`).

### Baseline re-measure held

Exit criterion 2 asked for a FRESH baseline re-measure (the prior wyhh numbers
predate A2/d24n). The fresh full-SI `section-reset` baseline ($0.156 happy /
$0.363 unhappy) is within run-to-run noise of the prior wyhh findings ($0.188 /
$0.323). The baseline is stable post-A2/d24n.

## Exit criterion 1: rendered per-turn SI token floor

The per-turn SI floor is **deterministic** (a pure function of section size and
mode), so it is measured by rendering the real `build_form_context_message` per
section -- not contaminated by the live drip bug that bloats the JIT runs' live
text-in tokens. **The JIT SI is NOT constant:** post-A2 (bd jnjj.9) the manifest
SI lists every section field as a `field_id|spoken_name` pair, so the rendered
`{manifest_text}` grows ~linearly with field count (plus the JIT scaffolding
overhead). The full-SI dump grows faster (full per-field schemas), so the
reduction still increases with section size and peaks on the LARGEST I-90
section -- but it is materially smaller than an earlier (retracted) estimate of
~66.9%, and on SMALL sections JIT is actually LARGER than full-SI:

| section | fields | full-SI chars | JIT-SI chars | reduction |
|---|---:|---:|---:|---:|
| **section-medical** (largest) | **54** | **9503** | **5382** | **43.4%** |
| section-substance-history | 25 | 6339 | 4426 | 30.2% |
| section-living-situation | 21 | 5718 | 4466 | 21.9% |
| section-trauma-history | 17 | 5251 | 4198 | 20.1% |
| section-client-info | 12 | 4588 | 3699 | 19.4% |
| section-demographics | 9 | 4313 | 3879 | 10.1% |
| section-relationships | 6 | 4113 | 3785 | 8.0% |
| section-legal-history | 5 | 3746 | 3611 | 3.6% |
| section-functioning / -family-history | 4 | ~3650 | ~3630 | ~0% |
| section-reasons-counseling | 6 | 3863 | 4054 | **-4.9%** |
| section-spirituality | 2 | ~3420 | ~3680 | **~-8%** |
| section-safety-risk (smallest) | 1 | ~3350 | ~3740 | **~-12%** |

(Measured per section in an ISOLATED process each -- `get_settings` is
`@lru_cache(maxsize=1)` and `ai_context` imports it by reference, so an
in-process loop that monkeypatches `_config.get_settings` leaks the JIT/full
mode across calls and yields WRONG numbers. The negatives on small sections are
real: JIT's manifest + scaffolding overhead exceeds a small full-dump.
Break-even is ~9-12 fields, NOT ~1-2.)

Headline: on section-medical (54 fields, the bead's target "REAL LARGEST I-90
section") the rendered SI drops 9503 -> 5382 chars (~2376 -> ~1346 tok/turn at
~4 chars/tok), a **43.4%** per-turn SI reduction. So the SI reduction the
manifest swap buys is real on big sections (and NEGATIVE on small ones) -- but
even on the largest section it does not convert to a real-dollar win today
because of the drip defect, which forces the model into a non-advancing loop
whose growing transcript dwarfs the SI savings.

> **Correction (post fresh-eyes):** an earlier version of this doc claimed the
> JIT SI was "~constant (~3150 chars)" and reported 66.9% on section-medical via
> a 3149-char JIT SI. That was a measurement artifact (the lru_cache/by-reference
> `get_settings` leak above). The correct, process-isolated number is 5382 chars
> / 43.4%. The NO-GO verdict is unaffected (both legs are live-measured).

## Root cause of the JIT correctness collapse (BLOCKING for A5)

The JIT next-field drip never delivers any field after the first, so the model
gets the first field's schema and then flies blind for fields 2..N. Confirmed
both empirically (drip returns `None` for every field) and by code path:

- In JIT mode the backend sets `self._schema = {"fields": [first_field], "manifest": {...}, ...}`
  -- only the FIRST field is in `fields`; the rest live only in the manifest
  (`backend/routes/websocket_routes.py:671-678`).
- On each successful update/confirm, `callback_handler` calls
  `FormFillingService.get_next_field_schema_for_jit(field_id)` (single call site,
  `backend/services/callback_handler.py:556-557`) to compute the next field's
  schema; it is later inserted into the tool response at `:776-777`.
- But that method delegates to `manifest_service.get_next_field_schema(part_data=self._schema, current_field_id)`
  (`form_filling_service.py:935-938`), and `get_next_field_schema` finds "next"
  by INDEX within `part_data["fields"]` (`manifest_service.py:78-94`) -- it never
  consults the manifest. With `fields` permanently holding only the first field,
  the index lookup for any field returns `current_index+1 >= len(fields)` -> None.
- Nothing ever appends loaded fields back into `self._schema["fields"]`
  (verified: no such mutation exists in `backend/`).

So the drip returns `None` for EVERY field in both production and the harness.
This is a production defect that the cost spike surfaced; it overlaps with the
G3 correctness arm. (Verified offline against the harness's JIT schema: drip
returned `None` after firstName / middleName / lastName / preferredName.)

### Filed follow-up

Bug bead filed for the JIT next-field drip defect (drip reads
`self._schema["fields"]` instead of the manifest, so it returns None past field
1). A5 (jnjj.12) is blocked on it: re-run this 4-cell matrix after the fix to
get a clean cost comparison, since today's JIT run cost is dominated by the
non-advancing loop, not the SI.

## Harness notes

- `section-reset-jit` arm reuses the full per-section-reset flow (sub-schema,
  `switch_to_section` restart at each boundary) but synthesizes the post-A2
  `handshake_jit` schema (`jit_handshake_schema`) so `build_form_context` renders
  the manifest SI. Matches the production JIT schema shape
  (`websocket_routes.py` JIT branch) -- including, faithfully, the
  one-field-in-`fields` shape that triggers the drip defect.
- The live plan exercises the first three sections (client-info -> reasons ->
  living-situation), so the live run's per-turn SI delta is the smaller
  first-section case (full 4588 vs jit 3699 chars on client-info); the
  LARGEST-section SI floor is the rendered section-medical number above (the
  bead's headline, 43.4%). A live run that reaches section-medical would widen
  the SI gap -- but is moot until the drip defect is fixed.
- **SI-floor measurement gotcha:** `get_settings` is `@lru_cache(maxsize=1)` and
  `ai_context` imports it by reference, so rendering all sections in one process
  while monkeypatching `_config.get_settings` leaks the JIT/full mode between
  calls and produces WRONG (mode-swapped) numbers. Measure each section in its
  OWN process (set `USE_JIT_SCHEMA` in env + `get_settings.cache_clear()` at
  start). This is why an earlier in-process table reported a bogus ~66.9%.
