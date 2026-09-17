# Doc index -- polyglot-pdf

*Last updated: 2026-09-16 (bd polyglot-pdf-uijam: sprint 23 security + data-leak audit plan added to the active sprint plans row; no code changed in this edit).*

The canonical map of this project's docs. Tier 1 (this file + CLAUDE.md) is
always loaded; everything else is reached on demand. See
[`doc-architecture.md`](doc-architecture.md) for the system.

The full tier-2 set exists (populated under the docs-reorg epic
`polyglot-pdf-gfb`, closed). When a doc and the code disagree, the code is the
ground truth -- fix the doc first as a separate commit.

## Architecture & process

| Doc | Covers |
|-----|--------|
| [`doc-architecture.md`](doc-architecture.md) | The 3-tier progressive-discovery doc system + the freshness discipline. |
| [`technical_guide.md`](technical_guide.md) | System-wide routes / endpoints / cross-surface gotchas, plus the **Surface contracts** map (every cross-surface data contract with producer/consumer code sites -- the blast-radius reference). |
| [`schema_format.md`](schema_format.md) | The `FormSchema` JSON spec (Form > Parts > Sections > Fields). Owned by [`standards/terminology.md`](standards/terminology.md). |
| [`doctrine/planning.md`](doctrine/planning.md) | SPEAR (Scope/Plan/Execute/Assess/Resolve) per-epic: Why/How/What ownership, exit rubrics, bead taxonomy, model tiering, parallel execution. |
| [`doctrine/workflow.md`](doctrine/workflow.md) | Beads cadence, session start/end, the agent-swarm tooling, bead-creation exit-criteria convention. |
| [`doctrine/review-flow.md`](doctrine/review-flow.md) | The two-layer Claude-based review: pre-PR adversarial fresh-eyes assess loop, then ONE outer adversarial pass -- Opus cross-surface for source, Haiku prose review for docs-only (no external reviewer). |
| [`doctrine/promotion-tiers.md`](doctrine/promotion-tiers.md) | worktree -> local -> dev -> demo promotion (no prod); the gated demo-deploy authority. |
| [`doctrine/drain-handover.md`](doctrine/drain-handover.md) | R2 clean-drain / handover: PreCompact auto-compaction raises a drain flag; the orchestrator finishes or splits its in-flight bead (tracker is the handoff) and stops claiming new work. |
| [`beads-setup.md`](beads-setup.md) | One-time beads install + sync wiring (prerequisite for the swarm tooling). |
| [`doctrine/branch-protection-setup.md`](doctrine/branch-protection-setup.md) | This repo's actual `main`/`dev` GitHub rulesets. The generic agent-executable template lives at [`branch-protection-setup.md`](branch-protection-setup.md). |
| **Active sprint plans** | `sprint_<N>_<slug>_plan.md` -- listed here while at repo root; archived to `archive/` at closeout (rows recorded in [`archive_completed_plans.md`](archive_completed_plans.md)). Active: [`sprint_5_i90-authoring-loop_plan.md`](sprint_5_i90-authoring-loop_plan.md) -- PDF->JSON authoring loop (epic `polyglot-pdf-7a9`); [`sprint_7_secretary-build_plan.md`](sprint_7_secretary-build_plan.md) -- secretary build: `ask_secretary` as a live feature (epic `polyglot-pdf-jnjj`, bead `jnjj.45`); [`sprint_12_async-validator_plan.md`](sprint_12_async-validator_plan.md) -- decoupled async validator, page-end correction rail (epic `polyglot-pdf-09da`); [`sprint_13_multilingual-ux_plan.md`](sprint_13_multilingual-ux_plan.md) -- multilingual voice UX: translated spoken names (epic `polyglot-pdf-tupu`) + deterministic field focus (epic `polyglot-pdf-66ek`); [`sprint_14_translation-quality-gate_plan.md`](sprint_14_translation-quality-gate_plan.md) -- translation quality gate: context-first bake + verify/rectify loop (epic `polyglot-pdf-sekc`); [`sprint_16_instructions-enrichment_plan.md`](sprint_16_instructions-enrichment_plan.md) -- instructions enrichment: booklet-grounded per-field guidance (epic `polyglot-pdf-wsao`); [`sprint_17_acroform-integrity_plan.md`](sprint_17_acroform-integrity_plan.md) -- AcroForm integrity: field<->widget ledger + truthful editor (epic `polyglot-pdf-did2`); [`sprint_18_editor-ux-overhaul_plan.md`](sprint_18_editor-ux-overhaul_plan.md) -- schema-editor UX overhaul: embedded findings, honest gates, review-last; [`sprint_19_firm-tier-kit-lifecycle_plan.md`](sprint_19_firm-tier-kit-lifecycle_plan.md) -- firm tier + kit lifecycle: revision archive on republish, draft/complete/unpublished statuses, guarded hard delete, firm-scoped kit visibility (epics `polyglot-pdf-7jmy` + `polyglot-pdf-02ye`); [`sprint_20_sol-intro-tts_plan.md`](sprint_20_sol-intro-tts_plan.md) -- Sol introduces himself: scripted Cloud-TTS intro + first-person disclaimer, one clip per language, pre-Agree Live session deleted (epic `polyglot-pdf-s1iex`). [`sprint_21_editor-identity_plan.md`](sprint_21_editor-identity_plan.md), [`sprint_21_docs-harness-overhaul_plan.md`](sprint_21_docs-harness-overhaul_plan.md) -- per-user identity for the schema editor: replace the two shared tokens with per-user accounts, user-scoped kit locking, and attribution (epic `polyglot-pdf-ijntk`). [`sprint_22_admin-console_plan.md`](sprint_22_admin-console_plan.md) -- admin console program: separate admin service + console, credits ledger, telemetry + BigQuery, Cloud Build deploy plane, Stripe (program epic `polyglot-pdf-4uvh2`; epics `polyglot-pdf-b66pb`, `polyglot-pdf-e374w`, `polyglot-pdf-43c99`, `polyglot-pdf-nacfo`, `polyglot-pdf-m5exr`). [`sprint_23_security-audit_plan.md`](sprint_23_security-audit_plan.md) -- security + data-leak audit: PII at rest, credential/log leaks, cross-tenant access, live posture; 15 children in four waves (epic `polyglot-pdf-uijam`). Each plan file carries its own full scope; the epic's `plan:` metadata points back here. |

