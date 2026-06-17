# G1 keystone probe -- flash-lite contradiction recall vs in-SI check

**Bead:** polyglot-pdf-jnjj.5 (GATES Pillar B: B3/B4/B5/B1)
**Date:** 2026-06-17
**Verdict:** **NO-GO on removing the in-SI check.** Keep a minimal inline check;
do NOT delete the SI ADDRESS CONSISTENCY prose. (Exit criterion 3, NO-GO branch.)

---

## What was measured

Three arms scored on a labeled set of 80 cases (34 contradiction + 46 clean),
each case a contract-2 minimal client-state payload over REAL I-90 address/date
fields:

| arm | recall | precision | TP | FN | FP | TN | strict recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| **in_si_check** (incumbent, `gemini-2.5-flash` + verbatim in-SI prose) | **1.000** | 1.000 | 34 | 0 | 0 | 46 | 0.853 |
| **flash_lite** (proposed, `gemini-2.5-flash-lite` + dedicated prompt) | **0.853** | 1.000 | 29 | 5 | 0 | 46 | 0.647 |
| **no_check** (floor) | 0.000 | n/a | 0 | 34 | 0 | 46 | 0.000 |

- **Recall** = fraction of the 34 real contradictions the arm flagged
  (case-level: any flag overlapping the implicated fields). This is the
  safety-relevant number -- did the check catch the contradiction at all.
- **Precision** = of the cases the arm flagged, the fraction that were real
  contradictions. Both live arms had ZERO false positives on the 46 clean cases
  (including the deliberate precision traps: US territories, coherent foreign
  addresses, two-distinct-address blocks, sparse state).
- **strict recall** = the stricter scoring where the arm's flagged field SET must
  exactly equal the ground-truth set (not just overlap). Reported for context;
  the gate uses case-level recall.

Raw per-case results + run config:
`scripts/spikes/data/g1_contradiction_recall_20260617T121146.csv` (+ `.meta.json`).
Reproduce: `GEMINI_API_KEY=... PYTHONPATH=. python backend/scripts/probe_g1_contradiction_recall.py`.

(An earlier run -- `..._20260617T114232.*` -- used an invalid placeholder ZIP
"00000" in the city_state cases, which let the in_si arm "detect" via a spurious
ZIP-vs-state path and credited the wrong capability; the city_state ZIPs were
corrected to valid state-matching ZIPs and the probe re-run, per a pre-PR
fresh-eyes finding. The corrected run is the one reported here. flash_lite recall
rose 0.735 -> 0.853 on the cleaner cases; the NO-GO is unchanged.)

**Run-to-run variance:** flash-lite is non-deterministic, so absolute per-arm
recall carries sampling noise of a few cases (between the two runs, flash_lite's
zip_state misses landed on different cases though the count held at 12/14). The
GATE signal -- flash_lite recall strictly below the incumbent's perfect 1.000 --
is robust to that noise; a single re-run will not flip a 0.853-vs-1.000 gap to GO.

## GO/NO-GO (exit criterion 3)

> GO iff flash-lite recall >= in-SI check recall at acceptable precision; else B
> is revised (keep a minimal inline check, do NOT remove SI prose).

