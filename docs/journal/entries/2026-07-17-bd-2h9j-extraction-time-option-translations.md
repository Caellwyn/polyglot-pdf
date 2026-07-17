---
date: 2026-07-17
bead: polyglot-pdf-2h9j
title: "feat(extractor): bake option label_translations at authoring time + backfill the 4 kits"
tags: [extractor, conventions, schema-editor]
---

## Trigger

The extraction-time half of the maintainer-approved two-part option-label i18n
plan (2026-07-16, in-chat; the runtime half shipped as bd ow1e). Option labels
reached non-English voice sessions in English; ow1e translates them per process
at session start via the secretary; this bead bakes STOCK translations into the
kit JSON so they become deterministic, reviewable artifacts and the runtime
call short-circuits via the already-shipped kit-precedence rule. Maintainer
direction at planning (2026-07-16): pro-tier translations (extraction already
runs gemini-2.5-pro), an extraction-time checkbox that can be turned OFF when
just testing extraction strategies, and full DECOUPLING so translations can run
standalone on an already-extracted schema -- no re-doing the i-90. Plan file:
`C:\Users\caell\.claude\plans\i-d-like-you-pick-iridescent-hanrahan.md`.

## What shipped

- NEW `bake_label_translations(schema, text_ai, languages, only_missing,
  concurrency)` in `backend/services/option_translation.py` -- the authoring
  counterpart of the runtime builder, sharing `_collect_labels` so both sides
  of the precedence contract live in one module. Per language: dedupe unique
  labels, ONE batched `translate_labels` call over what the kit lacks, fan-out
  to every option carrying that label. Idempotent (any accepted key form counts
  as covered; re-runs are no-ops; future language additions are cheap);
  per-language failures skip-and-report (one flaky language never costs the
  other 15); `only_missing=False` is the stale-after-rename remedy.
