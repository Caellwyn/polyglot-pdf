# Secretary Gate 1 (RECALL) -- findings

bd polyglot-pdf-jnjj.26. **Characterization, NOT a GO/KILL.** This is the keystone
feasibility question for the principal/secretary architecture (epic jnjj): can a
cheap model (`gemini-2.5-flash-lite`) answer prose questions about a filled I-90
form well enough to act as the "secretary" that holds the form catalog + values?
The verdict stance (maintainer, 2026-06-18) is to read the numbers with the
existing human-verification net in mind -- the principal voices every secretary
answer back as a verifiable statement, the user confirms through the principal
(never the secretary directly), and the UI focus indicator shows which field is
referenced -- and judge "good enough + CYA," not to auto-fail on a threshold.

## What was run

- **Secretary model:** `gemini-2.5-flash-lite`.
- **Context:** the REAL I-90 (`form-kits/i-90/schema.json`, 132 fields / 8 parts /
  16 sections) rendered in a SINGLE format -- grouped-by-section -- from a shared
  synthetic fixture (a name-changed applicant with mailing + separate physical
  address, dates, parents, an interpreter, and NO preparer). Format comparison is
  the deferred follow-up bd jnjj.37.
- **Battery:** 49 labeled prose queries across six difficulty tiers (see
  `backend/scripts/secretary_recall_corpus.py`).
