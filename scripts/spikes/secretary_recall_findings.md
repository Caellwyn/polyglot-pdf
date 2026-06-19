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
- **Artifacts:** `scripts/spikes/data/secretary_recall_20260618T190211.csv`
  (every query/answer/sourced_from/judge row verbatim) + `...190211.meta.json`.
  Reproduce: `GEMINI_API_KEY=... PYTHONPATH=... backend/scripts/probe_secretary_recall.py`.
  The probe is NON-DETERMINISTIC (live model sampling) -- exact per-case verdicts
  AND the headline counts vary run to run (observed: hallucination count swung
  2-to-5 across two runs of the same battery). The numbers below are ONE run; the
  STABLE signal is the tier shape + the failure-MODE set, not a precise count. A
  larger battery or multi-seed averaging would be needed to pin a number (a
  follow-up, not this feasibility pass).

## Headline

**Flash-lite reliably FINDS the right fields and rarely makes up values; its real
weakness is current-vs-previous-NAME confusion, plus a tendency to OVER-SHARE
(correct extra values).** The over-sharing is the SAFE failure direction -- an
over-inclusive answer is caught by the principal's verify-back loop; a confident
WRONG value would not be.

| metric (whole battery, n=49; ONE run) | value |
|---|---|
| hit rate (cited >=1 correct field, clarifiers count) | **~0.93** |
| mean grounding recall | **~0.90** |
| mean grounding precision | **~0.78** (over-sharing pulls this down) |
| strict exact-set match | ~0.59 |
| **Sonnet-judged hallucination (made-up/WRONG value)** | **5/49** (varies 2-5 run to run) |
| Sonnet-judged over-inclusion (correct EXTRA value) | **4/49** (varies; ~9 the prior run) |
| confident-wrong (coarse cite+claim signal) | 16/49 (over-counts harm) |
| rendered context size | **~9,500 tokens** (note: ~2x the research-plan estimate) |

## Per-tier characterization (one run -- directional, small N)

| tier | n | recall | precision | hit | synth_ok | disamb_ok | halluc | over_inc |
|---|---|---|---|---|---|---|---|---|
| easy | 5 | 1.00 | 0.87 | 1.00 | 1.00 | 1.00 | 0 | 1 |
| aliasing | 6 | 0.83 | 0.83 | 0.83 | 0.83 | 1.00 | 1 | 0 |
| ambiguous | 10 | 0.77 | 0.68 | 0.80 | 0.90 | 1.00 | 0 | 2 |
| synthesis | 10 | 0.95 | 0.77 | 1.00 | 0.80 | 1.00 | 2 | 1 |
| distant | 9 | 0.92 | 0.93 | 1.00 | 0.89 | 1.00 | 0 | 0 |
| applicability | 9 | 0.93 | 0.80 | 1.00 | 0.78 | 1.00 | 2 | 0 |

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
- **synthesis / applicability:** the tiers that produce most hallucinations --
  multi-field name gathers and "have they answered X" name questions where the
  model confuses current vs previous name (see triage).
- **distant:** good at relate-two-far-apart-fields and at the hidden-vs-empty
  distinction (preparer block correctly read as not-applicable; applicable-but-empty
  fields read as "not answered yet").

## Triage of the flagged cases (honest accounting)

The corrected judge separates harm from over-sharing. Across the two runs, the
hallucinations cluster into THREE stable failure modes (the exact set in any single
run varies with sampling; this run had 5):

**Mode 1 -- current-vs-previous NAME confusion (the dominant, highest-stakes
mode; recurs every run).** When a query targets the previous/green-card name, the
model reports the CURRENT name (or reverses the from/to direction of a name change),
e.g.:
- "What was their full name on the green card?" -> gives the current family name
  (Okafor) instead of the prior one (Eze).
- "Did their name change, and from what to what?" -> inverts the direction.
- "Have they given their previous name?" -> answers with the current name.
This IS the legal-intake risk the bead named ("a confident wrong 'name'"). Not
field-invention -- the model reads the right cluster but mis-assigns which member is
"current" vs "previous." The I-90's own field labels are near-identical across the
two clusters, which is almost certainly the cause. **The #1 target for prompt/context
hardening.**

**Mode 2 -- near-duplicate sibling field (recurs).** "Postal code on their mailing
address?" -> sources the FOREIGN `p1_line6h_postalcode` (empty) instead of the US
`p1_line6f_zipcode` (62704) and claims no value. (Partly a corpus ground-truth
ambiguity -- the query literally says "postal code.")

**Mode 3 -- cross-field inference on a yes/no question (recurs).** "Was an
interpreter used?" -> infers "no" from the unchecked English-proficiency checkbox
while the Part 6 interpreter NAME fields are filled. Fix: steer yes/no questions to
the relevant VALUE fields, not a tangential self-cert checkbox.

**Over-inclusion -- benign (4 this run, ~9 the prior run):** correct values
volunteered beyond the question (e.g. "their last name?" -> current AND previous;
"their email?" -> applicant AND interpreter). Values are right; the model just
over-answers. Caught by verify-back. Whether to suppress is a product call -- a
human secretary volunteering "you also have a previous name on file" may be a
feature.

**Confident-wrong (16, coarse):** the deterministic cite+claim signal. It includes
the hallucinations, most of the over-inclusions, and a few borderline ground-truth
cases. Use the judge's `hallucinated`, not this counter, for the harm read.

## What this suggests

1. **Feasibility: yes, with the verification net.** High recall (~0.90) + a small
   handful of wrong-value cases (2-5 across runs, clustering into 3 nameable failure
   modes) is what the principal/secretary split needs, BECAUSE the principal voices
   answers back for user confirmation. Over-sharing is self-correcting under that
   net. Caveat: the harm count is NOISY at n=49 -- treat feasibility as "promising,
   pending a larger/multi-seed run," not "proven at X%."
2. **The dominant real risk is current-vs-previous NAME disambiguation** (mode 1
   above, every run). Prompt/context work to target: make the current-name vs
   previous/green-card-name clusters unmistakable in the rendered context (the
   I-90's own field labels are near-identical), and for "from what to what"
   name-change questions, pin which field is the FROM and which is the TO. Modes 2
   (us-zip vs foreign-postal sibling) and 3 (yes/no inference from a tangential
   checkbox) are secondary targets.
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
