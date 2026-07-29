# Journal (tier 3 -- historical, append-only)

One file per sprint/bead: `entries/YYYY-MM-DD-bd-<code>-<slug>.md`. Append-only
at the corpus level -- write a NEW file, never edit an old one. If a past lesson
is wrong, write a new entry that says so and cite the original by filename.

**Frontmatter (YAML):** `date`, `bead`, `title`, `tags` (required); `sprint`,
`pr` (optional). Tags come verbatim from [`TAGS.md`](TAGS.md).

**Body (five sections):** Trigger / What shipped / Lessons / Doc freshness /
Files touched.

`scripts/journal_scaffold.py <bead-id>` emits the skeleton; you fill the prose.
The tag set is the per-feature index: `grep -l '<tag>' entries/*.md`.

**Harness telemetry is a CLOSED ARCHIVE** (bd polyglot-pdf-40r4). The sprint-1
harness-tuning A/B experiment (epic `polyglot-pdf-hrn`) concluded on 2026-07-05;
its conclusions are in
[`telemetry/FINAL_REPORT.md`](telemetry/FINAL_REPORT.md). Closeout no longer
writes telemetry rows and `scripts/harness_ledger.py` is gone. The dataset is
retained read-only in two places: [`harness_ledger.jsonl`](harness_ledger.jsonl)
(the pre-2026-06-10 archive) and [`telemetry/*.json`](telemetry/) (the
per-closeout rows). Analyze BOTH (dedup by `session_id` + `recorded_at`) for the
full historical cost dataset -- see [`telemetry/README.md`](telemetry/README.md).

See [`../doc-architecture.md`](../doc-architecture.md) for the full system.
