---
bead: polyglot-pdf-cb6i
beads_closed: [polyglot-pdf-cb6i]
date: 2026-06-28
tags: [harness, testing]
---

# harness_ledger: compute USD cost from token counts

## Trigger

The maintainer asked to track COST alongside the other harness metrics after
merging PR #260: "You know how to pull token burn from metadata and you have cost
tables." The telemetry rows (`docs/journal/telemetry/*.json`, bd hrn.1) already
captured per-model token counts (input / output / cache-read / cache-creation,
split orchestrator vs subagent) but carried NO dollar figure.

## What shipped

Added a price table + cost computation to `scripts/harness_ledger.py`:

- **`MODEL_PRICES_PER_MTOK`** -- per-million-token base rates (input/output):
  opus-4-8 $5/$25, sonnet-4-6 $3/$15, haiku-4-5 $1/$5 (plus fable-5, opus-4-7/4-6).
  Resolved by id PREFIX so the dated transcript id `claude-haiku-4-5-20251001`
  maps to its family. Prices pulled from the claude-api skill (the authoritative
  `shared/models.md`); recorded to bd memory for re-use.
- **Cache multipliers on the base INPUT rate** (`shared/prompt-caching.md`): read
  0.1x, write 1.25x. The rows do NOT record which TTL a write used; Claude Code's
  default cache is the 5-MINUTE TTL, so cache-creation is priced at 1.25x and the
  assumption is documented in code (`cache_write_ttl_assumed: "5m"` on the block).
  `input_tokens` is the uncached remainder.
- **`compute_cost(models)`** -> a `cost_usd` block mirroring the tokens/models
  structure: per-(actor, model) cost, per-model totals, orchestrator/subagent/
  grand totals, plus an `unpriced_models` list. An unknown model id contributes
  $0 and is flagged (never raises -- warn-only, matching the rest of the ledger).
- **`build_row`** now emits `cost_usd` on every row.

Verified on a real session row (the j268 closeout): **~$92 total** -- $82
orchestrator (Opus) + $9.71 subagents (Sonnet + Haiku). Concrete, useful numbers.

**Pre-PR assess:** rubric both criteria PASS (see PR body). Fresh-eyes (Sonnet,
1 round) verified the math (cache-read 0.1x, cache-write 1.25x, the combined
$36.75 vector, the dated-haiku-id prefix resolve) and returned NO-GAPS. It noted
two non-gap findings: (1) a latent AttributeError if a model entry's counts value
were None (not reachable via parse_transcript, but the "never raises" contract is
broader) -- ADOPTED: guard a None/non-dict counts (and a None actor value) to zero
+ a test; (2) a sub-penny (1e-14) rounding artifact when a model spans both actors
-- left as-is (invisible at 6dp).

**Scope note:** the bead's `surfaces` metadata named `backend/tests/` but the
real test file is the top-level `tests/test_harness_ledger.py` (where the hrn.1
ledger tests already live) -- a harmless metadata slip; the change-surface guard
just over-reserved a path I didn't touch.

## Lessons

- **Pull model prices from the claude-api skill, not memory.** The cache
  multipliers (read 0.1x, write 1.25x/2.0x by TTL) materially change the math
  given the huge cache-read counts in these rows -- guessing them would have been
  wrong. Recorded the table + formula to bd memory
  [anthropic-token-pricing-for-telemetry] for re-use without re-fetching.

## Doc freshness

No doc tracks `scripts/harness_ledger.py` (the freshness checker flagged ~19
STALE docs, but every one tracks backend/frontend source this scripts-only branch
did NOT touch -- pre-existing staleness from other merges to dev). Nothing to bump.

## Files touched

- `scripts/harness_ledger.py` (price table incl. 4.5 models + compute_cost +
  cost_usd in build_row)
- `tests/test_harness_ledger.py` (cost tests)

## Codex round 2 (telemetry rows dropped from the PR)

Round 1 flagged that a telemetry row this PR added lacked cost_usd -- I backfilled
it. Round 2 then surfaced deeper problems with shipping session telemetry rows in
this PR at all: (1) the cb6i row was `cost_category: audit` but still `arm: A`, and
`derive_experiment_state` counts any arm regardless of category, so it would skew
baseline_A; (2) two rows shared one long session's start (`f600dafa`), so the
later row's token/cost totals are CUMULATIVE (include the earlier closeouts), not
per-closeout -- double-charging arm A. Both are real, and both are properties of
committing cumulative/mislabeled session rows, not of the cost code. Decision:
DROP both telemetry rows from this PR -- the deliverable is the cost CODE + tests,
which is clean on its own; the rows brought orthogonal data-quality issues. Round
2 also caught a real code gap (Finding 3): the price table omitted the still-active
Opus/Sonnet 4.5 ids, which would fall through to $0 -- ADOPTED (added 4.5 prefixes
+ a test). The ~167 historical rows that also lack cost_usd are a separate one-time
migration (bd polyglot-pdf-mvq4).
