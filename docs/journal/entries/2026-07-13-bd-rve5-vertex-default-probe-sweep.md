---
date: 2026-07-13
bead: polyglot-pdf-rve5
title: "Sweep 17 probe/diag/bakeoff scripts to the Vertex-default _client() pattern (billing directive)"
tags: [cost, testing]
---

## Trigger

Maintainer directive 2026-07-12 (bd memory `all-live-model-work-runs-on-vertex`):
all live-model work runs on Vertex so costs land on the tracked billing project.
`probe_secretary_recall.py` was converted first (the reference `_client()`); this
bead sweeps the remaining scripts that still built `genai.Client(api_key=...)`
directly. The bead listed 13; a fresh-eyes pass (repo-wide multiline grep) found
4 MORE ungated live-model constructions the single-line search had missed --
two `scripts/spikes/diag_compression_*` Live-API diagnostics (a declared surface)
and two `scripts/bakeoff/arm_{gemini,documentai}` extraction arms -- so 17 total
were converted (criterion 1 is worded repo-wide under `scripts/`).

## What changed

Each script's client construction now uses the Vertex-default `_client()` pattern
copied faithfully from `probe_secretary_recall._client`: `VERTEXAI` unset/`true`
-> `genai.Client(vertexai=True, project=GOOGLE_CLOUD_PROJECT,
location=VERTEX_LOCATION|us-central1)` (with a printed warning if the project env
is unset); `VERTEXAI=false` + `GEMINI_API_KEY` is the explicit AI-Studio escape
hatch (`sys.exit(2)` if the key is missing).

- **8 scripts already had a `_client()`** (plain AI-Studio-only body) -- body
  replaced: `probe_3p1_1007`, `probe_confirm_field`, `probe_g1_contradiction_recall`,
  `probe_g1b_model_size_bakeoff` (also dropped its partial `GOOGLE_CLOUD_LOCATION`
  opt-in for the canonical `VERTEX_LOCATION`), `probe_secretary_latency`,
  `probe_si_bisect_i9q8`, `probe_tool_call`, `probe_tool_call_id`.
- **4 built the client INLINE** -- factored into a module-level `_client()`:
  `diag_compression_connect_boundary`, `diag_native_audio_1011`,
  `diag_native_audio_1011_tools`, `diag_turn_reliability_4sv7`. The three
  `diag_native_audio*`/`diag_turn_reliability` scripts also had a preflight
  `if not GEMINI_API_KEY` gate that would have wrongly blocked a Vertex run --
  narrowed to fire only when `VERTEXAI=false`.
- **1 class-based** (`gemini_enhancer_v2.GeminiEnhancerV2`): added
  `_client(api_key=None)` -- an explicit `api_key=` still takes the AI-Studio path
  (unchanged for any caller passing one), but the default (the sole repo caller,
  `test_gemini_extraction_v2.py`, passes no args) now flows through Vertex.

- **4 MORE found by fresh-eyes** (multiline `genai.Client(\n api_key=...)` the
  first grep missed), all Live-API/heavy-call and threading `http_options`, so
  each got a `_client(http_options=None)` that passes it through both branches:
  `scripts/spikes/diag_compression_apiversion.py` +
  `scripts/spikes/diag_compression_cascade.py` (both also had a preflight
  `if not GEMINI_API_KEY` gate narrowed to `VERTEXAI=false`), and
  `scripts/bakeoff/arm_gemini.py` + `scripts/bakeoff/arm_documentai.py` (the
  live-model extraction-bakeoff arms; arm_documentai's DocAI client is separate
  and untouched).

Each header/usage docstring was updated to show the Vertex run form as primary
with the `VERTEXAI=false GEMINI_API_KEY=...` escape hatch, plus a one-line note:
converted for rve5, one-shot diagnostic NOT re-verified against live Vertex
post-conversion, and (on the Live-API/bidiGenerateContent scripts) the Vertex
model-id variant may need adjustment per bd a079.

Only client construction + header text changed -- no probe logic, model ids,
prompts, or measurement code.

## Exit criteria

- **(1) No ungated `genai.Client(api_key=)`:** a repo-wide multiline grep over
  `backend/scripts/` + `scripts/` confirms every remaining occurrence sits inside
  a `VERTEXAI=false` escape-hatch branch, is `gemini_enhancer_v2`'s explicit
  `api_key=` override, is `llm_providers.py`'s pre-existing `VERTEXAI` gate, or is
  the docstring MENTION at `diag_compression_apiversion.py:6`. Satisfied for the
  bead's scope. OUT OF SCOPE (filed as bd polyglot-pdf-w6en): one live-model
  construction remains at `backend/tests/contract/test_tool_contracts.py:169` --
  a test, not a script, outside criterion 1's `backend/scripts/`+`scripts/`
  wording; noted for a follow-on rather than folded in here.
- **(2) Converted probes verified or incompatibility documented:** no live run was
  made (spend is gated by the experimentation skill, and these are retired
  one-shot diagnostics). Each converted script's header documents that it is
  Vertex-default but not re-verified live, and flags the Live-API model-id caveat
  (bd a079) -- the "incompatibility documented" arm of the criterion. A future
  gated run confirms any specific probe if it is ever re-exercised.

## Verification

- All 13 `py_compile` clean; ASCII-only across every edit; git diff touches
  exactly the 13 target files.
- The Vertex-default branch structure matches the reference `_client()` verbatim;
  the escape hatch reaches `genai.Client(api_key=key)` only when
  `VERTEXAI != "true"` and the key is present.

## Files touched

- `backend/scripts/{probe_3p1_1007,probe_confirm_field,probe_g1_contradiction_recall,probe_g1b_model_size_bakeoff,probe_secretary_latency,probe_si_bisect_i9q8,probe_tool_call,probe_tool_call_id}.py`
- `scripts/spikes/{diag_compression_connect_boundary,diag_native_audio_1011,diag_native_audio_1011_tools,diag_turn_reliability_4sv7,diag_compression_apiversion,diag_compression_cascade}.py`
- `scripts/bakeoff/{arm_gemini,arm_documentai}.py`
- `scripts/bakeoff/prior_extractor/gemini_enhancer_v2.py`
