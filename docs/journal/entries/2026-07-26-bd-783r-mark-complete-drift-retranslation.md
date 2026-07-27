---
date: 2026-07-26
bead: polyglot-pdf-783r
title: "feat(editor): re-translate drifted spoken names/option labels at Mark complete (gate + 1s/5s per-language backoff)"
tags: [schema-editor, extractor, conventions]
---

## Trigger

Human editors adjust English spoken names and option labels during review. The
editor already DROPS an item's baked translations on the first real edit
(`FieldEditor.tsx` -- `delete spoken_name_translations` / `delete
label_translations`, from bd tupu.3 / d25e), so the old translations would
otherwise ship stale (translating the OLD wording). The maintainer asked for the
DRIFT case specifically -- catch an English string that changed since it was last
translated -- fixed ONCE at the "Mark complete" boundary, not via a per-field
button editors mash as they go, and without burning tokens re-translating things
that did not drift. (The "translation never landed" case is the translation
protocol's job, not this gate's.) Decisions locked in-chat 2026-07-26.

## What shipped

- NEW server-side sweep inside `set_editor_kit_status`
  (`backend/routes/editor_kit_routes.py`), AFTER the cheap structural gates
  (PDF-exists / schema-validate / extraction_info / v2-stamp / lint) so a schema
  that will be rejected anyway never pays for the pro-tier sweep (fresh-eyes cost
  finding): `_sweep_drifted_translations` runs the SAME
  `bake_label_translations` as `/translate-options` with `only_missing=True` --
  so it fills exactly the dropped-on-edit (drifted) set plus anything never
  translated, and never re-litigates a non-drifted translation -- persists the
  swept schema (into the `_bakeoff.authoring.option_translation` provenance slot
  the extraction post-pass + `/translate-options` already write), then GATES on
  full coverage.
- The sweep runs as a STEP of the editor-authorized completion, so the route
  stays `require_editor_role` -- which also means an EDITOR (who cannot call the
  author-tier `/translate-options`) can finally fix drift.
- Per-language retry with backoff (maintainer-set 1s then 5s -> 3 attempts):
  `bake_label_translations` gained `attempt_delays` and retries a language whose
  forward `translate_items` call fails, sleeping INSIDE each `_bake_one` task and
  OUTSIDE the concurrency semaphore -- so languages stay concurrent (cap 4, kept
  per maintainer) and a recovering language does not hold a slot while it waits.
  The per-language `attempts` count rides the report. Default `attempt_delays=()`
  keeps the pre-783r single-attempt shape (the runtime session-start path, which
  has a hard 20s bound a multi-second backoff would blow, is untouched).
- HARD GATE via NEW `translation_coverage_summary(schema)` (built on
  `translation_lint.coverage_findings(..., attempted=True)`): if ANY supported
  language is still incomplete after the sweep, completion is REFUSED (409) with
  the editor-facing message "N of M language translations complete. Please try
  again later to finish (retrying only the missing ones)." A kit with nothing to
  translate is trivially complete (never trapped in draft). Idempotent: a
  re-press retries only the still-missing languages.
- No Gemini creds -> 503 refusal pointing the editor at the maintainer
  (josh@caellwynai.com) -- a config/deploy issue, not an editor one.
- Frontend (`schema-editor/src/components/RemoteCatalogue.tsx`): the complete
  flip shows an elapsed-seconds ticker ("Re-translating & validating... 42s",
  the extraction-ticker pattern) via `completingId`, and the success notice notes
  how many drifted translations were refreshed. `setRemoteStatus` now returns the
  typed `KitStatusResult` (`retranslated`, `translationModel`) instead of void.

## Decisions defended

- **Drift signal = the drop-on-edit gap, not a per-item hash/timestamp.** Because
  an edit drops translations, a drifted item is exactly an item with a present
  source and missing translation -- no new schema state needed.
- **Retry lives inside `_bake_one`, not a whole-bake re-loop.** A "gather all ->
  sleep -> gather all again" retry would serialize the waits and re-attempt
  already-succeeded languages; the in-task backoff keeps concurrency and only the
  failing language waits.
- **Gate hard-blocks (per maintainer), but self-heals.** Pressing Mark complete
  does the remaining work; `only_missing` makes each press cheap.
- **Sweep runs LAST, after the cheap structural gates** (fresh-eyes cost finding):
  validate / extraction_info / v2-stamp / lint reject a bad schema for free, so
  only a schema that will actually complete pays for the pro-tier sweep.
  Translations are additive and affect none of those gates.

## Doc freshness

No tier-2 doc tracks the changed files: the editor surface
(`backend/routes/editor_kit_routes.py`, `backend/services/option_translation.py`,
`schema-editor/src/*`) has no `docs/components/*` doc -- its record is this
journal entry. `check_doc_freshness.py` flags several STALE standards docs
(`stateless-architecture`, `validation-delegation`, `voice-and-vad`,
`terminology`, `technical_guide`, ...), but each tracks files this branch did NOT
touch (`config.py`, `form_filling_service.py`, `schemaFormState.ts`,
`live_ai_gemini.py`, ...) -- they were stale before this branch and are left as-is
(warn-only gate; Step 2 "leave it, note it in the journal").

## Follow-up

- bd polyglot-pdf-z0mz (deferred): SSE streamed per-step progress
  ("2 of 17... retrying Russian... 3 of 17...") -- the maintainer's preferred end
  UX; shipped the staged ticker now as the smaller step.

## Testing

- `backend/tests/unit/test_option_translation_bake.py`: retry-with-backoff (sleeps
  in order, recovers), retry exhausted -> failed, default single-attempt, and the
  `translation_coverage_summary` helper (empty/partial/complete).
- `backend/tests/unit/test_editor_kit_routes.py`: sweep runs then completes
  (reports the count), coverage-incomplete blocks with the "N of M" message and
  stays draft, no-creds 503 with the contact message, fully-translated is a no-op.
  The `client` fixture stubs the sweep to a no-op so the OTHER gate tests are
  unaffected; the sweep tests un-stub it and mock only the bake + client
  constructor (no live model call).
- `schema-editor` RemoteCatalogue + remoteKitStore suites: the drift notice and
  the 409 refusal surface.
- FE-in-worktree friction (memory: frontend-tests-in-worktrees-via-junction):
  vitest 4's `.vite-temp` config transform will not resolve `vite` through the
  worktree node_modules junction on Windows; ran the two FE files from the MAIN
  checkout (real node_modules) and restored via `git checkout`. 54 FE + 209
  backend (editor + translation suites) pass.
