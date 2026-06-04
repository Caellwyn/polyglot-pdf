---
date: 2026-06-04
bead: polyglot-pdf-l3a.1
title: "Compression root cause: an unreleased stub on native-audio (DEAD END)"
tags: [performance, postmortem]
---

## Trigger

The `45o` window-size sweep found that enabling Gemini Live
`ContextWindowCompressionConfig` did NOT bound billed `prompt_token_count` -- it kept
compounding past the trigger as if compression were off. `l3a.1` was filed to find out
WHY before we'd ever turn the feature on. The maintainer asked to dig in: "I want to
know why this is not working."

## What shipped

A diagnostic investigation (no production behavior change beyond one no-op hook) that
**root-caused the failure by elimination** and recorded it as a dead end so we never
walk this path again.

Findings (all verified against the live endpoint):

- **`contextWindowCompression` is a silent no-op on every native-audio Live model
  reachable on our key.** The server ACCEPTS the config (no rejection) but never evicts.
- **Ruled out, each with a throwaway probe:**
  - bad syntax -- serializes to the correct `triggerTokens`/`slidingWindow`/`targetTokens`.
  - API rejection -- accepted across triggers 200-4096 (`diag_compression_connect_boundary.py`).
  - wrong API version -- `v1alpha` == `v1beta`, both compound ~7x, neither evicts
    (`diag_compression_apiversion.py`). This killed the most promising lead (a Context7
    crumb said preview features need `v1alpha`).
  - model-specificity -- `gemini-2.5-flash-native-audio` behaves identically to 3.1.
- **Untestable here:** no cascade Live model is reachable on our key (all `1008`;
  `models.list()` returns only native-audio). The genai docs' compression example uses
  a cascade model -- so the most consistent read is that the SDK type exists **ahead of
  the server implementation**: an unreleased/unsupported stub for native-audio.

Conclusion: **not a viable cost path for our model family.** The `l3a` epic's premise
(compression -> linear cost) does not hold on our models.

**Decisions (maintainer-directed):**
- Closed `l3a.1` (root cause found); **no cascade follow-up filed** -- even if it worked
  on cascade, we run native-audio, so it's not worth tracking.
- Closed `7kp` ("retire hacks made redundant by compression") as **obsolete** -- its
  precondition (compression live+validated) is now unreachable.
- Left `c5t` (GoAway) and `wnt` (session resumption) OPEN -- they were only *deferred
  out of* compression work; they're independent Live-API session-management items.
- **Left the compression code as-is (default off).** It's gated behind
  `CONTEXT_COMPRESSION_ENABLED` (default `false`) and inert; the doc banner + bd memory
  warn against enabling it. Kept plumbed for a zero-code enable IF Google ships
  native-audio support (re-verify against the endpoint first).

**Generalizable lesson recorded:** capability/availability questions for google-genai
Live get a *live-endpoint probe*, never a doc read -- docs (Google's, vendored, Context7)
and SDK types describe the INTENDED API and run ahead of the server; they go stale
silently. Stored as bd memories `compression-noop-on-native-audio-live` and
`gemini-capability-questions-need-endpoint-probe`, and in `genai_docs/README.md`.

## Lessons

- **The SDK serializing a config proves nothing about whether the server implements it.**
  A type can exist for an unreleased feature; the config flows to the wire and is
  silently dropped. Only an endpoint probe tells you it's live.
- **Google/genai docs go stale confidently.** The best-practices doc actively *claims*
  compression works, with an example for a model class it doesn't apply to. Worse than
  silence.
- **Eliminate by cheap probes, not reasoning.** Each hypothesis (api_version, model,
  trigger floor) was killed by a tiny targeted run, not by argument -- which is what kept
  a wrong lead (v1alpha) from becoming a production change.

## Doc freshness

- **Bumped:** `docs/components/context-compression.md` (STATUS banner at top + validation
  section rewritten to the dead-end verdict) and `docs/genai_docs/README.md` (DEAD-END
  hard-won fact + endpoint-probe doctrine).
- **Reviewed and left as-is:** the freshness checker flagged `voice-ai.md`,
  `ai-models.md`, `hipaa-pii-policy.md`, `logging-and-cost.md`, `risk-rating.md`,
  `voice-and-vad.md`, `config-deployment.md`, `confirmation-and-audit.md`,
  `technical_guide.md` -- all by *mtime* (they track `config.py` / `live_ai_gemini.py`,
  touched only by the no-op diagnostic hook). No substantive change to those docs; left
  unbumped per the closeout rule, already stale before this branch (2026-06-01/02).

## Files touched

- `backend/adapters/live_ai_gemini.py` -- added `_on_raw_usage` diagnostic hook (default None = prod no-op).
- `docs/components/context-compression.md` -- dead-end STATUS banner + validation rewrite.
- `docs/genai_docs/README.md` -- dead-end fact + endpoint-probe doctrine.
- `scripts/spikes/diag_compression_usage.py` -- raw usage_metadata dump (off/on).
- `scripts/spikes/diag_compression_connect_boundary.py` -- accept/reject boundary probe.
- `scripts/spikes/diag_compression_apiversion.py` -- v1beta vs v1alpha eviction probe.
- `scripts/spikes/diag_compression_cascade.py` -- cascade-model eviction probe (unreachable here).
- `scripts/spikes/l3a1_compression_rootcause_findings.md` -- the findings write-up.