**flash_lite recall 0.853 < in_si_check recall 1.000 -> the GO condition fails ->
NO-GO.** Precision is not the problem (flash_lite is perfect on the clean set);
recall is. The incumbent in-SI check, run at the same boundary over the same full
state, caught every contradiction; the cheap validator missed 5 of 34 (~15%).
(Both arms received the same explicit date-sanity instruction; the in-SI arm's
prose is the verbatim ADDRESS CONSISTENCY block from config.py:379-385, with that
date-sanity line and a JSON-output line added identically to BOTH arms so the
comparison stays symmetric -- see the probe's IN_SI_PROMPT comment.)

**Miss honesty:** all 5 flash_lite misses had `n_flagged=0` (an empty verdict),
not a mislabeled flag. The probe's fail-open path returns an empty `conflicts`
list on a JSON-parse error or API exception too, and it does not persist a
parse/error marker to the CSV -- so the artifact alone cannot prove an empty
verdict was a genuine "no contradiction found" rather than a swallowed error.
This does not threaten the NO-GO: a swallowed error would only DEFLATE flash_lite
recall, making the (already-failing) gate more conservative, never produce a
wrongful GO. The live run showed no parse/error log warnings during the misses.

Removing the in-SI prose and delegating ENTIRELY to flash-lite would let ~15% of
the contradiction classes this corpus covers pass unchecked -- a real correctness
regression against the incumbent. So: **the in-SI ADDRESS CONSISTENCY prose
(jnjj.13 / B1) MUST NOT be removed on this evidence.**

## Where flash_lite fails (recall by class)

| class | flash_lite | in_si_check |
|---|---:|---:|
| zip_state (ZIP not in stated state) | 12/14 | 14/14 |
| **state_country (US state + foreign country)** | **2/5** | 5/5 |
| province_us (foreign province + US state) | 5/5 | 5/5 |
| city_state (US city not in stated state) | 4/4 | 4/4 |
| future_dob (DOB in the future) | 3/3 | 3/3 |
| admission_dob (admitted before born) | 3/3 | 3/3 |

The failure is **concentrated**: 3 of the 5 misses are `state_country` (e.g.
mailing state "New York" with mailing country "Canada"); the other 2 are
zip_state. On the state_country misses flash_lite returned an EMPTY conflict list
-- it did not mislabel the fields, it genuinely did not notice the
state-vs-country contradiction. zip_state, the canonical and most-common class,
holds up well (12/14). The other classes (province_us, city_state, the two date
classes) are at ceiling, but the corpus has too few of each to read precisely.

**Promptability note (does NOT change the verdict).** The state_country prompt
line ("a US state filled together with a foreign country") was explicit, yet
flash-lite still missed it -- so this is at least partly a model-capability gap,
not just a wording oversight. A future B3 prompt iteration MIGHT recover some of
these (e.g. by asking the model to first classify each address block as
US-vs-foreign before checking), but the gate is decided on measured recall as it
stands, and a prompt that has to be hand-tuned to a known failure set is itself a
fragility signal. Re-running this probe is the cheap way to test any B3 prompt
revision before trusting it.

## Corpus provenance (exit criterion 1 -- stated, not fudged)

The corpus is **SYNTHETIC INJECTION over REAL I-90 field structure**, NOT real
user transcripts. There is no captured-transcript corpus for this project: the
demo is pre-pilot and the backend logs NO field values (PII policy), so there is
nothing to mine. Every case is hand-authored in `backend/scripts/g1_corpus.py`.
The field IDs, spoken names, and types are real (verbatim from
`form-kits/i-90/schema.json`, Parts 1/6/7 address + date clusters); the values
and the contradictions are fabricated.

**Bias direction:** synthetic injection is cleaner and more on-distribution than
the messy, half-filled, mid-correction state a real voice session produces.
Per the bead's own warning, **read every recall number as an UPPER BOUND** on
real-world recall, not an estimate of it. That makes the NO-GO STRONGER, not
weaker: flash-lite already falls short of the incumbent on the easy synthetic
set, so it will not do better on harder real data.

## Comparison fairness (exit criterion 2 -- bias addressed, residual recorded)

The bead flagged a structural bias: in production, arm (i) (in-SI check) fires
mid-conversation with only the fields filled SO FAR, while arm (ii) (flash_lite)
fires at a section/form boundary over FULL state. A naive static-set comparison
would hand arm (ii) more evidence and bias the result toward GO.

**Removed in this probe:** both live arms were evaluated at the SAME boundary
over the SAME full-state payload. The comparison isolates "which model+prompt
detects contradictions better," not "who saw more fields." (And the bias would
have favored GO -- yet flash_lite still lost, so the controlled comparison only
reinforces the NO-GO.)

**Residual bias recorded (not eliminated, by design):**
1. In production the in-SI check ALSO has the live conversational/audio channel
   and the user's own confirmations; arm (i) here is a text-only proxy
   (`gemini-2.5-flash`, the 2.5 voice tier's text sibling) given the verbatim
   prose. The proxy is faithful to the DETECTION DECISION (made on the
   transcript), but it does not capture any extra signal the audio turn carries.
2. In production the in-SI check fires after EACH address-cluster field, not once
   at the boundary -- more shots on goal. The boundary-only evaluation here is
   the harder setting for the incumbent, so it understates the incumbent's
   real-world recall and again favors GO.

Both residuals push toward GO, and GO still failed. The NO-GO is robust to them.

## Consequence for the epic

- **B1 (jnjj.13, remove ADDRESS CONSISTENCY prose): BLOCKED by this NO-GO.** Do
  not remove the SI prose. The prose stays as the primary contradiction check.
- **B3/B4/B5 (the flash-lite validator service, triggers, steering):** NOT
  pointless -- flash_lite at perfect precision and 0.853 recall is a useful
  SECOND, defense-in-depth net at section/form boundaries (it catches things the
  per-field in-SI check might miss, at zero false-positive cost). But it is an
  ADDITION to the in-SI check, not a REPLACEMENT for it. The epic's Pillar B
  framing ("so the LIVE voice model no longer has to carry the in-SI check") does
  NOT survive this gate; B ships as belt-and-suspenders, or is rescoped.
- **Token-cost implication:** the SI-reduction win attributed to deleting the
  ADDRESS CONSISTENCY prose does not materialize (the prose is ~6 lines / a few
  hundred chars; it stays). The bigger SI savings live in the JIT/manifest work
  (Pillar A), which this gate does not touch.

This is a maintainer-facing **product-direction** input (B's core premise was
"replace the in-SI check"); the NO-GO is recorded here and surfaced in the PR
merge report, but the rescope of B (addition vs replacement) is the maintainer's
call to confirm.
