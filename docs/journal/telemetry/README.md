# Harness telemetry -- read BOTH sources for the full dataset

Each closeout writes one JSON file here (`<timestamp>-<session-prefix>.json`,
~97+ files and counting) capturing that PR's harness cost: token split
(orchestrator vs. subagent, by model), wall-clock, bead ids, experiment arm, and
the closeout counters. This is the **live** telemetry system (bd polyglot-pdf-hrn.1).

**The full dataset is TWO sources, not one:**

| Source | Coverage | Shape |
|--------|----------|-------|
| [`../harness_ledger.jsonl`](../harness_ledger.jsonl) | **pre-2026-06-10 archive** (last appended 2026-06-10) | one JSON object per line |
| `docs/journal/telemetry/*.json` (this dir) | **2026-06-10 onward** (current) | one JSON file per closeout |

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

`scripts/harness_ledger.py` writes new rows here; see
[`../../doc-architecture.md`](../../doc-architecture.md) for where this sits in the
doc system.