- **Scoring:** deterministic GROUNDING (does the answer's `sourced_from` field-id
  trace match the case's expected ids?) + a Sonnet prose JUDGE
  (`claude-sonnet-4-6`) for synthesis / disambiguation / hallucination.
- **Artifacts:** `scripts/spikes/data/secretary_recall_20260618T170938.csv`
  (every query/answer/sourced_from/judge row verbatim) +
  `...170938.meta.json`. Reproduce:
  `GEMINI_API_KEY=... PYTHONPATH=. <main-venv-python> backend/scripts/probe_secretary_recall.py`.

## Headline

**Flash-lite reliably FINDS the right fields and almost never makes up values; its
weakness is OVER-RETRIEVAL (low precision), not fabrication.** That is the safe
failure direction for this architecture: an over-inclusive answer is caught by the
principal's verify-back; a confident *fabrication* would not be. There was exactly
**1 hallucination in 49 cases**, and **2 truly-wrong answers** total (see below) --
both on fields outside the rendered context's clean mapping.

| metric (whole battery, n=49) | value |
|---|---|
| hit rate (cited >=1 correct field) | **47/49 (0.96)** |
| mean grounding recall | **0.92** |
| mean grounding precision | **0.81** (the weak spot: over-inclusion) |
| strict exact-set match | 29/49 (0.59) |
| Sonnet-judged hallucination | **1/49** |
| truly-wrong answers (see triage) | **2/49** |
| rendered context size | **~9,461 tokens** (note: ~2x the research-plan estimate) |

## Per-tier characterization

| tier | n | recall | precision | strict | hit | synth_ok | disamb_ok | halluc |
|---|---|---|---|---|---|---|---|---|
| easy | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0 |
| aliasing | 6 | 0.83 | 0.83 | 0.83 | 0.83 | 0.83 | 1.00 | 0 |
| ambiguous | 10 | 0.97 | 0.75 | 0.50 | 1.00 | 0.60 | 0.80 | 0 |
| synthesis | 10 | 0.98 | 0.79 | 0.50 | 1.00 | 0.90 | 0.90 | 0 |
| distant | 9 | 0.94 | 0.85 | 0.56 | 1.00 | 0.89 | 1.00 | 0 |
| applicability | 9 | 0.80 | 0.71 | 0.44 | 0.89 | 0.78 | 0.89 | 1 |

(Per-tier N is small for the hard tiers -- read the rates as directional, not
precise. The verbatim rows in the CSV are the real evidence.)

Reading the tiers:
- **easy / aliasing:** strong. Aliasing (prose != spoken_name, leaning on
  `help.instructions`) worked -- e.g. "green card name" -> the previous-name
  cluster. The one aliasing miss is the zip/postal confusion below.
- **ambiguous / synthesis:** recall ~perfect, precision drops because the model
  ADDS related-but-unrequested fields (e.g. "what's their last name?" -> returns
  current AND previous family name). The values are correct; it over-answers.
- **distant:** good at the relate-two-far-apart-fields task (mailing-vs-physical,
  born-abroad), though one case ("admitted after born?") gave the date without
  doing the comparison.
- **applicability:** the hardest tier. The hidden-vs-empty distinction mostly
  worked (correctly said preparer = self-prepared/not-applicable; current middle
  name = "not answered yet"), but it produced the one real hallucination.

## Triage of the flagged cases (honest accounting)

The raw `confident_wrong` counter (9/49) OVER-counts harm: it fires whenever the
answer cites a field outside the expected set AND asserts a value. Most of those
are benign over-inclusion (judge: "ok" / "not incorrect"). The honest split:

**Truly wrong (2) -- the cases that matter:**
1. `alias_zip_mailing` -- "postal code on their mailing address?" The model
   sourced `p1_line6h_postalcode` (the FOREIGN postal-code field, empty) instead of
   `p1_line6f_zipcode` (the US zip, 62704) and answered "not entered yet." A
   wrong-but-plausible sibling field -> a confident wrong "not answered."
2. `app_interpreter_used` -- "was an interpreter used?" The model sourced a
   NON-EXISTENT field id (`p5_checkbox1a`) and asserted "no interpreter," when the
   interpreter name fields were filled (Maria Garcia). The single hallucination,
   and the only answer that asserts a flatly false fact.

**Benign over-inclusion (cited extra CORRECT fields; judge ok):**
`amb_their_name`, `syn_name_change_summary`, `dist_mailing_vs_physical`,
`dist_born_abroad`, `dist_full_legal_history`, `app_preparer_used`.

**Disambiguation soft-spots (correct values, weak handling of ambiguity):**
- `amb_country` -- "what country is on file?" omitted country-of-birth, named only
  the two address countries (didn't surface all three candidates).
- `amb_middle_name` / `app_middle_vs_previous_middle` -- handled current vs
  previous middle name but didn't clearly attribute which is which.
- `syn_physical_addr` -- dropped the zip from a read-back (recall miss).

## What this suggests

1. **Feasibility: yes, with the verification net.** Near-perfect hit rate + ~0
   fabrication is exactly what the principal/secretary split needs, BECAUSE the
   principal voices answers back for user confirmation. Over-inclusion is the
   dominant error and it is self-correcting under that net (the user hears the
   extra detail and ignores/corrects it).
2. **The two real risks are field-DISAMBIGUATION errors, not invention.** Both
   truly-wrong cases are the model picking a wrong sibling field (zip vs foreign
   postal; a hallucinated checkbox). Prompt/context work to target: make
   near-duplicate fields (us-zip vs foreign-postal; the yes/no applicability
   checkboxes) more distinguishable in the rendered context, and instruct the
   model to cite ONLY ids that appear in the context (the invented `p5_checkbox1a`
   would have been caught by a "must exist in context" rule).
3. **Precision is tunable.** "Answer ONLY what was asked; do not volunteer related
   fields" in the secretary prompt would lift precision/strict-match; whether that
   is desirable is a product call (a real secretary volunteering "you also have a
   previous name on file" may be a feature, not a bug).
4. **Context size is ~2x the plan's estimate (~9.5k vs 2.7-5.9k tokens).** Feeds
   Gate 2 (jnjj.27): the explicit-cache minimum and per-call cost should be sized
   against ~9.5k, not ~5k. (Estimate is chars/4; tiktoken was not installed -- a
   true count may differ.)

## Caveats (every number is an UPPER BOUND)

- **Two stacking inflation sources:** (a) the fixture VALUES are clean and
  coherent, unlike messy half-filled mid-correction real state; (b) the QUERIES are
  hand-authored to map onto fields, more on-distribution than spontaneous speech.
  Both push recall up. Real-world recall will be lower.
- **Single context format** (grouped-by-section). A different format could move
  these numbers materially -- that is the explicit follow-up (jnjj.37).
- **Catalog gaps vs the plan:** the I-90 schema has NO `spoken_aliases` and no
  `section_label` field populated (both are in the TS types only). The renderer
  derives the section label by joining `section_id` -> `sections[].label` and omits
  aliases. Aliasing recall here therefore rests on `help.instructions` (132/132)
  alone, NOT on aliases.
- **Applicability (`shown`) is a synthetic fixture map**, not computed from the
  real `show_if`/`controls_fields` logic; it models how the frontend tracks
  shown/hidden but the specific hidden set is hand-authored.
- **Small per-tier N** (5-10). Tier rates are directional; the verbatim CSV rows
  are the primary evidence.
- The `confident_wrong` counter in the probe is a coarse precondition flag
  (wrong-cite AND asserts-value); use the judge's `hallucinated` + this triage for
  the real harm count (1 hallucination, 2 truly-wrong).
