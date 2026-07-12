---
name: experimentation
description: Plan and run a measurement/probe experiment against the live app (cost, accuracy, latency, or behavior of a new method). Use before writing any new probe/spike script, before extending an existing one to a new sweep, or when asked to "measure", "A/B test", "bake off", or "get real numbers on" anything that calls a live Gemini model. Enforces two mandatory gates -- a prior-work audit and a pre-spend cost estimate -- before any API call is made. Wraps scripts/spikes/ and backend/scripts/probe_*.py. Not for open-ended web research -- if a `deep-research` skill is available in this environment, use that instead for multi-source web research questions.
---

# Running an experiment

This skill exists because this repo has **repeatedly burned real money and real
time re-running research that had already been done**, or running sweeps whose
cost nobody estimated first. Two incidents anchor the two mandatory gates below:

- **bd `polyglot-pdf-6cfu.5`** (2026-07-11/12): a chunk-size re-measure almost
  re-ran a pro-tier form-level validator sweep using the probe's *untuned*
  prompt, when `g1c_tuning_findings.md` already showed the tuned prompt lifting
  flash-lite precision 0.77->0.96 @20-field chunks -- and prior pro-tier
  form-level numbers already existed. A five-minute grep would have saved the
  run. (bd memory `research-lit-review-before-experiments`)
- **bd `0zp3`** (live-model sweep): a multi-model x multi-size sweep ran with no
  upfront estimate and came back **~$80**, 40% of it `gemini-3-flash-preview`
  output tokens -- a model the data then *rejected*. Nobody had pruned the loser
  after round 1; it re-ran through the full sweep + retries (~46k calls). (bd
  memory `cost-discipline-for-live-model-experiments-learned-the`)
- A single Vertex `gemini-2.5-flash` probe arm (bake-off, 2026-07-11, 107 calls)
  emitted 595k **thinking**-output tokens = $1.49 = 92% of that day's entire
  Vertex bill, because Vertex enables thinking on `2.5-flash` **by default**
  and nobody set a thinking budget. (bd memory
  `vertex-flash-thinking-dominates-probe-cost`)

**The two gates below are not optional process theater -- skipping either one is
exactly how the incidents above happened.**

---

## Gate 1 -- Prior-work audit (before writing any new code)

Before touching a probe script or planning a sweep, search for whether this
question has already been answered, partially answered, or ruled out.

1. **Findings docs** -- `scripts/spikes/*_findings.md` (grep the topic; ~20 exist
   covering compression, DTI cost, secretary latency/recall, tool-call
   reliability, model bake-offs, tuning). Read the ones that match, not just
   their filenames -- a findings doc's *specific numbers* (a tuned prompt, a
   chunk size, a rejected model) are the thing that gets missed by a filename-only
   skim.
2. **Journal** -- `docs/journal/entries/`, filtered via
   [`docs/journal/TAGS.md`](../../../docs/journal/TAGS.md) for the relevant tag.
3. **Beads memories** -- `bd memories <keyword>` (full text via
   `bd recall <key>`). Cost/probe/model-behavior lessons live here even when no
   findings doc was written.
4. **Existing probe/harness scripts** -- `backend/scripts/probe_*.py` and
   `scripts/spikes/*.py`. If one already exercises the same code path, **extend
   it** (new arm/flag) rather than writing a parallel script; a second script
   that patches config differently is how the `harness-get-settings-multimodule-patch`
   trap (see Scar tissue below) gets re-triggered.
