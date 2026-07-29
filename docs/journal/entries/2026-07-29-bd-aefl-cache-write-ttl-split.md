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

On a **real mixed session** measured with the final code (4,379,684 tokens at 1h
and 3,048,565 at 5m), the previously-reported total was **10.1% below** the true
one -- $155.32 where the correct figure is $172.82. (Stated against the true
value, matching the "under-reported by 37.5%" framing above; the same $17.50
delta is 11.3% *of the old figure*.) The split genuinely cuts both ways: this is
per-bucket accuracy, not a blanket multiplier bump, and the 5m bucket is not
vestigial.

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

## Two more, each one layer down

The review layers then found two further defects in the fix itself. Both are
the *same* failure mode as the original bug, which is the interesting part: each
round closed one path by which tokens could be silently mis-priced, and exposed
the next.

**Bucketing by subtracting aggregates (`polyglot-pdf-9qf2`, a real dollar
error).** `parse_transcript` accumulated the flat count and the TTL breakdown
independently across records, and the remainder was then derived as
`assumed = flat - (1h + 5m)` from those **aggregates**. That is only sound if
every record contributes proportionally to both sides -- and records are not
uniform. A record carrying a breakdown with a zero flat field, aggregated
alongside a genuinely legacy record on the same model, cancels the legacy tokens
to zero: they price at **$0** while the block reports `"measured"`. Reproduced
through the real parser at **$6.62 charged where $10.75 is correct**.

Fixed by computing each record's remainder **at parse time**, while that
record's own flat count and breakdown are still paired. Aggregate-level
subtraction is now impossible rather than merely unobserved.

**An unmodelled TTL kind vanishing entirely (`polyglot-pdf-41c1`).** The
per-record remainder was still anchored on the flat field alone, so a future
`ephemeral_12h_input_tokens` beside a zero flat field computed all three buckets
to zero: **5,000,000 tokens priced at $0.00, labelled `"none"`** -- "no cache
writes at all" -- on a real charge. Only the unmodelled-kind half is
speculative; the zero-flat-with-breakdown half is common (**167 such records**
across 1,238 local transcripts). It also falsified `_split_cache_writes`' own
docstring, which promised exactly that an unmodelled kind lands in the assumed
bucket.

Fixed by anchoring the remainder on the **larger** of the flat count and the
breakdown's own total, so neither side can be silently dropped. Verified inert
on all **117,796** real `cache_creation` records -- zero differing tokens --
because every real record carries exactly the two modelled keys.

Both were filed as out-of-scope by the reviewers who found them, and both were
fixed inline anyway. The reasoning was the same each time: a money bug that is
dormant only because of the current wire format is still a money bug; it sat in
code this change introduces; and in both cases the code contradicted a promise
its own docstring made.

**A fourth defect, and the point where the loop converged.** The
`41c1` guard summed unmodelled members of `cache_creation` by *value type*, so
a future numeric non-token sibling would be charged as cache-write tokens -- a
`ttl_seconds: 3600` would overcharge **3.25x**. That is not an invented schema:
`usage.server_tool_use` already carries non-token integer counts
(`web_search_requests` / `web_fetch_requests`). Fixed by matching the
`ephemeral_<ttl>_input_tokens` **shape** rather than a bare `*_input_tokens`
suffix -- the looser suffix still double-charges a summary member like
`total_input_tokens` on top of the buckets it summarizes (verified; the
reviewer who suggested the suffix withdrew it).

That fourth finding is where the triage changed. The first two defects were
**reachable on real data**; the last two require a schema Anthropic has not
shipped, and *each existed only because the previous fix created its surface*.
That is a loop generating its own findings rather than converging on latent
ones -- every round adds guard surface, and guard surface is itself reviewable
surface. The two speculative fixes also have **opposite** failure directions
(41c1 under-reports, dxgj over-reports), so they bracket each other: a stable
resting point. Further hardening would mean guarding a guard with no wire
evidence to discipline the design.

## The wire validates the anchor

Hunting for a reachable defect, a reviewer examined `usage.iterations` -- a real
key on **83,151 records** carrying its own nested `cache_creation`, which no
round had looked at. Two findings, both reassuring:

- The ledger never reads `iterations`, and that is **correct**: it duplicates
  the top-level usage on every real record, so reading it would double-count.
- On **all 167** zero-flat records, the iterations' token sum equals the
  top-level breakdown **exactly**.

The second is independent corroboration from the wire itself that the breakdown
-- not the zero flat field -- is the truthful figure on those records. The
`max(flat, breakdown)` anchor was therefore right on **real data**, not merely
as defensive hardening; anchoring on the flat field alone would have been wrong
today.

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
- **Never derive a per-item quantity by subtracting aggregates.** `assumed =
  total_flat - (total_1h + total_5m)` looks algebraically obvious and is wrong
  the moment the items are not uniform: one record's surplus cancels another's
  deficit, and the cancellation is invisible. Compute the remainder where the
  paired values still belong to the same record.
- **Anchor a "leftover" bucket on the MAXIMUM of every source that could
  contain it, not on one of them.** Anchoring on the flat field alone meant a
  token kind absent from that field had nowhere to land and silently ceased to
  exist. If two sources can each describe the same quantity, the leftover has to
  be measured against whichever is larger.
- **Each of these bugs was the previous one, one layer down.** Fixing "the
  label disagrees with the charge" exposed "the buckets disagree with the
  records"; fixing that exposed "the records disagree with the wire"; fixing
  *that* exposed "the guard mis-reads the wire's shape". When a fix addresses a
  class of failure rather than an instance, re-ask the same question at the next
  layer in before shipping.
- **Know when a review loop has stopped finding bugs and started making them.**
  The first two defects here were reachable on real data and worth every round.
  The last two required an unshipped schema, and each existed *only because the
  previous fix created its surface* -- guard code is itself reviewable code, so
  a loop that keeps hardening will keep finding things forever. The triage that
  ended it: **is this reachable on the current wire format or on stored data?**
  Reachable is a blocker; hypothetical gets filed. Both reviewers independently
  agreed once that test was stated, and one noted the useful stopping signal --
  the two speculative fixes have opposite failure directions (one under-reports,
  one over-reports), so they bracket each other rather than leaving an open edge.
