# Doc index -- polyglot-pdf

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
| [`technical_guide.md`](technical_guide.md) | System-wide routes / endpoints / cross-surface gotchas. |
| [`schema_format.md`](schema_format.md) | The `FormSchema` JSON spec (Form > Parts > Sections > Fields). Owned by [`standards/terminology.md`](standards/terminology.md). |
| [`doctrine/planning.md`](doctrine/planning.md) | SPEAR (Scope/Plan/Execute/Assess/Resolve) per-epic: Why/How/What ownership, exit rubrics, bead taxonomy, model tiering, parallel execution. |
| [`doctrine/workflow.md`](doctrine/workflow.md) | Beads cadence, session start/end, the agent-swarm tooling, bead-creation exit-criteria convention. |
| [`doctrine/review-flow.md`](doctrine/review-flow.md) | The two-layer Claude-based review: pre-PR adversarial fresh-eyes assess loop + Opus-5 outer review (no external reviewer). |
| [`doctrine/promotion-tiers.md`](doctrine/promotion-tiers.md) | worktree -> local -> dev -> demo promotion (no prod); the gated demo-deploy authority. |
| [`doctrine/drain-handover.md`](doctrine/drain-handover.md) | R2 clean-drain / handover: PreCompact auto-compaction raises a drain flag; the orchestrator finishes or splits its in-flight bead (tracker is the handoff) and stops claiming new work. |
| [`beads-setup.md`](beads-setup.md) | One-time beads install + sync wiring (prerequisite for the swarm tooling). |
| [`doctrine/branch-protection-setup.md`](doctrine/branch-protection-setup.md) | This repo's actual `main`/`dev` GitHub rulesets. The generic agent-executable template lives at [`branch-protection-setup.md`](branch-protection-setup.md). |
| **Active sprint plans** | `sprint_<N>_<slug>_plan.md` -- listed here while at repo root; archived to `archive/` at closeout (rows recorded in [`archive_completed_plans.md`](archive_completed_plans.md)). Active: [`sprint_1_harness-tuning_plan.md`](sprint_1_harness-tuning_plan.md) -- harness tuning: token burn, bounded autonomy (epic `polyglot-pdf-hrn` closed; roadmap epic `polyglot-pdf-h2r` still open); [`sprint_5_i90-authoring-loop_plan.md`](sprint_5_i90-authoring-loop_plan.md) -- the I-90 authoring loop: good-enough auto-pass (empirical prompt pick) + joyful schema-editor (undo, search, controls_fields UI, one-step save) + one end-to-end loop proof (epic `polyglot-pdf-7a9`); [`sprint_6_editor-authoring-power_plan.md`](sprint_6_editor-authoring-power_plan.md) -- editor authoring power from real W-7 touch-up feedback: field grouping (merge/split), interactive preview, help-from-instructions (/TU + optional instructions-PDF upload), form versioning (epic `polyglot-pdf-s4dp` closed; loop-proof bead `polyglot-pdf-ue5s` still open); [`sprint_7_secretary-build_plan.md`](sprint_7_secretary-build_plan.md) -- secretary build: turn the ask_secretary tool + cheap-text-model agent from research probes into a live feature (full schema at handshake, byte-stable cached catalog + append-only values/shown tail; bead `polyglot-pdf-jnjj.45`); [`sprint_8_preview-mode_plan.md`](sprint_8_preview-mode_plan.md) -- preview mode: dual user-switchable view modes (live pdf.js-rendered PDF with value painting + snap-to camera, alongside the existing linear form), all default-off behind `?previewUi=1` until explicit maintainer cutover (epic `polyglot-pdf-js7q`); [`sprint_11_continuous-dti-law_plan.md`](sprint_11_continuous-dti-law_plan.md) -- continuous-DTI law of the land: flip code defaults to the continuous production values, single recall path (retire `get_field_value` for `ask_secretary`), validator->`switch_to_field` correction rail, UI/docs/tests alignment, legacy section-reset deletion last (epic `polyglot-pdf-fc7t`); [`sprint_12_async-validator_plan.md`](sprint_12_async-validator_plan.md) -- decoupled async validator: overlapping flash-lite windows run in the background, findings queue in client state and surface at page-end through the correction rail, re-arm steered markers on value change, gated pro-tier far-pair pass (epic `polyglot-pdf-09da`); [`sprint_13_multilingual-ux_plan.md`](sprint_13_multilingual-ux_plan.md) -- multilingual voice UX fixes from the 6mzi five-language assessment: quick-fix bundle (add Russian, decline/spell-back SI rules, harness localization), probes (speech-config language code, register guidance), then two epics -- translated spoken field names (epic `polyglot-pdf-tupu`) and id-less voice tools / deterministic field focus (epic `polyglot-pdf-66ek`); [`sprint_14_translation-quality-gate_plan.md`](sprint_14_translation-quality-gate_plan.md) -- translation quality gate: context-first forward translation (structured `translate_items` payload + per-language glossary/register file + temp 0) plus a verify/rectify loop in the bake (mechanical lint -> back-translate -> bilingual judge -> bounded rectify, fail-open, default-ON), flags on every authoring surface, ending in a full verified re-bake of all kits (epic `polyglot-pdf-sekc`); [`sprint_16_instructions-enrichment_plan.md`](sprint_16_instructions-enrichment_plan.md) -- instructions enrichment: booklet-grounded per-field guidance from a dedicated post-extraction LLM stage (decoupled storage/delivery: short synthesized `help.instructions` + verbatim `help.details`, inline v1 delivery, secretary whole-booklet floor, born-verified loop with booklet-containment lint, provenance no-clobber; w7 backfill as validation); [`sprint_17_acroform-integrity_plan.md`](sprint_17_acroform-integrity_plan.md) -- AcroForm integrity: deterministic field<->widget ledger at extraction (unresolvable-claim/unbacked-field/coverage hard-fails + extraction_info stamping), publish-gate lint backstop, amber-until-reviewed truthful editor, and the grey Ignored quarantine escape hatch (epic `polyglot-pdf-did2`). |

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
| Beads remote bootstrap (hydrate `bd` in a fresh remote/web session) | [`components/beads-remote-bootstrap.md`](components/beads-remote-bootstrap.md) | `scripts/beads_remote_bootstrap.py`, `scripts/bd_prime.py` |

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
| Risk rating (high/med/low; feeds fresh-eyes self-escalation) | [`standards/risk-rating.md`](standards/risk-rating.md) |
| SI reduction (system-instruction shape + reduced-SI floor) | [`standards/si-reduction.md`](standards/si-reduction.md) |
| WebSocket protocol (handshake + message-type union) | [`standards/ws-protocol.md`](standards/ws-protocol.md) |
| Validation delegation (cheap-model validator contracts) | [`standards/validation-delegation.md`](standards/validation-delegation.md) |
| Section-reset deprecation (DEPRECATED-but-LIVE fallback; deletion inventory) | [`standards/section-reset-deprecation.md`](standards/section-reset-deprecation.md) |

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
