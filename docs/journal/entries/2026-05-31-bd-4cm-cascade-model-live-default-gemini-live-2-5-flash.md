---
date: 2026-05-31
bead: polyglot-pdf-4cm
title: "Retire dead MODEL_LIVE; add USE_PREMIUM_MODEL native-audio A/B toggle"
tags: [refactor, conventions]
---

## Trigger

`polyglot-pdf-4cm` (child of the AI-models epic `polyglot-pdf-9nl`): the live
Gemini contract test connected with a real key and the server closed with
**1008** -- `models/gemini-live-2.5-flash-preview is not found for API version
v1beta, or is not supported for bidiGenerateContent`. That string was the
`MODEL_LIVE` default (`backend/config.py:18`), the cascade-path model used when
`USE_NATIVE_AUDIO=False`. Dormant in prod (default is `USE_NATIVE_AUDIO=True`),
but the fallback path was broken until the name was fixed.

The bead asked to "find the valid cascade model name." Mid-investigation the
maintainer corrected the framing: **we do not use cascade/half-cascade at all --
the voice path is native audio-to-audio only.** So the fix is to retire the dead
selection machinery, not to hunt a replacement cascade name.

## What shipped

**Retired the cascade selection, replaced with a native-audio A/B toggle.**
- `config.py`: removed `MODEL_LIVE` and `USE_NATIVE_AUDIO`. Added
  `USE_PREMIUM_MODEL` (bool, default `false`) + two module consts
  (`MODEL_NATIVE_PREMIUM = gemini-3.1-flash-live-preview`,
  `MODEL_NATIVE_STANDARD = gemini-2.5-flash-native-audio-preview-12-2025`) and a
  `model_validator` that resolves `MODEL_NATIVE` from the flag unless an explicit
  `MODEL_NATIVE` env is pinned (non-empty wins).
- `dependencies.py`: always uses `MODEL_NATIVE` (no more ternary).
- `main.py`: `/health` reports `native` + `premium` flag; dropped the dead `live` key.
- `live_ai_gemini.py`: adapter fallback default -> standard native model.
- contract test: defaults to the native model we actually run.

**Verified live against the real endpoint** (key present in env): connecting with
`gemini-2.5-flash-native-audio-preview-12-2025` + `response_modalities:["AUDIO"]`
established a session and returned a real audio response (51,200 bytes of
`audio/pcm;rate=24000`). The 1008 is gone -- model name is valid.

**Vendored google-genai SDK docs.** The maintainer added four reference files to
`docs/genai_docs/` (codegen instructions, `genai.live` module ref, end-to-end Live
examples, Live API best-practices) because web search + Context7 are unreliable
for this SDK (Context7's google.genai Python entry is broken). Wrote a folder
`README.md` (contents table + hard-won facts), and wired discovery via a new
"External references" section in `docs/INDEX.md` and two rows in the CLAUDE.md
trigger table (the Gemini-adapter row + a catch-all for any `google-genai` call).

**Deferred / filed as beads (not in this PR):**
- New epic `polyglot-pdf-l3a` (P1) + 4 phase-chained children
  (`tak` spike -> `nv0` design -> `45o` implement -> `7kp` retire): adopt the
  Live API's `ContextWindowCompressionConfig` + context-size limits. This was a
  game-changer surfaced while reading `live-api-best-practices.md`: the API bills
  by **compounding** context (every turn re-bills all accumulated tokens; native
  audio accrues ~25 tokens/sec), and server-side compression can both cap cost and
  replace the fragile manual disconnect/restart/carry-over logic we built to bound
  context. Cross-linked to `daa` (1011 mitigation) and `umv` (restart metadata).
- The contract test still asserts on **TEXT** output, which native-audio models
  1007-reject -- it can't pass against any valid native model as written. Noted
  here; left as-is this PR pending the maintainer's call on rewriting it to AUDIO.

**Fresh-eyes review:** _(filled at Step 8 after triage)_

## Lessons

- **Gemini model naming is inconsistent across Google's own sources** -- the 2.5
  native model appears as both `gemini-2.5-flash-native-audio-preview-12-2025` and
  `gemini-live-2.5-flash-preview`, and a separate *cascaded* `gemini-live-2.5-flash`
  exists too. Do not infer "native vs cascade" from a name; verify against the live
  endpoint. A 1008 means the exact string is unavailable, not that an architecture
  is dead.
- **Native-audio Live models emit AUDIO only.** `response_modalities:["TEXT"]` gets
  a 1007; text comes via `input_transcription`/`output_transcription` on
  `server_content`. Any TEXT-asserting smoke test is broken-by-design against them.
- For this SDK, trust `docs/genai_docs/` over training data / web / Context7.

## Doc freshness

- `docs/technical_guide.md`: env-var table updated -- replaced the `MODEL_NATIVE`
  (stale alias) + `MODEL_LIVE` rows with `USE_PREMIUM_MODEL` + a derived
  `MODEL_NATIVE` row; removed `USE_NATIVE_AUDIO` from the non-env tunables list.
  (No `**Tracks:**` line, so the freshness checker skips it; bumped by hand.)
- `docs/INDEX.md`: added "External references" section pointing at `genai_docs/README.md`.
- `CLAUDE.md`: added two trigger-table rows for the genai SDK docs.
- `docs/genai_docs/README.md`: new (folder index + hard-won facts).
- `check_doc_freshness.py`: clean for all tracked tier-1/tier-2 docs (the
  sprint-plan-row warning is pre-existing and unrelated).

## Files touched

- `backend/config.py` -- USE_PREMIUM_MODEL + native-model consts + _resolve_model validator; drop MODEL_LIVE/USE_NATIVE_AUDIO
- `backend/dependencies.py` -- always use MODEL_NATIVE
- `backend/main.py` -- /health: native + premium flag, drop live key
- `backend/adapters/live_ai_gemini.py` -- adapter fallback default -> standard native model
- `backend/tests/contract/test_live_ai_gemini_integration.py` -- default to native model
- `docs/technical_guide.md` -- env-var table
- `docs/INDEX.md` -- External references section
- `CLAUDE.md` -- genai_docs trigger rows
- `docs/genai_docs/README.md` (new) + the 4 vendored SDK reference files
