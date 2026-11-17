# 3.x flash-lite re-validation -- secretary + validator + back-translate

**Bead:** polyglot-pdf-u0kcc (follow-up to bd polyglot-pdf-bd1zs, the 2026-10-21
move of `MODEL_LABELING` and `TRANSLATION_VERIFY_BT_MODEL` to
`gemini-3.1-flash-lite`). **Date:** 2026-11-17. **SDK:** google-genai 2.8+
(post-cutover). **Endpoint:** Vertex, project `polyglot-demo-aa709`, location
`global` (the 3.x lite models 404 at `us-central1`). **Spend:** ~$1.36 measured
from the runs' own usage records (budget ~$3, cap $6).

## Question

The lite text tier moved models and nobody re-measured it. Does
`gemini-3.1-flash-lite` (the default) or `gemini-3.5-flash-lite` (the
`TextAIGemini` outage fallback) regress against the 2.5 baselines on:
validator contradiction recall and precision, secretary answer quality,
latency against the shipped deadline/timeout, thinking-token billing, and
implicit-cache hit rate? Plus a spot check of the back-translation leg of the
translation gate.

## Verdict: NO REGRESSION -- 3.x lite is equal or better on quality

| | 2.5 baseline (record) | 2.5-flash-lite **same-day control** | **3.1-flash-lite** | **3.5-flash-lite** |
|---|---|---|---|---|
| G1 contradiction recall (34 cases x2) | 0.853 | 0.794 (54/68) | **1.000 (68/68)** | **1.000 (68/68)** |
| G1 precision (46 clean x2) | 1.000 | 0.964 (2 FP) | **1.000** | **1.000** |
| Clean-corpus precision, shipped prompt @20 / @40 | -- | 0.914 / 0.851 | **0.970 / 1.000** | **1.000 / 1.000** |
| Clean-corpus precision, g1c tuned prompt @20 / @40 | 0.958 / 0.967 | 1.000 / 0.930 | 1.000 / 1.000 | 1.000 / 1.000 |
| Clean-corpus recall, shipped prompt @20 / @40 | -- | 1.000 / 0.952 | 1.000 / 1.000 | 1.000 / 1.000 |
| Secretary hallucinations (judged, /49) | 5 (range 2-5) | 5 | **1** | **2** |
| Secretary grounding recall / precision | 0.89 / 0.81 | 0.901 / 0.805 | 0.912 / **0.871** | 0.912 / 0.807 |
| Secretary latency p50 / p90 | ~0.95s / 1.2-1.4s | 0.91s / 1.12s | 1.06s / 1.28s | 1.05s / 1.30s |
| Secretary calls over 2.5s deadline / 8s timeout | -- | 2/98 / 0 | 2/147 / 0 | 2/147 / 0 |
| Thinking tokens billed (default config) | -- | 62 total | **0** | **0** |
| Implicit-cache hit rate (back-to-back loop) | 96-98% | 18% | 41% | 42% |

The headline: the cheap validator on 3.x lite caught **every** labeled
contradiction on the G1 corpus, twice over. The 2.5 lite model missed 5 of 34
in June and 14 of 68 today. The judged secretary hallucination count fell from
5 to 1 out of 49.
The costs of the move: the 3.x models are ~0.15s slower at the median, and they
cost ~2.6x more per secretary call than 2.5-flash-lite. That cost is still below
`gemini-2.5-flash`, which is what deployed secretary/validator calls actually ran
on before bd1zs (`MODEL_LABELING` was never pinned).

No regression bead was filed: nothing regressed. The three follow-ups below are
filed or noted.

## What was run (method)

**Deploy fidelity was the main fix to the probes.** Every probe still called
`generate_content` directly with its OWN copy of the prompt. The secretary probe's
copy predates the shipped kind-A/B/C rubric, so it measured a different system.
New `backend/scripts/lite_probe_textai.py::RecordingTextAI` is a `TextAIGemini`
on Vertex with an EMPTY fallback chain, so one model is measured per arm. It
records each call's latency, raw reply, error type, and the full usage. The
usage covers `thoughts_token_count` and `cached_content_token_count`, which the
adapter's fail-open path hides. The probes drive the **shipped** call through it:

- secretary: `TextAIGemini.ask()`, which is production `SECRETARY_SI` + `render_static_catalog`
  stable prefix + `render_values_tail` fresh tail, no `thinking_config`
  (`probe_secretary_recall.py --prod-path`, `probe_secretary_latency.py --arms prod`);
