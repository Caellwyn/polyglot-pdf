# Research plan: principal/secretary architecture (SI reduction via task delegation)

> Two halves of ONE system: a thin **principal** (the live voice model) fed the
> current question via **Dynamic Turn Injection**, and a cheap **secretary**
> (flash-lite) that holds the form catalog + values and answers the principal's
> prose memory/navigation queries. The big win is a TINY principal SI; the
> secretary is what makes a tiny principal still able to navigate.

*2026-06-16. Epic polyglot-pdf-jnjj (SI reduction via task delegation; epic plan:
`~/.claude/plans/stateless-tinkering-zebra.md`). Written for the product owner.
This is a RESEARCH plan -- it defines what to measure and the kill-gates, not a
build commitment. The principal/secretary direction was **maintainer-directed in
the 2026-06-16 design discussion** (a new architectural direction within the
epic's "task delegation" thesis, authorized directly by the owner rather than
derived from the written epic plan); it broadens the A pillar beyond the
manifest-swap-only framing.*

## The idea

Model the voice-fill system on a **legal professional hierarchy**: a **principal**
(the live voice model talking to the client) and a **secretary** (a cheap, fast
assistant model that holds the form's full field catalog and the client's current
answers). When the principal needs a past answer -- "what did the client say her
previous last name was?" -- it doesn't stop to dig through the whole form in its
own context; it **buzzes the secretary** with a prose question and gets back
either the answer or a clarifying question ("did they mean their married name or
their maiden name?").

**Why this shape.** The measured cost reality (see
[`../standards/logging-and-cost.md`](../standards/logging-and-cost.md)) is that on
the production model (2.5), the **system instruction re-sent every turn is
95-98% of the bill**. The cheapest possible principal carries ONLY the current
question's full context plus the recent conversation -- never the whole form. But
a principal that thin **cannot navigate**: it doesn't know other fields exist, so
it can't go back to a previous answer or circle back to an unfilled one. The
secretary restores that capability **without** putting the form catalog in the
expensive per-turn context: the catalog lives with the cheap model instead.

The principal/secretary split is the general form of the same lever the
section-reset flow already pulls (cap the principal's context to less than the
whole form). JIT/manifest was one compromise point on that spectrum
(section-sized context); this architecture pushes to the per-question end while
keeping navigation (via the secretary).

## The principal: Dynamic Turn Injection (replaces the JIT schema-drip)

The principal's SI is **tiny and static** (~behavioral rules only, target <=200
tokens): "you are a voice intake assistant; fill one field at a time; the backend
injects the current field's guidance before each turn; for anything about past
answers or other fields, call `ask_secretary`." It carries NO form catalog and NO
field schemas.

The current field's guidance (spoken_name, help.instructions, format_hint,
options, validation hints) is supplied as a **`client_content` text turn**, NOT in
the SI and NOT via a tool-response schema drip. The backend injects the active
field's guidance before the user answers it; when the field is done, it injects
the next field's guidance. This is the same mechanism the cost harness already
exercises at SECTION granularity (`switch_to_section` + activity brackets) -- just
finer-grained, per field.

