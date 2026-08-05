# Standards (tier 2)

*Last updated: 2026-08-05 (docs audit bd polyglot-pdf-2zk3: clarified that README index stubs are exempt from Tracks/stamp requirement).*

Cross-cutting rules that span surfaces: `standards/<concern>.md`. Typical set:
`testing.md`, `security.md`, `performance.md`, `conventions.md`, `review.md`.

One non-typical member: [`risk-rating.md`](risk-rating.md) -- a static
high/med/low risk rating of files (+ key functions) that the fresh-eyes
self-escalation clause leans on so the cheap reviewer doesn't re-derive "is this
dangerous?" from scratch (`polyglot-pdf-hrn.3`).

Each doc (this README excepted) carries a `**Tracks:**` line + a `*Last updated:*` stamp, CURRENT STATE
ONLY. When a journal lesson generalizes, add a one-liner here (with an
`<a name="...">` anchor) citing the entry -- this is how a per-sprint lesson
becomes a standing rule. Promote the ones that bite repeatedly up to CLAUDE.md's
scar-tissue list.

See [`../doc-architecture.md`](../doc-architecture.md) for the full system.
