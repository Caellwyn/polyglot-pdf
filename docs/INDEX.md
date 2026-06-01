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
| [`technical_guide.md`](technical_guide.md) | System-wide routes / endpoints / cross-surface gotchas. |
| [`doctrine/workflow.md`](doctrine/workflow.md) | Beads cadence, session start/end, the agent-swarm tooling. |
| [`doctrine/review-flow.md`](doctrine/review-flow.md) | The parallel Copilot + fresh-eyes review procedure. |
| [`doctrine/promotion-tiers.md`](doctrine/promotion-tiers.md) | feature -> dev (staging) -> main (prod) promotion. |
| [`beads-setup.md`](beads-setup.md) | One-time beads install + sync wiring (prerequisite for the swarm tooling). |
| [`branch-protection-setup.md`](branch-protection-setup.md) | One-time GitHub ruleset setup (agent-executable). |
| **Active sprint plans** | `sprint_<N>_<slug>_plan.md` (none yet) -- listed here while at repo root; archived to `archive/` at closeout. |

## Components (tier 2 -- per surface)

| Surface | Doc | Code |
|---------|-----|------|
| WebSocket session routing / handshake | [`components/websocket-routing.md`](components/websocket-routing.md) | `backend/routes/websocket_routes.py` |
| Gemini Live voice adapter (session, tools, audio) | [`components/voice-ai.md`](components/voice-ai.md) | `backend/adapters/live_ai_gemini.py` |
| Schema forms + client state | [`components/schema-forms.md`](components/schema-forms.md) | `frontend/src/schema-forms/`, `frontend/src/shared/` |
| PDF filling | [`components/pdf-filling.md`](components/pdf-filling.md) | `backend/routes/pdf_fill_routes.py`, `backend/services/form_kits.py` |
| Auth | [`components/auth.md`](components/auth.md) | `frontend/src/contexts/AuthContext.tsx`, `backend/services/auth.py`, `firestore.rules` |
| Config + deployment | [`components/config-deployment.md`](components/config-deployment.md) | `backend/config.py`, `deploy-*.sh`, `firebase.json` |

## Standards (tier 2 -- cross-cutting)

| Concern | Doc |
|---------|-----|
| AI models + pricing (swappable, A/B) | [`standards/ai-models.md`](standards/ai-models.md) |
| Voice + VAD (manual activity signals) | [`standards/voice-and-vad.md`](standards/voice-and-vad.md) |
| HIPAA / PII policy | [`standards/hipaa-pii-policy.md`](standards/hipaa-pii-policy.md) |
| Confirmation + audit trail | [`standards/confirmation-and-audit.md`](standards/confirmation-and-audit.md) |
| Stateless architecture (client owns state) | [`standards/stateless-architecture.md`](standards/stateless-architecture.md) |
| Logging + cost | [`standards/logging-and-cost.md`](standards/logging-and-cost.md) |
| Terminology (parts/sections, field-id brackets, form-session) | [`standards/terminology.md`](standards/terminology.md) |
| Testing | [`standards/testing.md`](standards/testing.md) |

## External references (vendored SDK docs)

| Topic | Doc | Read when |
|-------|-----|-----------|
| `google-genai` SDK + Gemini Live API (authoritative; web/Context7 unreliable) | [`genai_docs/README.md`](genai_docs/README.md) | Before writing/changing any code that touches the Gemini SDK -- esp. `backend/adapters/live_ai_gemini.py`. |

## Journal (tier 3 -- historical)

Per-file entries live in [`journal/entries/`](journal/entries/), tagged per
[`journal/TAGS.md`](journal/TAGS.md). Grep by tag to find every entry on a topic.
Start here for verified current architecture:
[`2026-05-30-bd-j2l-reorientation-brief.md`](journal/entries/2026-05-30-bd-j2l-reorientation-brief.md).

## Archive (superseded -- history only)

Pre-reorg canonical/source docs, kept verbatim for history. **Do not cite as
current** -- their content lives in the tier-1/tier-2 docs above.

| Archived doc | Superseded by |
|--------------|---------------|
| [`archive/PROJECT_CONTEXT.md`](archive/PROJECT_CONTEXT.md) | CLAUDE.md + this INDEX + the tier-2 set |
| [`archive/TECHNICAL_GUIDE.md`](archive/TECHNICAL_GUIDE.md) | [`technical_guide.md`](technical_guide.md) + `components/` + `standards/` |
| [`archive/AUTH_AND_PROFILES_PLAN.md`](archive/AUTH_AND_PROFILES_PLAN.md) | [`components/auth.md`](components/auth.md) |
| [`archive/ENV_VARIABLES.md`](archive/ENV_VARIABLES.md) | [`components/config-deployment.md`](components/config-deployment.md) |
| [`archive/releases/`](archive/releases/README.md) | the journal (legacy dated release notes) |
| [`../planning_documents/archived/`](../planning_documents/archived/README.md) | various tier-2 docs (see its README) |
