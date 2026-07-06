---
date: 2026-07-05
bead: polyglot-pdf-choa
title: "DTI continuous-session reliability: known-id coercion, first-field confirm, manual-edit pointer, Vertex compression bounds"
sprint: 8
tags: [voice-ai, dti, compression, si, testing, postmortem]
---

## Trigger

Maintainer report: "my DTI and compression window combination runs are erroring
-- I want the app to run for 30 questions continuously and reliably without
error." Three open reliability beads (choa: first field auto-confirmed without
read-back; ezg2: current-field pointer lost after a manual edit; 8vy3:
off-by-one fills the wrong real field) all blocked the compression-window
tuning bead (ctu8), whose continuous-session candidate arm had been producing
unreadable errors. jnjj.46 (hallucinated field_id) was already closed by the
static-SI epic (PR #264); PR #251 (fuzzy recovery) was its superseded,
deliberately-unmerged predecessor -- no other PR had touched these beads.

## What shipped

**choa (SI wording).** `INITIATING_MESSAGE`'s "DO NOT verify previous fields -
move directly to asking for the next field" read, on field 1 (which has no
previous fields), as a confirm exemption -- the model filled and confirmed
field 1 without the read-back. Reworded: the carve-out now names
ALREADY-CONFIRMED fields, and the first field is explicitly pinned to the
normal fill -> read-back -> "Is that correct?" -> confirm workflow.
`get_confirmation_policy` (all three branches + the non-sectioned default in
`build_form_context`) now states the end-of-section review is IN ADDITION to
per-field confirmation -- referencing, not restating, the per-field step (the
yn6q double-read guard). Live-verified on BOTH SI paths: a legacy/section-reset
harness run (the demo's path) and the continuous DTI runs each show field 1
read back ("You entered/said 12345678. Is that correct?") before confirm_field.

**ezg2 (manual-edit pointer).** `sendManualFieldUpdate` now refreshes state
from the persisted snapshot BEFORE computing the next field (the old order
computed the hint from pre-edit state, so it pointed back at the just-edited
field -- a latent bug), computes the next field ONCE, and in DTI mode rides its
full schema as `next_field_schema` on the `manual_field_update` message. The
backend threads it to `send_manual_field_update`, which merges it via
`merge_field_schema` -- re-establishing the coercion pointer + validation entry
exactly as the confirm path does. Wire change is an additive optional key, both
halves in this PR, absent from legacy clients (backward compatible). Unit
tests: backend manual-edit trio in `test_dti.py`; new
`webFormConnection.manualedit.test.ts` on the frontend.

**8vy3 + the coercion refinement (the big one).** The h1bn coercion treats the
model's field_id as advisory and re-points any mismatch onto the current
field. Live 30q continuous evidence inverted the cost/benefit: the model's ids
were correct in EVERY call across the final runs (105/106 in the jnjj.46
re-measure, ~100% now), but when it legitimately corrected a PREVIOUS field
(late answer after its confirm advanced the pointer -- e.g. after its own
unscripted "is your physical address different?" clarifying question), the
blanket coercion misfiled the correction onto the current field: one run had
the street landing in the apartment-number field, "12" in city, the zip in
province -- five corrupted fields, all caused by coercion, none by the model.
This also bites production: ANY user correction after a confirm advanced the
pointer would be misfiled. Refinement: an id that RESOLVES to a known field
(handshake schema or a client-delivered merge; `_is_known_field_id`) is
authoritative; only an UNRESOLVABLE id -- the jnjj.46 hallucination mode -- is
coerced. Update and confirm sides symmetric (`is_known_field` injected into
`CallbackHandler`). The old 8vy3 drift mode (wrong-real-id for the current
answer) is accepted as the rarer risk; exact-id discipline under static-SI
guidance is what actually holds the line, and the final run had zero
wrong-field fills.

**Vertex compression bound (adapter).** The Live API hard-bounds
`trigger_tokens` to [5000, 128000] AT CONNECT -- Vertex closes with 1007 and
the session never opens. The DTI per-form derivation (jnjj.35) produces ~2800
for the I-90, so EVERY DTI+compression session on Vertex died before opening:
a root cause of the "combination runs erroring". `_build_live_config` now
clamps the trigger into the legal range (logs
`compression_trigger_clamped_to_api_bounds`); the window (eviction landing
zone) keeps its derived per-form value. The old 2800/2200 "winning
calibration" was measured on AI Studio, whose prepaid credits are now depleted
(1011) -- all live runs are Vertex now.

**Harness (measure_form_session_costs.py).** `--vertex` (ADC; swaps the 2.5
model id to `MODEL_NATIVE_STANDARD_VERTEX`); `--continuous` (one uninterrupted
DTI session over the whole plan -- the ctu8 candidate arm) with
production-faithful GoAway reconnect (the Vertex connection caps at ~9-10 min
and announces via go_away; the FakeClient mirrors the frontend's pre-emptive
reconnect); REAL manual-VAD activity brackets (`DISABLE_GEMINI_VAD=True` --
the old "neutralized sensitivities" never disabled automatic VAD, and Vertex's
VAD intermittently missed gTTS utterance ends, hanging the model ~41s/turn
until the whole dialog wedged); the FakeClient now applies empty-string values
and mirrors the production `hasUsableValue` gate (bd w3ic) so the SI's
fill-optional-with-empty flow is satisfiable (its absence wedged a run in an
infinite empty-fill/confirm loop at the postal-code field); spoken-name keys
in the recall map (all 17 get_field_value lookups found=True in the last runs,
vs 0-4 before); +9 section-4 I-90 plan questions (plan now 34) so a
30-question continuous run fits; any-of expected values for text country
fields.

## Verification

- Backend suite: 882 passed. Frontend suite: 743 passed (38 files).
- Final live run (solo, Vertex, `--arm dti --continuous --compression
  --trigger 5000 --window 3500 --questions 30 --debug`): **28/30 fill (93%),
  29/30 confirmed** (the 1 unconfirmed is the last question's confirm still in
  flight at run end), **zero errors, zero stalls, zero hallucinated ids, zero
  wrong-field fills**, 7 evictions (4.9k -> 3.4k tok) with coherent dialog
  across every one, 1.28s mean turn latency. The 2 misses: "twelve B" ASR-heard
  as "20" (intermittent; the same cached audio scored correct on the mailing
  copy; a real user says "no" at the read-back), and date-of-birth written
  ISO (`1990-03-05`) instead of `MM/DD/YYYY` -- right data, format-normalizer
  territory (bd cn0e family).
- Run artifacts committed under `scripts/spikes/data/costs_i90_2.5_dti_cont_*`
  (the progression of 4 continuous runs + the choa legacy-path run).

## Scar tissue / lessons

- **Vertex Live sessions on the demo project run ONE at a time** -- a second
  concurrent session kills the first mid-run (1000 "operation was cancelled").
  bd memory `vertex-live-one-session-at-a-time`.
- **"Neutralized VAD sensitivities" is not disabled VAD.** Explicit activity
  brackets require `automatic_activity_detection.disabled=True`; otherwise the
  adapter silently no-ops them and the server's VAD segments your synthetic
  audio however it likes.
- **A window sized for a gentle trigger becomes a lobotomy under a clamped
  one.** With trigger forced from 2800 to 5000 but window still 2200, each
  eviction chopped ~3000 tokens -- stripping the current-field guidance DTI
  depends on (post-eviction double-asks, secretary lookups, drift). Window
  3500 (eviction keeps ~1.5k tokens of recent turns above the SI floor) stayed
  coherent across 7 evictions. ctu8's sweep should treat the WINDOW as the
  independent variable with trigger fixed at the 5000 floor.
- **The continuous arm must handle GoAway** (~9-10 min Vertex connection cap).
  Production's client already reconnects (bd c5t); anything driving a
  continuous session (harness, future session-resumption work) must too.

## Open threads

- ctu8 (compression-window tuning) is now UNBLOCKED: continuous DTI runs are
  clean and repeatable; constraints + starting calibration recorded on the
  bead.
- fsoa (correct id rejected -- merge-timing gap) remains open/P3; not observed
  in any of this session's runs.
- Date-format adherence (ISO vs MM/DD/YYYY) belongs to the format-preset
  normalizer work (cn0e).
