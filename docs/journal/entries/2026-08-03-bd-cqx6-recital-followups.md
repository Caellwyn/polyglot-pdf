---
date: 2026-08-03
bead: polyglot-pdf-cqx6
title: "fix(voice): option-recital follow-ups -- safe-direction type gate, enum hardening, translated hint labels"
tags: [conventions, testing]
---

## Trigger

Three follow-up beads filed by the pre-PR reviews of the option-recital work
(bd polyglot-pdf-6bq8 / s503), bundled into one PR per the bead/PR contract
(each too small for its own review cycle): polyglot-pdf-cqx6 (unknown-type
fallback direction), polyglot-pdf-0rm1 (untranslated English option labels in
the next-field hint), and polyglot-pdf-285t (two deferred review nits). The
maintainer asked for explanations of cqx6 and 0rm1 and said to carry on with
the next beads.

## What shipped

- **cqx6 -- the type gate names the ask-directly side.**
  `ai_context.RECITAL_OPTION_TYPES` ({radio, checkbox, checkbox_group})
  became `ASK_DIRECTLY_OPTION_TYPES` ({select}), inverting the fallback: an
  option-bearing field with an unrecognized or ABSENT type (nothing in
  `form_models.py` forbids `options` on a text field, and LLM extraction has
  invented odd types before) now degrades toward the read-ALL recital -- the
  accessibility-safe direction -- instead of silently losing it. Selects keep
  the ask-directly marker at every count; radio/checkbox groups keep the
  count-based split. Pinned by a parametrized test over
  None/''/text/number/select/radio/checkbox_group.
- **0rm1 -- the hint speaks the session language.** All three kits are fully
  baked (W-7 21/21, I-90 294/294, F-1040 24/24 option labels x 17 languages),
  so this was a code-path gap, not a data gap: `formatNextFieldHint` embedded
  raw English `o.label` while the guidance block used translations. The
  function now takes the session language and resolves each label through
  `label_translations` (lowercase-name keys, per-option English fallback);
  all seven call sites pass it. The quoted field NAME and `field_id` stay
  English by contract -- the backend's `_translate_hint` matches on the quoted
  English name (bd tupu.2). Nine vitest cases pin the behavior.
- **285t nits.** (1) The render unwraps a `(str, Enum)` `FieldType` member
  before classifying -- `str(FieldType.RADIO)` is `'FieldType.RADIO'`, which
  would have silently diverted an enum-typed radio to ask-directly (latent:
  all production callers pass raw JSON dicts). (2) The template carve-out pin
  asserts the contiguous "marks the list as a standard list" phrase (the
  split-substring version stayed green under clause drift) and the test is
  renamed off "long_list".

**Live verification (Spanish session, W-7, Vertex 2.5 native-audio):** the
reason ask recited all 8 options IN SPANISH with full labels ("a. Extranjero
no residente ... h. Otro (consulte las instrucciones)"). Dev-log inspection
of the initiating message showed no English option labels on that surface
(the spoken hint's parenthetical is stripped before speech; the options ride
the translated guidance block). The confirm-response hint surface is covered
by the vitest pins -- it is produced by the same single `formatNextFieldHint`.

## Lessons

- **Name the exception side of a gate, not the default side.** "Recite only
  these types" silently reclassified every unforeseen input into the
  degraded branch; "ask directly only for selects" makes unforeseen inputs
  fail toward the safe behavior. When a gate's two sides differ in user harm,
  the enumerated set should be the harmful side.
- A "missing translations" symptom is not always a data gap: both kits were
  fully baked; only one of the two channels read the bake.

## Doc freshness

- `docs/standards/si-reduction.md` -- bumped: gate inversion, enum unwrap,
  and the hint-label translation are recorded in the per-field-guidance
  bullet and header.
- The pre-existing stale set flagged by the freshness checker (recorded in
  the bd 6bq8 entry) is unchanged by this diff and left as-is.

## Files touched

- `backend/services/ai_context.py` -- ASK_DIRECTLY_OPTION_TYPES gate + enum
  unwrap.
- `backend/tests/unit/test_dti_si_voice_rules.py` -- parametrized type-gate
  test, enum test, contiguous template pin + rename.
- `frontend/src/navigation.ts` -- `formatNextFieldHint(field, order,
  language)` label translation.
- `frontend/src/webFormConnection.ts`, `frontend/src/schema-forms/state/
  schemaFormState.ts`, `frontend/src/demo/VoiceOverlay.tsx`,
  `frontend/src/demo/VoiceOverlayMobile.tsx` -- call sites pass the session
  language.
- `frontend/src/__tests__/navigation-hint.test.ts` -- 4 new translation
  cases.
- `docs/standards/si-reduction.md` -- freshness bump.
- `docs/journal/entries/2026-08-03-bd-cqx6-recital-followups.md` -- this
  entry.