5. **Check the SDK-cutover boundary.** Any finding dated before 2026-06-11
   (the `google-genai` 1.38.0 -> 2.8.0 cutover, PR #156) is a **stale
   hypothesis, not a fact** (bd memory `pre-sdk28-findings-stale-recheck-everything`).
   If the only prior evidence predates the cutover, that does NOT satisfy this
   gate -- it tells you the question needs a fresh, cheap re-check, not that it's
   settled.

**Write down, in the plan/PR/journal entry, what you found and why it doesn't
already answer the question.** If it silently does answer the question, stop --
cite it, don't re-run it.

---

## Gate 2 -- Cost estimate + go-ahead (before the first live API call)

Every run that calls a live model (Vertex Gemini, live or text) needs an
upfront estimate **before** it executes, not a post-hoc bill surprise.

### 1. Estimate the formula

```
estimated_cost = sum over each (model, arm) of:
    n_calls x avg_input_tokens x input_rate
  + n_calls x avg_output_tokens x output_rate
  (+ thinking tokens as a SEPARATE output-rate line if thinking is not disabled)
```

- **Rates**: `backend/config.py::GEMINI_PRICING_BY_FAMILY` (per-1M list prices,
  documented per-family in
  [`docs/standards/logging-and-cost.md`](../../../docs/standards/logging-and-cost.md#token--cost-tracking-live-today)
  and [`docs/standards/ai-models.md`](../../../docs/standards/ai-models.md)).
  Use the CURRENT table in the file, not a remembered number -- rates change
  when a model family is added.
- **`n_calls`**: total across every arm of the sweep, not just one cell. A
  matrix of `M models x N sizes x R repeats` is `M*N*R`, and retries multiply it
  further -- budget for a realistic retry rate on flaky models, don't assume zero.
- **Token counts**: pull real numbers from a prior findings doc for the same
  code path if one exists (Gate 1), or run ONE cheap single-call pilot first and
  measure actual `usage_metadata` before committing to the full sweep size.
- **Thinking budget is the single most common estimate-buster.** Vertex enables
  thinking BY DEFAULT on `gemini-2.5-flash` (not `-lite`). If your arm uses
  `2.5-flash` or stronger and you have not explicitly set `thinking_config` to a
  bounded budget (or disabled it), your estimate is wrong -- thinking-output
  tokens can dwarf the answer tokens by 10-50x. Set the budget FIRST, THEN
  estimate.

### 2. Default to the cheapest tier that can answer the question

- Probes default to **flash-lite** unless the question specifically requires a
  stronger tier (e.g. testing whether a stronger model changes the answer).
  (bd memory `vertex-flash-thinking-dominates-probe-cost`)
- If a stronger tier (`flash`, `pro`) IS needed, that is exactly when the
  thinking-budget line above is mandatory, and it should usually be a small
  targeted arm, not the whole sweep.

### 3. Get a go-ahead before spending

- State the estimate in dollars, not just token counts, in a message to the
  maintainer (per this project's plain-language communication rule -- lead
  with what you're measuring and why, then the number).
- **Rule of thumb from `0zp3`: an unexpected bill is worse than a slow
  experiment.** If the estimate is more than a trivial pilot cost (rough
  anchor: more than a few dollars, or any sweep with more than ~50 live calls),
  treat it as a per-instance ask (same posture as the demo-deploy gate in
  CLAUDE.md) -- don't treat a prior go-ahead for a *different* sweep as
  standing authorization for this one.
- A single cheap pilot call (one model, one arm, a handful of turns) to
  ground-truth the token estimate does not need a separate go-ahead; the FULL
  sweep does.

### 4. Prune as you go

- After round 1 of a multi-arm sweep, drop any arm that is clearly losing
  (slow, flaky, or answering the question in the negative) from later rounds
  instead of carrying it through the whole matrix. This is how `0zp3` burned
  ~10M tokens on a model the data had already rejected.
- On a fix-driven re-run, re-run **only the affected cells**, not the whole
  matrix.
- Cap retries hard on flaky models/endpoints -- unbounded 5xx/timeout retries
  multiply call count silently.

---

## Running the probe itself

1. **Vertex only, always.** ALL live-model work -- probes, harnesses, spikes,
   production -- runs on Vertex (`GOOGLE_CLOUD_PROJECT` + ADC), never AI Studio
   (`GEMINI_API_KEY`), so spend lands on the tracked billing project. AI Studio
   is a deliberate, explicitly-flagged exception only (e.g. a model not yet
   available on Vertex). If a script builds `genai.Client(api_key=...)`,
   convert it to the Vertex-default pattern in `backend/adapters/text_ai_gemini.py`
   (`vertexai=True, project=os.getenv("GOOGLE_CLOUD_PROJECT")`) -- note that
   `backend/scripts/probe_secretary_recall.py::_client` is itself still
   AI-Studio-keyed as of this writing; do not copy it as a Vertex example.
   (bd memory `all-live-model-work-runs-on-vertex`)
2. **Deploy-fidelity for anything touching the live/voice path.** A probe of
   the live Gemini session (tool declarations, system-instruction path,
   content shape) must represent what deploy actually sends -- production tool
   declarations, the real SI builder (`build_form_context_message` with a real
   schema), realistic answer content. A stripped-down probe config
   (`tool_declarations=None`, a one-line stand-in SI) is a **different system**
   and its verdicts do not transfer -- this produced a week of false "2.5 is
   unstable" verdicts (bd `h04c`) while the deploy-shaped config was stable the
   whole time. Deviate from deploy config only as a deliberate, **labeled**
   experimental arm (an isolation control), never as the default. Full rule:
   [`docs/standards/testing.md`](../../../docs/standards/testing.md#live-endpoint-probes-and-spikes-deploy-fidelity-is-mandatory).
   (bd memory `live-probes-must-mirror-deploy-config`)
3. **Serialize runs.** Concurrent live sessions are not a stability problem
   (Vertex handles ~1000 concurrent live sessions/project fine -- the old
   "one session at a time" claim was overturned, bd memory
   `vertex-live-one-session-at-a-time`) but still run probes serially so
   per-run cost/latency/token numbers aren't confounded by a second session's
   traffic.
4. **Patch config on every importing module, not just the definer.** If the
   probe monkeypatches something like `get_settings()` to change model/arm
   config mid-run, `from backend.config import get_settings` is a BY-REFERENCE
   import -- patching the definer does not reach `ai_context`,
   `callback_handler`, `form_filling_service`, etc., which each hold their own
   reference. Patch every importing module and restore in a `finally`. This
   silently rendered the wrong system instruction for an entire arm before it
   was caught (bd `jnjj.25`; bd memory `harness-get-settings-multimodule-patch`).
5. **Be as suspicious of your own harness/debug code as of the model.** A
   Pydantic-vs-dict mismatch in debug code (`f.get('id')` on a `FormField`)
   crashed every fill silently and sent a prior session chasing a phantom
   model-behavior bug for a full investigation before the real cause (a debug
   line) was found. When a probe's results look surprising, check the probe
   code path before concluding the model can't do X. (bd memory
   `g3-cost-harness-unreliable-for-fill-accuracy`)

## Where to find related driving agents

Live-model experiments often need to drive part of the app to generate
realistic traffic, not just call the API directly:

- **Voice form-fill loop** -- [`voice-harness`](../voice-harness/SKILL.md) drives
  the real frontend + backend + real Gemini with scripted audio fixtures
  (no human mic), asserting on field-fill/confirm/advance outcomes. Use it when
  the experiment needs a realistic multi-turn voice session (e.g. measuring
  DTI cost/fill-accuracy under a new SI shape) rather than a scripted text-only
  probe.
- **Local dev stack** -- [`run-local`](../run-local/SKILL.md) brings up
  backend+frontend for manual/interactive probing when a scripted harness isn't
  the right tool for the question.
- **Cost/token harness library** -- `scripts/spikes/measure_form_session_costs.py`
  and `scripts/spikes/cost_matrix_lib.py` already implement multi-arm
  session-cost sweeps (model x SI-shape x turn-count) with the pricing table
  wired in; check whether your question fits an existing `--arm` before adding
  a new script.

## Recording the result

- Write (or extend) a `scripts/spikes/<topic>_findings.md` with the method,
  the actual measured numbers, and the verdict -- this is what Gate 1 searches
  next time. State the model/SDK version and date so a future session can judge
  staleness (see the SDK-cutover rule above).
- Commit the raw run data alongside the findings doc (existing convention:
  `scripts/spikes/data/` for CSV/JSON run artifacts, or a `<topic>_runs.jsonl`
  next to the script) so a later session can re-derive the findings doc's
  numbers instead of taking them on faith.
- If the finding changes a documented invariant (a component doc, a standards
  doc, CLAUDE.md scar tissue), update that doc in the same PR -- don't leave
  the correction only in the findings file.
- If the finding is a durable process lesson (not just a one-off number),
  `bd remember` it so it survives to the next session per
  `scar-tissue-must-be-repo-discoverable` -- local-only memory is invisible to
  web/cloud sessions.
