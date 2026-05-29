# Components (tier 2)

One doc per user-facing surface or subsystem: `components/<surface>.md`.

Each MUST carry, near the top:
- a `**Tracks:**` line listing the code-path globs it owns (parsed by
  `scripts/check_doc_freshness.py`), and
- a `*Last updated: YYYY-MM-DD. See [...](...)*` stamp.

CURRENT STATE ONLY -- no `Previously:` chains, no history sections. Before
changing a surface's code, read its doc; if the doc is wrong, fix it FIRST as
a separate commit (a "trigger read" -- list these in CLAUDE.md).

See [`../doc-architecture.md`](../doc-architecture.md) for the full system.
