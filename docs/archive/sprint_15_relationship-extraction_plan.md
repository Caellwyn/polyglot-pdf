# Sprint 15 -- Relationship extraction (lift the (b) arm of the auto-pass)

Commissioned 2026-07-25; maintainer-approved same day (plan-mode approval
after one revision narrowing scope to relationships only). Epic:
`polyglot-pdf-o2bs`. Successor to the authoring-loop epic `polyglot-pdf-7a9`
(sprint 5), whose two remaining children (`ue5s`, `7a9.19`) are unaffected.

## Why (L1)

The authoring loop shipped: one-command auto-pass
(`scripts/authoring/extract_form.py`) + schema-editor touch-up, with the (a)
field-extraction half solved on I-90 (field F1 96.7-98.5, exact
`pdf_field_name` 100%). The residual human touch-up labor is concentrated in
the (b) relationships half: the best arm recovers only ~45-55% of `show_if`,
and the logic keys (`conditional_logic` / `conditional_behavior`) sit at 0%
across every arm tested (7a9.5 recommendation,
`docs/journal/entries/2026-06-07-bd-7a9.5-authoring-recommendation.md`).
The maintainer narrowed this phase to that one target: significantly
improving relationship extraction is the win.

Maintainer constraints (2026-07-25, in-chat):
- `help.instructions` extraction is handled in a PARALLEL session -- out of
  scope here.
- I-589 / big-form work stays indefinitely parked; NO form-coverage expansion.
- **i-90 remains the gold standard (tune set); w7 remains the test set** -- a
  significantly different format, never tuned against, proving cross-format
  generalization.
- Relationships are bidirectional: `show_if` (dependent side) and the trigger
  side ("which fields does this one affect").

## Ground truth on "bidirectional" (verified in code)

The v2 FormSchema stores relationships **target-side only**: `show_if` /
`require_if` on the affected field, plus the logic keys `conditional_logic` /
`conditional_behavior` (gold encodes e.g. the I-90 read-only unlock under
`conditional_logic` -- bd 7a9.16). The trigger-side key `controls_fields` was
DELETED at the P6.2 v2 flip (bd d9lz) and is lint-ERRORed as
`legacy-trigger-side-logic`; the scorer deliberately excludes it
(`scripts/schema_score.py:496-506`).

But the mirroring machinery already exists:
`backend/services/controls_fields_mirror.py` (bd h76m.16 / c3y6) converts
trigger-side draft emissions into v2 target-side keys -- `shows` ->
`show_if`, `makes_required` -> `require_if` -- via `schema_repair.py`. The
four remaining trigger actions (`hides` / `locks` / `unlocks` /
`makes_optional` -- read-only and negation logic) have NO clean target-side
equivalent and are only *reported*, not converted. That unconverted residue
is exactly the `conditional_logic` / `conditional_behavior` territory scoring
0% today.

So "bidirectional" here means: **harvest relationship edges however the LLM
expresses them** (from either end), canonicalize everything into the v2
target-side keys, and lose nothing silently -- NOT adding trigger-side
storage back to the schema.

## Design decisions

- **Research-then-ship split** (mirrors the 7a9 pattern): a measured bake
  (R2) picks the approach on i-90 ONLY; w7 is scored for reporting but never
  iterated against. The bake runs under the `/experimentation` skill gates
  (prior-work audit + pre-spend cost estimate; the default extractor model is
  the local Claude CLI, free in-env, so incremental cost is small Gemini arms
  at most).
- **The four unconvertible trigger actions are in scope** via mapping into
  the existing `conditional_logic` / `conditional_behavior` keys where gold
  semantics allow (else loud repair-report + lint surfacing). This implements
  existing schema semantics -- no new schema contract.