- validator: `render_validator_payload()` (shipped `CONTRADICTION_SI`) into
  `TextAIGemini.validate()` (`probe_g1_contradiction_recall.py --lite-prompt prod`,
  `probe_g1c_tuning.py --prompts prod`);
- back-translate: `TextAIGemini.back_translate()` (`translation_gate_probe.py --bt-only`).

**A same-day 2.5-flash-lite control arm runs the identical harness**, so model
differences are not confounded with harness or schema drift. That drift is
real: today's I-90 catalog is ~13.1k prompt tokens, against ~9.5k in June, after
the v2 migration and translations. The 2.5 control's G1 recall (0.794) landing
below its June record (0.853) is that drift plus sampling noise. That is why the
3.x numbers are compared to the control first and to the record second.

**Inputs.** No kit is tracked in git (CLAUDE.md scar #10). The I-90 schema the
probes read was restored as an UNTRACKED scratch copy from its last tracked
version (`a208b45f0^:form-kits/i-90/schema.json`) and is not committed. The G1
corpus (80 cases) and the g1b clean answer-key corpus (wf3q) are the existing
labeled sets. Sizes 20/40 are the per-section window sizes; 132 (end-of-form)
is the 2.5-pro pass, not the lite tier, so it was not run.

**Runs (all serial except g1c at concurrency 6):**

| run | calls | artifact (`scripts/spikes/data/`) |
|---|---|---|
| secretary latency, prod arm, 3.1 x2 passes / 3.5 x2 / 2.5 x1 | 98 / 98 / 49 | `secretary_latency_20261117T133019` / `T133216` / `T133318` |
| G1 recall, prod prompt, x2 repeats, per model | 160 each | `g1_contradiction_recall_20261117T133542` (3.1) / `T133752` (3.5) / `T134008` (2.5) |
| g1c clean corpus, prod + tuned prompts, sizes 20/40, x2 | 260 each | `g1c_precision_20261117T134110` (3.1) / `T134202` (3.5) / `T134248` (2.5) |
| secretary recall, prod path, 49 queries | 49 each | `secretary_recall_prod_<model>_20261117T*` |
| secretary judge (blind, all 147 answers) | -- | `secretary_recall_judge_20261117.csv` |
| back-translate spot check, es + zh gold + plants | 2 each | `translation_bt_spotcheck_20261117T214849Z` |

**Judge substitution, disclosed.** The secretary probe's built-in judge shells
out to the `claude` CLI, and that CLI's login had expired ("OAuth session
expired"). The recall runs therefore used `--no-judge`. The deterministic
grounding and confident-wrong layers are unaffected. The hallucination and
over-inclusion layer was then graded by ONE Sonnet subagent. It used the
probe's own `JUDGE_PROMPT` rubric on all 147 answers, shuffled and stripped of
model identity, and only then were they unblinded. One judge, one standard,
blind: the cross-model comparison is fair. The absolute counts are comparable
to June's CLI-Sonnet judge but not identical in harness.

## Findings in detail

### 1. Validator recall and precision -- better, not worse

- **G1 (80-case keystone corpus):** both 3.x models scored recall 1.000 with zero
  false positives, across both repeats. Strict recall, where the exact
  field-set must match, was 0.941 (3.1) and 0.853 (3.5). The control's was
  0.588.
- **Clean corpus at window sizes:** the **shipped** `CONTRADICTION_SI` reaches
  precision 0.97-1.00 on 3.x. On the 2.5 control it reaches 0.85-0.91.
  The g1c precision tuning (`PROMPT_TUNED`, 0.77->0.96 on 2.5-lite) was never
  shipped into the lite window prompt; it lives only in the 2.5-pro
  `WHOLE_FORM_PRO_SI`. On 3.x lite it is no longer needed: the shipped prompt is
  already at ceiling. One 3.5 tuned@20 cell dropped 2 of 32 recall. The tuned
  prompt is not shipped, so this is noted, not actioned.
- **Implication beyond this bead (filed, not acted on):** the G1 NO-GO of
  2026-06-17 rested on lite recall 0.853 being below the in-SI check's 1.000.
  That NO-GO kept the in-SI ADDRESS CONSISTENCY prose as the primary check. On
  3.x lite the validator now matches 1.000 on that corpus. Whether that reopens
  trimming the prose is a product call: see the follow-up bead below.

### 2. Secretary answer quality -- equal or better

- Judged hallucinations (made-up or wrong values): **3.1: 1/49, 3.5: 2/49, 2.5
  control: 5/49** (June record: 5, range 2-5).
- 3.1's one hallucination (`alias_zip_mailing`) is a shared aliasing trap that
  all three models hit. The query asks for the "postal code on their mailing
  address". The I-90 has a literal *Postal Code* field (the foreign one, empty)
  next to the filled *ZIP Code*. The models answer "not answered yet", which is a
  false absence. The rendered context is correct: the ZIP shows `"62704" |
  shown=true`. So this is a query/schema wording trap, not a model regression.
- 3.5's second error is a one-letter email slip (`daeze.` for `adaeze.`).
- Grounding: 3.1 has the best precision of the three (0.871). Recall is ~0.91
  everywhere.

### 3. Latency vs `SECRETARY_DEADLINE_S=2.5` / `SECRETARY_TIMEOUT_S=8`

- Secretary, pooled latency + recall runs: 3.1 p50 1.06s, p90 1.28s, p99 3.11s,
  max 5.17s. 2/147 calls exceeded the 2.5s deadline and none exceeded the 8s
  timeout. 3.5 is near-identical (max 7.05s). The 2.5 control is ~0.15s faster
  at the median with the same 2-over-deadline count.
- Validator, 420 calls/model: 3.1 p50 0.86s / p90 1.08s / max 9.55s. 3.1's
  three >8s cells are all in the concurrent g1c run, and its row latency
  includes retry backoff after HTTP 429s (next section).
- **Developer report "3.1-flash-lite spikes of 25-30s": NOT reproduced.** No 3.x
  call exceeded 10s across ~1,100 calls. The worst single call of the whole
  study was the **2.5** control's 22.4s validator outlier. The 3.x small-call
  variance is no worse than 2.5's (validator p90-p50 spread 0.22s on 3.1 vs
  0.33s on 2.5). A 1-in-500 spike would still be invisible at this n.

