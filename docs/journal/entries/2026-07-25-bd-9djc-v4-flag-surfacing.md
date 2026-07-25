---
date: 2026-07-25
bead: polyglot-pdf-9djc
title: "V4: flag surfacing -- CLI FLAGS block, extraction provenance, editor ValidationPanel"
tags: [schema-editor, extractor, conventions]
---

## Trigger

V4 of the translation-quality-gate epic (`polyglot-pdf-sekc`, plan:
`docs/sprint_14_translation-quality-gate_plan.md`). V3 (`polyglot-pdf-9ikj`)
put the verify/rectify loop inside the shared bake and returns its flags on
the report dict -- but only extraction persisted them, the CLI printed
nothing, and the editor route dropped them entirely (the V3 fresh-eyes note:
editor-triggered bakes spent the verify credits and discarded the findings).
This bead is the surfacing half of epic criteria 3 + 4: the flags must reach
every authoring surface.

## What shipped

- **One durable channel, three surfaces.** The design center: the bake
  report (flags included) is persisted at
  `_bakeoff.authoring.option_translation` -- extraction already stored it
  verbatim; the editor route now writes the SAME slot before storing the
  schema -- and `backend/services/schema_lint.py` RE-EMITS the persisted
  flags as WARNING findings (`TRANSLATION_FLAG_RULES`, severity pinned
  regardless of the stored dict, malformed slots skipped). That makes the
  existing ValidationPanel render the translation worklist on every lint
  pass -- editor-baked and extraction-baked kits alike, surviving reloads
  and saves -- with zero new panel plumbing.
- **CLI** (`scripts/authoring/translate_option_labels.py`): a FLAGS summary
  block (counts by rule + rule/path lines; messages deliberately withheld --
  they can quote foreign script, the cp1252 console hazard), `--flags-out`
  JSON artifact carrying the complete findings (ensure_ascii), `--no-verify`
  opt-out, and a visible verify status line covering both skip paths
  (`--no-verify` and `TRANSLATION_VERIFY_ENABLED=false`) plus per-language
  verify counts on the per-language lines. `--check` now passes
  `verify=False` explicitly (report-only mode no longer constructs the lite
  verify adapter at all).
- **Extraction** (`scripts/authoring/extract_form.py`): a count-only console
  summary line (`_translation_flag_summary`, unit-testable helper); the
  provenance slot was already written verbatim.
- **Editor route** (`backend/routes/editor_kit_routes.py`):
  `TranslateOptionsResponse.flags` + the provenance persist; the post-bake
  lint counts on the same response now include the persisted flags.
  Idempotent re-runs (nothing fresh, no new flags) do NOT erase the
  persisted worklist.
- **schema-editor**: friendly `RULE_LABELS` for the four translation rules,
  a flag count + pointer in the translate notice, `_bakeoff` modeled on
  `FormSchema` so the load->edit->save round-trip visibly preserves it
  (both round-trip helpers spread top-level keys, verified).
- **Rider (maintainer directives 2026-07-25, folded in to avoid a docs-only
  PR):** plan doc records the 2-kit V5 scope (i-90 + w7, ~$4-5 worst case)
  and a model-facing purpose note (translations steer the voice model's
  language consistency; no user-facing display translation -- compliance);
  glossary `digits_policy` reworded from user-entry to model-facing framing;
  `DHS` added to the do-not-translate list (USCIS-side coverage).
- Tests: planted-flag pins on all three surfaces with zero live calls --
  lint re-emission (4 rules, severity pin, malformed-slot tolerance), route
  persist+response+idempotent-keep, CLI block/artifact/both opt-out paths,
  extraction passthrough + summary helper, ValidationPanel +
  RemoteCatalogue component tests.
- Fresh-eyes triage: (filled at closeout -- see PR.)

## Lessons

- **Persist-then-re-emit beats response-plumbing for transient authoring
  findings.** The verify flags exist only at bake time; threading them
  through every consumer UI would have meant new state on three surfaces.
  Storing them in the schema's provenance slot and having the linter re-emit
  them bought durability (reload/save-safe) and a single render path for
  free. The generalization: if a finding should OUTLIVE the request that
  produced it, put it where the linter already looks.
- The route-drops-report-keys failure mode (V3's editor route) is worth
  checking whenever a shared service grows a report key: grep every call
  site for consumers of the new key before calling the feature shipped.

## Doc freshness

- `docs/sprint_14_translation-quality-gate_plan.md` -- updated per the
  maintainer rider (V5 scope/cost + purpose note). No component/standards
  doc tracks the flag-surfacing seam specifically; reviewed and left as-is.
- CLAUDE.md untouched.

## Files touched

- `backend/services/schema_lint.py` -- TRANSLATION_FLAG_RULES + persisted-flag re-emission
- `backend/routes/editor_kit_routes.py` -- flags on TranslateOptionsResponse + provenance persist
- `scripts/authoring/translate_option_labels.py` -- FLAGS block, --flags-out, --no-verify, verify status
- `scripts/authoring/extract_form.py` -- _translation_flag_summary console line
- `schema-editor/src/components/ValidationPanel.tsx` -- translation RULE_LABELS
- `schema-editor/src/components/RemoteCatalogue.tsx` -- flag count in the translate notice
- `schema-editor/src/utils/remoteKitStore.ts` -- TranslateOptionsReport.flags
- `schema-editor/src/types/schema.ts` -- _bakeoff round-trip key
- `form-kits/_translation/glossary.json` -- digits_policy reword + DHS (rider)
- `docs/sprint_14_translation-quality-gate_plan.md` -- V5 scope/cost + purpose note (rider)
- tests: `backend/tests/test_schema_lint.py`, `backend/tests/unit/test_editor_kit_routes.py`, `tests/test_translate_option_labels_cli.py`, `tests/test_extract_form_lint.py`, `schema-editor/src/components/ValidationPanel.test.tsx`, `schema-editor/src/components/RemoteCatalogue.test.tsx`
