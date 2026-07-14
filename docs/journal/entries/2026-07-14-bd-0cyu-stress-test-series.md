---
date: 2026-07-14
beads: [polyglot-pdf-0cyu, polyglot-pdf-3gt9]
epic: polyglot-pdf-00pt
tags: [harness, performance, testing]
---

# Full-system stress-test series (E0-E6): the assembled system, measured live

Epic `polyglot-pdf-00pt`, run bead `polyglot-pdf-0cyu`. The P0 harness (bd
n86b/eh1h, PR #432) built the rig; this is the live measurement series that ran
on it, plus the reconcile + fixes the runs forced. 25 live Vertex runs,
**$39.29** of the $42-approved ceiling.

## What shipped

**The reconcile (bd 3gt9 + the seam pass).** Before spending, the harness's
validator-seam stand-in was reconciled to the landed W2/W3/W4 client (it was
written against the pre-W2 spec, marked RECONCILE-BEFORE-E1). The audit found a
load-bearing gap: W3 split "conflict reported" from "steer delivered" --
`validation_result` is now report-only, findings queue client-side, and the
steer injects only via a separate `drain_findings` round-trip. The old harness
set `steered` at report time and never called `handle_drain_findings` at all,
so it would have measured steer latency from the wrong event. Rebuilt to
settledness-driven windows + the report->queue->drain->result flow + W4
steered-clear-on-value-change + the W6 pro pass at form-complete + per-model
ledger pricing (a 2.5-pro call must not bill at flash-lite rates). Also fixed
`3gt9` (7 answered fields whose unhappy "wrong" phrasing equalled the right
answer) with a build-time guard so the class can't recur.

**The series.** E0 pilot -> E1 happy x3 -> E2 realistic x3 -> E3 unhappy x3
(one with the pro pass) -> E4 reactivity x11 -> E6 Spanish pilot + full. Each
run emits a summary.json with all-in USD, wall-clock, fill accuracy + failure
modes, validator P/R + steer compliance, secretary/nav latency, and the error
taxonomy. Findings synthesized in `scripts/spikes/systems_stress_findings.md`
(executive verdict + investor table + 10 data sections), cost-curve charts in
`scripts/spikes/data/charts/`, and the pitch source material consolidated under
`pitch/i90-stress-test/`.

**Headline numbers.** $2.44 +/- $0.04 and ~16 min for a full happy I-90; flat
$0.021/question marginal cost (cost is LINEAR in form length -- the compression
window killed the escalating-context curve); Spanish fill accuracy 88.5% vs
English 85.8% (multilingual holds); validator caught 100% of planted near-pairs
+ one real transcription error in the wild; W6 pro pass $0.0045/6.6s live.

**Fixes the runs forced (harness only -- product issues went to beads).**
E0 exposed that `CONTINUOUS_SESSION` was left False in harness settings, so the
model saw the 7-tool catalog and called the deprecated switch_section
(fixed -> 6-tool parity); Vietnamese names mis-transcribed unspelled (fixed to
spell-out phrasing, and filed as a product bug). E1 exposed a spontaneous-1011
wedge in the harness's dead-session detection (fixed: is_session_active +
stall-streak breaker) and that the steer window discarded organic validator
catches (fixed). E4 exposed the harness's field resolver was stricter than
production's (fixed to full resolveFieldForNavigation parity).

## Beads filed (product findings, NOT fixed here -- maintainer sequences)

Nine, all on the dolt remote with run-artifact evidence + exit criteria:
`cx23` (P1: checkbox decline sometimes CHECKS the box -- legal-form wrong
answer), `2af7` (chatty-secretary mode: per-field spoken-name lookups, the
biggest combined cost/latency/accuracy lever), `5roy` (non-Anglo name
transcription), `3vby` (switch_to_field identifier hallucination), `a1ql` (kit
`required` shape mismatch -- gate never enforced), `kpa1` (g1b answer-key
staleness), `o0ow` (signature field carries a phone pattern), the token-log
`session_cumulative` cost-reset-on-reconnect finding (under-reports spend >2x),
and the voice-harness `runMultiSectionScenario` staleness. Plus a deployed-
latency-capture follow-up (below).

## Assess outcome

The pre-PR fresh-eyes/Opus loops already cleared the P0 harness (PR #432). This
branch is the measurement RUN on that reviewed rig plus small harness fixes +
data artifacts + docs; the code fixes are each narrow and were exercised by the
34-test suite (kept green throughout) and by the live runs themselves.

## Doc freshness

No tier-1/tier-2 doc tracks `scripts/spikes/` or `pitch/`; the findings doc IS
the record. The pre-existing `voice-and-vad.md` / `technical_guide.md`
staleness (flagged since PR #432, against files this branch does not touch) is
left for the branch that touches those surfaces.

## Named limitation

Deployed turn-latency is the one un-captured metric: the deployed demo verified
GO (loads/connects/streams over Vertex, no 1011), but the production build
strips the harness audio hooks and the measurement env has no mic, so no full
voice turn can be driven headlessly. All latency in the report is LOCAL and
asterisked as an upper bound (deployed is faster -- co-located backend). Filed
as a follow-up; needs a hooks-enabled demo build or a human voice test-drive.
