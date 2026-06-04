---
date: 2026-06-03
bead: polyglot-pdf-nv0
title: "Design: map Gemini context-window compression onto the stateless backend"
tags: [voice-ai, cost, architecture, design]
---

## Trigger

`bd polyglot-pdf-nv0` (phase 2 of epic `l3a`): design how the Gemini Live API's
server-side `ContextWindowCompressionConfig` (compression trigger + sliding window)
and size limits fit our stateless backend where the client owns all field state.
Fed by the `tak` spike (PR #34), which quantified the compounding re-billing curve.
Design-doc-first; no code change in this bead (`45o` owns the adapter wiring).

## What shipped

A new tier-2 component doc, [`docs/components/context-compression.md`](../../components/context-compression.md),
registered in `docs/INDEX.md` and the `CLAUDE.md` trigger-read table. Plus
design-decision notes pushed onto the downstream beads and two deferred-scope beads
filed.

**The headline finding.** I modeled the cumulative cost with code from the `tak`
curve + in-repo 3.1 pricing, across two session profiles (40 short turns, 120
long-intake turns). The key insight is the *shape*: today's unbounded context
re-bills a context that grows ~linearly with turns, so **cumulative cost is
quadratic (~n^2) in session length**; a sliding window caps per-turn context, making
per-turn cost constant and **cumulative cost linear (~n)**. Against the current
system (unbounded -- the real baseline), a window saves ~3x-10x and the gap *widens*
with length: $6.79 -> ~$0.94 at 120 turns (~7x), $26.86 -> $1.91 at 240 turns (~14x).
At deployment scale that is the difference between viable and runaway per-form
economics. So compression is a **large cost win vs. the status quo**, on top of the
duration (lifts the 15-min cap) and simplicity/robustness wins. The only nuance: a
window is not the theoretical *minimum* (a full context reset, which we don't have,
keeps no history and would be marginally cheaper) -- but that residual gap is small
next to quadratic->linear. A second consequence: the docs' example 25k trigger never
fires for us (40-turn sessions peak ~9k tokens; the 15-min cap, not turn count,
bounds real length), so recommended params are a low ~5k trigger / ~3-4k window.

(Note: an earlier draft of this doc wrongly anchored "is it a cost win?" against a
hypothetical periodic-reset baseline that does not exist in the code, and concluded
"not a cost win." Corrected before merge -- the real baseline is the unbounded status
quo, against which it is a big win.)

**Verified SDK syntax.** The vendored `docs/genai_docs/` names
`ContextWindowCompressionConfig` but ships no runnable example, so I introspected
the installed `google-genai` in `backend/.venv`: `context_window_compression`
takes `trigger_tokens` (int) + `sliding_window=SlidingWindow(target_tokens=int)`;
`target_tokens` must be `< trigger_tokens` and defaults to `trigger/2` if unset.
The doc records this as the canonical reference for `45o`.

**Stateless reconciliation + PII layering.** The doc establishes that compression
operates on the live in-session context only -- it does not touch handshake
rehydration, adds no server-side state, and preserves the stateless invariant. It
adds a three-layer PII table (client may store/send; Cloud Run never; Gemini holds
ephemerally) per maintainer clarification, noting that a sliding window changes the
*eviction profile* of PII in Gemini's context (window schedule vs. section-switch /
teardown) -- a conscious, documented choice, not a silent one.

**Workaround map (hand-off to `7kp`) -- corrected after a code audit.** Fresh-eyes
flagged, and I confirmed, that the backend **never built a cost-motivated
context-bounding restart**: the idle-timeout watchdog closes the WS on inactivity
(health/UX, does not call finalize), the Level-3 finalize is a frontend-initiated
farewell flow (UX), and the section-switch restart is an intentional reset. Today
context simply grows unbounded (the `tak` curve). So there is **nothing for
compression to retire** -- `7kp`'s scope shrinks from "remove hacks" to a
verification/cleanup pass, and the epic title ("replace manual disconnect/restart
hacks") predates this audit. Compression itself is gated behind
`CONTEXT_COMPRESSION_ENABLED` so the bounded-vs-unbounded behaviour is one env var
from reverting. (My initial draft mischaracterized the idle/Level-3 path as a
cost-motivated finalize; fixed before merge.)

**Beads.** Updated `45o` (param + syntax notes) and `7kp` (sideline map). Filed two
deferred-scope beads under epic `l3a`: `wnt` (evaluate `session_resumption` -- likely
a no-go, in tension with the stateless design) and `c5t` (adopt GoAway handling --
small UX follow-up). Both wired parent-child and verified; state pushed to Dolt.

## Defended autonomous decisions

- **Artifact form = tier-2 component doc.** The bead said "design doc first" without
  naming the form; I picked a discoverable component doc over a bead-note or
  journal-only capture (step-3 form-of-artifact call).
- **Introspected the live SDK rather than trusting the vendored docs** for the exact
  field names -- the docs lacked an example and web/Context7 are unreliable for this
  SDK.
- **Filed `wnt`/`c5t` instead of expanding `45o`** -- session-resumption + GoAway are
  beyond this bead's scope (scope-creep -> file a bead, don't ask).
- **Recommended deferring session-resumption** as a design *position* (not a binding
  product call) -- it reintroduces server-correlated session state the stateless
  design avoids; flagged for re-evaluation rather than killed outright.

## Doc-freshness note

`check_doc_freshness.py` flags several tier-2 docs (`voice-ai.md`, `ai-models.md`,
`hipaa-pii-policy.md`, `logging-and-cost.md`, `risk-rating.md`, `voice-and-vad.md`,
`config-deployment.md`) as stale against `backend/adapters/live_ai_gemini.py` /
`callback_handler.py`. These are **pre-existing** and not touched by this
docs-only bead -- the flagged code files have a newer filesystem mtime than the
docs' stamps but were not modified here. Reviewed and left as-is; out of scope for
this PR.
