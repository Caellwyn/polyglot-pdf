---
date: 2026-07-24
bead: polyglot-pdf-ch7j
title: "V2: context-carrying translate_items + glossary/style file + deterministic mechanical lint"
sprint: 14
tags: [conventions, testing]
---

## Trigger

First build bead of the translation-quality-gate epic (`polyglot-pdf-sekc`,
plan `docs/sprint_14_translation-quality-gate_plan.md`, approved 2026-07-23
after three review rounds). Every shipped translation (~10,900 strings) came
from a single bare-string model call checked only for JSON shape; this bead
ships the PREVENTION inputs (context-carrying translation payload, official
glossary, temperature 0, ambiguity self-flag) and the cheapest DETECTION
layer (the deterministic mechanical lint) -- all with zero live model calls,
ahead of the V1 probe and the V3 verify/rectify loop.

## What shipped

- **`TextAIGemini.translate_items`** (sibling of `translate_labels`):
  structured items `{id, kind (field-name | option-set | section-title),
  text | options + parent_question}`, option sets translated AS UNITS,
  glossary/register/DNT/digits-policy prompt injection (caller passes
  `translation_lint.glossary_prompt_context`'s slice), temperature 0.0, an
  `ambiguous` self-flag array in the response, per-item shape validation
  with unknown ids/options dropped, fail-open None, counts-only logging.
  `translate_labels` kept its contract for existing callers (its
  temperature moved 0.1 -> 0.0, the plan's Part A.3 determinism decision;
  the validator/secretary paths still send NO temperature -- cache-prefix
  stability untouched).
- **`form-kits/_translation/glossary.json`** (+ README): term pins for
  es/zh seeded from IRS Pub 850 + USCIS renderings (provenance + the
  promote-confirmed-good pattern recorded in `_meta`), register lines and
  expected-script entries for all 17 non-English languages, the
  language-independent do-not-translate list, form-number/format-mask
  patterns, and the explicit ASCII-digits policy line (plan review round 3).
- **`backend/services/translation_lint.py`**: pure-function mechanical
  checks (empty, non-ASCII digits, source digit runs survive, format masks
  byte-exact, DNT terms + form numbers byte-identical, expected-script,
  glossary pins), kit-schema traversal emitting `schema_lint.LintFinding`s
  (severity WARNING, rule `translation-mechanical`, parent-carrying paths),
  a 4-kit sweep entry point and an ASCII-safe CLI (`python -m
  backend.services.translation_lint`, exit 0/1/2).

**Tolerances were tuned on measured data, not guessed** (the review-round-3
"or it flags everything" warning proved out immediately):
- Script check piloted as present+dominant: flagged correct translations
  keeping un-DNT'd Latin acronyms ("ZIP code" -> arabic=6, latin=7).
  Demoted to PRESENCE-only.
- Then the shipped i-90 still produced ~600 wrong-script findings -- all US
  state names deliberately kept Latin-identical in ar/hi/ur ("Alabama" ->
  "Alabama"), which the translate prompt itself sanctions (proper nouns
  unchanged). Identity-kept strings are now SKIPPED by the script check:
  identity is a translator choice the lint cannot prove wrong; the V3
  bilingual judge owns that call.
- Final sweep over the 4 shipped kits: **225 findings, high precision** --
  90 non-ASCII-digit violations (the Persian bake used Extended
  Arabic-Indic digits: "Dependent 1" -> U+06F1), 109 lost source digit
  runs (mostly the same strings), 17 pin misses (es filing-status labels
  differ from the Pub 850 renderings; es "wages" not rendered "salario"),
  5 dropped "SSN" (ar), 4 wrong-script. These stand as the pre-audit of
  the shipped kits; V5's re-bake through the full pipeline is what fixes
  them (deliberately NOT hand-patched here -- review S1: no re-bake before
  the verify loop exists).

Deferred/next: V1 probe (`polyglot-pdf-i36i`) now unblocked; V3
(`polyglot-pdf-9ikj`) consumes the lint + `translate_items` in the bake.

**Fresh-eyes triage (round 1, Sonnet -- GAPS-FOUND (2) + 2 advisories):**
- ADOPTED (blocker): the lint's finding paths used a prettier
  `fields[<id>].` format that `schema_lint.field_id_of()` cannot parse --
  every finding would have carried `field_id=None` into V4's editor
  surfacing. Paths now emit the house `fields[<idx>] (id=<id>)` shape,
  round-trip pinned in tests.
- ADOPTED (already fixed pre-verdict, independently): stale
  validation-delegation.md temperature line + the missing `translate_items`
  port declaration -- both landed in the port/doc commit while the review
  ran.
- DEFERRED (true nit -> bd polyglot-pdf-qwex): deploy-script `--all` loops
  now log a spurious skip warning for `form-kits/_translation/`.

## Lessons

- **Lint tolerances need measurement, not intuition.** Two rounds of
  real-kit sweeps (864 -> 845 -> 225 findings) each exposed a
  flag-everything class the design review had only abstractly warned
  about. Piloting a deterministic check against real data before shipping
  it is cheap and changed the design twice.
- **Identity-kept translations are a semantic question.** A mechanical
  checker cannot distinguish "Alabama" (correct identity) from "Given
  name" (lazy identity); that split needs a judge with context. Charter
  discipline -- the lint proves wrongness, the judge weighs choices --
  decided where the check belongs.
- **Bash-tool file writes do not persist in this harness (sandboxed);
  Write/Edit tools do.** Cost several confused minutes on an
  ASCII-escaping fix; use Write/Edit for all file mutations.

## Doc freshness

- `docs/sprint_14_translation-quality-gate_plan.md` NEW (the epic's plan of
  record) + its row in `docs/INDEX.md`'s Active sprint plans.
- `docs/standards/validation-delegation.md` BUMPED: the `ITextAI` port grew
  a fourth method (`translate_items`, added to
  `backend/ports/text_ai_port.py` with the house non-abstract fail-loud
  default), and the `translate_labels` temperature line updated 0.1 -> 0.0.
- `docs/standards/ai-models.md` reviewed, left as-is (no model/config knob
  changed; `OPTION_TRANSLATION_MODEL` untouched).
- `docs/components/config-deployment.md` reviewed, left as-is (no new env
  var in this bead; `TRANSLATION_VERIFY_ENABLED` lands with V3).
- Other STALE flags from the freshness checker (stateless-architecture,
  terminology, testing, voice-and-vad, ws-protocol, technical_guide) track
  files this branch did NOT touch -- pre-existing staleness, left as-is.

## Files touched

- `backend/adapters/text_ai_gemini.py` -- translate_items; translate_labels
  temperature 0.1 -> 0.0.
- `backend/ports/text_ai_port.py` -- translate_items on the ITextAI port
  (non-abstract fail-loud default, house convention).
- `docs/standards/validation-delegation.md` -- fourth-method bullet + temp
  line + stamp bump.
- `backend/services/translation_lint.py` -- NEW: mechanical lint + glossary
  loader + kit sweep CLI.
- `form-kits/_translation/glossary.json` -- NEW: the glossary/style data
  file.
- `form-kits/_translation/README.md` -- NEW: directory contract.
- `backend/tests/unit/test_translate_items.py` -- NEW (11 tests).
- `backend/tests/unit/test_translation_lint.py` -- NEW (22 tests).
- `backend/tests/unit/test_text_ai_gemini.py` -- temperature pin 0.1 -> 0.0.
- `docs/sprint_14_translation-quality-gate_plan.md`, `docs/INDEX.md` -- the
  sprint-14 plan of record + index row.
