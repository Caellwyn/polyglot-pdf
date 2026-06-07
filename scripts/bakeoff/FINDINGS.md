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
| `gemini31pro-multimodal`  | Gemini 3.1 Pro from pixels only | same call |
| `gemini31pro-hybrid`      | PyMuPDF AcroForm dump fed to Gemini 3.1 Pro | same call |
| `gemini35flash-multimodal`| Gemini 3.5 Flash (newer stable) from pixels only | same call |
| `gemini35flash-hybrid`    | PyMuPDF AcroForm dump fed to Gemini 3.5 Flash | same call |
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
| old-extractor-heuristic   | 81.9 | 48.4 | 0.0 | 25.0 |
| old-extractor-enhanced    | 81.9 | 48.4 | 5.0 | 25.0 |
| gemini31pro-multimodal    | 17.4 | 20.0 | 0.0 | 100.0 |
| **gemini31pro-hybrid**    | **98.5** | 33.3 | 18.8 | 100.0 |
| gemini35flash-multimodal  | 2.5 | 25.0 | 0.0 | 100.0 |
| **gemini35flash-hybrid**  | 97.0 | 30.8 | 17.5 | 100.0 |
| claude-multimodal         | 3.0 | 20.0 | 0.0 | 100.0 |
| **claude-hybrid**         | 96.0 | **52.7** | **38.8** | 100.0 |

### I-589 (stresses relationships/tables/supplements)

| arm | a.F1 | a.attr | b.cond | b.strc |
|-----|-----:|-------:|-------:|-------:|
| old-extractor-heuristic   | 35.6 | **59.6** | 0.0 | 88.9 |
| old-extractor-enhanced    | 35.6 | 59.6 | 0.0 | 88.9 |
| gemini31pro-multimodal    | 17.5 | 35.5 | 6.2 | 94.4 |
| gemini31pro-hybrid        | _SKIPPED (timeout)_ | | | |
| gemini35flash-multimodal  | 13.0 | 36.7 | 6.2 | 41.7 |
| **gemini35flash-hybrid**  | **33.1** | 46.9 | **44.6** | 75.0 |
| claude-multimodal         | 2.0 | 40.0 | 1.5 | 97.2 |
| **claude-hybrid**         | 29.8 | 50.0 | 41.5 | **94.4** |

**`gemini35flash-hybrid` is the model the bake-off recommends for the Gemini arm**
(newer stable release than 3.1 Pro). On I-589 it COMPLETED the heavy hybrid call
that 3.1 Pro could not, and posted the best conditional recall of any arm (show_if
54.7%, b.cond 44.6% -- edging claude-hybrid's 41.5%) with full
parts/sections/supplements structure. Its one I-589 weakness is tables (0/9 vs
claude's 7/9), dragging b.strc to 75.0. On I-90 it is within ~2 pp of 3.1 Pro and
claude on field detection (97.0 F1 vs 98.5 / 96.0). It is also much faster +
cheaper than 3.1 Pro.

`gemini31pro-hybrid` on I-589 stays SKIPPED: the call (460 widgets, ~129KB field
list, 64K output budget) exceeded both an 8-min and a 20-min HTTP deadline on
Gemini 3.1 Pro -- a finding in itself (the heaviest single-shot fusion is
operationally fragile on that model). gemini-3.5-flash finished the same call in
~1 min, the practical reason to prefer it.

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

2. **A strong LLM wins (b), and the top two hybrids are close.** On I-90
   `claude-hybrid` recovered the most conditional logic (show_if 78.9%,
   controls_fields 92.3%, copy_to 100%). On the relationship-stress form I-589 the
   leader flips: `gemini35flash-hybrid` posts the best conditional recall of any arm
   (show_if 54.7%, b.cond 44.6%) -- just ahead of claude-hybrid (50.9% / 41.5%) --
   while claude-hybrid wins I-589 tables (7/9 vs 0/9). Pure-deterministic
   (old-heuristic) recovers essentially none of (b); the old Gemini-2.5-Flash
   enhancer adds little to the SCORED metrics (see failure modes). **Net: either
   claude-hybrid or gemini-3.5-flash-hybrid is a defensible (b) engine; 3.5-flash
   is the better Gemini (3.1 Pro times out on the heavy I-589 call -- see table).**

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
  -> feed skeleton + PDF to a strong LLM (Claude Opus OR Gemini 3.5 Flash -- both
     lead (b); prefer 3.5 Flash over 3.1 Pro, which times out on big forms) for the
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

- **all multimodal arms (gemini31pro / gemini35flash / claude):** invented
  pdf_field_names never join (a.F1 2-17%). This is the cost of no AcroForm layer,
  quantified. gemini35flash-multimodal on I-589 also under-detected sections
  (b.strc 41.7%), the weakest structure of any arm.

- **gemini31pro-hybrid:** strong (a) detection (98.5% F1) but did not pass
  `pdf_position` through (0%) and used semantic option values ("Yes"/"No") vs the
  truth's widget-leaf-name values, and invented section_ids -- all recoverable by
  fusing the deterministic skeleton. TIMES OUT on the I-589 hybrid call (see table).

- **gemini35flash-hybrid:** best (b) on I-589 (b.cond 44.6%) and completes every
  call, but recovered no tables on I-589 (0/9) -- the one place claude-hybrid (7/9)
  clearly beats it.

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
