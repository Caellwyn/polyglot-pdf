---
title: "Harness moves to the 5 series: Opus 5 / Sonnet 5 defaults + telemetry pricing"
date: 2026-07-28
bead: polyglot-pdf-sw8h
tags: [models, telemetry, cost, authoring, harness]
---

# polyglot-pdf-sw8h -- all locally run models to the 5 series

## Why

Follow-on to bd `polyglot-pdf-wntz` (the review-doctrine rename), which was
docs-only by design. The audit that closed wntz turned up **version-pinned
model IDs in executable code** -- out of scope there, filed here.

Maintainer directive 2026-07-28: *"all locally run models, everything in our
harness, should be upgraded to the version 5s -- sonnet 5 and opus 5."*

## The real bug: telemetry silently priced Opus 5 sessions at $0

`scripts/harness_ledger.py` prices tokens from a prefix-keyed table. It had
rows for `claude-opus-4-8`/`4-7`/`4-6`/`4-5`, `claude-sonnet-4-6`/`4-5`,
`claude-haiku-4-5`, and `claude-fable-5` -- but **no `claude-opus-5` and no
`claude-sonnet-5`**.

Per the table's own comment (added after Codex PR #261), an unpriced model ID
is "silently dropped to $0 as unpriced". So from the moment code production
moved to Opus 5, every closeout telemetry row **under-reported cost on exactly
the sessions we now run most** -- Fable sessions were priced, Opus 5 sessions
were not. This is a reporting-correctness bug, not a naming nit, and it is the
reason this bead was worth doing on its own rather than folding into a rename.

Rates added (verified against the `/claude-api` skill's model table, 2026-07-28):

| Model | Input $/MTok | Output $/MTok |
|---|---|---|
| `claude-opus-5` | 5.00 | 25.00 |
| `claude-sonnet-5` | 3.00 | 15.00 |

**Sonnet 5 intro-rate decision, and the correction that followed.** The docs
advertise an introductory $2.00/$10.00 for Sonnet 5 through 2026-08-31. The
table prices the **standard** $3.00/$15.00.

The first draft justified that as a deliberate conservative over-statement -- a
cost table outlives a promo, so pricing the intro rate would silently
under-report from 2026-09-01. **That reasoning was wrong, and the second
independent Opus review caught it.** It probed live billing and reconciled a
real `claude -p --model claude-sonnet-5` call to an implied input rate of
**$3.0000/MTok exactly** -- the standard rate, charged today, inside the claimed
promo window. Re-probed independently before acting on it: same result to four
decimals. The intro rate is simply not being applied to this account.

So the shipped number was right for the wrong reason -- and the wrong reason was
the dangerous half. A comment claiming the row is deliberately over-stated until
2026-08-31 invites the next maintainer to "correct" it down to $2/$10, which
would create a ~33% under-report: exactly the silent under-costing this bead
exists to kill. The comment now records the measured rate and tells the reader
to re-probe rather than trust the published promo.

## What else moved

**Local authoring / bakeoff defaults (the `claude` CLI path).** Seven scripts
shipped `claude-opus-4-8` as their `--model` default:
`scripts/authoring/{extract_form,eval_extraction,enrich_instructions}.py`,
`scripts/bakeoff/{arm_llm_native,arm_llm_native_chunked,order_probe}.py`,
`scripts/spikes/relationship_bake.py`. All now default to `claude-opus-5`.

**The secretary-recall probe judge.** `backend/scripts/probe_secretary_recall.py`
pinned `JUDGE_MODEL = "claude-sonnet-4-6"`; now `claude-sonnet-5`.

**Test fixtures** in `backend/tests/unit/{test_editor_kit_routes,
test_extractor_provider_auth}.py` that pass a model ID through the extractor
provider path.

## What was deliberately NOT changed

- **The backend's deployed extraction path.** `backend/config.py`'s
  `EXTRACTOR_MODEL` defaults to `gemini-2.5-pro`, and the comment there is
  explicit that it *must* be a `gemini-*` model on Cloud Run. This bead's scope
  was "locally run models"; the hosted Gemini path is untouched.
- **The 4-series pricing rows.** Kept for the same reason the file already
  states: those models are still active, and a session on one must be priced
  rather than dropped to $0.
- **`tests/test_pr_review_watcher.py:1456`** and the journal/research/telemetry
  corpus, which say "Opus 4.8" because that is what actually ran.
- **`tests/test_harness_ledger.py` / `tests/test_llm_providers.py` fixtures**
  that use 4-series IDs as arbitrary strings exercising routing and pricing.
  They are not assertions about the current default, and the 4-series rows they
  depend on are still in the table -- rewriting them would have been churn that
  weakened coverage of the still-active models.

## Judge-score comparability (the one real caveat)

Bumping the probe judge is not free: judge scores recorded **before** this
change are not directly comparable to scores after it. The affected records are
`scripts/spikes/secretary_recall_findings.md`,
`secretary_context_format_findings.md`, and the `*.meta.json` rows stamping
`"judge_model": "claude-sonnet-4-6"`.

This was flagged to the maintainer as a decision before the change, and the
answer was to upgrade. Mitigation shipped in the code: a comment at
`JUDGE_MODEL` naming the affected files and saying to re-baseline rather than
diff across the boundary. Each run already stamps its own `judge_model` into
its meta.json, so the boundary is machine-detectable in the data itself -- no
row is ambiguous about which judge produced it.

## Verification

- `_price_for_model()` exercised directly against the new IDs, including a
  dated variant (`claude-opus-5-20260701`) and the `claude-fable-5` /
  `claude-opus-4-*` neighbours, to confirm the longest-prefix resolver does not
  shadow the new short keys. Two new tests pin this:
  `test_5_series_models_are_priced_not_unpriced` (mirrors the existing 4.5
  guard) and `test_opus_5_not_shadowed_by_4_series_prefixes`.
- All seven authoring/bakeoff scripts parse `--help` cleanly (exit 0) **under
  `backend/.venv`** -- on a bare interpreter `eval_extraction.py` and
  `enrich_instructions.py` exit 1 with `ModuleNotFoundError: pydantic`, the
  repo's normal venv requirement rather than a regression from this change. A
  source-level assertion confirms each script carries the expected count of
  `claude-opus-5` occurrences with zero `claude-opus-4-8` remaining.
- Edited `.py` files byte-verified ASCII-clean (CLAUDE.md scar #6).

## Scar tissue

- **An unpriced model ID in a cost table fails silently and in the expensive
  direction.** The table drops unknown IDs to $0 rather than raising, so a
  model upgrade that skips the pricing table produces confidently wrong cost
  reporting with no error anywhere. Any change to which models we *run* must
  check the table that prices them. The new test is the guard.
- **A promo rate is the wrong default for a durable table.** Pick the rate that
  is correct after the promo lapses; a table that silently goes stale on a
  future date is the same failure mode as an unpriced model.
- **Price from the bill, not from the price list.** The published rate and the
  rate actually charged are different facts. Here the docs advertised an active
  introductory rate that billing was not applying -- a live `claude -p` call
  reports `total_cost_usd` alongside its token counts, so the real rate can be
  solved for in one call. Do that before writing a rate into a cost table.
- **A right answer with a wrong justification is still a defect.** The Sonnet-5
  row was correct while the comment above it was false, and the comment was the
  part a future maintainer would act on -- it argued for changing the row to a
  value that would have under-reported by ~33%. Review the reasoning attached to
  a constant, not just the constant.