- **Provisional bars are set final at baseline time** (R1) and logged on the
  epic bead, per the rubric rule in
  [`docs/doctrine/planning.md`](doctrine/planning.md) ("changes are logged on
  the epic bead").

## Exit rubric (epic `polyglot-pdf-o2bs`)

| # | Criterion (binary) | Verify |
|---|---|---|
| 1 | Relationship metrics are complete and baselined: `schema_score.py` reports per-key recall for `show_if`, `require_if`, `conditional_logic`, `conditional_behavior` AND counts edges harvested from trigger-side emissions (mirrored, not dropped); i-90 + w7 baselines recorded on the epic bead BEFORE any pipeline change, with the final bars for #2/#3 set and logged there. | `python scripts/authoring/eval_extraction.py` table + `schema_score.py --json`; baseline comment on the epic bead. |
| 2 | On i-90 (tune set): `show_if`+`require_if` recall >= 70% (provisional; from ~45-55%) AND `conditional_logic`/`conditional_behavior` recall >= 50% of gold entries (from 0%), with NO (a)-half regression (field F1 >= 96). | Before/after `schema_score.py --json` on i-90. |
| 3 | On w7 (test set): the SAME shipped pipeline -- never tuned on w7 -- meets the relationship-recall bar set at baseline time (provisional: >= 60% absolute or >= +20 points over baseline), with no (a) regression on w7. | `schema_score.py --json` on w7; the R2 journal documents i-90-only iteration. |
| 4 | Zero silent drops: every trigger-side relationship the LLM emits is either canonicalized into a v2 key (`show_if`/`require_if`/`conditional_logic`/`conditional_behavior`) or surfaced in the repair report + lint as needs-human -- proven by unit tests covering all six action kinds. | Backend repair/lint test suites green; lint on a fresh extracted draft shows no `legacy-trigger-side-logic` ERROR without a matching repair-report entry. |

## Bead tree

Order: R1 -> R2 -> R3; R4 is parallelizable with R2/R3 (disjoint surfaces).

| Bead | Scope | Surfaces | Inherits |
|------|-------|----------|----------|
| `polyglot-pdf-eprg` (R1) | Relationship metrics + baselines: per-key recall for all four relationship keys + trigger-side-harvest accounting in the scorer; relationship columns in `eval_extraction`; record i-90 + w7 baselines on the epic bead and set + log the final bars. | `scripts/schema_score.py`, `scripts/authoring/eval_extraction.py`, `tests/test_schema_score_v2_dialect.py`, `tests/test_eval_extraction.py` | 1 |
| `polyglot-pdf-dsbl` (R2) | RESEARCH bake (i-90 only; w7 report-only): candidate arms -- dedicated relationships second pass over printed conditional text + dump; explicit trigger-side elicitation harvested via the mirror; few-shot from i-90 gold; targeted `conditional_logic`/`conditional_behavior` elicitation. Measured pick + journal. Under `/experimentation` gates. No pipeline changes. | `scripts/spikes/`, `scripts/bakeoff/research/` | 2, 3 (measurement) |
| `polyglot-pdf-kfni` (R3) | SHIP the winning approach in the pipeline + tests; final i-90/w7 numbers recorded against the R1 bars. | `scripts/bakeoff/arm_llm_native.py`, `scripts/authoring/extract_form.py`, possibly new `scripts/authoring/relationships_pass.py`, `tests/test_extract_form_relationships.py` | 2, 3 (final) |
| `polyglot-pdf-xbfm` (R4) | Harvest completeness: extend the mirror so `hides`/`locks`/`unlocks`/`makes_optional` map into `conditional_logic`/`conditional_behavior` where gold semantics allow, else loud repair-report + lint surfacing; zero silent drops; tests for all six action kinds. | `backend/services/controls_fields_mirror.py`, `backend/services/schema_repair.py`, `backend/services/schema_lint.py`, `backend/tests/` | 4 |

Planning ticket (standalone, closes with the plan-filing PR):
`polyglot-pdf-6fr5`.

## Out of scope

- `help.instructions` extraction (parallel session owns it).
- New forms, I-589 / big-form / table / chunking work (indefinitely parked).
- `copy_to` and `overflow_to_supplement` improvements (still scored, not
  targeted this phase).
- Editor UX changes (the editor is already target-side-only; ConditionBuilder
  exists).
- Hardening beads `yaua` / `rqlr` / `7a9.19` (standalone backlog).
- Any schema-model change (no trigger-side storage returns; v2 target-side
  canon stands).

## Verification (end-to-end)

- R1's baseline run is the measurement anchor; bars are logged on the epic
  bead before any pipeline change.
- R2 is behavioral proof under the experimentation gates; its journal is the
  decision record (including i-90-only iteration discipline).
- R3's before/after `schema_score --json` on i-90 AND w7 settles criteria 2-3.
- R4's unit tests over all six trigger-action kinds settle criterion 4.
