# Sprint 4 -- Sliding-window context management exploration (post-SDK-2.8 re-test)

*Approved by the maintainer 2026-06-12. Epic bead: see "Bead tree" below.*
*Doctrine: [docs/doctrine/planning.md](doctrine/planning.md). This plan is the
Scope+Plan half of SPEAR; each child bead runs Execute/Assess/Resolve through
`/next-bead` and `/closeout`.*

## Why

A post-SDK-cutover probe (bd `polyglot-pdf-eycd`, 2026-06-11) found that Gemini
Live's `ContextWindowCompressionConfig` sliding window -- a proven silent no-op
on native-audio models as of 2026-06-04 (bd `l3a.1`, SDK 1.38.0) -- **now evicts
on `gemini-3.1-flash-live-preview`** under google-genai 2.8.0: prompt tokens
dropped 1,972 -> 1,046 on crossing trigger=1500/window=800. `gemini-2.5` is
untested: its probes crashed with 1011 internal errors after the first turn,
BEFORE the trigger could fire (same instability class as bd `daa`).

If compression holds on the production model tier, it could replace the
section-disconnect context management: lifting the 15-minute audio cap (a whole
form in one continuous session -- a product capability change), converting
quadratic in-session cost growth to linear, and simplifying the architecture.
This epic establishes whether that is real, what it costs, and ends with the
maintainer's go/no-go on a cutover epic (the cutover itself is out of scope).

Maintainer constraints baked into the design:

- **Text and audio tokens are measured separately** (billed differently; the
  maintainer's earlier cost digging found text-in tokens dominated total cost --
  that finding drove the current JIT-schema/section-reset architecture and must
  be re-checked here, not assumed).
- **PII lifetime in Gemini's ephemeral context is NOT a concern** (maintainer
  call, 2026-06-11) -- do not weigh it in the go/no-go.
- **All pre-cutover experimental findings are stale hypotheses** (bd memory
  `pre-sdk28-findings-stale-recheck-everything`): re-verify, and update docs
  where stale claims live, as part of each bead.

## Exit rubric

| # | Criterion | Verify |
|---|-----------|--------|
| 1 | A fresh, endpoint-verified compression verdict exists per model (2.5, 3.1) on SDK 2.8.0: does eviction occur, and does the config cause errors -- from a matrix of {off / on-but-trigger-never-fires / on-with-low-trigger} x N>=5 repeats x 2 separate days, with captured error payloads classifying the 2.5 failure (transient / compression-triggered / our bug) | Read the new spike findings doc; the DEAD END banner in `docs/components/context-compression.md` is replaced with the new per-model verdict; re-run command included |
| 2 | Per-question token/cost CSVs exist: both models x three arms (unbounded / section-reset emulation / sliding window) x both scripts (happy: 2 turns/question; unhappy: 4 turns/question), one row per question 1-20 with columns exactly: question number, audio in tokens, audio in cost, audio out tokens, audio out cost, text in tokens, text in cost, text out tokens, text out cost, total tokens, total cost -- pricing re-verified against Google's published page and date-stamped | Open the CSVs; 20 rows + 11 columns; spot-check one row's cost = tokens x `config.py` rate |
| 3 | A window-size recommendation exists, derived from the measured growth curve via elbow analysis weighted by an assumed real-world happy/unhappy mix, and reporting latency at the compression event and per-turn tool-call compliance before/after eviction | Read the analysis doc; every number traceable to a CSV |
| 4 | A plain-language go/no-go decision brief (current system vs sliding-window revamp: cost, latency, reliability, 15-min-cap lift) is delivered and the maintainer's decision is recorded on the epic bead | Brief exists; maintainer decision logged on the epic bead |

Rubric changes, if any, are logged on the epic bead -- never silent.

## Why three arms (not two)

The originally sketched comparison was "unbounded baseline vs sliding window."
But the decision-relevant baseline is the **current production flow -- section
resets** -- which already bounds context by restarting the Gemini session at
section boundaries (re-sending a ~3.4-3.6 KB system instruction each time; a
20-question run on the demo form crosses roughly 2 section boundaries). The
three arms are therefore:

- **(a) unbounded single session** -- yields the raw growth curve the elbow
  analysis needs;
- **(b) section-reset emulation** -- the real cost baseline the go/no-go is
  judged against, and the arm that exposes the per-reset text-in re-send cost;
- **(c) sliding window** -- the candidate.

## Bead tree

One bead = one PR. Children 1 and 2 have disjoint surfaces and no ordering edge:
**parallelizable**. Child 3 depends on 1 (the go) and 2 (the instrument);
child 4 depends on 3. The epic is blocked by all four (parent-child deps).

| Child | Title | Surfaces (writes) | Inherits |
|---|---|---|---|
| 1 | Compression diagnosis matrix on SDK 2.8 (both models) + doc banner update. Fixes the probe verdict-logic bug first (it keyed on `cached_content_token_count`; the real eviction signal is a `prompt_token_count` drop). **Ends in escalation gate: report verdict to maintainer, get the go.** | `scripts/spikes/diag_compression_usage.py`, new `scripts/spikes/` matrix script + findings doc, `docs/components/context-compression.md` | 1 |
| 2 | Per-question token/cost CSV instrumentation + 20-question happy/unhappy scripts (value+confirm; value/no/correct/yes) with audio fixtures or cached gTTS; pricing verification vs Google's published page | new `scripts/spikes/` measurement script + prompt scripts/fixtures, `backend/config.py` (pricing date-stamp comment only) | 2 |
| 3 | Three-arm measurement run: both models x {unbounded, section-reset emulation, sliding window} x {happy, unhappy}; collects per-question CSVs, latency at the compression event, per-turn tool-call compliance | new data/findings files under `scripts/spikes/` only | 2, 3 |
| 4 | Elbow analysis + plain-language go/no-go decision brief. **Ends in escalation gate: maintainer renders the go/no-go.** | new analysis/brief doc under `docs/` | 3, 4 |

## Out of scope

- The cutover epic itself (filed separately only if the step-4 go/no-go is a go).
- PII-lifetime policy in Gemini context (maintainer: not a concern).
- Session-resumption / GoAway work (open beads `wnt`, `c5t` -- the go/no-go
  brief notes interactions, does not implement).
- Fixing 2.5's 1011 instability itself (bd `daa` territory) -- child 1 only
  classifies it.

## Evidence base (for the executing agents)

- bd `polyglot-pdf-eycd` -- the post-cutover probe evidence (3.1 eviction
  numbers, 2.5 1011 status). Closed as absorbed into this epic.
- `scripts/spikes/l3a1_compression_rootcause_findings.md` -- the pre-cutover
  dead-end diagnostics (now historical; useful for the diagnostic technique).
- `scripts/spikes/tak_token_curve_findings.md` -- the unbounded-curve method.
- The adapter already logs per-turn per-modality tokens + costs to
  `backend/logs/token_usage.jsonl` (`live_ai_gemini.py` usage handling;
  `docs/standards/logging-and-cost.md`) -- the CSV instrumentation reads this,
  it does not re-derive token accounting.
- `docs/components/context-compression.md` -- carries the stale DEAD END banner
  until child 1 replaces it.
