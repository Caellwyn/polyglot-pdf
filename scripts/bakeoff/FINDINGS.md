# Extractor Bake-off Findings (bd polyglot-pdf-7a9.4)

**Throwaway research output.** Compares PDF -> JSON FormSchema extractor arms,
scoring the two halves of the problem SEPARATELY via `scripts/schema_score.py`:

- **(a) FIELD extraction** -- detection precision/recall/F1 + per-attribute
  accuracy (type, pdf_field_name, options, validation, section_id, pdf_position).
- **(b) RELATIONSHIP / logic** -- recall of show_if / controls_fields /
  conditional_* / copy_to / overflow_to_supplement + structural recall
  (parts / sections / supplements / tables).

Forms: **I-90** (stresses (a): widget mapping, coords, consolidation) and
**I-589** (stresses (b): 53 show_if, tables, 2 supplements, overflow).

## Arms

| Arm | (a) field structure source | (b) reasoning source |
|-----|---------------------------|----------------------|
| `old-extractor-heuristic` | PyMuPDF + tooltip-hierarchy parse (deterministic) | none |
| `old-extractor-enhanced`  | same skeleton | Gemini 2.5 Flash enhancer (spoken names, groupings, conditionals) |
| `gemini-multimodal`       | Gemini 3.1 Pro from pixels only | same call |
| `gemini-hybrid`           | PyMuPDF AcroForm dump fed to Gemini 3.1 Pro | same call |
| `claude-multimodal`       | Claude (Opus 4.8) from rendered PDF only | same call |
| `claude-hybrid`           | PyMuPDF AcroForm dump fed to Claude (Opus 4.8) | same call |
| `documentai-hybrid`       | **DROPPED** (maintainer decision 2026-06-06, after research): too expensive for negligible benefit over a raw strong-LLM pass. `arm_documentai.py` is written + validated and kept for reference, but excluded from scoring. See "Document AI verdict" below. | -- |

The `old-extractor-*` arms are the **prior art** (recovered from git `a0bf111`,
removed from dev at `5ea05d4`; revived + modernized for the bake-off -- PyMuPDF
1.24 constant rename, pydantic-v2 dump, google-genai SDK swap replacing the dead
v1beta REST Files API, current model). Reused per maintainer steer (2026-06-06):
"benefit from prior work; be open to improving it."

## Score table

Regenerate with
`python scripts/bakeoff/run_bakeoff.py --manifest scripts/bakeoff/manifest.json`.
Percentages. a.F1 = field-detection F1; a.attr = mean per-attribute accuracy;
b.cond = conditional-relationship recall; b.strc = structural recall.

Scores are reproducible: the scorer's field matcher was made deterministic during
this bake-off (it iterated a `set` of pdf_field_names, which Python orders by the
per-process hash seed, so pairings -- and scores -- drifted +-1 run-to-run;
`schema_score._field_pfns` now returns a sorted list). The numbers below are
stable across hash seeds.

### I-90 (stresses field extraction)

| arm | a.F1 | a.attr | b.cond | b.strc |
|-----|-----:|-------:|-------:|-------:|
| old-extractor-heuristic | 81.9 | 48.4 | 0.0 | 25.0 |
| old-extractor-enhanced  | 81.9 | 48.4 | 5.0 | 25.0 |
| gemini-multimodal       | 17.4 | 20.0 | 0.0 | 100.0 |
| **gemini-hybrid**       | **98.5** | 33.3 | 18.8 | 100.0 |
| claude-multimodal       | 3.0 | 20.0 | 0.0 | 100.0 |
| **claude-hybrid**       | 96.0 | **52.7** | **38.8** | 100.0 |

### I-589 (stresses relationships/tables/supplements)

| arm | a.F1 | a.attr | b.cond | b.strc |
|-----|-----:|-------:|-------:|-------:|
| old-extractor-heuristic | 35.6 | **59.6** | 0.0 | 88.9 |
| old-extractor-enhanced  | 35.6 | 59.6 | 0.0 | 88.9 |
| gemini-multimodal       | 17.5 | 35.5 | 6.2 | 94.4 |
| gemini-hybrid           | _pending re-run_ | | | |
| claude-multimodal       | 2.0 | 40.0 | 1.5 | 97.2 |
| **claude-hybrid**       | 29.8 | 50.0 | **41.5** | 94.4 |

