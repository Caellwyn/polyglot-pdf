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
mode), so it is measured analytically -- not contaminated by the live drip bug
that bloats the JIT runs' live text-in tokens. The JIT SI is ~constant (~3150
chars: the manifest's `field_id|spoken_name` pairs + ONE field's full schema);
the full-SI dump scales linearly with the section's field count. The reduction
is therefore monotonic in section size and peaks on the LARGEST I-90 section:

| section | fields | full-SI chars | JIT-SI chars | reduction |
|---|---:|---:|---:|---:|
| **section-medical** (largest) | **54** | **9503** | **3149** | **66.9%** |
| section-substance-history | 25 | 6339 | 3220 | 49.2% |
| section-living-situation | 21 | 5718 | 3356 | 41.3% |
| section-trauma-history | 17 | 5251 | 3169 | 39.6% |
| section-client-info | 12 | 4588 | 3156 | 31.2% |
| section-demographics | 9 | 4313 | 3267 | 24.3% |
| ... (smaller sections) | <=6 | ~3300-4100 | ~3200-3300 | 0.6-21.0% |
| section-safety-risk (smallest) | 1 | 3307 | 3288 | 0.6% |

Headline: on section-medical (54 fields, the bead's target "REAL LARGEST I-90
section") the rendered SI drops 9503 -> 3149 chars (~2376 -> ~787 tok/turn at
~4 chars/tok), a **66.9%** per-turn SI reduction. Break-even (JIT's fixed
manifest overhead) is ~1-2 fields. So the SI reduction the manifest swap buys is
REAL and large on big sections -- it just does not convert to a real-dollar win
today because of the drip defect, which forces the model into a non-advancing
loop whose growing transcript dwarfs the SI savings.

## Root cause of the JIT correctness collapse (BLOCKING for A5)

The JIT next-field drip never delivers any field after the first, so the model
gets the first field's schema and then flies blind for fields 2..N. Confirmed
both empirically (drip returns `None` for every field) and by code path:

- In JIT mode the backend sets `self._schema = {"fields": [first_field], "manifest": {...}, ...}`
  -- only the FIRST field is in `fields`; the rest live only in the manifest
  (`backend/routes/websocket_routes.py:671-678`).
- On each successful update/confirm, `callback_handler` calls
  `FormFillingService.get_next_field_schema_for_jit(field_id)` to drip the next
  field's schema into the tool response
  (`backend/services/callback_handler.py:556-557`, `:776-777`).
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
  first-section case (4587 vs 3698); the LARGEST-section SI floor is the
  analytic section-medical number above (the bead's headline). A live run that
  reaches section-medical would only widen the SI gap further -- but is moot
  until the drip defect is fixed.
