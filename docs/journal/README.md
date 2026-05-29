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

See [`../doc-architecture.md`](../doc-architecture.md) for the full system.
