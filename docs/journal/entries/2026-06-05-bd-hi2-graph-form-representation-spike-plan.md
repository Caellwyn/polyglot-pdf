---
date: 2026-06-05
bead: polyglot-pdf-hi2
title: "Graph-based form representation (client-hydrated, LLM-traversable) -- research spike plan"
tags: [research, plan, schema-forms, voice-ai, architecture]
---

> **Status: PLANNING (not shipped).** This is the up-front plan for the `hi2`
> research epic, committed to the repo so remote/cloud sessions can read it and so
> we can revisit the rationale if a stage turns out to be a dead end. The
> per-stage *findings* land in their own bead closeouts; the final verdict lands
> in the `hi2.6` recommendation entry. If a stage is abandoned, record why here
> (or in that stage's entry) rather than deleting the reasoning.

## Trigger

`bd polyglot-pdf-hi2`, expanded from a one-line stub ("explore graph databases vs
JSON schema for forms") after a brainstorm with Gemini. The maintainer's vision:
represent each parsed PDF as a **graph** (the empty structure), stored by the
backend per form exactly as `schema.json` is today; at runtime the graph is
**hydrated client-side** as the user fills the form (values populate nodes, live
in `sessionStorage` like state does now), and the **LLM traverses the hydrated
graph via tool calls** to gather context, walk dependencies to direct the user,
and validate answers.

Output of the epic is a **measured recommendation + journal entry + throwaway
prototype** -- NOT shipped production code.

## Why this is worth exploring

1. **Authoring is manual.** There is no PDF -> schema extraction pipeline in the
   repo; schemas are curated by hand. The only forms authored on disk today are
   **I-90** (`form-kits/i-90/schema.json`, plus `_backup`/`_archived` variants)
   and **I-589** (`example_pdfs/i-589/` has *three* JSON artifacts --
   `i589_schema.json`, `i589_rich_schema_with_tu.json`,
   `i589_internal_structure.json`). I-485 / I-765 / N-400 are aspirational ("in
   flight"), not present. **Picking the canonical ground-truth file is an explicit
   first step of `hi2.1`** (the I-589 schema is ambiguous across three files; the
   precision/recall scoring in `hi2.4` is meaningless if it scores against the
   wrong one). Each new form costs real authoring time.
2. **The LLM consumes a flattened view.** The **default** runtime path is the
   *legacy full-schema* handshake, which ships ~7.4k tokens of flattened section
   text (`backend/services/ai_context.py`). JIT manifest mode exists but is
   **feature-flagged behind `USE_JIT_SCHEMA`**, not the default. Conditional logic
   is split across `show_if` (reactive) and `controls_fields` (proactive) -- the
   *same* edge encoded from opposite ends -- and the model can't *traverse*
   dependencies on demand. The 5 existing tools (`update_form_fields`,
   `get_form_status`, `switch_section`, `get_field_value`, `confirm_field` --
   `backend/config.py`) include no **dependency-graph** traversal primitive (i.e.
   "what does field X control / require?"). Note `get_form_status` and
   `get_field_value` *do* retrieve values -- and **already round-trip to the
   client over the WS** (`callback_handler.py` -> `request_form_state_from_client`
   -> `form_state_response`); see the topology caveat under Problem B.

## Key reframe vs. the original brainstorm

An earlier sketch (Gemini) proposed storing/fetching *filled field values* in
Spanner Graph server-side. That breaks the load-bearing **stateless-backend
invariant** (client owns all field values; backend never persists them --
`docs/standards/stateless-architecture.md`) and the **HIPAA/PII policy**
(`docs/standards/hipaa-pii-policy.md`). The maintainer's client-hydrated design
avoids this entirely: the backend stores only the graph *structure* (non-PII,
exactly like the JSON schema today); values live and are traversed client-side.
The "graph DB as runtime engine" (Spanner) question therefore largely dissolves --
what's needed is a graph *data model* + a client-side traversal layer the LLM
queries through tool calls, not a hosted graph database.

## Core question

Does representing forms as a **graph** -- authored once, stored by the backend per
form, **hydrated client-side** at runtime, and **traversed by the LLM via tool
calls** -- beat today's hand-authored JSON + flattened-section/JIT-manifest
approach on (a) authoring effort, (b) token cost, (c) dependency handling, and
(d) validation quality? And can the empty graph be auto-authored from a PDF via
Document AI + Gemini?

## Two separable sub-problems

### Problem A -- Authoring / ingestion (PDF -> graph structure)
Auto-generate the empty form graph from a raw PDF (Document AI Form Parser ->
Gemini structuring pass -> emit graph/`FormSchema`-shaped artifact). **Offline,
pre-deployment, never sees user values -- invariant-clean.** This is the real
bottleneck (no extraction pipeline exists today).

### Problem B -- Runtime representation (client-hydrated, LLM-traversable graph)
Whether the backend-served form representation should be a graph that the client
**hydrates** with values and the LLM **traverses via tool calls**, replacing the
current flattened-section schema / JIT manifest handshake.

- The current structure is already ~70-80% graph-native (if anything an
  understatement -- `backend/models/form_models.py` is already an edge list:
  `section.fields`, `part.section_ids`, `show_if.field`,
  `controls_fields[].shows/hides/unlocks/...` are all ID references, i.e. directed
  edges). So the *modeling* maps almost mechanically. The open bet is the
  **runtime traversal layer + LLM tool-call interface**, not the data shape.
- **The make-or-break topology (stated up front, not buried).** The LLM runs
  *server-side* (Gemini, proxied by the backend). The hydrated, value-bearing
  graph must live *client-side* (PII invariant -- backend may not hold values). So
  "LLM traverses the hydrated graph via tool calls" is **inherently a
  round-trip-per-hop design**: model emits function call -> backend -> **over the
  WS to the browser and back** -> result -> model resumes. This is a **Gemini Live
  (realtime voice)** session, where every hop is added latency the user hears as a
  pause and Live is billed partly on *session duration*, not just tokens.
  **CORRECTION (fresh-eyes, finding #1) -- the baseline is NOT zero round-trips.**
  Two of the five existing tools (`get_form_status`, `get_field_value`) **already**
  pay exactly this WS round-trip today: `callback_handler.py` ->
  `request_form_state_from_client` -> the `form_state_response` frame in
  `websocket_routes.py`. So the graph design does not *introduce* the
  client-round-trip cost -- it potentially *increases the number* of such hops per
  field (a multi-hop dependency walk vs. one `get_form_status`). The correct
  measurement for `hi2.2` is therefore **graph-traversal hops vs. the existing
  single-tool-call round-trip cost** (a known quantity), NOT vs. the zero-round-trip
  legacy full-schema path. This makes the latency picture less obviously fatal than
  the first draft implied: the question is the *delta in hop count*, not the
  existence of the hop. It remains the spike's #1 measurement and the most likely
  "reject/defer" gate, but framed against the right baseline.
- **Storage tier (maintainer-ranked): client-side primary, ephemeral-backend
  fallback.** Spike the **client-side hydrated graph** (lives in `sessionStorage`,
  traversed in the browser; LLM reaches it through tool calls routed over the WS)
  first. Only evaluate **ephemeral per-request backend hydration** if client-side
  traversal proves too heavy. **CAVEAT (fresh-eyes, finding #6) -- "ephemeral" is
  subtler than "per-request."** A multi-hop dependency walk is a session-long
  operation, so ephemeral-backend hydration is really two sub-options: (a)
  re-request from the client on *every* hop (pure client-side with extra steps --
  invariant-clean but the most round-trips), or (b) hold the hydrated graph in a
  backend dict keyed by `session_id` *across* the multi-hop sequence -- which is
  **in-memory per-session field-value state, exactly what the stateless invariant
  forbids** (`docs/standards/stateless-architecture.md`: "no ... in-memory dict
  that outlives the request handling"). Option (b) is the stateless violation
  renamed; only (a) is clean. `hi2.6` must make this distinction explicit if it
  recommends the ephemeral-backend tier at all -- "sharp PII edge but workable" is
  not a sufficient description. **Persisting values server-side (the "beef up
  compliance and store user data" path) is OUT of scope to decide here** -- it's a
  strategic product/compliance fork for the maintainer.
- **Wire-contract constraint:** any new representation must still compile down to
  what the frontend renderer and `/ws/fill` handshake expect, OR the bead must
  justify changing them (a step-2 escalation -- see Decision points).

### Out of bounds (record as rejected)
Storing/fetching **filled field values server-side** (Gemini's original Spanner
Phase-2). Recorded as a known-conflicting design, **explicitly ruled out** unless
the maintainer chooses to revisit the stateless invariant. Keeps the invariant
intact by default.

## Evaluation criteria

1. **Authoring speed** -- hand-curation hours/form vs. ingest-then-correct hours.
2. **Extraction correctness** (Problem A) -- field detection, type inference,
   `pdf_field_name`/`pdf_position` accuracy, conditional-logic recovery; measure
   precision/recall against a known-good hand-authored schema.
3. **Token cost** -- LLM traverses the graph on demand vs. shipping the whole
   section. **Baseline against the legacy full-schema path (~7.4k tokens), the
   actual default** -- not the already-lean feature-flagged JIT manifest.
4. **Latency / session duration (Problem B, first-class -- not a footnote).**
   Wall-clock cost of traversal tool calls round-tripping backend->client->backend
   *mid-voice-session*, and the effect on total Gemini Live session duration
   (billed). A token win that adds audible pauses or lengthens the session can be
   a net loss; measure head-to-head, not just token count.
5. **Dependency handling** -- can the LLM walk `controls_fields`/`show_if`
   closures to direct the user and decide what's next/required, as first-class
   traversal rather than the current split logic? (A graph model also dedupes the
   `show_if`<->`controls_fields` redundancy into one bidirectional-queryable
   edge -- a cheap, demonstrable win independent of the runtime bet.)
6. **Validation quality** -- can the model validate an answer against its
   dependents via traversal?
7. **Client-side feasibility / weight** -- bundle size, traversal latency in the
   browser, tool-call round-trip cost over the WS.
8. **Invariant / PII interaction** -- per-tier statement (client-side: clean;
   ephemeral-backend: clean ONLY in the re-request-per-hop variant, a stateless
   violation in the hold-across-hops variant -- see the Problem B caveat; persist:
   out of scope).
9. **Complexity / maintainability** -- new graph lib/model + traversal layer vs.
   a flat JSON file + existing renderer.

## Spike / prototype steps (throwaway; stores NO values anywhere durable)

These map 1:1 to the child beads (see family map below).

1. **Graph-model one real form** (`hi2.1`). **First, pick the canonical
   ground-truth schema file** (I-90's `schema.json`, or one of the three I-589
   files -- name it, since `hi2.4` scores against it). Translate it into a node/edge
   model (Form/Part/Section/Field/Option/Condition/PdfCoordinate +
   HAS_SECTION/CONTAINS_FIELD/TRIGGERS/MAPS_TO). Enumerate the "doesn't map
   cleanly" set -- **this is a discovery task, NOT an exhaustive pre-seed**:
   `FormField` carries ~25-30 non-ID-reference attributes, so the modeling will
   surface more than the seed list. Known-messy seeds (imperative/behavioral, not
   structural edges): `conditional_behavior.pdf_field_flag_change` (raw PDF bit
   manipulation -- the messiest), `auto_fill_na`, `copy_to`,
   `overflow_to_supplement`, plus validation presets, `table`/multi-entry columns,
   supplements, translations. "Done" = the FULL non-mapping set enumerated, not
   just the seeds confirmed. Also demonstrate the cheap win: collapsing the
   `show_if`<->`controls_fields` redundancy into one bidirectional edge.
2. **Build a runnable LLM tool-call traversal prototype, instrumented for
   latency** (`hi2.2`). Hydrate the graph with sample (non-real) values and wire
   actual LLM tool calls against it -- e.g. `get_field_dependencies(field_id)`,
   `get_next_required_field()`, `validate_against_dependents(field_id)`. **Measure
   tokens, wall-clock latency per round-trip, and total session duration against
   TWO baselines: (i) the existing single-tool-call round-trip (`get_form_status`,
   which already round-trips to the client) -- the apples-to-apples comparison; and
   (ii) the legacy full-schema path** on the same form. The central bet is the
   *delta in client-hop count per field* (multi-hop walk vs. one `get_form_status`),
   not the existence of the hop -- price that, not just tokens.
3. **Compile-back check** (`hi2.3`). Verify the graph representation **semantically
   compiles to a valid handshake the existing renderer + `/ws/fill` accept** --
   NOT byte-identical output. The wire format (`manifest.parts` / `part_id` keys)
   is already mid-migration (`polyglot-pdf-zun`); freezing the prototype to a
   moving target wastes spike time. Gate for Problem B.
4. **Ingestion spike (Problem A)** (`hi2.4`). Push one blank USCIS PDF through
   Document AI Form Parser + a Gemini-on-Vertex structuring pass; emit a draft
   graph; **measure** field precision/recall and conditional-logic recovery
   against the hand-authored ground truth.
5. **Client-weight probe** (`hi2.5`). Estimate browser bundle/traversal cost of
   the graph + traversal layer; note where ephemeral-backend hydration would
   become necessary.

## Files / docs the recommendation must reference

- `docs/standards/stateless-architecture.md` -- the invariant; basis for ruling
  value-storage out and keeping hydration client-side.
- `docs/standards/hipaa-pii-policy.md` -- no values/PII at rest or in logs
  server-side.
- `docs/schema_format.md` -- authoritative `FormSchema` spec; the compile target.
- `backend/models/form_models.py` -- Python models; schema source of truth in
  code (extraction ground truth + compile target).
- `frontend/src/schema-forms/types/schema.ts` -- frontend contract the renderer
  consumes.
- `frontend/src/schema-forms/state/schemaFormState.ts` --
  `SchemaFormStateManager`; where the hydrated graph would live client-side.
- `backend/adapters/live_ai_gemini.py` + `backend/services/form_filling_service.py`
  + `backend/services/ai_context.py` -- how the LLM gets form context today
  (legacy ~7.4k-token flattened path); where traversal tool calls would attach.
- `backend/config.py` -- the 5 current tool declarations + `USE_JIT_SCHEMA` flag.
- `backend/routes/websocket_routes.py` -- the `/ws/fill` handshake (legacy +
  `handshake_jit`) the representation must still produce.
- `backend/routes/pdf_fill_routes.py` -- existing schema -> filled-PDF direction
  (the inverse of the ingestion spike).
- `CLAUDE.md` "Escalation vs. autonomy" (step 2) -- doctrine for the decision
  points below.

## Decision points requiring maintainer escalation

The epic **recommends**; the maintainer **authorizes**. None are decided inside
the research beads:

1. **Changing the `/ws/fill` handshake / JIT manifest wire contract** to carry a
   graph representation -- a new contract other code depends on (step-2).
2. **Ephemeral backend value-hydration**, if the spike shows client-side is too
   heavy -- touches the PII edge; needs explicit sign-off.
3. **Persisting values server-side** (the compliance/"store user data" path) -- a
   documented-invariant break + strategic product/compliance fork.
4. **Adopting Document AI as a standing pipeline dependency** (Problem A) --
   lower-risk (offline, invariant-clean) but still a new paid-API dependency.
5. **Adopting any hosted graph DB** (e.g. Spanner) at runtime -- only if the spike
   surprises us and client-side traversal is infeasible; a new operational/cost/
   security dependency (step-2).

## Working hypothesis (to test, not assume)

- **Problem A (ingestion):** high-value, invariant-clean win; likely worth a
  follow-on implementation bead.
- **Problem B (client-hydrated graph + LLM tool-call traversal):** likely outcome
  is **"adopt-partially"** -- adopt the graph *model* (it dedupes
  `show_if`/`controls_fields` and cleans dependency queries, a defensible win on
  its own) but the *runtime LLM-traversal-over-WS* piece probably loses on **voice
  latency / session duration** unless the spike surprises us. No hosted graph DB
  needed either way. The spike confirms or overturns this with numbers.

## Bead family

```
hi2  Epic (this plan)                                              [P1]
├─ hi2.1  Graph-model one real USCIS form into nodes/edges         [P1]  foundation; only ready entry point
│   ├─ hi2.2  Latency-instrumented LLM traversal prototype         [P1]  Problem B central bet
│   │   └─ hi2.3  Compile-back: graph -> valid /ws/fill handshake  [P2]  Problem B gate (needs .2's interface)
│   ├─ hi2.4  Ingestion spike: Document AI + Gemini structuring     [P2]  Problem A, parallel track
│   └─ hi2.5  Client-weight probe: browser bundle + traversal cost  [P3]
└─ hi2.6  Compile recommendation + journal entry                   [P1]  blocked on .2/.3/.4/.5
```

`hi2.1` is the foundation all other children build on. `hi2.3` depends on **both**
`hi2.1` AND `hi2.2` (fresh-eyes finding #4): the compile-back target only makes
sense once `hi2.2` has sketched the node/edge shape + traversal API, else it
freezes a premature interface that `hi2.2` then changes. `hi2.4` (Problem A) is
engineering-parallel and depends on `hi2.1` only for its scoring ground-truth;
`hi2.6` produces the adopt/adopt-partially/reject/defer verdict.

## Verification (how the epic's own work is checked)

- Prototypes are throwaway, not wired into the app, and store no real values.
- Token AND latency/session-duration measurements are head-to-head on the *same*
  form vs. **two baselines**: the existing single-tool-call WS round-trip
  (`get_form_status`) and the legacy full-schema path.
- Compile-back check demonstrably produces a handshake the existing renderer +
  `/ws/fill` accept (semantic validity, not byte-identity).
- The recommendation (`hi2.6`) lands as a journal entry citing the docs above;
  escalation points are listed explicitly for the maintainer.

## Fresh-eyes review (2026-06-05, pre-PR)

A fresh-eyes pass verified the plan's codebase claims against source and surfaced
six findings, all folded in above:

1. **Latency baseline was wrong (blocking).** `get_form_status`/`get_field_value`
   already pay the client WS round-trip today (`callback_handler.py` ->
   `request_form_state_from_client`). The graph design doesn't *introduce* the hop;
   it changes the *hop count per field*. `hi2.2` now measures against the existing
   single-tool-call round-trip, not a false zero. Reframes Problem B as less
   obviously latency-fatal.
2. **I-589 ground truth is ambiguous** (three JSON files on disk). Picking the
   canonical file is now an explicit first step of `hi2.1`.
3. **"No traversal primitive" clarified** to "no *dependency-graph* traversal" --
   `get_form_status`/`get_field_value` are value-lookup primitives.
4. **Missing dep edge** `hi2.3` -> `hi2.2` (compile-back needs `hi2.2`'s
   interface). Edge added to the bead tree.
5. **Doesn't-map list is a discovery task, not an exhaustive pre-seed** (`FormField`
   has ~25-30 non-edge attributes). `hi2.1` "done" = full enumeration.
6. **Ephemeral-backend tier is subtler than "per-request"**: the hold-across-hops
   variant is the stateless violation renamed; only re-request-per-hop is clean.
   `hi2.6` must distinguish them.

## Closeout record

- **Tests:** 189 passed, 2 skipped (closeout prep, `backend/tests/`). This branch
  changes no source, so the green run stands.
- **Doc freshness:** the checker flags ~16 stale `docs/` files, but every one is
  stale against backend/frontend commits dated 2026-06-04 that are already on
  `dev` -- NOT against anything this branch touched (this branch adds one journal
  entry and zero tracked source files). Reviewed and left as-is; they were stale
  before this branch and bumping unrelated docs would be scope creep.
- **Beads housekeeping:** no orphans. One stale in_progress bead surfaced
  (`polyglot-pdf-hrn`, harness tuning, ~4 days) -- a separate, unrelated
  workstream, not touched here; left for its own owner.
- **Review:** journal-only PR -> Copilot review skipped per the closeout
  review-worthiness gate (no runtime regression possible). Fresh-eyes ran (its
  six findings are folded in above).