**Why this REPLACES the JIT schema-drip (bd jnjj.22).** The Live API WebSocket
cannot change the SI mid-session, and the old JIT plan tried to drip field
schemas through tool responses -- which is the mechanism that is broken (the
backend only ever holds one field's schema; bd jnjj.22). Dynamic Turn Injection
sidesteps it entirely: guidance arrives as conversation turns, so there is no
schema-drip to fix. jnjj.22 is therefore reframed from "fix the drip" to "replace
the schema-drip with per-question injection."

**Anti-accumulation (a sub-decision, NOT the main win).** Injected guidance must
not pile up across questions. Options, in priority order of importance (all
second-order to "shrink the SI"):
- **Calibrated-eviction (the candidate):** size the context-compression window to
  ~the static SI, so each turn's injected guidance is deterministically evicted
  after its turn and the backend re-injects the NEXT field's guidance fresh. This
  turns eviction from "hope it fires" into a mechanism. Builds directly on the l3a
  finding: compression was useless ONLY because the SI was huge and unevictable;
  with a tiny SI and the guidance in evictable `client_content`, compression
  finally has the right target. (UNVERIFIED on 2.5 native-audio -- a measured
  gate, see Gate 1.5.)
- **Per-turn re-injection:** inject the current field's guidance EVERY turn (so the
  window only ever needs to hold one field's worth) -- robust but chattier.
- **Session-reset / explicit "disregard prior guidance" prompt:** fallbacks if
  calibrated eviction does not behave.

These anti-accumulation choices are explicitly **small fish.** The BIG win is the
tiny principal SI + offloading catalog/value awareness to the secretary; how we
prevent accumulation (compression vs. reset vs. per-turn re-inject) is a
second-order calibration we pick by measurement.

## What we've settled (design decisions, 2026-06-16)

1. **The secretary is a NEW tool call**, e.g. `ask_secretary(query)`, native to
   the existing Gemini tool-call flow (alongside `update_form_fields` /
   `confirm_field`). It is a **separately-programmed agent** -- its own system
   instruction and config -- NOT the B-pillar validator. It may share the cheap
   model and the client-state plumbing with the validator, but it is a different
   brain doing a different job.
2. **Model: `gemini-2.5-flash-lite`** (~$0.10 / 1M tokens). Single target. Staying
   in the Gemini family is a **HARD constraint** -- the HIPAA BAA covers Gemini
   only; adding another model family is legal overhead we will not take on for
   research. So model choice is fixed; the question is whether flash-lite is FAST
   ENOUGH, not which model.
3. **The principal takes prose, not field IDs.** It asks in natural language; the
   secretary maps prose to the right field(s). The principal's context therefore
   needs NO field catalog at all -- the whole structure moves to the secretary.
   This is a deeper SI cut than the manifest swap (which still listed every
   field).
4. **The secretary's information contract** (derived from its two jobs --
   prose->field mapping, and value/status retrieval):
   - **Static, from the schema** (the disambiguation context): `id`,
     `spoken_name`, `spoken_aliases`, `help.instructions` (+ `help.format_hint`),
     `section_label`/positional context, `type`, `options`. This is what lets it
     map a prose query to the correct field and disambiguate the ~5 "name" fields.
   - **Dynamic, from the client `sessionState`** (NOT the schema, NOT the
     backend): current `value`, `filled`/`confirmed` status, and **whether the
     field is currently shown** (applicability). The front-end already tracks
     shown/hidden for its own conditional UI rendering, so the secretary gets
     applicability FOR FREE and never evaluates `show_if`/`copy_from` itself. This
     keeps the secretary a retrieval specialist, not a logic engine, and honors
     the stateless-backend invariant (client owns state).
   - **Excluded:** PDF mechanics (`pdf_position`, `pdf_field_name`, `is_comb`,
     widget consolidation), regex/`validation.pattern` (the secretary reports
     values, it does not re-validate), and raw conditional logic (the client
     already resolved applicability).
5. **Caching architecture: static prefix + flat-values tail.** The secretary's
   request is `[CACHED: secretary SI + static field catalog] + [FRESH, small:
   current values + applicability + the prose query]`. The static catalog never
   changes within a session -> ideal cache content. Values change every turn ->
   they ride in the small uncached tail, built from the live `sessionState` form
   state (deterministically current; a separate append-only client-side input log
   may exist for compliance but is NOT what the model parses -- the model only
   ever sees clean current state, never a contradiction log it would have to
   reduce by timestamp). Explicit-vs-implicit caching is an open question gated on
   verifying Gemini's caching facts first (see Gate 2).

## The three gates (sequenced, each KILLABLE)

Run in order; a fail at any gate stops the spend on the next. Modeled on the
G1/G2 keystone-probe discipline.

### Gate 0 (prerequisite, not optional): measure on the REAL I-90

ALL secretary measurement uses the real I-90 schema
(`form-kits/i-90/schema.json`: 8 parts / 16 sections / 132 fields, with
`help.instructions` on 132/132), NOT the demo schema. The demo
(`adult_intake_demo_schema.json`) is non-representative (flat `description` on
2/174 fields, no nested `help`) and invalidated the prior JIT measurements.
Depends on the harness port (bd jnjj.24) and the help-context fix (bd jnjj.23).

### Gate 1 -- RECALL: can a cheap model find the right field from prose?

