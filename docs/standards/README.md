# Standards (tier 2)

Cross-cutting rules that span surfaces: `standards/<concern>.md`. Typical set:
`testing.md`, `security.md`, `performance.md`, `conventions.md`, `review.md`.

Two non-typical members:

- [`risk-rating.md`](risk-rating.md) -- a static high/med/low risk rating of files
  (+ key functions) that the fresh-eyes self-escalation clause leans on so the cheap
  reviewer doesn't re-derive "is this dangerous?" from scratch (`polyglot-pdf-hrn.3`).
- [`bead-tiers.md`](bead-tiers.md) -- the closed `tier` / `work_class` metadata
  enums every NEW bead declares (pre-2026-08-05 beads are untagged; retrofit is not
  required), so a cheap session can query the tracker for work sized to it and the
  expensive sessions stay on work only they can do (`polyglot-pdf-1bsx`).

Each carries a `**Tracks:**` line + a `*Last updated:*` stamp, CURRENT STATE
ONLY. When a journal lesson generalizes, add a one-liner here (with an
`<a name="...">` anchor) citing the entry -- this is how a per-sprint lesson
becomes a standing rule. Promote the ones that bite repeatedly up to CLAUDE.md's
scar-tissue list.

See [`../doc-architecture.md`](../doc-architecture.md) for the full system.
