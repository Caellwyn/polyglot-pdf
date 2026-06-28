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

**Pre-PR assess:** rubric both criteria PASS (see PR body). Fresh-eyes
<FRESH_EYES_OUTCOME>.

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

- `scripts/harness_ledger.py` (price table + compute_cost + cost_usd in build_row)
- `tests/test_harness_ledger.py` (8 new cost tests)
- `docs/journal/telemetry/2026-06-28T02-58-15Z-f600dafa.json` (the orphaned j268
  row that missed PR #260's merge -- lands here)
