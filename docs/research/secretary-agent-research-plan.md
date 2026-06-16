# Research plan: the "secretary" agent (principal/assistant SI reduction)

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
(section-sized context); the secretary pushes toward the per-question end while
keeping navigation.

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

### Gate 3 -- COST: does delegating to the secretary actually save money?

Only if Gates 1-2 pass. **Measure** the full-session cost of the
principal/secretary system vs. today's section-reset baseline (re-measured on the
I-90, bd jnjj.25): the thin principal SI should shrink the 95% text-in bill
dramatically, net of the (cheap, possibly-cached) secretary calls. KILL if the
net is not a clear win over section-reset.

## Relationship to the rest of epic jnjj

- **The JIT/manifest cost question is NOT settled.** The merged G2 (bd jnjj.6)
  NO-GO is **invalidated** (wrong schema, starved payload, blocking drip bug) --
  it means "JIT-as-built is broken," NOT "JIT isn't worth it." A valid go/no-go
  is bd jnjj.25 (G2-REDO), gated on jnjj.22 + jnjj.23 + jnjj.24.
- **The secretary and JIT are points on the same spectrum** (how much of the form
  the principal carries: whole-form -> section -> current-question-only). G2-REDO
  measures the section/JIT end; this plan researches the current-question +
  secretary-navigation end. They inform each other; neither presupposes the other.
- **Shared infra with the B pillar:** the secretary reuses the cheap-model adapter
  and client-state payload the validator (bd jnjj.14, `TextAIGemini`) establishes,
  but is a distinct agent.

## Prerequisite beads (must land before secretary measurement)

- **jnjj.22** -- fix the JIT next-field drip (so any per-question context delivery
  works).
- **jnjj.23** -- fix the voice-model SI to carry `help.instructions`/`help.*` (the
  principal's current-question context must be production-faithful; today it is
  silently dropped on real forms).
- **jnjj.24** -- port the cost/measurement harness to the real I-90 schema (shared
  by G2-REDO and the secretary recall/latency tests).

## Open question for the owner

The secretary research and G2-REDO both depend on the same three prerequisite
fixes. Sequencing options once those land: (a) run G2-REDO first (does the
section/JIT approach become viable on the real I-90 with correct context?), then
research the secretary only if JIT still disappoints; or (b) research the
secretary in parallel, since it is a different architecture that may win
regardless of the JIT verdict. To be decided when the prerequisites are closer to
done.
