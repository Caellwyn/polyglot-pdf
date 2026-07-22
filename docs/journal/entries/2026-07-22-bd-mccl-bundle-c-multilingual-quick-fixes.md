---
date: 2026-07-22
bead: polyglot-pdf-mccl
title: "feat(i18n): sprint-13 Bundle C -- add Russian, decline/spell-back SI rules, discard-rejected-value, localized harness confirms"
tags: [conventions, harness, testing]
---

## Trigger

Sprint 13 (docs/sprint_13_multilingual-ux_plan.md, approved 2026-07-22) Bundle
C: the five clear/easy fixes from the 6mzi five-language assessment, shipped
first so the epics build on a corrected base. This PR bundles five whole beads
per the bead/PR contract (each too small for its own review cycle): mccl,
nb2c, s39z, djnk, lo37 -- plus the sprint plan-of-record itself.

## What shipped

- **mccl -- Russian is a supported language.** SPOKEN_LANGUAGES entry +
  `russian: ru-RU` in the BCP-47 bias map + Russian entries in the three
  per-component translation maps (overlay, connection-timeout, disclaimer
  buttons + text) + Russian option-label bake across the 4 kits (162 labels,
  one batched pro call per kit). Both mirror enforcement tests updated (18
  languages).
- **nb2c -- declines always store empty.** Both SIs' NOT-APPLICABLE rule now
  explicitly forbids the literal text "N/A"/"none"/any-language equivalent
  (the zh run wrote literal N/A where every other language stored empty).
- **s39z -- spell-back in English letter names.** Both NAMES blocks require
  reading Latin spellings back by ENGLISH letter names in every session
  language (the ru run verified NGUYEN as Cyrillic letter names and a
  mis-spelled LIN sailed through).
- **djnk -- rejected values die.** The update_form_fields validation-error
  response now orders the model to DISCARD rejected values and re-ask (the hi
  run reused a rejected invented '10' as the next field's fill over the
  user's real '12'). Scoped to validation rejections; unknown-field text
  unchanged. Interim: epic 66ek supersedes.
- **lo37 -- the harness persona confirms in-language.** confirm_yes/reject
  phrases per language in the multilang fixture; the stress harness resolves
  them per --lang (local names, not shadowing -- the UnboundLocalError trap).
- Sprint plan-of-record + INDEX row; epics 66ek/tupu + children + D beads
  filed with sequencing deps; 37le closed as superseded by tupu.

## Verification

Full backend suite 1172 passed (5 new pins); frontend 1032 passed. Live
reruns (findings doc "Bundle C verification" section): **ru 12/14** -- input
transcription now predominantly Russian (bias works), Latin spell-backs, all
names correct, kit-baked labels covered 100% (text cost $0); **zh 14/14** --
declines empty, no desync this run (single run; non-recurrence is A1's n>=3
job). New evidence: ru apt "12" filled as "19" -- the ww9y short-numeric
class in a second language, recorded on the bead.

## Lessons

- Kit-precedence works as designed at scale: a fully-baked language costs $0
  in runtime translation.
- The short-numeric mis-generation (ww9y) is language-independent and
  recurred despite correct input transcription -- it is a generation problem,
  not an ASR problem.

## Doc freshness

Sprint plan + INDEX row added. BUMPED (this branch changed their tracked
files with content effect): tool-call-flow.md (the djnk DISCARD rule on
validation-error responses), voice-ai.md (the nb2c/s39z SI rules + djnk).
REVIEWED-AND-LEFT (tracked-file mtime only, content unaffected by this
branch's SI-text/message edits): config-deployment.md, ai-models.md,
context-compression.md, jit-schema.md, confirmation-and-audit.md (its
confirmation-LOGGING content is untouched by the response-message change),
plus the pre-existing stale set from earlier branches (2026-07-12..17).

## Files touched

- frontend: shared/languages.ts(+test), demo/overlayTranslations.ts,
  schema-forms/components/{connectionTimeoutTranslations.ts,DisclaimerModal.tsx}
- backend: utils/language_codes.py, config.py (SI rules),
  services/callback_handler.py (discard rule),
  tests/unit/{test_transcription_language_bias.py,test_tool_contract_static.py,
  test_djnk_discard_rejected_value.py (NEW)}
- form-kits/*/schema.json (Russian label bake)
- scripts/spikes/{measure_form_session_costs.py,fixtures/multilang_phrases.json,
  multilingual_ux_findings.md} + 2 verification run data sets
- docs/{sprint_13_multilingual-ux_plan.md (NEW),INDEX.md} + this entry
