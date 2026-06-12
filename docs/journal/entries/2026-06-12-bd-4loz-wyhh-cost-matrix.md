---
date: 2026-06-12
bead: polyglot-pdf-4loz
title: "Per-question cost instrument (4loz) + three-arm token matrix (wyhh): section resets beat sliding window; duration GoAway survives compression"
sprint: 4
tags: [testing, performance]
---

## Trigger

Sprint-4 epic `polyglot-pdf-hcsl`, beads 2 and 3 (maintainer go: "go ahead
4loz and wyhh", 2026-06-12), under the deploy-fidelity directive recorded that
morning (probes mirror the deploy config; measurements use the real system
instructions and realistic content). This PR bundles both whole beads: the
instrument and the measurement run it exists for.

## What shipped

- **The instrument** (`scripts/spikes/measure_form_session_costs.py`, bd
  `4loz`): drives the REAL form-filling stack -- FormFillingService +
  CallbackHandler + RequestCoordinator + LiveAIGemini, the production
  `build_form_context_message` system instruction over the real demo schema,
  production TOOL_DECLARATIONS -- against live Gemini with cached gTTS audio
  (42 clips committed under `fixtures/audio_cache/`), simulating the frontend
  client (state ownership, navigation-hint format, the synchronous
  confirm_field round-trip). Emits the maintainer's exact 11-column
  per-question CSV plus a meta sidecar (per-turn latency, per-question tool
  calls, prompt curve, eviction drops, captured errors). Three arms:
  unbounded / section-reset (production `switch_to_section` restarts) /
  sliding-window.
- **Pricing verification** (bd `4loz`): both `GEMINI_PRICING_BY_FAMILY` rows
  match Google's published page exactly (2.5 native-audio, and 3.1 flash-live
  at the page's `#gemini-3.1-flash-live-preview` anchor the maintainer
  supplied after an earlier fetch missed it); date-stamped in
  `backend/config.py`.
- **The matrix** (bd `wyhh`): 12/12 cells (2 models x 3 arms x 2 paths, 20
  questions each, ~USD 10.6 live spend), per-question CSVs + sidecars under
  `scripts/spikes/data/`, analyzed in
  `scripts/spikes/form_session_costs_findings.md`. Headlines:
  1. **Section resets beat the sliding window decisively under the current SI
     architecture** (2.5 happy: $0.188 vs $0.330/$0.338) -- the dominant cost
     is the per-turn re-billed, UNEVICTABLE system instruction (whole-form SI
     ~8.2k tokens; 97-98% of 2.5 spend was text-in), and compression only
     evicts conversation above that floor. Confirms the maintainer's original
     cost finding with fresh controlled data.
  2. **Compression alone cannot deliver "whole form in one session": the
     session-duration GoAway still arrives.** Both 3.1 single-session unhappy
     runs were terminated at ~13-15 min (`1008 ... failed to close the
     connection after receiving a GoAway signal once the session durat...`)
     WITH compression evicting (16 drops). The whole-form flow requires the
     GoAway -> reconnect -> resumption path (c5t shipped; l3a.2 policy open;
     wnt resumption decided). `docs/components/context-compression.md`'s
     "lifts the 15-min cap" claims corrected to this nuance.
  3. **No latency penalty at eviction** (medians flat before/after first
     eviction; 2.5 got faster after -- smaller prompts).
  4. **3.1 costs 3-5x 2.5 for the same work** (thinking tokens bill as
     output at the higher text-out rate).
- **Data caveats recorded in the findings doc:** the two GoAway-truncated 3.1
  cells under-count questions ~13-20; one 2.5 section-reset cell lost part of
  a section to a `1006` transient (the driver does not mid-section reconnect
  the way the production client does); section-reset "eviction" counts are
  restart curve-resets, not compression.
- **Fresh-eyes:** entry written pre-loop; rounds/triage in the merge ping.
  Codex credits still exhausted; the fresh-eyes record stands per the gate.

## Lessons

- **An unevictable floor caps what any windowing strategy can save.** Sizing
  trigger/window without subtracting the fixed base (SI + tools) makes
  compression look broken when it is merely starved -- the elbow analysis
  (bd `6x1y`) must work in evictable-mass terms, not raw token counts.
- **"Lifts the cap" claims need WHICH cap named.** Compression lifts the
  context-size cap; the session-duration GoAway is a separate wall-clock
  ceiling answered by reconnect + resumption. A probe that ignores GoAway is a
  faithful model of any client that ignores GoAway.
- **Headless deploy-fidelity drivers are practical.** Simulating only the
  frontend's contract (state, hints, confirm acks) over a fake WebSocket let
  the entire production backend path run unmodified -- and the instrument's
  gaps (no mid-section auto-reconnect) surfaced real architecture
  requirements rather than instrument bugs.

## Doc freshness

- Bumped with content: `docs/components/context-compression.md` (comparison
  table + success criterion 3: duration-GoAway nuance, SI-floor leverage cap).
- `backend/config.py` pricing comment re-stamped (2026-06-12, both rows
  verified).
- The pre-existing dev-side staleness flags (sprint-3 backend files vs older
  doc stamps) remain out of this branch's scope, as recorded in the h04c
  entry.

## Files touched

- `scripts/spikes/measure_form_session_costs.py` (new) -- the instrument
- `scripts/spikes/fixtures/audio_cache/*.pcm` (new, 42) -- cached utterances
- `scripts/spikes/data/costs_*.csv` + `costs_*.meta.json` (new, 12 cells)
- `scripts/spikes/form_session_costs_findings.md` (new) -- matrix analysis
- `docs/components/context-compression.md` -- duration/leverage corrections
- `backend/config.py` -- pricing verification stamp
- `docs/journal/entries/2026-06-12-bd-4loz-wyhh-cost-matrix.md` (this)
