---
date: 2026-11-17
bead: polyglot-pdf-u0kcc
title: "measure(quality): secretary + validator recall on gemini-3.1-flash-lite vs the 2.5 baselines"
tags: [performance, testing, harness]
---

## Trigger

Bd `polyglot-pdf-bd1zs` (2026-10-21) moved the cheap text tier from
2.5-flash-lite to `gemini-3.1-flash-lite`: `MODEL_LABELING` (secretary +
per-section validator) and `TRANSLATION_VERIFY_BT_MODEL`. The outage fallback
became `gemini-3.5-flash-lite`. Nobody re-measured quality or latency after the
move. This was one independent piece of a post-migration validation (a sibling
session took the Live voice model). Three developer reports were also to be
checked: 25-30s latency spikes on 3.1-flash-lite, MINIMAL thinking still being
billed as output, and 3.5-flash-lite output costing 67% more. Bundled: bd
`polyglot-pdf-nwnys` (scripts/bakeoff drops thinking tokens).

## What shipped

**Verdict: no regression. 3.x lite is equal or better on every quality
measure.** Full numbers are in `scripts/spikes/3p1_lite_revalidation_findings.md`;
the raw data is committed under `scripts/spikes/data/*20261117*`.
- Validator G1 recall: 1.000 (68/68) on both 3.1 and 3.5, against 0.794 for a
  same-day 2.5 control and the 0.853 record.
- Validator clean-corpus precision: 0.97-1.00 on the shipped prompt.
- Judged secretary hallucinations: 1/49 on 3.1, against 5/49 for the control.
- Latency: median ~1.05s, nothing over the 8s timeout, and no 25-30s spikes
  in ~1,100 calls.
- Thinking tokens: 0 under the default config.
- Implicit cache: warms slowly (41% over 98 back-to-back calls, not 96-98%).
- 3.1-flash-lite alone returned some HTTP 429s, which production absorbs by
  falling back to 3.5.
- Spend ~$1.36 (budget ~$3).

**Probe fidelity fix.** Every probe called `generate_content` with its own
stale prompt copy. New `backend/scripts/lite_probe_textai.py::RecordingTextAI`
drives the SHIPPED `TextAIGemini` call: production prompts, content order and
config, with an empty fallback chain. It records the latency, raw reply,
transport error and full usage that the adapter's fail-open path hides. New
flags drive it:
- `probe_secretary_recall --prod-path`
- `probe_secretary_latency --arms prod --repeats`; its default chain is now
  3.1 -> 3.5
- `probe_g1_contradiction_recall --lite-model/--lite-prompt prod/--skip-in-si/--repeats`
- `probe_g1c_tuning --model/--prompts prod/--repeats`
- `translation_gate_probe --bt-only`

The probes now default to Vertex `global`, where the 3.x lite models live. The
validator-rail probe's text client had silently 404'd and fail-opened on 3.1;
it now uses the adapter's own location.

**nwnys:** the four Gemini usage sites in `scripts/bakeoff` now build their
records through `scripts/bakeoff/usage_tokens.py::gemini_usage_tokens`, which
folds thinking into output. `test_bakeoff_usage_tokens.py` pins the folding AND
the complete set of call sites. All four mutations went red: drop the fold, or
revert each site.

**Tests:** `test_lite_probe_textai.py` covers usage + thinking + cache capture,
the error record, per-task isolation under `gather`, and the empty chain. All 5
were mutation-verified. The first draft of the empty-chain test was vacuous: it
used 3.5, which IS the default fallback, so dedup hid the mutation. It was
caught and fixed.

**Judge substitution.** The secretary probe's `claude` CLI judge had an
expired OAuth login. Recall ran `--no-judge`, and one Sonnet subagent graded
all 147 answers blind with the probe's own `JUDGE_PROMPT` rubric.

**Follow-ups filed:**
- `polyglot-pdf-kmfsp`: the G1 NO-GO premise flipped on 3.x lite, so the
  in-SI prose question is open again. This is a product call.
- `polyglot-pdf-dcbxe`: measure the deployed 3.1 429/fallback rate against
  validator window concurrency.
- A note on `polyglot-pdf-jnjj.41` with the cache data.

## Lessons

- **A same-day control arm beats a remembered baseline.** The 2.5 control's
  G1 recall came in at 0.794, below its own June record of 0.853, on the
  identical harness. The schema grew from ~9.5k to ~13.1k tokens, and live
  sampling is noisy. Compared to the record alone, 3.x would have looked
  better than it is; against the control, the gap is clean.
- **A probe's private prompt copy is a deploy-fidelity bug waiting to happen.**
  The secretary probe's prompt predated the shipped kind-A/B/C rubric. Driving
  the real adapter, with a recorder for what fail-open hides, removes the copy
  instead of re-syncing it.
- **When every model makes the same error, suspect the input first.** All three
  models said the mailing "postal code" was unanswered. The render was correct;
  the I-90 has a literal (foreign) *Postal Code* field beside the filled *ZIP
  Code*. It is a wording trap, not a model regression.
- **A test that pins a default can pass vacuously when the test value equals
  the default.** Pick a value the mutation would change.

## Doc freshness

- `docs/standards/validation-delegation.md`: the "0.853 ... not re-measured on
  3.1" sentence was replaced with the 3.x re-measure and a pointer to
  `kmfsp`. Its `*Last updated:*` stamp was deliberately NOT bumped: the doc's
  own note (bd 6dn2n) keeps the stale date as a re-verification signal, and
  one corrected sentence is not that re-verification.
- `docs/standards/ai-models.md` was reviewed and left unchanged; no invariant
  it states changed.

## Files touched

- `backend/scripts/lite_probe_textai.py` (new)
- `backend/scripts/probe_secretary_recall.py`
- `backend/scripts/probe_secretary_latency.py`
- `backend/scripts/probe_g1_contradiction_recall.py`
- `backend/scripts/probe_g1c_tuning.py`
- `backend/scripts/probe_g1b_model_size_bakeoff.py`
- `backend/scripts/probe_validator_rail.py`
- `scripts/spikes/translation_gate_probe.py`
- `scripts/bakeoff/usage_tokens.py` (new)
- `scripts/bakeoff/arm_gemini.py`
- `scripts/bakeoff/arm_documentai.py`
- `scripts/bakeoff/llm_providers.py`
- `backend/tests/unit/test_lite_probe_textai.py` (new)
- `backend/tests/unit/test_bakeoff_usage_tokens.py` (new)
- `scripts/spikes/3p1_lite_revalidation_findings.md` (new)
- `scripts/spikes/data/*20261117*` (27 raw-data files)
- `docs/standards/validation-delegation.md`