### 4. Rate-limit (429) behavior -- new, operational

- 3.1-flash-lite returned **HTTP 429** (`ClientError 429`, resource exhausted).
  It happened on 1 of 99 serial secretary calls, and in a burst of 4
  consecutive attempts on one window during the 6-way-concurrent g1c run. The
  same run had 1 more on the raw-call arm. **3.5-flash-lite and 2.5-flash-lite
  returned zero 429s** under the same load.
- In production a 429 is "transient availability", so `TextAIGemini` falls back
  to 3.5-flash-lite. The user-visible effect is one extra round-trip, not a
  failure. The deployed fallback rate is not visible from here. Follow-up filed.

### 5. Thinking tokens -- none billed under the default config

- Production sends no `thinking_config` on the lite path, so the API default
  applies. Across every 3.x call that recorded usage, `thoughts_token_count`
  was **0**: secretary, validator and back-translate, ~1,100 calls. The 2.5
  control reported 62 thought tokens in total, which is negligible.
- **Developer report "MINIMAL thinking is still billed as output": not
  observed** on these task shapes. Both meters already bill
  `thoughts_token_count` at the output rate (bd1zs). If Google starts emitting
  thoughts here, the cost lines will show it without a code change.

### 6. Implicit cache -- warms slowly on 3.x; do not budget on 96-98%

- In a back-to-back loop of 98 identical-prefix secretary calls, 3.1 hit 41%
  and 3.5 hit 42%. The 2.5 control hit 18% over 49 calls. The June 96-98% figure
  does not reproduce.
- The pattern is warm-up, not instability: on 3.1 the first ~30 calls missed,
  then ~90% hit (`...H...HHH..H.HH..HH.HHHHHHH.HHHH...`). When a call did hit,
  ~12.2k of its 13.1k prompt tokens were cached.
- A real session makes a handful of widely spaced secretary calls (bd 2af7
  measured 1/10 in-session). **Cost projections should assume the secretary's
  input is uncached.** The durable fix is explicit caching, which is already
  bead jnjj.41; this data was added there as a note.

### 7. Cost per call (list prices from `backend/config.py`)

| | 2.5-flash-lite | 3.1-flash-lite | 3.5-flash-lite |
|---|---|---|---|
| secretary, uncached (~13.1k in, ~60 out) | $0.0013 | **$0.0034** | $0.0041 |
| validator window (~460 in, ~50 out) | $0.00007 | $0.00019 | $0.00026 |

