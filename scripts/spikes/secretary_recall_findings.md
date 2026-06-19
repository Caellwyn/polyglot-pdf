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
both are field-disambiguation / reasoning errors over fields that WERE in the
rendered context (a wrong sibling field, and a wrong inference from a real
checkbox), not invented ids.

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
   (Caveat: this is also a borderline GROUND-TRUTH case -- the query literally says
   "postal code," and `p1_line6h_postalcode` IS spoken "mailing postal code," so the
   model's literal match is defensible; the corpus expected the US-applicant
   domain-aliasing answer "zip = postal code." Read this as much a corpus-design
   ambiguity as a model error.)
2. `app_interpreter_used` -- "was an interpreter used?" The model sourced
   `p5_checkbox1a` (a REAL field: spoken "I can read and understand English") and
   asserted "no interpreter, the applicant can read and understand English," while
   the Part 6 interpreter name fields were filled (Maria Garcia). The single
   hallucination -- but NOT an invented id: it is a REASONING error. The model
   inferred "no interpreter needed" from the English-proficiency self-cert checkbox
   and ignored the filled interpreter block. (Earlier drafts of this doc wrongly
   called `p5_checkbox1a` non-existent; it is real and was in the rendered context.
   The fix is therefore NOT a "cite only ids in context" guard -- that would not
   have caught it -- but making the Part 5 English-proficiency vs Part 6
   interpreter-used relationship explicit, or instructing the model to check the
   interpreter NAME fields directly for an interpreter-used question.)

**Benign over-inclusion (cited extra CORRECT fields; judge ok):**
`amb_their_name`, `syn_name_change_summary`, `dist_mailing_vs_physical`,
`dist_born_abroad`, `dist_full_legal_history`, `app_preparer_used`.

**Ambiguous-but-correct over-inclusion (1):** `amb_last_name` -- "what's their last
name?" returned current AND previous family name (both correct values); the user
asked only for the current one. Judge flagged synthesis_ok=0 for over-retrieval.
(This is the 9th confident-wrong case -- precision noise, not harm.)

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
2. **The two real risks are field-DISAMBIGUATION / REASONING errors, not
   invention.** Neither truly-wrong case is a hallucinated id -- both cite REAL
   fields. `alias_zip_mailing` picked a wrong sibling field (us-zip vs foreign
   postal -- and is partly a corpus-ground-truth ambiguity). `app_interpreter_used`
   is a reasoning error (inferred "no interpreter" from a real English-proficiency
   checkbox, ignoring the filled interpreter block). Prompt/context work to target:
   make near-duplicate fields (us-zip vs foreign-postal) more distinguishable in
   the rendered context, and for cross-field inference questions ("was an
   interpreter used?") steer the model to check the relevant VALUE fields directly
   rather than a tangential self-cert checkbox. A "cite only ids in context" guard
   would NOT have helped here (both ids were in context).
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
  shown/hidden but the specific hidden set is hand-authored. NOTE the fixture
  hides the preparer block INCOMPLETELY -- 12 Part-7 fields are marked hidden but
  ~7 secondary ones (unit type, province, postal, the preparer checkboxes, the
  signature field) default to shown=true. So the applicability tier's "self
  prepared" context is mixed, not cleanly hidden, which slightly inflates that
  tier's difficulty (e.g. `app_preparer_used` sourced a leaked
  `p7_line8a_signatureofpreparer`). A cleaner fixture (hide the WHOLE Part-7
  block) would be a fairer applicability test.
- **Small per-tier N** (5-10). Tier rates are directional; the verbatim CSV rows
  are the primary evidence.
- The `confident_wrong` counter in the probe is a coarse precondition flag
  (wrong-cite AND asserts-value); use the judge's `hallucinated` + this triage for
  the real harm count (1 hallucination, 2 truly-wrong).
