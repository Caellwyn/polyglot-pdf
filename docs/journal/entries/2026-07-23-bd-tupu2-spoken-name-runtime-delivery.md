---
date: 2026-07-23
bead: polyglot-pdf-tupu.2
title: "feat(i18n): runtime spoken-name + section-label delivery -- the model hears field names in the session language (epic tupu step 2)"
tags: [conventions, testing, harness]
---

## Trigger

Epic polyglot-pdf-tupu step 2: tupu.1 baked per-field spoken-name
translations into the kits; this bead delivers them to the voice model at
runtime, so non-English sessions stop hearing English field jargon ("uscis
online account number" read aloud) and stop burning a secretary call per
field for names (the fr assessment run: 14/14 questions).

## What shipped

- **The named ow1e contract change:** `get_option_label_overrides` ->
  `get_translation_overrides`, returning a frozen `TranslationOverrides`
  (option_labels + spoken_names + section_labels), built in ONE cached
  batched call per (form, language) over the union of kit-uncovered strings;
  kit translations win; fail-open to `EMPTY_OVERRIDES`. The pinned runtime
  tests migrated wholesale.
- **Delivery threading:** `spoken_name_overrides` through
  `get_field_guidance` (the manifest_service:116 hook) and
  `render_field_guidance` at every call site, PLUS the channels beyond the
  guidance render that the adversarial plan review enumerated: the
  switch_to_field success message, switch candidate/clarify lists,
  ask_secretary `fields` arrays, the next-field-hint quoted-name substitution
  (initiating message + confirm/skip responses, with the section-complete
  branches guarded), and `previous_spoken_names`. Section labels thread into
  `render_section_metadata`.
- **SI rule (both SIs):** FIELD NAMES ALOUD -- guidance names are already in
  the session language when a translation exists; never read a raw id or an
  English name/label aloud in a non-English session; never call a tool to
  translate or fetch a field name.
- **The latency race, found live and fixed:** the first sanity run spoke a
  perfect Spanish session EXCEPT the greeting's English section title -- the
  runtime-only section labels forced a live translate call at session start
  that outran the greeting render. Fix: section `label_translations` baked
  into the kits (bake extension + 4-kit x 17-language backfill; FormSection
  model + both TS types), making the start build kit-covered and instant,
  plus a 2s bounded fail-open await in `send_initiating_message`. Live
  re-check: greeting fully Spanish, `hint_translated=True`, 132 overrides
  present at greeting time, text cost ~$0 (kit precedence).
- Out-of-scope finds filed: bd polyglot-pdf-che4 (kit spoken_names carry
  audible numeric suffixes -- "numero de registro de extranjero 1" -- a
  pre-existing extraction wart now visible in translations).
- Tests: runtime suite migrated + union/section pins; new
  test_spoken_name_delivery.py (echo channels, hint substitution, SI pin);
  full backend 1186 passed; both frontend typechecks clean.

## Lessons

- **Kit translation coverage is a LATENCY invariant, not just a cost win**:
  any uncovered string class re-introduces a live model call on the session-
  start critical path, and the greeting will not wait. If a future string
  class joins the union (part labels, help text), bake it or accept an
  English first turn.
- The three-map union build kept the one-batched-call-per-language pin
  intact through two scope additions -- the membership-split pattern scales.

## Doc freshness

schema_format.md already documents the convention (tupu.1); section
label_translations follow the identical pattern -- added mention rides the
next schema_format touch (the doc's section-11 wording is generic enough to
cover it; noted here per the stale-before-you rule the checker applies to
the other flagged docs, none of whose content this branch changes).

## Files touched

- backend/services/option_translation.py (TranslationOverrides + union build
  + section collect/fan-out + cache entry)
- backend/services/form_filling_service.py (three maps + getters + bounded
  await + hint substitution + section metadata threading)
- backend/services/callback_handler.py (getters + echo channels + hint
  substitution + render threading)
- backend/services/manifest_service.py, backend/services/ai_context.py
  (override hooks)
- backend/config.py (FIELD-NAMES-ALOUD rules, both SIs)
- backend/models/form_models.py (FormSection.label_translations), both TS
  schema types
- form-kits/*/schema.json (section-label backfill)
- backend/tests/unit/{test_option_translation.py (migrated),
  test_option_translation_bake.py, test_spoken_name_delivery.py (NEW)}
- scripts/spikes/data (verification runs) + this entry