- CANONICAL KEY SETTLED (the decision ow1e's review deferred here): the
  lowercase spoken-language NAME ("spanish"). The docs' bare ISO-639-1
  examples ("zh", "tl") never resolved in the runtime reader -- it derives
  short codes from BCP-47 stems ("cmn", "fil") -- so names are the only form
  that always resolves, and they match the repo's name-keyed i18n maps. The
  tolerant reader stays for hand-authored kits. `docs/schema_format.md`
  section 11 + the FieldOption docstring corrected;
  `docs/standards/terminology.md` gained the canon row.
- Three decoupled consumers of the one bake:
  1. `extract_form.py` post-pass (step 3f, after repair / before validate) --
     default ON, credential-gated (no Gemini creds -> skipped; keeps
     claude-CLI-only dev a no-op), FAIL-OPEN (extraction never fails because
     translation failed), `--no-translate-options` / `--translation-model`;
     report rides `_bakeoff.authoring.option_translation`. The hosted extract
     route threads a `translate_options` Form flag (default true) into the
     subprocess, surfaced as a default-checked "translate options" checkbox in
     the schema-editor's Run-extraction controls.
  2. NEW `POST /api/editor/kits/{id}/translate-options` (repair-route shape:
     author-gated, draft-only 409-on-complete, in-process bake, put_schema,
     re-lint) + a "Translate options" kit action in RemoteCatalogue that
     reloads the open kit on success (gated on saved state, like Mark
     complete).
  3. NEW `scripts/authoring/translate_option_labels.py` CLI (mirrors
     backfill_option_positions.py): `--kit/--schema`, `--check` (report-only,
     zero API calls), `--languages`, `--model`, `--force`; exit codes 0/1/2;
     counts-only ASCII output.
- New `OPTION_TRANSLATION_MODEL` setting (default `gemini-2.5-pro` -- the
  EXTRACTOR_MODEL one-off-per-form rationale). All consumers construct
  `TextAIGemini` with `fallback_models=()` (a chosen tier fails loud, never
  silently degrades to the lite chain) and `thinking_budget=512` for pro (the
  W6 pattern). The RUNTIME secretary path is untouched (still lite).
- BACKFILL: all 4 shipped kits baked via the CLI on Vertex pro -- i-90 (294
  options / 116 unique labels), f1040 (24/20), w7 + w7-2 (13/13 each), 16
  non-English languages, all succeeded, ~64 batched calls (~$1 one-time).
  Re-run `--check` exits 0 on all 4 (idempotency proof); diffs are pure
  label_translations additions (values/labels untouched, ASCII-escaped JSON).
- Live verification (dev-local, W-7 Spanish): `option_translation_ready`
  `override_count=13` with ZERO `text_ai_translate` events -- the ow1e
  kit-precedence no-op is real; the injected field-1 guidance carried
  `"Solicitar un ITIN nuevo" (use value: apply_for_a_new_itin)`.
- Beads filed: polyglot-pdf-d25e (editor label rename keeps now-wrong
  translations -- FieldEditor spreads the option on rename; remedy today is
  `--force`), polyglot-pdf-ierm (on-screen display of translated labels --
  maintainer chose voice-only scope now), and a first-session handshake gap
  found during live verification (see Lessons).

## Lessons

- A FIRST session's WS handshake carries `spoken_language: null`: the frontend
  persists `state.selectedLanguage` only at DISCLAIMER-AGREE
  (`VoiceOverlay.tsx` ~1197), after the first connect. So the disclaimer-phase
  connection gets an en-US ASR bias and skips the ow1e translation task; the
  post-agree flow reconnects with the saved state (observed live: second
  connect got es-US + option_translation_applied), so fields still render
  translated. Filed as its own bug bead (seed the language at SELECTION time).
- The Bash tool's script-text layer can decode `\uXXXX` escape sequences back
  into literal characters before execution -- an ASCII-only fix written as
  `src.replace(chr(0xED), "í-as-text")` silently no-oped until the
  backslash was split out of the literal (`"\\" + "u00ed"`). When enforcing
  scar #6 mechanically, verify the file bytes afterward, not the tool echo.
- `json.dump` without a trailing newline created a gratuitous EOF diff on all
  4 committed kits (they end with a newline) -- the new CLI now writes one.
  When a patch tool must produce minimal diffs, diff the whole file early.

## Doc freshness

- Bumped: `docs/standards/ai-models.md` (OPTION_TRANSLATION_MODEL entry),
  `docs/components/config-deployment.md` (extraction knobs +
  translate-options route), `docs/technical_guide.md` (editor route table),
  `docs/standards/terminology.md` (canonical label_translations key row),
  `docs/schema_format.md` (section 11 rewrite -- part of the change itself).
- Reviewed and LEFT (flagged stale by mtime but tracking files this branch did
  not change, or where this branch's config.py addition does not alter what
  the doc describes): auth.md, context-compression.md, jit-schema.md,
  tool-call-flow.md, voice-ai.md, confirmation-and-audit.md,
  hipaa-pii-policy.md, logging-and-cost.md, risk-rating.md,
  section-reset-deprecation.md, voice-and-vad.md -- each was already stale
  from other branches' files before this one.

## Files touched

- `backend/services/option_translation.py` -- bake_label_translations +
  settled-key docstrings.
- `backend/config.py` -- OPTION_TRANSLATION_MODEL.
- `backend/routes/editor_kit_routes.py` -- extract-route translate_options
  flag; NEW translate-options route + TranslateOptionsResponse.
- `backend/models/form_models.py` -- FieldOption.label_translations docstring.
- `scripts/authoring/extract_form.py` -- step-3f post-pass + flags.
- `scripts/authoring/translate_option_labels.py` -- NEW backfill CLI.
- `schema-editor/src/utils/remoteKitStore.ts` -- translateOptions opt +
  translateRemoteKitOptions.
- `schema-editor/src/components/RemoteCatalogue.tsx` -- checkbox + standalone
  action.
- `form-kits/{i-90,f1040,w7,w7-2}/schema.json` -- baked translations.
- `docs/schema_format.md` + the four bumped docs above.
- Tests: NEW `backend/tests/unit/test_option_translation_bake.py` (18 run
  items), NEW `tests/test_translate_option_labels_cli.py` (5),
  `backend/tests/unit/test_editor_kit_routes.py` (+6),
  `schema-editor/src/components/RemoteCatalogue.test.tsx` (+6 incl. threading
  pin update).
