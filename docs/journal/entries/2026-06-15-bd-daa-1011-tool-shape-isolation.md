---
date: 2026-06-15
bead: polyglot-pdf-daa
tags: [postmortem, testing, conventions]
title: "Gemini 2.5 native-audio 1011: wire-verified root cause -- incomplete tool declaration x tool solicitation"
---

## Trigger

bd `polyglot-pdf-daa` (open since 2026-05-30) chased an ~80%-rate `1011 Internal
error` on `gemini-2.5-flash-native-audio` and oscillated for weeks between
"transient Google-side outage" and "real bug," never landing. The 2026-06-12
compression matrix (bd `h04c`) found a correlation -- 2.5 dies turn-1 with no /
minimal tools, stable with the full production set -- and a published forum report
was drafted claiming "no tools -> crash; pass tools to fix." The maintainer asked
the right question before we recommended "always pass an empty tools list": is that
fix actually necessary AND effective? Designing the test surfaced a confound that
invalidated the simple reading, so this bead is the dedicated isolation experiment.

## What shipped

- **A confound, found and defeated.** Two things made the prior data
  un-interpretable: (1) our adapter NEVER sends a true no-tools config -- when
  given none it injects a NAME-ONLY fallback stub (`live_ai_gemini.py`
  `_build_live_config`), so "no tools crashed" actually meant "an incomplete
  declaration crashed"; (2) the `google-genai` SDK silently collapses a typed
  `LiveConnectConfig(tools=[])` to no-tools before the wire
  (`live.py:1174-1175`: `model_copy(update={'tools': None})` + falsy `[]`), so the
  empty-list question is untestable through the config object and `model_dump()`
  is not wire evidence.
- **A raw-SDK probe that captures and injects at the wire**
  (`scripts/spikes/diag_native_audio_1011_tools.py`): wraps the SDK `ws_connect`
  (class-level async-CM -- an instance-level `__aenter__` override is silently
  ignored by `async with`, a real bug caught during the build) to record the exact
  `setup` packet AND mutate `setup["tools"]` for shapes the typed config cannot
  express. Every cell is asserted against the `tools` value actually on the wire.
- **The verdict (wire-verified, ~110 live sessions):** the turn-1 `1011` needs
  BOTH (a) a structurally INCOMPLETE `function_declaration` on the wire (a `name`
  with no `parameters` schema) AND (b) tool-soliciting prompts. It is a RATE, not
  deterministic: one name-only declaration crashed 24/30 (~80%) under the
  form-filling persona; the SAME declaration under a "you're a pirate, just chat"
  persona crashed 0/5. All of these SURVIVE at 0%: omit tools, true wire
  `tools:[]`, `tools:[{functionDeclarations:[]}]`, one fully-typed declaration, the
  full production set. So the original "no tools -> crash" report was WRONG on both
  cause and fix.
- **Fix (corrected):** declare tools COMPLETELY (typed `parameters` on every
  declaration), or send none -- never a name-only/placeholder declaration.
  "Always pass `[]`" is safe but unnecessary and was the wrong mental model.
- **Docs corrected to the verdict:** the public forum report
  (`scripts/spikes/gemini-2p5-1011-tool-declarations-report.md`) rewritten;
  the `voice-ai.md` scar-tissue note rewritten; the dolt bd memory
  `gemini-2p5-1011-needs-tool-declarations` corrected; `daa` carries the
  root-cause comment + is tied `related` to `h04c`.
- **Review:** docs + standalone spike-script only (no runtime code), so
  review-skipped. The fresh-eyes pass that mattered here was the PLAN review
  (pre-experiment), which caught the two CRITICAL confounds (SDK tools-collapse;
  `model_dump` is not wire evidence) that reshaped the whole experiment -- without
  it we would have published a clean-looking but wrong result.

## Lessons

- **Capture the wire, not the config object.** A config-object experiment could
  not have answered the empty-list question (the SDK erases it) and would have
  recorded misleading evidence. Wrapping `ws.send` to capture/inject the setup
  packet was non-negotiable -- generalizes to any "what did the SDK actually send"
  question (added emphasis in the report's reproduction notes).
- **A flaky bug needs a rate, not a sample.** An early 10/10 cluster on the
  name-only cell looked deterministic; widening to N=30 revealed ~80%. Publishing
  "always crashes" would have been wrong. Run N>=20 before calling a live-endpoint
  behavior deterministic.
- **Your own fallback can manufacture the bug you're chasing.** The adapter's
  name-only stub WAS the crashing shape; "we sent no tools" was a lie the wire
  exposed. Audit injected/fallback config before blaming the upstream.
- **Background `run_in_background` runs did not survive `SessionStart:resume`
  here** -- two monolithic runs were orphaned (0-byte output, dead). The robust
  pattern was chunked foreground-ish batches with raw redirect to a controlled log
  file (no pipe) + committing the harness early so a resume can't lose it.

## Doc freshness

- Bumped with content: `docs/components/voice-ai.md` (scar-tissue note corrected;
  Last-updated -> 2026-06-15). New file: the rewritten report +
  the probe + per-cell evidence JSON under `scripts/spikes/`.
- Reviewed and left as-is: the freshness checker flagged
  `context-compression.md`, `tool-call-flow.md`, `confirmation-and-audit.md` as
  STALE, but all three track BACKEND files this branch never touched (pre-existing
  dev-side staleness) -- out of scope here.
- Beads housekeeping: two pre-existing stale in_progress epics (`hrn`, `jf6w`,
  neither this branch's) touched to reset the >1d flag (note: `bd comment` does not
  bump `updated_at`, a tooling cosmetic; the documented touch satisfies the triage).

## Files touched

- `scripts/spikes/diag_native_audio_1011_tools.py` (new) -- raw-SDK wire
  capture/inject isolation probe.
- `scripts/spikes/gemini-2p5-1011-tool-declarations-report.md` -- rewritten to the
  two-factor verdict (was the confounded "no tools -> crash" draft).
- `scripts/spikes/data/diag_1011_tools_{batch1,batch2,batch3,rate,combined}.json`
  (new) -- per-cell raw evidence with captured wire `tools`.
- `docs/components/voice-ai.md` -- scar-tissue note corrected + Last-updated bump.
- (bd memory `gemini-2p5-1011-needs-tool-declarations` + `daa` comment: corrected
  via dolt, not git.)