## Components (tier 2 -- per surface)

| Surface | Doc | Code |
|---------|-----|------|
| WebSocket session routing / handshake | [`components/websocket-routing.md`](components/websocket-routing.md) | `backend/routes/websocket_routes.py` |
| Gemini Live voice adapter (session, tools, audio) | [`components/voice-ai.md`](components/voice-ai.md) | `backend/adapters/live_ai_gemini.py` |
| Tool-call flow (code expectation vs. wire; dev-log key) | [`components/tool-call-flow.md`](components/tool-call-flow.md) | `backend/adapters/live_ai_gemini.py`, `backend/services/callback_handler.py` |
| Context-window compression (session cost/duration bounding) | [`components/context-compression.md`](components/context-compression.md) | `backend/adapters/live_ai_gemini.py`, `backend/config.py`, `backend/services/form_filling_service.py` |
| Schema forms + client state | [`components/schema-forms.md`](components/schema-forms.md) | `frontend/src/schema-forms/`, `frontend/src/shared/` |
| JIT schema loading (manifest path; A1 audit + fix-list) | [`components/jit-schema.md`](components/jit-schema.md) | `backend/services/manifest_service.py`, `backend/services/ai_context.py` |
| PDF filling | [`components/pdf-filling.md`](components/pdf-filling.md) | `backend/routes/pdf_fill_routes.py`, `backend/services/form_kits.py` |
| Preview mode / pdf-view (flag-gated in-browser PDF surface) | [`components/pdf-view.md`](components/pdf-view.md) | `frontend/src/pdf-view/` |
| Auth | [`components/auth.md`](components/auth.md) | `frontend/src/contexts/AuthContext.tsx`, `backend/services/auth.py`, `firestore.rules` |
| Config + deployment | [`components/config-deployment.md`](components/config-deployment.md) | `backend/config.py`, `deploy-*.sh`, `firebase.json` |
| Admin service + console (privileged control plane: config, audit log, deploy) | [`components/admin-service.md`](components/admin-service.md) | `admin_backend/`, `admin-console/`, `scripts/bootstrap_admin_user.py` |
| Beads remote bootstrap (hydrate `bd` in a fresh remote/web session) | [`components/beads-remote-bootstrap.md`](components/beads-remote-bootstrap.md) | `scripts/beads_remote_bootstrap.py`, `scripts/bd_prime.py` |