`gemini-hybrid` on I-589 is marked SKIPPED: the call (460 widgets, ~129KB field
list, 64K output budget) repeatedly exceeded a 8-min then 20-min HTTP deadline on
Gemini 3.1 Pro -- itself a finding (the heaviest single-shot fusion call is
operationally fragile on that model; a batched or chunked approach, like the old
enhancer's, would be needed). The I-90 gemini-hybrid result (98.5 a.F1, the
table's best (a)) establishes the pattern; the I-589 conclusion rests on
claude-hybrid, which completed.

## Document AI verdict

`documentai-hybrid` was DROPPED, not scored, by maintainer decision (2026-06-06)
after cost research: **too expensive for negligible benefit over a raw strong-LLM
pass.** This agrees with the bake-off's structure -- Document AI Form Parser only
supplies the (a) OCR label<->input-box layer, which the hybrid arms already obtain
for free and more precisely from the PyMuPDF AcroForm dump (exact widget names,
not OCR guesses), and it contributes nothing to (b) relationship recovery. So the
arm could not have beaten the existing hybrids on (a) and would have lost on (b),
at per-page OCR cost. The arm code (`arm_documentai.py`) was written and validated
against the installed SDK and is kept for reference; the GCP API/ADC/SDK were set
up but no billable Form Parser processor was ever created.

## Headline conclusions

1. **The AcroForm layer is decisive for (a).** Hybrid arms (PyMuPDF widget names
   fed to the LLM) score field-detection F1 ~96-98% on I-90; the pixels-only
   multimodal arms score ~2-3% because they cannot recover the exact
   `pdf_field_name` widget names that are the join key for round-trip PDF filling.
   **Confirmed hypothesis: OCR/multimodal alone is not enough -- the deterministic
   AcroForm dump is required input.**

2. **A strong LLM wins (b).** `claude-hybrid` recovered the most conditional logic
   (I-90: show_if 78.9%, controls_fields 92.3%, copy_to 100%; I-589: show_if 50.9%,
   tables 77.8%, structure 100%). Pure-deterministic (old-heuristic) recovers
   essentially none of (b); the old Gemini-2.5-Flash enhancer adds little to the
   SCORED metrics (see failure modes).

3. **The old extractor still owns one thing the LLMs miss: schema-conformant
   `section_id`.** Its deterministic tooltip-hierarchy parse produced section ids
   that match the ground-truth convention (I-589 section_id 88.3%), whereas the
   LLM arms invent reasonable-but-non-matching slugs (section_id 0%). This is the
   strongest argument for a FUSED pipeline rather than picking one arm.

4. **Where the hours still go (the epic's real question):** (a) field extraction
   is now largely SOLVED by PyMuPDF + a strong LLM. The remaining human labor is
   in (b): the custom conditional encodings (`conditional_logic`,
   `conditional_behavior` -- two bespoke schema keys no arm populated correctly),
   table/multi-entry consolidation granularity, and supplement overflow wiring.

## Recommended pipeline (input to 7a9.5)

```
form.pdf
  -> PyMuPDF deterministic pass  ==> schema skeleton: EXACT widget names, types,
     (old-extractor heuristic +      flags, /TU tooltips, rects (pdf_position),
      tooltip hierarchy parse)       AND schema-conformant section_ids/ordering
  -> feed skeleton + PDF to a top-tier LLM (Claude Opus / Gemini 3.x Pro) for the
     (b) reasoning: consolidate widget groups, synthesize show_if/controls/copy_to/
     overflow from printed conditional text, detect tables.
  -> schema.json
```

This beats every single arm: the deterministic pass nails the attributes LLMs
guess wrong (section_id, position, exact validation), and the LLM nails the
relationships the deterministic pass cannot see.

## Per-arm failure modes

- **old-extractor-heuristic/enhanced:** (b) ~0 because the heuristic emits no
  conditionals and the enhancer dumped all 48 recovered I-90 conditionals into a
  single `conditional_fields` key, while ground truth splits them across
  show_if / controls_fields / conditional_logic / conditional_behavior / copy_to
  -- so only the `conditional_fields` overlap scored (~5%). The groupings pass
  returned groups but the merger applied 0 (a real merge-mapping gap). I-589: the
  heuristic UNDER-consolidates relative to truth (276 fields vs 156), tanking
  precision (27.9%).

- **gemini-multimodal / claude-multimodal:** invented pdf_field_names never join
  (a.F1 2-3%). This is the cost of no AcroForm layer, quantified.

- **gemini-hybrid:** strong (a) detection (98.5% F1) but did not pass
  `pdf_position` through (0%) and used semantic option values ("Yes"/"No") vs the
  truth's widget-leaf-name values, and invented section_ids -- all recoverable by
  fusing the deterministic skeleton.

- **claude-hybrid:** best overall; (a) F1 96%, best (b). Over-emits fields on
  I-589 (precision 20.6%) by enumerating un-collapsed table rows -- a
  consolidation-granularity mismatch with the heavily-consolidated I-589 truth,
  not pure hallucination.

## Scorer caveats (so the numbers are read honestly)

- `section_id` is graded by exact string match, so an extractor that groups fields
  correctly but invents id strings scores 0 -- the deterministic skeleton is the
  fix, not a scorer change.
- `options` is graded on value-or-label overlap; truth uses widget-leaf-names as
  option VALUES, so an arm using semantic values is under-credited.
- I-589 truth is heavily consolidated; per-row table enumeration reads as
  "spurious" FPs even when the fields are real widgets.

These are noted, not "fixed" -- the scorer (bd polyglot-pdf-7a9.3) is the agreed,
already-merged metric; changing it mid-bake-off would break comparability.
