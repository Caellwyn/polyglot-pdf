---
date: 2026-07-12
bead: polyglot-pdf-p5h2
title: "Retire get_field_value: ask_secretary is the single recall path"
sprint: 11
tags: [refactor, conventions]
---

## Trigger

Sprint-11 epic polyglot-pdf-fc7t child C2 (plan:
docs/sprint_11_continuous-dti-law_plan.md, approved decision D1). Two recall
tools confused the model and one was broken: get_field_value's lookup was
section-1-pinned in continuous mode until PR #403's interim widen, it overlaps
ask_secretary (whole-form, values + applicability, shipped jnjj.45), and
switch_to_field already returns the current value on navigation. The DTI SI
diet wants a smaller tool catalog.

## What shipped

get_field_value removed end to end (grep-checkable: zero mentions in
TOOL_DECLARATIONS, dispatch tables, SI text): the config.py declaration + the
legacy SYSTEM_INSTRUCTION TOOLS line; callback_handler dispatch + handler +
wiring; form_filling_service handle_get_field_value +
handle_field_value_response + the orphaned spoken-name wrappers;
request_coordinator's request/response cycle (shared machinery untouched);
websocket_routes' field_value_response case; the FE webFormConnection case +
handleGetFieldValueRequest + sendFieldValueResponse; and
schemaFormState.getFieldBySpokenName -- PR #403's widened lookup had NO other
production caller, so the interim fix retires with the tool (it remains the
documented revert path in git history). field_utils' get_available_spoken_names
+ find_similar_field_names deleted too: their only purpose was the tool's
not-found suggestions and fuzzy recovery was abandoned (PR #251). DTI SI recall
guidance (ai_context render_section_metadata) now steers to ask_secretary; the
legacy SI names no recall tool (it declares none). Doc tables that listed the
tool (tool-call-flow, voice-ai, ws-protocol, hipaa-pii-policy) updated with a
retirement pointer; the full continuous-DTI framing sweep remains C8 (ft47).

New static tests (test_tool_contract_static.py Part C) pin: no declaration
named get_field_value; the DTI SI recall guidance names ask_secretary and not
get_field_value; the legacy SI mentions no dead tool.

Live verification (exit criterion 2): backend/scripts/probe_secretary_recall.py
run on VERTEX with the production-primary model (gemini-2.5-flash-lite),
whole-form I-90 context -- 8/8 strict grounding across the easy + aliasing
tiers, 0 hallucinations, 0 confident-wrong (artifacts:
scripts/spikes/data/secretary_recall_grouped_20260712T102333.*).

Maintainer directive folded in (2026-07-12, direct ask): the probe now
DEFAULTS to Vertex (ADC + GOOGLE_CLOUD_PROJECT, VERTEX_LOCATION knob; AI
Studio only behind explicit VERTEXAI=false) so costs land on the tracked
billing project, and its default model moved from the AI-Studio-only
gemini-3.1-flash-lite (which 404s on Vertex) to the production primary. The
June-2026 2.5-lite 503 degradation that motivated the 3.1 default has passed.
Recorded durably in bd remember (all-live-model-work-runs-on-vertex); the
sweep of 14 other AI-Studio-only scripts is bd polyglot-pdf-rve5.

Implementation delegated to a Sonnet subagent (25-file sweep, decision fixed);
orchestrator-reviewed, then extended with the field_utils trim + the probe
Vertex/model fixes.

## Lessons

- A retired tool's support code hides beyond the dispatch path: suggestion
  helpers, response plumbing in the coordinator, ws routing cases, and doc
  tables all named it. "Zero grep hits" is the only honest completion test.
- A measurement script whose default model/credential path cannot run on the
  billing-tracked platform is broken-by-default once that platform is the
  policy -- align probe defaults with production primaries.

## Doc freshness

tool-call-flow.md, voice-ai.md, ws-protocol.md, hipaa-pii-policy.md: the
get_field_value rows/lines updated with a retirement note (Last updated
bumped). Their broader continuous-DTI framing staleness stays with C8 (ft47),
sequenced after the C7 deletion. tool-call-flow.md's missing switch_to_field
row (pre-existing, PR #396/#397 era) deliberately not fixed here.

## Files touched

25 source/test files (see PR diff) + this entry + probe data artifacts.
Beads: lt9z already closed by PR #403 (not superseded-close as planned --
the interim fix shipped first); rve5 filed (Vertex script sweep).
