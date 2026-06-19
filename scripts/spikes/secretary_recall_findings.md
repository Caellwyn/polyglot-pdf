# Secretary Gate 1 (RECALL) -- findings

bd polyglot-pdf-jnjj.26. **Characterization, NOT a GO/KILL.** This is the keystone
feasibility question for the principal/secretary architecture (epic jnjj): can a
cheap model (`gemini-2.5-flash-lite`) answer prose questions about a filled I-90
form well enough to act as the "secretary" that holds the form catalog + values?
The verdict stance (maintainer, 2026-06-18) is to read the numbers with the
existing human-verification net in mind -- the principal voices every secretary
answer back as a verifiable statement and the user confirms through the principal
(never the secretary directly) -- and judge "good enough + CYA," not to auto-fail
on a threshold. (A UI focus indicator exists, but it highlights the next/filled
field, NOT arbitrary fields a secretary answer referenced -- and `sourced_from` is
logged-only, never returned to the principal -- so do NOT count field-focus as a
mitigation for over-inclusive answers unless source ids are later wired through to
drive focus. The verify-back-and-confirm loop is the real net.)

## What was run

- **Secretary model:** `gemini-2.5-flash-lite`.
- **Context:** the REAL I-90 (`form-kits/i-90/schema.json`, 132 fields / 8 parts /
  16 sections) rendered in a SINGLE format -- grouped-by-section -- from a shared
  synthetic fixture (a name-CHANGED applicant with mailing + separate physical
  address, dates, parents, an interpreter, and NO preparer). Format comparison is
  the deferred follow-up bd jnjj.37.
- **Battery:** 49 labeled prose queries across six difficulty tiers (see
  `backend/scripts/secretary_recall_corpus.py`).
- **Scoring (three layers, deliberately separated):**
  - GROUNDING (deterministic): does the answer's `sourced_from` field-id trace
    match the case's expected ids? precision/recall on the id SET + a STRICT
    exact-set flag. Clarifying questions on genuinely-ambiguous queries count as
    hits, not misses.
  - A Sonnet prose JUDGE (`claude-sonnet-4-6`) that gets BOTH the expected-field
    values AND the full form state, so it can tell three things apart:
    **hallucination** (a made-up OR wrong value -- the real harm), **over-inclusion**
    (a CORRECT value from a field beyond what was asked -- benign over-sharing), and
    synthesis/disambiguation quality.
  - CONFIDENT-WRONG (deterministic): a wrong-cite OR a false-absence claim, paired
    with a confident (non-hedging, non-clarifying) assertion. A coarse precision
    signal -- it over-counts harm (see triage); the judge's `hallucinated` is the
    real harm count.
- **Artifacts:** `scripts/spikes/data/secretary_recall_20260618T183519.csv`
  (every query/answer/sourced_from/judge row verbatim) + `...183519.meta.json`.
  Reproduce: `GEMINI_API_KEY=... PYTHONPATH=... backend/scripts/probe_secretary_recall.py`.
  The probe is NON-DETERMINISTIC (live model sampling) -- exact per-case verdicts
  vary run to run; the tier-level shape is stable. The numbers below are one run.

## Headline

**Flash-lite reliably FINDS the right fields and rarely makes up values; its real
weakness is current-vs-previous-NAME confusion, plus a tendency to OVER-SHARE
(correct extra values).** The over-sharing is the SAFE failure direction -- an
over-inclusive answer is caught by the principal's verify-back loop; a confident
WRONG value would not be.

| metric (whole battery, n=49) | value |
|---|---|
| hit rate (cited >=1 correct field, clarifiers count) | **44/49 (0.90)** |
| mean grounding recall | **0.87** |
| mean grounding precision | **0.75** (over-sharing pulls this down) |
| strict exact-set match | ~0.59 |
| **Sonnet-judged hallucination (made-up/WRONG value)** | **2/49** |
| Sonnet-judged over-inclusion (correct EXTRA value) | **9/49** |
| confident-wrong (coarse cite+claim signal) | 17/49 (over-counts harm) |
| rendered context size | **~9,500 tokens** (note: ~2x the research-plan estimate) |

## Per-tier characterization (one run -- directional, small N)

| tier | n | recall | precision | hit | synth_ok | disamb_ok | halluc | over_inc |
|---|---|---|---|---|---|---|---|---|
| easy | 5 | 1.00 | 0.87 | 1.00 | 1.00 | 1.00 | 0 | 1 |
| aliasing | 6 | 0.67 | 0.67 | 0.67 | 0.83 | 1.00 | 0 | 0 |
| ambiguous | 10 | 0.87 | 0.72 | 0.90 | 0.90 | 1.00 | 0 | 3 |
| synthesis | 10 | 0.93 | 0.77 | 1.00 | 0.80 | 1.00 | 2 | 1 |
| distant | 9 | 0.89 | 0.77 | 0.89 | 0.89 | 1.00 | 0 | 2 |
| applicability | 9 | 0.85 | 0.76 | 0.89 | 1.00 | 1.00 | 0 | 2 |