The keystone. Give flash-lite the static catalog + flat values and a set of prose
queries (including the hard cases: the 5 ambiguous "name" fields, "go back to X",
"have I answered Y", value-vs-applicability). **Measure: does it return the
correct field + correct value/status, and does it ask a sensible clarifying
question when genuinely ambiguous?** Includes the disambiguation that
`help.instructions` is supposed to enable ("previous name = the name on your green
card"). KILL if a cheap model confidently returns the wrong field/value -- in
legal intake, a confident wrong "name" is a real harm. (Recall is first because
if the secretary can't reliably retrieve, latency and cost are moot.)

### Gate 2 -- LATENCY: is the blocking round-trip fast enough?

The secretary call is BLOCKING -- the principal waits mid-conversation before it
can answer the client (unlike the validator, which can be async). **Measure the
real round-trip** on the live demo: principal emits `ask_secretary` -> flash-lite
(with explicit-cached static catalog) -> answer back. KILL if it adds enough delay
that the "buzz the secretary" UX feels like waiting for someone to walk to the
basement. **Caching is THE lever here** -- this gate first establishes Gemini's
caching facts from authoritative sources (vendored `docs/genai_docs/` first, then
live API): explicit-cache token MINIMUM (does our ~2.7-5.9k-token catalog clear
it?), explicit storage cost vs. implicit discount at flash-lite pricing, and
cache-creation latency. Then measures cached-query latency.

### Gate 1.5 -- PRINCIPAL VIABILITY: does Dynamic Turn Injection hold together?

Runs alongside the secretary gates (it is the principal half). Two UNVERIFIED
claims must be measured on the real I-90 before the architecture is trusted (we
have been wrong about 2.5 native-audio behavior before -- treat as hypotheses):
1. **Calibrated eviction works.** With a tiny static SI and per-question guidance
   in `client_content`, does sizing the compression window to ~the SI actually
   evict old guidance turn-over-turn WITHOUT degrading fill behavior (the model
   doesn't lose the CURRENT field's guidance, and doesn't bleed the PREVIOUS
   field's)? Builds on l3a (compression was useless only because the SI was huge);
   this is the "now there's something evictable" re-test.
2. **Per-turn injection cost is what we expect.** Injecting ~150-200 tokens of
   guidance per turn (vs. carrying the form catalog) should be a large net
   reduction; measure it, don't assume.
KILL/adjust the anti-accumulation mechanism (calibrated eviction -> per-turn
re-inject -> session reset) based on what behaves.

### Gate 3 -- COST: does the principal/secretary architecture save money?

Only if the prior gates pass. **Measure** the full-session cost of the
injection-principal + secretary system vs. today's section-reset baseline
(re-measured on the I-90): the tiny principal SI should shrink the 95% text-in
bill dramatically, net of the (cheap, possibly-cached) secretary calls + the
per-turn guidance injection. KILL if the net is not a clear win over section-reset.

## Relationship to the rest of epic jnjj

- **The JIT schema-drip is being REPLACED, not repaired.** The merged G2 (bd
  jnjj.6) NO-GO measured the JIT-manifest mechanism, which is now superseded by
  Dynamic Turn Injection. jnjj.6's NO-GO stands only as "JIT-as-built is broken";
  it does not bear on this architecture. **G2-REDO (jnjj.25) is repurposed** from
  "measure JIT-as-built on the I-90" to "measure the injection+secretary
  architecture vs. the section-reset baseline" (Gate 3 above) -- the baseline
  comparison survives; the thing compared is what we will actually ship.
- **The spectrum:** how much of the form the principal carries (whole-form ->
  section -> current-question-only). Section-reset is today's baseline;
  injection+secretary is the current-question end. This plan pursues that end
  directly rather than the section/JIT middle.
- **Shared infra with the B pillar:** the secretary reuses the cheap-model adapter
  and client-state payload the validator (bd jnjj.14, `TextAIGemini`) establishes,
  but is a distinct agent.

## Prerequisite beads

- **jnjj.22** -- REFRAMED from "fix the JIT next-field drip" to "replace the
  schema-drip with per-question Dynamic Turn Injection" (the drip mechanism is
  deleted, not fixed; see the principal section above).
- **jnjj.23** -- fix the voice-model SI to carry `help.instructions`/`help.*`.
  This is the CONTENT injected per question (the principal's current-field
  guidance); today it is silently dropped on real forms.
- **jnjj.24** -- port the cost/measurement harness to the real I-90 schema (shared
  by every gate here).

## Sequencing

The prerequisites (jnjj.22 reframed, jnjj.23, jnjj.24) gate the measurement gates.
G2-REDO is repurposed as the Gate-3 injection-vs-baseline comparison (no separate
"is JIT-as-built viable" run -- that mechanism is being replaced). Open: whether
to build the principal (injection) and secretary in lockstep or stagger them; to
decide once the prerequisites are closer to done.
