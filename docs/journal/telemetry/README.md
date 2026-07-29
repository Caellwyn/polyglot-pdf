# Harness telemetry -- a CLOSED ARCHIVE (read BOTH sources for the full dataset)

**This telemetry system is RETIRED (bd polyglot-pdf-40r4).** The sprint-1
harness-tuning A/B experiment (epic `polyglot-pdf-hrn`) concluded on 2026-07-05 --
its verdict and analysis are in [`FINAL_REPORT.md`](FINAL_REPORT.md). Closeout no
longer writes rows, and `scripts/harness_ledger.py` has been removed: the `arm`
label was read by nothing once the experiment closed, and the per-closeout
instructions cost orchestrator tokens on every PR to record it.

The rows below are **retained read-only** as the evidence behind the report. Each
file (`<timestamp>-<session-prefix>.json`) captures one PR's harness cost: token
split (orchestrator vs. subagent, by model), wall-clock, bead ids, experiment arm,
and the closeout counters. Nothing appends to them anymore.

**The full dataset is TWO sources, not one:**

| Source | Coverage | Shape |
|--------|----------|-------|
| [`../harness_ledger.jsonl`](../harness_ledger.jsonl) | **pre-2026-06-10 archive** (last appended 2026-06-10) | one JSON object per line |
| `docs/journal/telemetry/*.json` (this dir) | **2026-06-10 .. 2026-07-28** (final) | one JSON file per closeout |

Reading only the JSONL makes it look like telemetry stopped on 2026-06-10 -- it did
not; it moved here (the per-file layout avoids merge conflicts on parallel PRs).
That misread actually happened once during a bd polyglot-pdf-h2r.4 review, which is
why this note exists (bd polyglot-pdf-icjr).

**To analyze the full history:** load both sources and **dedup by
`(session_id, recorded_at)`** -- the two share the same row schema (`session_id`,
`recorded_at`, `beads`, `arm`, `cost_category`, `tokens`, `wall_clock`, and the
closeout counters), so a row from either source is directly comparable. A given
session appears in at most one source, but dedup on the composite key is the safe
join if the cutover window ever double-counts.

Nothing writes new rows here (the ledger script is removed); see
[`../../doc-architecture.md`](../../doc-architecture.md) for where this sits in the
doc system.

## USD cost tracking is also retired (maintainer decision, 2026-07-29)

`harness_ledger.py` was the only home for the Anthropic per-MTok price table and
the per-TTL cache-write multipliers that turned a session transcript into a USD
figure (the `cost_usd` block on rows recorded after bd polyglot-pdf-cb6i). Deleting
the ledger (bd polyglot-pdf-40r4) removed that machinery too, and the maintainer
decided not to rebuild it standalone (bd polyglot-pdf-58o7, closed as won't-do):
**per-session USD cost is no longer tracked going forward.** Token counts (which
the ledger measured separately from pricing) are also no longer collected, since
nothing else in the repo reads a transcript's token split.

If USD tracking is ever wanted again, the verified rates are recoverable from git
history at the commit that deleted `scripts/harness_ledger.py` (bd
polyglot-pdf-40r4) -- notably the `claude-opus-5` / `claude-sonnet-5` price rows
added in PR #505 (bd sw8h) with a load-bearing comment warning not to "correct"
the Sonnet-5 rate down to the advertised intro price, and the 5m-vs-1h cache-write
split added in PR #506 (bd aefl), measured against 26.5M real cache-creation
tokens showing the old flat 1.25x assumption under-reported by 37.5%. Do not
recreate these rates from memory or from web pricing pages -- both PRs reconciled
them against live billing.
