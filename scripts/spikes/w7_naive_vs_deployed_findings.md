# W-7 session cost: deployed config vs naive baseline (bd polyglot-pdf-wiadk)

**Status: IN PROGRESS -- Phase 1 (live smokes).** Model `gemini-live-2.5-flash-native-audio`
(2.5 tier), Vertex, google-genai SDK >= 2.8. Date: 2026-08-27.

## Question

A. What does a real W-7 voice session cost all-in on the deployed config
(continuous DTI + production-DERIVED compression + secretary + pro-pass)?
B. What would the same session cost on a NAIVE implementation -- the full form
schema + the official IRS W-7 instruction booklet pasted into the system
instruction, one unbounded Gemini Live session, no compression, no secretary,
no DTI?

Framing note: internally, compression's design comparator is section-resets
(bd memory `section-resets-are-cost-mitigation`), never "vs unbounded". The
naive arm here is an EXTERNAL competitor baseline for a market/moat comparison,
not the internal design justification.

## Gate 1 (prior work) -- summary

- bd `polyglot-pdf-89mt` (2026-08-06): deployed-config W-7, happy $0.59 /
  unhappy $1.25 all-in on a 2,485-token SI. Stale: shipped SI grew to ~3,363
  tok and the spell-back cutover (PR #642) changed name-field turns. Raw
  artifacts deliberately unshipped; harness commits cherry-picked onto this
  branch (see git log).
- No true naive arm has ever been run in this repo (three-agent audit,
  2026-08-27).
- Live-API cached tokens: across all five real August W-7 runs (496 billed
  events), `cached_content_token_count` was NEVER reported (0 events nonzero).
  All replay pricing therefore bills prompt tokens at full rate and asserts
  cached == 0 on the Live path. Text-sidecar (secretary/pro-pass) calls DO
  cache and are priced with the cached-input discount via the harness's
  `price_text_usage` (bd 0cyu).
- Session limits (vendored live-api docs + journal 2026-06-15): uncompressed
  audio sessions hard-cap at 15 min; connection lifetime ~10 min (GoAway);
  no session resumption configured in this codebase. Naive-happy fits; a live
  naive-unhappy run may be API-terminated -- PRE-REGISTERED: if a naive run is
  terminated by the API (GoAway / server close in the adapter logs), that is a
  reported RESULT ("a naive session cannot complete this form in one session"),
  not a discarded run, provided the logs prove the server initiated the close.

## Measured constants (Phase 0)

- Naive SI: **27,923 tokens** (legacy full-schema SI, spell-back addendum off,
  + booklet; 109,722 chars) + **737** tool-declaration tokens (5-tool naive
  catalog) = **28,660 tokens** re-billed on every billed event (real
  `count_tokens` against `gemini-live-2.5-flash-native-audio`, 2026-08-27).
  An earlier count of 26,009 was WRONG -- the count script built the SI
  without the multi-module get_settings patch, so it rendered the DTI SI +
  booklet instead of the legacy full-schema SI + booklet (the jnjj.25 trap;
  fixed in count_naive_si_tokens.py the same day). Cross-check: the naive
  smoke's observed per-event text-in was ~28.7k tokens -- matches the
  corrected count, not the old one.
- Naive tool catalog: update_form_fields, get_form_status, confirm_field,
  skip_field, switch_to_field ONLY. The first naive smoke declared the full
  production catalog and measured the model actually CALLING ask_secretary --
  a ~29k-token context re-send burned on the fail-open answer. A naive
  competitor has no secretary, no spell-back TTS pipeline, and no section
  machinery, so those three declarations are filtered out of the naive arm
  (pinned by an allowlist test, mutation-verified).
- W-7 plan: 22 questions (realistic nonresident-filer path through the
  53-field schema). Happy = 2 turns/question; unhappy = 4 turns/question
  (wrong -> reject -> correct -> confirm).
- Rates (per 1M, `GEMINI_PRICING_BY_FAMILY`, verified 2026-05-30): 2.5 Live
  text-in $0.50, audio-in $3.00, text-out $2.00, audio-out $12.00.
- Cloud TTS (spell-back) is NOT exercised by the harness fake client (it acks
  `delivered` without fetching); deployed-arm TTS cost is computed separately
  from recorded `spellback_count`/`spellback_total_chars` at the published
  Chirp 3 HD rate (rate + retrieval date to be recorded at analysis time).

## Pre-registrations

1. (pending) Predicted full N-happy cost from the 6-question pilot, method:
   replay arithmetic extended from the pilot's own per-event trace (NOT a
   polynomial fit). To be written BEFORE the full N-happy run.
2. Naive-unhappy is reported as a band from two independent estimators
   ((a) naive replay of the measured D-unhappy trace -- biased LOW because it
   inherits the deployed arm's efficient turn structure; (b) turn-structure
   projection from the measured N-happy run). A live naive-unhappy run happens
   only if its projected cost <= $20 and the running total allows.
3. Schema-only (no booklet) naive variant is reported as billing-arithmetic
   only, behavior held fixed.

## Budget ledger (cap $100; single-run projection > $10 -> stop + re-estimate; total > $60 -> stop + ping)

| # | run | est. $ | actual $ | notes |
|---|-----|--------|----------|-------|
| 1 | D smoke, happy, --questions 5 | ~0.20 | | pipeline proof incl. spell-back on name fields |
| 2 | N smoke, happy, --questions 2 | ~0.15 | | pipeline proof, naive SI + no compression |
| 3 | N pilot, happy, --questions 6 | ~0.80 | | grounds the pre-registered N-happy prediction |

## Results

(pending)
