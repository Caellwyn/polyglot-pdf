# form-kits/_translation/

Shared translation-quality data for ALL kits (epic `polyglot-pdf-sekc`,
plan `docs/sprint_14_translation-quality-gate_plan.md`). This directory is
NOT a form kit: the kit stores (`backend/services/form_kits.py`) deliberately
skip it -- it is read directly from the repo/image filesystem by
`backend/services/translation_lint.py` (authoring-time code paths only).

- `glossary.json` -- the per-language glossary + style file: official term
  pins (es/zh, seeded from IRS Pub 850 + USCIS renderings), register lines,
  expected-script table, the do-not-translate list, and the ASCII-digits
  policy. Injected into the translate/judge/rectify prompts and consumed by
  the deterministic mechanical lint. UTF-8 data file -- non-ASCII content is
  deliberate here (CLAUDE.md scar #6 covers source files, not data).

Editing rules: keep pins to renderings verifiably used by the agency itself
(the defensibility rationale: "we match the agency's own terminology").
Confirmed-good translations from bake audits get promoted into the pins over
time. Before adding pins for inflecting languages (ru/ur/pl-class), read the
`pin_matching_caveat` in `_meta`.
