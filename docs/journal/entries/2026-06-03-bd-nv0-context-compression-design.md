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

**The headline finding (changed the design's thrust).** I modeled the per-turn cost
with code from the `tak` curve + the in-repo 3.1 pricing, across two session
profiles (40 short turns, 120 long-intake turns). Result: the **current
reconnect-every-N-turns hack is cheaper on cost than any sliding-window setting** --
a reconnect resets context to the ~271-token base, while a window only plateaus at
its ceiling. Both crush unbounded (~11x in long sessions), but no window beats the
hack on dollars (closest: 2k window @ 113% of the hack). So the epic's premise
"compression replaces the hacks AND saves cost" is only half true. The doc reframes
compression honestly as a **duration (lifts the 15-min audio cap) + UX (no audible
mid-call restart) + simplicity** win, explicitly *not* a cost win. A second
consequence: the best-practices doc's example 25k trigger would never fire for us
(our sessions peak ~9k tokens), so the recommended params are a low ~5k trigger and
~3-4k window.

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
*eviction profile* of PII in Gemini's context vs. the reconnect-flush -- a conscious,
documented choice, not a silent one.

**Workaround sideline map (hand-off to `7kp`).** Classified each manual workaround
as keep vs. sideline. The only thing compression makes redundant is the
cost-motivated forced-finalize; `7kp`'s contract is to **sideline it behind
`CONTEXT_COMPRESSION_ENABLED` (inverted), not delete it**, so the cheaper hack is one
env var from reverting if compression metrics disappoint. The section-switch restart
(intentional context reset), UX recovery prompts, `_intentional_shutdown`,
`previous_spoken_names` rehydration, token tracking, and the readiness queue all stay
active.

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