## Standards (tier 2 -- cross-cutting)

| Concern | Doc |
|---------|-----|
| AI models + pricing (swappable, A/B) | [`standards/ai-models.md`](standards/ai-models.md) |
| Voice + VAD (manual activity signals) | [`standards/voice-and-vad.md`](standards/voice-and-vad.md) |
| HIPAA / PII policy | [`standards/hipaa-pii-policy.md`](standards/hipaa-pii-policy.md) |
| Security posture (threat model, store inventory, route/gate matrix, credentials, third-party processors, live checks, accepted risks) | [`standards/security-posture.md`](standards/security-posture.md) |
| Confirmation + audit trail | [`standards/confirmation-and-audit.md`](standards/confirmation-and-audit.md) |
| Stateless architecture (client owns state) | [`standards/stateless-architecture.md`](standards/stateless-architecture.md) |
| Logging + cost | [`standards/logging-and-cost.md`](standards/logging-and-cost.md) |
| Terminology (parts/sections, field-id brackets, form-session) | [`standards/terminology.md`](standards/terminology.md) |
| Testing | [`standards/testing.md`](standards/testing.md) |
| Bead tiers (which model picks up a bead) | [`standards/bead-tiers.md`](standards/bead-tiers.md) |
| Risk rating (high/med/low; feeds fresh-eyes self-escalation) | [`standards/risk-rating.md`](standards/risk-rating.md) |
| SI reduction (system-instruction shape + reduced-SI floor) | [`standards/si-reduction.md`](standards/si-reduction.md) |
| WebSocket protocol (handshake + message-type union) | [`standards/ws-protocol.md`](standards/ws-protocol.md) |
| Validation delegation (cheap-model validator contracts) | [`standards/validation-delegation.md`](standards/validation-delegation.md) |
| Schema-key visibility (which model sees which schema key) | [`standards/schema-key-visibility.md`](standards/schema-key-visibility.md) |
| Section-reset deprecation (DEPRECATED-but-LIVE fallback; deletion inventory) | [`standards/section-reset-deprecation.md`](standards/section-reset-deprecation.md) |

## External references (vendored SDK docs)

| Topic | Doc | Read when |
|-------|-----|-----------|
| `google-genai` SDK + Gemini Live API (authoritative; web/Context7 unreliable) | [`genai_docs/README.md`](genai_docs/README.md) | Before writing/changing any code that touches the Gemini SDK -- esp. `backend/adapters/live_ai_gemini.py`. |

## Journal (tier 3 -- historical)

Per-file entries live in [`journal/entries/`](journal/entries/), tagged per
[`journal/TAGS.md`](journal/TAGS.md). Grep by tag to find every entry on a topic.
For current architecture, read [`technical_guide.md`](technical_guide.md)
(including its Surface contracts map) plus the per-surface
[`components/`](components/) docs -- those are maintained current state. The
[2026-05-30 re-orientation brief](journal/entries/2026-05-30-bd-j2l-reorientation-brief.md)
is the dated historical snapshot that preceded them.

## Archive (superseded -- history only)

Pre-reorg canonical/source docs, kept verbatim for history. **Do not cite as
current** -- their content lives in the tier-1/tier-2 docs above.

| Archived doc | Superseded by |
|--------------|---------------|
| [`archive/PROJECT_CONTEXT.md`](archive/PROJECT_CONTEXT.md) | CLAUDE.md + this INDEX + the tier-2 set |
| [`archive/sliding-window-go-no-go-brief.md`](archive/sliding-window-go-no-go-brief.md) | Shelved 2026-06-12 go/no-go recommendation (6x1y); compression later shipped separately -- [`components/context-compression.md`](components/context-compression.md) |
| [`archive/TECHNICAL_GUIDE.md`](archive/TECHNICAL_GUIDE.md) | [`technical_guide.md`](technical_guide.md) + `components/` + `standards/` |
| [`archive/AUTH_AND_PROFILES_PLAN.md`](archive/AUTH_AND_PROFILES_PLAN.md) | [`components/auth.md`](components/auth.md) |
| [`archive/ENV_VARIABLES.md`](archive/ENV_VARIABLES.md) | [`components/config-deployment.md`](components/config-deployment.md) |
| [`archive/releases/`](archive/releases/README.md) | the journal (legacy dated release notes) |
| [`../planning_documents/archived/`](../planning_documents/archived/README.md) | various tier-2 docs (see its README) |
