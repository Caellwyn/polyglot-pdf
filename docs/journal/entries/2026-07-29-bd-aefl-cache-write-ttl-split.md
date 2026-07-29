---
title: "Cache writes are priced per TTL bucket: 1h at 2.0x, not a flat 1.25x"
date: 2026-07-29
bead: polyglot-pdf-aefl
tags: [telemetry, cost, harness, measurement]
---

# polyglot-pdf-aefl -- cache writes priced per TTL bucket

## Why

`scripts/harness_ledger.py` priced **every** cache-creation token at 1.25x the
base input rate -- the 5-minute-TTL rate -- and stamped a hardcoded
`cache_write_ttl_assumed = "5m"` onto each telemetry row. The file's own comment
justified this as unavoidable: *"the ledger rows do NOT record which TTL a cache
write used."*

That premise was false on both counts. Transcript records **do** carry the
split, in `usage.cache_creation` as `ephemeral_1h_input_tokens` /
`ephemeral_5m_input_tokens` -- `parse_transcript` simply read the flat total and
discarded the breakdown. And the assumed default was the wrong one.

**Measured 2026-07-28**, across the three most recent sessions: 1,480
usage-bearing records carrying **26,512,214 cache-creation tokens -- all of them
`ephemeral_1h`, zero `ephemeral_5m`.** A 1-hour cache write costs **2.0x** the
base input rate, so every one of those tokens was under-reported by 37.5%.

Found during the review of bd `polyglot-pdf-sw8h` (the model-5 sweep), filed
rather than folded in, since it is a pricing-model change and not a model-ID
rename.

## The correction to the correction

Early single-turn probes suggested a ~36% under-report, and that figure got
repeated. It is real but unrepresentative: those probes were 100% 1h writes.

A **real mixed session** measured on the final code (4,379,684 tokens at 1h and
3,048,565 at 5m) moves **10.1%** -- $155.32 to $172.82. The split genuinely cuts
both ways. This is per-bucket accuracy, not a blanket multiplier bump, and the
5m bucket is not vestigial.

## Verified against the bill, not against itself

Cost arithmetic that only agrees with itself proves nothing, so the fix was
checked against Anthropic's own billed figure. A live single-turn
`claude -p --model claude-sonnet-5` call:

| | |
|---|---|
| Anthropic billed | `$0.2117982` |
| New split math | `$0.2117982` (delta `0.000000000`) |
| Old flat-1.25x math | `$0.1357572` |

Re-confirmed after the round-2 refactor on a Haiku call: billed `$0.0498067`,
computed `$0.0498067`, delta zero.

**No silent re-pricing of history.** All **376** committed telemetry rows were
re-priced under both the old and new code: **zero** changed. Legacy rows carry
no breakdown, so they take the 5m fallback and keep exactly the pricing they
were written with.

## What shipped

- `parse_transcript` accumulates two new per-TTL counters off
  `usage.cache_creation`. They are a **breakdown** of
  `cache_creation_input_tokens`, never additive to it.
- `_split_cache_writes(counts)` returns
  `(measured_1h, measured_5m, assumed_5m)`. Anything the breakdown does not
  account for -- a legacy record, or a TTL kind not yet modelled -- lands in
  `assumed_5m` and is priced at 1.25x.
- `_cost_for_counts` prices each bucket at its own multiplier.
- `compute_cost` replaces the hardcoded `cache_write_ttl_assumed` with a
  measured `cache_write_ttl_source` (`measured` / `assumed-5m` / `mixed` /
  `none`), the per-bucket token counts, and `cache_write_tokens_5m_assumed` so a
  reader can tell a measured 5m write from a fallback guess.

## The bug the review found in the fix

The first draft computed the diagnostic label from **global** token sums,
re-derived independently of the per-model split that does the pricing. Two
mislabels, both reproduced:

- **Cross-model cancellation.** One model's measured tokens cancelled another's
  assumed ones: sonnet `{flat: 0, 1h: 1M}` plus haiku `{flat: 1M}` reported
  `"measured"` while haiku's million had gone through the fallback.
- **A breakdown with a zero flat field reported `"none"`** -- *"no cache writes
  at all"* -- on a real, non-zero cost. Not hypothetical: **93 records /
  1,102,515 tokens** in one live session have exactly that shape, and the label
  claimed no cache writes on a **$6.62** charge.

The reviewer filed this as out-of-scope, since the dollar total is correct in
every case and only the descriptive label was wrong. It was fixed inline
instead: **this bead exists precisely to stop the ledger presenting an
assumption as a measurement**, so shipping a diagnostic with that same defect
would have been self-defeating -- and it was a bug in code this change
introduces, not a pre-existing one.

The fix makes the label structurally incapable of disagreeing with the charge:
the buckets are accumulated inside the same loop that prices them, from the same
call. Tracked and closed as `polyglot-pdf-uksl`.

## Scar tissue

- **A comment asserting "the data doesn't record X" is a claim to verify, not a
  constraint to design around.** The TTL was in the record the whole time; the
  ledger discarded it and then documented the loss as a limitation. Check the
  raw input before accepting that a field is unavailable.
- **Validate money math against the bill, not against itself.** Internal
  consistency proves nothing about correctness. `claude -p --output-format json`
  reports `total_cost_usd` beside the token counts, so a single call reconciles
  the whole formula.
- **A diagnostic that describes how trustworthy a number is must be derived from
  the same computation that produced the number.** Re-deriving it "equivalently"
  from the same inputs is where the two silently drift apart -- here, into
  labelling a $6.62 charge as no charge at all.