**Developer report "3.5-flash-lite output costs 67% more than 3.1": true**
($2.50 vs $1.50 per M), **but immaterial here.** These calls emit ~40-70
output tokens against ~13k input, so 3.5 is ~20% dearer per secretary call,
not 67%. It only serves on a 3.1 outage or 429.

### 8. Back-translation spot check (`TRANSLATION_VERIFY_BT_MODEL`)

- One shipped-path call per language: es and zh, 15 gold + 7 planted items each.
  Every model returned 22/22 ids.
- **Every semantic plant survives the round trip on all three models**: negation
  flip, box->line near-synonym, sibling swap (both halves), numeral change. So
  the pro judge downstream still sees each corruption. The DNT-term plant is the
  lint's job, not the back-translation's.
- Gold items: 3.1 paraphrases slightly more than 2.5 (similarity to the English
  source 0.965/0.907 vs 0.973/0.965). Every low-similarity case read by hand is
  meaning-preserving, e.g. "Dependent 1 first name" -> "First name of dependent
  1". 3.5 paraphrases most ("Single" -> "Unmarried"); as the fallback that is
  acceptable, not preferred. 3.1 is fit for the role.

## Follow-ups

- **Filed, P3 (bd polyglot-pdf-kmfsp):** re-open the G1 decision. Lite validator recall on 3.x now
  matches the in-SI check on the G1 corpus. Whether that justifies trimming the
  in-SI ADDRESS CONSISTENCY prose is a maintainer/product call. No change was
  made here.
- **Filed, P3 (bd polyglot-pdf-dcbxe):** measure the deployed 3.1->3.5 fallback rate
  (`text_ai_used_fallback_model`) and check the window-validator concurrency
  cap against 3.1-flash-lite's 429 behavior.
- **Noted on jnjj.41:** the implicit-cache data in section 6.
- Not filed: the "postal code" aliasing trap. It is shared across models,
  pre-existing, and the principal's verify-back loop catches it. Recorded here
  in case a future secretary-quality pass wants it.

## Probe changes that ship with this (reusable)

- `lite_probe_textai.py` (new): the recording adapter described above.
- `probe_secretary_recall.py --prod-path`; `probe_secretary_latency.py --arms prod
  --repeats N`. The latency probe now defaults to the 3.1 -> 3.5 chain instead of
  the hardcoded 2.5-flash-lite, and its invalid `gemini-flash-lite-latest` entry
  was dropped. It also reports calls over the deadline and timeout, p99, and
  thinking tokens.
- `probe_g1_contradiction_recall.py --lite-model --lite-prompt prod --skip-in-si
  --repeats`; `probe_g1c_tuning.py --model --prompts prod,tuned --repeats`
  (g1c's raw path now folds `thoughts_token_count` into output).
- `translation_gate_probe.py --bt-only <models>`.
- Probes default to Vertex `global`. `probe_validator_rail.py`'s TEXT client now
  takes the adapter's `global` default rather than the Live model's
  `VERTEX_LOCATION`. Before this change its validator 404'd on 3.1 at
  us-central1 and silently fail-opened to "no conflicts".
- bd polyglot-pdf-nwnys (bundled): `scripts/bakeoff` Gemini usage records now
  count thinking tokens via `scripts/bakeoff/usage_tokens.py`, pinned by
  `backend/tests/unit/test_bakeoff_usage_tokens.py`.

## Reproduce

```
GOOGLE_CLOUD_PROJECT=polyglot-demo-aa709 VERTEX_LOCATION=global PYTHONPATH=<repo> \
  python backend/scripts/probe_secretary_latency.py --arms prod --model gemini-3.1-flash-lite --repeats 2
python backend/scripts/probe_g1_contradiction_recall.py --skip-in-si --lite-prompt prod --lite-model <m> --repeats 2
python backend/scripts/probe_g1c_tuning.py --model <m> --prompts prod,tuned --sizes 20,40 --repeats 2
python backend/scripts/probe_secretary_recall.py --prod-path --model <m> [--no-judge]
python scripts/spikes/translation_gate_probe.py --langs es,zh --bt-only <m1>,<m2>
```

All of these need `form-kits/i-90/schema.json` present locally as untracked
scratch (see Inputs). Live sampling is non-deterministic: the stable signals
are the 3.x-vs-control gaps, not exact counts.
