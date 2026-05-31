---
date: 2026-05-31
bead: polyglot-pdf-w0d
title: "Voice/WS/AI spine docs (w0d + rvz + 4rz + 5df) + #31 follow-ups"
tags: [conventions, review]
---

# polyglot-pdf-w0d (+rvz, +4rz, +5df): voice/WS/AI spine standards+component docs

One PR bundling the four docs that cover the voice form-filler's spine — they all
share `live_ai_gemini.py` / `websocket_routes.py` / `connection.ts` and cross-link
each other. Also folds in three fresh-eyes follow-up fixes to the already-merged
#31 logging batch.

## Trigger

Next batch of the docs-reorg epic (`polyglot-pdf-gfb`) after the logging/PII batch
(#31). The voice/WS/AI surface is the highest-value cluster and `5df` (ai-models)
unblocks `2hy`, the last child of the near-done model epic `9nl`.

## What shipped

Four new tier-2 docs, each verified line-by-line against the **dev-branch** code,
plus four `docs/INDEX.md` rows flipped from `_(planned)_` to live links:

- **components/websocket-routing.md** (w0d) — `/ws/fill` handshake (legacy +
  `handshake_jit`), the full control-message table, the **frontend-driven**
  section switch (`manual_section_switch` → `switch_to_section`, `drop_audio`
  guard; there is no backend `complete_section` tool), the 5s idle watchdog
  (`idle_timeout` → close 1000), and warm-vs-cold reconnect including the Nov-10
  `paused`-flag-reset bug fix. Flags `RECONNECTION_FLOW_SUMMARY.md` as an unshipped
  proposal, not current behavior.
- **components/voice-ai.md** (rvz) — `LiveAIGemini` lifecycle, audio-queue
  drop-not-block, manual activity signals, barge-in (logs+skip on the backend;
  flush is frontend-side), tool routing, `response_modalities=["AUDIO"]`, the
  `_intentional_shutdown` reset scar tissue, one-adapter-per-connection, cost
  tracking.
- **standards/ai-models.md** (5df) — `USE_PREMIUM_MODEL` tiers, `MODEL_NATIVE`
  resolution + env override, `dependencies.py` injection, the A/B flow, family-keyed
  cost link. Unblocks `polyglot-pdf-2hy`.
- **standards/voice-and-vad.md** (4rz) — `DISABLE_GEMINI_VAD` + manual
  `activity_start/end` ordering, the `vad_config.json` tuning params + `/api/vad-config`
  WS, fill- vs spoken-language, PTT (default on), hallucination mitigations.

Plus the **#31 follow-ups** (the merged logging docs): `self._model` →
`self._model_name` in logging-and-cost; clarified that confirmation logging uses
`structlog` (stdout), **not** the project `StructuredLogger`/BigQuery path; the
`ai-models.md` link now resolves (written this batch). Stamps on those two bumped
to 2026-05-31.

Fresh-eyes triage (round 1): _(filled at closeout)_.

## Lessons

- **Write from the code, not the bead — again.** While self-reviewing voice-ai I
  had claimed the backend sends a `b"__INTERRUPT__"` sentinel through `on_audio` on
  barge-in. It does not — it logs `GEMINI_INTERRUPTED`, resets audio tracking, and
  `continue`s; the flush is entirely frontend-side. Caught by re-grepping before
  push. Same failure mode the recall memory warns about; the fix is mechanical
  verification of every concrete claim.
- **A doc that documents a planned doc creates a dead link.** logging-and-cost
  (shipped in #31) linked `ai-models.md` before it existed — only resolved once
  this batch wrote it. When a doc forward-references a sibling, either write them
  together or land the link in the batch that creates the target.

## Doc freshness

All 7 component/standards docs touched: freshness OK; `tests/test_doc_freshness.py`
38 passed; conventions clean. `technical_guide.md` shows STALE but this branch
didn't touch it (pre-existing; owned by `polyglot-pdf-gfb.2`) — left as-is.

## Files touched

- `docs/components/websocket-routing.md` — new (w0d)
- `docs/components/voice-ai.md` — new (rvz)
- `docs/standards/ai-models.md` — new (5df)
- `docs/standards/voice-and-vad.md` — new (4rz)
- `docs/standards/logging-and-cost.md` — #31 follow-up (self._model_name) + stamp
- `docs/standards/confirmation-and-audit.md` — #31 follow-up (structlog clarify) + stamp
- `docs/INDEX.md` — four rows → live links
- `docs/journal/entries/2026-05-31-bd-w0d-...md` — this entry
