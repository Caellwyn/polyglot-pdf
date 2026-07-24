---
date: 2026-07-25
bead: polyglot-pdf-alry
title: "V3b: bake + runtime forward paths onto the context-carrying translate_items call"
sprint: 14
tags: [refactor, testing]
---

## Trigger

The split half of bd 9ikj (the bead as filed spanned two PRs; split logged
there): Part A.1 + A.5 of the sprint-14 plan -- the forward translation
finally carries CONTEXT (the known worst case for short-string translation
was the bare deduped string list), and the runtime session-start fallback
rides the SAME call instead of silently diverging.

## What shipped

- **Bake forward path** (`bake_label_translations`): ONE `translate_items`
  call per language whose payload the schema already pays for -- field
  names and section titles as single items; option labels grouped into
  their SETS with the field's spoken name as `parent_question` (sets
  dedupe by their ordered label tuple, so the identical Yes/No twins
  translate once); `form_metadata.title` + `form_number` as the form
  reference; the glossary now loads UNCONDITIONALLY and injects into the
  forward prompt (previously verify-only). A whole set rides the payload
  even when partially kit-covered -- context needs the full set --
  and membership filtering keeps kit precedence absolute (pinned).
- **Ambiguous self-flags**: the translator's `ambiguous` ids resolve to
  their source strings and surface as `translation-ambiguous-source`
  WARNING findings in `report["flags"]` -- ALSO when the verify gate is
  off (they come from the forward call, not the loop). The flag-assembly
  condition widened accordingly.
- **Runtime fallback** (`build_translation_overrides`): the same
  context-carrying call (full schema in hand, payload free). Honest
  residual documented in code: runtime translations remain UNVERIFIED (no
  judge at session start -- latency); post-V5 this path only fires for
  new/edited kits pre-bake.
- **Param rename**: `verify_glossary` -> `glossary` on
  `bake_label_translations` (it now feeds the forward prompt too).
- **Test migration**: bake pins (22+1 new ambiguous pin), runtime pins
  (28), editor-route fakes -- all onto translate_items payload-shape
  assertions (`_payload_kinds` helpers). The kit-precedence pin changed
  meaning deliberately: the WHOLE set is sent for context, and the pin now
  asserts the conflicting in-set answer for a covered label is DROPPED.
- **Test-hygiene fix (found during migration, introduced by 9ikj):** the
  editor-route tests ran the default-ON verify gate against
  `_build_verify_lite_ai`'s REAL adapter construction (the route's
  TextAIGemini patch does not reach it) -- on a machine with live
  credentials that could fire real back-translate calls from unit tests.
  The `translate_ai` fixture now patches `_build_verify_lite_ai` to an
  offline stub (fail-open, zero live calls), with the hazard documented
  in-file.

Known simplification (deliberate, noted): two DIFFERENT option sets
sharing one label still share one translation (the flat source-keyed
downstream maps; same as the pre-migration behavior, now with strictly
more context). Distinct per-set renderings for a shared label would need
per-option keying end-to-end -- not worth it at current scale.

**Fresh-eyes round-1 catches (both fixed in-loop):** (1) the authoring
CLI's `--check` `_Probe` and its test suite's `FakeTextAI` still spoke
`translate_labels` -- the CLI's check mode silently reported languages as
FAILED (AttributeError masked by the bake's per-language try/except) and
2 of its 5 tests failed; both migrated to translate_items, and check mode
now documents that an empty result keeps the verify gate dormant. (2) The
same live-call test hazard fixed in the editor-route tests existed in the
CLI test suite too -- its `_inject` now patches `_build_verify_lite_ai`
offline. This ALSO exposed a session-process gap: the pre-PR "full suite"
runs all night targeted `backend/tests` only; the CLI tests live in the
top-level `tests/` harness suite (the closeout skill's note says
backend/tests is named "for speed, not to exclude the harness suite").
This PR's pre-PR run covers BOTH suites.

## Lessons

- **A stubbed-adapter patch does not reach internally constructed
  siblings.** The route test patched the module's TextAIGemini, but the
  verify gate built its lite adapter from a different import site --
  live-credential machines would have made real calls from unit tests.
  When a service constructs its own adapters, give tests a seam
  (patchable builder) and CHECK for construction behind patches -- in
  EVERY test suite that reaches the gate, not just the first one found.
- **"Full suite" must mean both suites.** `backend/tests` alone missed
  the top-level `tests/` harness-suite consumers of the migrated
  function; the breakage was real and pre-existing tests caught it only
  when the reviewer ran them.

## Doc freshness

- `docs/standards/validation-delegation.md` reviewed: the translate_items
  bullet's "Consumers land with the forward-path migration (bd alry)"
  line is now satisfied -- bumped the line to present tense.
- Sprint-14 plan reviewed, no change needed (Part A.1/A.5 described this
  exactly).

## Files touched

- `backend/services/option_translation.py` -- payload builder + flattener
  + form-name helper; bake + runtime switched; ambiguous flags;
  glossary param rename.
- `backend/tests/unit/test_option_translation_bake.py` -- migrated pins +
  ambiguous-flag pin.
- `backend/tests/unit/test_option_translation.py` -- migrated pins.
- `backend/tests/unit/test_editor_kit_routes.py` -- fakes migrated + the
  offline-lite hygiene patch.
- `backend/tests/unit/test_translation_verify.py` -- stub + kwarg rename.
- `docs/standards/validation-delegation.md` -- consumer line bumped.
