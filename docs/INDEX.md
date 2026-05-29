# Doc index -- <PROJECT NAME>

The canonical map of this project's docs. Tier 1 (this file + CLAUDE.md) is
always loaded; everything else is reached on demand. See
[`doc-architecture.md`](doc-architecture.md) for the system.

## Architecture & process

| Doc | Covers |
|-----|--------|
| [`doc-architecture.md`](doc-architecture.md) | The 3-tier progressive-discovery doc system + the freshness discipline. |
| [`technical_guide.md`](technical_guide.md) | System-wide routes / endpoints / cross-surface gotchas. |
| [`doctrine/workflow.md`](doctrine/workflow.md) | Beads cadence, session start/end, the agent-swarm tooling. |
| [`doctrine/review-flow.md`](doctrine/review-flow.md) | The parallel Copilot + fresh-eyes review procedure. |
| [`doctrine/promotion-tiers.md`](doctrine/promotion-tiers.md) | feature -> dev (staging) -> main (prod) promotion. |
| [`beads-setup.md`](beads-setup.md) | One-time beads install + sync wiring (prerequisite for the swarm tooling). |
| [`branch-protection-setup.md`](branch-protection-setup.md) | One-time GitHub ruleset setup (agent-executable). |
| **Active sprint plans** | `sprint_<N>_<slug>_plan.md` (none yet) -- listed here while at repo root; archived to `archive/` at closeout. |

## Components (tier 2 -- per surface)

| Surface | Doc |
|---------|-----|
| _(add one row per `components/<surface>.md` as you create them)_ | |

## Standards (tier 2 -- cross-cutting)

| Concern | Doc |
|---------|-----|
| _(add rows for `standards/*.md`: testing, security, performance, conventions, review, ...)_ | |

## Journal (tier 3 -- historical)

Per-file entries live in [`journal/entries/`](journal/entries/), tagged per
[`journal/TAGS.md`](journal/TAGS.md). Grep by tag to find every entry on a topic.