(Per-tier N is small -- read the rates as directional, not precise. The verbatim
CSV rows are the real evidence; the disambig_ok rate of ~1.0 is the strongest
signal -- the model handles genuine ambiguity well, either covering candidates or
clarifying.)

Reading the tiers:
- **easy / aliasing:** strong recall. Aliasing leans on `help.instructions`
  (present on 132/132 fields) -- e.g. "green card name" resolves to the
  previous-name cluster.
- **ambiguous:** recall high, disambiguation excellent (~1.0) -- the model covers
  the candidate set or names each. Precision dips from benign over-inclusion.
- **synthesis:** the tier that produced BOTH hallucinations this run -- multi-field
  name gathers where the model confused current vs previous name (see triage).
- **distant / applicability:** good at relate-two-far-apart-fields and at the
  hidden-vs-empty distinction (preparer block correctly read as not-applicable;
  applicable-but-empty fields read as "not answered yet").

## Triage of the flagged cases (honest accounting)

The corrected judge separates harm from over-sharing:

**Hallucinations -- the cases that matter (2):** BOTH are the SAME failure mode --
current-vs-previous (green-card) NAME confusion, in the synthesis tier:
1. "What was their full name on the green card?" -> reported the green-card family
   name as the CURRENT family name (the issued-card name) instead of the prior
   name. A wrong value, not a made-up one.
2. "Did their name change, and from what to what?" -> got the DIRECTION backwards
   (stated changed-from = the current name). The values are real; the
   from/to mapping is inverted.
This is exactly the legal-intake risk the bead called out ("a confident wrong
'name'"). It is NOT field-invention -- the model reads the right cluster but
mis-assigns which member is "current" vs "previous." It is also the highest-stakes
error class on this form and the clearest target for prompt/context hardening
(label the current-name vs previous-name groups more explicitly; the I-90's own
field names are nearly identical across the two clusters).

**Over-inclusion -- benign (9):** correct values volunteered beyond the question
(e.g. "what's their last name?" -> current AND previous; "their email?" ->
applicant AND interpreter). Values are right; the model just over-answers. Caught
by verify-back. Whether to suppress this is a product call -- a human secretary
volunteering "you also have a previous name on file" may be a feature.

**Confident-wrong (17, coarse):** the deterministic cite+claim signal. It includes
the 2 hallucinations, most of the 9 over-inclusions, and a few borderline
ground-truth cases (e.g. "postal code" literally matching the foreign
`p1_line6h_postalcode` field rather than the US `zipcode` the corpus expected).
Use the judge's `hallucinated` (2), not this counter, for the harm read.

## What this suggests

1. **Feasibility: yes, with the verification net.** High recall + only 2
   wrong-value cases (both a single, nameable failure mode) is what the
   principal/secretary split needs, BECAUSE the principal voices answers back for
   user confirmation. Over-sharing is self-correcting under that net.
2. **The one real risk is current-vs-previous NAME disambiguation.** Both
   hallucinations are this. Prompt/context work to target: make the current-name
   vs previous/green-card-name clusters unmistakable in the rendered context (the
   I-90's own field labels are near-identical), and for "from what to what"
   name-change questions, pin which field is the FROM and which is the TO.
3. **Over-inclusion is tunable, but may be desirable.** "Answer only what was
   asked" would lift precision; whether to is a product call.
4. **Context size is ~2x the plan's estimate (~9.5k vs 2.7-5.9k tokens).** Feeds
   Gate 2 (jnjj.27): size the explicit-cache minimum + per-call cost against
   ~9.5k. (chars/4 estimate; tiktoken not installed -- a true count may differ.)

## Caveats (every number is an UPPER BOUND)

- **Two stacking inflation sources:** (a) the fixture VALUES are clean and
  coherent, unlike messy half-filled mid-correction real state; (b) the QUERIES are
  hand-authored to map onto fields, more on-distribution than spontaneous speech.
  Both push recall up. Real-world recall will be lower.
- **NON-DETERMINISTIC:** live-model sampling means per-case verdicts vary run to
  run (e.g. an earlier run flagged a postal/zip miss and an interpreter-inference
  miss that this run did not). The tier-level shape and the
  current-vs-previous-name failure mode reproduce; specific case IDs do not.
- **Single context format** (grouped-by-section). A different format could move
  these numbers materially -- the explicit follow-up (jnjj.37).
- **Catalog gaps vs the plan:** the I-90 schema has NO `spoken_aliases` and no
  `section_label` field populated (both TS-types-only). The renderer derives the
  section label by joining `section_id` -> `sections[].label` and omits aliases;
  aliasing recall rests on `help.instructions` (132/132) alone.
- **Applicability (`shown`) is a synthetic fixture map**, not computed from the
  real `show_if`/`controls_fields` logic; the whole Part-7 preparer block is hidden
  so the "self-prepared" context is clean.
- The probe ABORTS on a secretary API/parse failure (no silent metric corruption);
  `--allow-errors` scores anyway and records the error list in meta.json.
