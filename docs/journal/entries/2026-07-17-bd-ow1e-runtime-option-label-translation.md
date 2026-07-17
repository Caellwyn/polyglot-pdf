---
date: 2026-07-17
bead: polyglot-pdf-ow1e
title: "feat(i18n): runtime option-label translation via the secretary (approved plan; kit-precedence + flag)"
tags: [conventions, testing]
---

## Trigger

The yo5t tester session surfaced option-label misfires: multiple-choice labels
reach the voice model in English only (`_sanitize_options` strips the dead
`label_translations` field; all 344 option dicts across the four kits have it
empty), so the model translates them aloud on the fly -- and sometimes does not
("Male or Female" spoken in English in a Spanish session; "Lawful Permanent
refident"). The oqkj SI rule was a mitigation, not a fix. Maintainer approved
(2026-07-16, in-chat) the two-part plan: runtime translation NOW (this bead),
extraction-time kit translations LATER (bd polyglot-pdf-2h9j). Also decided:
supported spoken languages must be code-backed -- Quechua (the one entry with
no BCP-47 code) is removed. Plan file:
`C:\Users\caell\.claude\plans\i-i-d-like-to-shiny-corbato.md`.

## What shipped

- NEW `backend/services/option_translation.py`: collects the UNIQUE option
  labels from the full-form schema, applies kit `label_translations` first
  (accepting name / lowercase / short-code / full-code keys until 2h9j settles
  the canonical form), and batch-translates the remainder in ONE lite-tier JSON
  call. Process-level cache keyed `(form_number, language)` stores the in-flight
  asyncio task (concurrent sessions share one call; the shared build is shielded
  from any one session's teardown); failures -- including the 20s
  `asyncio.wait_for` bound -- return `{}` and are NOT cached, so the next
  session retries.
- `TextAIGemini.translate_labels(labels, name, code)` on the `validate()`
  pattern: JSON mime, lite fallback chain, shape-validated, fail-open signal is
  `None` (distinct from a valid empty dict). Determinism levers per the plan:
  the prompt pins the output language by NAME + BCP-47 CODE ("Respond
  UNMISTAKABLY in <Name>") and `_generate` gained an optional `temperature`
  param (0.1 here; None default keeps the validator/secretary requests
  byte-identical so their implicit-cache prefixes are untouched -- pinned by
  `test_validate_sends_no_temperature`).
- Wiring: `RUNTIME_OPTION_TRANSLATION_ENABLED` (default true) in config;
  `FormFillingService.start_session` fires a background task when the language
  is known, non-English, and code-backed and a text model is wired
  (`_spoken_language` is handshake-seeded pre-connect since bd y25o).
  Session-start only; a future re-fire hook is noted at the
  `send_initiating_message` language-set site. `end_session` cancels the
  session's awaiter (never the shared build).
- Consumption: `get_field_guidance` / `render_field_guidance` gained an
  optional `option_label_overrides`; overridden options carry the translated
  label and OMIT `spoken_label` (an English spoken_label next to a translated
  label would reintroduce the mixed-language confusion); `value` is untouched
  so tool-call matching is unaffected. All four render paths thread it:
  initiating message (form_filling_service) and confirm / skip /
  switch_to_field (callback_handler, via an injected
  `get_option_label_overrides` getter on the `get_fill_language` pattern).
- DTI SI MATCHING block reworded: labels are now normally already in the
  session language; the test-pinned "NEVER read an English label aloud
  verbatim" sentence survives, scoped to the English-fallback window.
- Quechua removed from `SPOKEN_LANGUAGES` + the three per-component translation
  maps (overlayTranslations, connectionTimeoutTranslations, DisclaimerModal);
  `test_map_covers_spoken_languages_except_quechua` became the strict
  `test_map_covers_all_spoken_languages` (map keys == supported set, no
  exceptions), mirrored by a new frontend `languages.test.ts`.
- Mid-build fix (found live): the cache key's form id came from the per-section
  schema, which on a DTI manifest-first handshake has no `form_metadata` and
  resolved to "unknown" -- two different forms in one language would have shared
  a cache entry. The key now derives from the full-form catalog the labels are
  collected from (`test_cache_key_uses_full_schema_form_number`).
- Live verification (dev-local, W-7): three Spanish sessions shared ONE
  secretary call (13/13 labels; cache hits logged for sessions 2-3); the
  injected field-1 guidance carried `"Solicitar un nuevo ITIN" (use value:
  apply_for_a_new_itin)`; an English session and a
  `RUNTIME_OPTION_TRANSLATION_ENABLED=false` Spanish session both rendered
  English labels with no translation call; the language modal shows 17
  languages.
- Fresh-eyes/outer-review triage: recorded in the PR + merge ping (this entry
  predates the loops; closeout appends nothing here -- the scorecard lives in
  the PR body).

## Lessons

- A background task that awaits a SHARED cached task must `asyncio.shield` it:
  cancelling one session's awaiter would otherwise cancel the build every other
  session is waiting on. Distinguish "I was cancelled" from "the build was
  cancelled" via `task.cancelled()`.
- The per-section schema on a manifest-first handshake has NO `form_metadata` --
  anything keying on "the form" must read the full-form catalog, not the
  handshake schema (the "unknown" cache-key bug above; found only by reading
  the live log, not by the unit suite).
- Uvicorn `--reload` under the dev-local runner did not actually recycle the
  worker on file change during a live session (WatchFiles logged the reload;
  one translate call still served pre- and post-edit sessions) -- restart the
  stack when a backend code change must be live, do not trust hot reload.

## Doc freshness

- Bumped `docs/standards/validation-delegation.md` (the `ITextAI` port grew
  `translate_labels()`), `docs/standards/si-reduction.md` (guidance option
  labels now render pre-translated), and
  `docs/standards/stateless-architecture.md` (the schema-data-only boundary
  example for the new process cache).
- Reviewed and LEFT: `docs/standards/terminology.md`,
  `docs/standards/voice-and-vad.md`, `docs/technical_guide.md` -- this branch's
  touches to their tracked files do not change what those docs describe (naming
  canon / VAD signals / ops guide), and each was already stale from other
  files before this branch. `docs/standards/ai-models.md` untouched -- the
  secretary model chain is unchanged (the new call rides the existing
  `MODEL_LABELING` adapter).
- Local memory `language-support-18-growing-to-90-never-pin` updated to 17 +
  the code-backed invariant.

## Files touched

- `backend/services/option_translation.py` -- NEW: builder + process cache.
- `backend/adapters/text_ai_gemini.py` -- `translate_labels()`; `_generate`
  optional `temperature`.
- `backend/ports/text_ai_port.py` -- `translate_labels` default (fail-loud).
- `backend/config.py` -- `RUNTIME_OPTION_TRANSLATION_ENABLED`; DTI MATCHING
  rewording.
- `backend/services/form_filling_service.py` -- background task lifecycle,
  getter injection, initiating-message render, end_session cancel.
- `backend/services/callback_handler.py` -- overrides getter threaded into the
  confirm / skip / switch_to_field renders.
- `backend/services/ai_context.py`, `backend/services/manifest_service.py` --
  optional override substitution (spoken_label omitted on overridden options).
- `backend/utils/language_codes.py` -- code-backed invariant comment (Quechua
  gone).
- `frontend/src/shared/languages.ts` (+ NEW `languages.test.ts`),
  `frontend/src/demo/overlayTranslations.ts`,
  `frontend/src/schema-forms/components/connectionTimeoutTranslations.ts`,
  `frontend/src/schema-forms/components/DisclaimerModal.tsx` -- Quechua removed.
- Tests: NEW `backend/tests/unit/test_option_translation.py` (22);
  `test_text_ai_gemini.py` (+8 translate/temperature);
  `test_transcription_language_bias.py` (strict enforcement).
