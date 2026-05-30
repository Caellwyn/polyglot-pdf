# Doc index -- polyglot-pdf

The canonical map of this project's docs. Tier 1 (this file + CLAUDE.md) is
always loaded; everything else is reached on demand. See
[`doc-architecture.md`](doc-architecture.md) for the system.

Tier-2 docs are being populated under the docs-reorg epic (`polyglot-pdf-gfb`).
Rows tagged _(planned -- `bead`)_ name the doc that **will** live there and the
bead that owns it; until it lands, use the cited code path. When you create a
doc, drop the _(planned)_ tag and make the name a link.

## Architecture & process

| Doc | Covers |
|-----|--------|
| [`doc-architecture.md`](doc-architecture.md) | The 3-tier progressive-discovery doc system + the freshness discipline. |
| [`technical_guide.md`](technical_guide.md) | System-wide routes / endpoints / cross-surface gotchas. _(skeleton -- being populated under `polyglot-pdf-gfb.2`; until then use the brief + cited code paths.)_ |
| [`doctrine/workflow.md`](doctrine/workflow.md) | Beads cadence, session start/end, the agent-swarm tooling. |
| [`doctrine/review-flow.md`](doctrine/review-flow.md) | The parallel Copilot + fresh-eyes review procedure. |
| [`doctrine/promotion-tiers.md`](doctrine/promotion-tiers.md) | feature -> dev (staging) -> main (prod) promotion. |
| [`beads-setup.md`](beads-setup.md) | One-time beads install + sync wiring (prerequisite for the swarm tooling). |
| [`branch-protection-setup.md`](branch-protection-setup.md) | One-time GitHub ruleset setup (agent-executable). |
| **Active sprint plans** | `sprint_<N>_<slug>_plan.md` (none yet) -- listed here while at repo root; archived to `archive/` at closeout. |

## Components (tier 2 -- per surface)

| Surface | Doc | Code |
|---------|-----|------|
| WebSocket session routing / handshake | `components/websocket-routing.md` _(planned -- `polyglot-pdf-w0d`)_ | `backend/routes/websocket_routes.py` |
| Gemini Live voice adapter (session, tools, audio) | `components/voice-ai.md` _(planned -- `polyglot-pdf-rvz`)_ | `backend/adapters/live_ai_gemini.py` |
| Schema forms + client state | `components/schema-forms.md` _(planned -- `polyglot-pdf-93c`)_ | `frontend/src/schema-forms/`, `frontend/src/shared/` |
| PDF filling | `components/pdf-filling.md` _(planned -- `polyglot-pdf-2yu`)_ | `backend/routes/pdf_fill_routes.py`, `backend/services/form_kits.py` |
| Auth | `components/auth.md` _(planned -- `polyglot-pdf-y3l`)_ | _(see bead)_ |
| Config + deployment | `components/config-deployment.md` _(planned -- `polyglot-pdf-22q`)_ | `backend/config.py`, `deploy-*.sh`, `firebase.json` |

## Standards (tier 2 -- cross-cutting)

| Concern | Doc |
|---------|-----|
| AI models + pricing (swappable, A/B) | `standards/ai-models.md` _(planned -- `polyglot-pdf-5df`)_ |
| Voice + VAD (manual activity signals) | `standards/voice-and-vad.md` _(planned -- `polyglot-pdf-4rz`)_ |
| HIPAA / PII policy | `standards/hipaa-pii-policy.md` _(planned -- `polyglot-pdf-b11`)_ |
| Confirmation + audit trail | `standards/confirmation-and-audit.md` _(planned -- `polyglot-pdf-gbn`)_ |
| Stateless architecture | `standards/stateless-architecture.md` _(planned -- `polyglot-pdf-pki`)_ |
| Logging + cost | `standards/logging-and-cost.md` _(planned -- `polyglot-pdf-m8s`)_ |
| Terminology (sections vs parts) | `standards/terminology.md` _(planned -- `polyglot-pdf-m3f`)_ |
| Testing | `standards/testing.md` _(planned -- `polyglot-pdf-jh8`)_ |

## Journal (tier 3 -- historical)

Per-file entries live in [`journal/entries/`](journal/entries/), tagged per
[`journal/TAGS.md`](journal/TAGS.md). Grep by tag to find every entry on a topic.
Start here for verified current architecture:
[`2026-05-30-bd-j2l-reorientation-brief.md`](journal/entries/2026-05-30-bd-j2l-reorientation-brief.md).
