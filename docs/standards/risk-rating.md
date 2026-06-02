# Risk rating

**Tracks:** backend/adapters/live_ai_gemini.py backend/routes/websocket_routes.py backend/routes/pdf_fill_routes.py backend/config.py backend/ports/live_ai_port.py backend/models/

*Last updated: 2026-06-02*

A static high/med/low risk rating for the files (and key functions) in this repo.
It exists as a **cheap, pre-computed signal a reviewer can lean on instead of
re-deriving "is this dangerous?" from scratch** -- specifically the
[fresh-eyes self-escalation clause](../../.claude/agents/fresh-eyes-reviewer.md)
(`.claude/agents/fresh-eyes-reviewer.md` §Self-escalation): when a small diff is
routed to the cheap model (Haiku) by [`pick_review_model.py`](../../scripts/pick_review_model.py),
a touch of a **high-risk** file here is one of the triggers to stop and recommend
a Sonnet re-review. The size router makes **no** risk judgment by design; this doc
is the risk half of that split. (Plan of record: `docs/sprint_1_harness-tuning_plan.md`
§Supporting #5, bead `polyglot-pdf-hrn.3`.)

This is a discipline, not an enforced gate: no script parses this file today. It
is read by humans and by reviewers reasoning about a diff. Keep it current the
same way every tier-2 doc is kept current -- when a file's risk profile changes
(a new cross-file contract, a new external dependency), update the rating here.

## What the ratings mean

| Rating | Meaning | A change here... |
|--------|---------|------------------|
| **high** | A bug ships a regression, breaks a hidden caller, or burns money/leaks data. | always warrants the strong reviewer; a Haiku run that touches one must self-escalate. |
| **med** | Mistakes are usually caught locally, but the file has real callers or behavior. | is fine for the cheap reviewer **unless** it also trips a self-escalation trigger (cross-file symbol, multi-surface, genai wiring). |
| **low** | Self-contained; a bug here rarely escapes the file. | is safe for the cheap reviewer on a small diff. |

The rating is a property of the **file's blast radius**, not of any one diff. A
one-line change to a high-risk file is still high-risk -- that is exactly the case
the size router can't see and this doc exists to flag.

## What makes a file high-risk

A file is **high** if **any** of these hold (these mirror the fresh-eyes
self-escalation triggers, so the doc and the clause stay in lockstep):

1. **It touches Gemini / `google-genai` wiring** -- the live-AI adapter, the
   AI port contract, tool/function declarations, model/config selection, or
   VAD/activity signals. This SDK's failure modes are subtle and under-documented
   (see [`docs/genai_docs/`](../genai_docs/README.md) and the scar-tissue note on
   trusting the vendored docs over web/Context7), so it is **always** high.
2. **It exports a contract other files depend on** -- a wire format, an API/route
   shape, a shared schema or model, a port/interface, or a widely-imported helper.
   A signature or behavior change can break callers that don't appear in a short diff.
3. **It can regress runtime behavior in a way that costs money or leaks data** --
   anything spending Gemini tokens, anything in the PII/PHI logging path, anything
   that fills or renders the PDF the user signs.

A file is **med** if it has real callers/behavior but a bug tends to surface
locally; **low** if it is self-contained (a leaf script, a test, an isolated util).

## Seed ratings (current state)

Seeded from the `RISKY_GLOBS` intuition called out in the sprint plan
(`live_ai_gemini.py`, `websocket_routes.py`, `pdf_fill_routes.py`) and extended
to the cross-file contracts that meet the criteria above. Not every file is
listed -- **anything not listed is treated as `low` until rated otherwise.**

### High

| File | Why high |
|------|----------|
| `backend/adapters/live_ai_gemini.py` | The only `google-genai` importer; the Gemini Live adapter (criterion 1). Drives all tool calls and spends tokens (criterion 3). |
| `backend/ports/live_ai_port.py` | The AI port contract the adapter implements and the routes depend on (criterion 2 + the genai boundary). |
| `backend/routes/websocket_routes.py` | The WS session handshake/routing contract -- the wire format the client rebuilds context from (criterion 2). |
| `backend/routes/pdf_fill_routes.py` | Fills/renders the PDF the user signs; a bug corrupts the legal artifact (criterion 3). |
| `backend/config.py` | Model/config selection, including which Gemini model and VAD env are read; imported ~11 places (criteria 1 + 2). |
| `backend/services/callback_handler.py` | The PII/PHI logging path (field IDs, spoken-name labels) -- the policy surface (criterion 3). |
| `backend/services/form_kits.py` | The form-kit definitions PDF filling and schema forms both build on (criterion 2 + 3). |
| `backend/models/` (`tool_models.py`, `websocket_models.py`, `form_models.py`) | Shared schemas / tool declarations crossing the adapter, routes, and client wire (criteria 1 + 2). |

### Med

| File | Why med |
|------|---------|
| `backend/services/ai_context.py` | Builds the system instruction / context for the adapter -- real behavior, but bugs surface in the adapter it feeds. |
| `backend/services/form_filling_service.py`, `manifest_service.py`, `validation_handler.py`, `request_coordinator.py` | Service-layer logic with callers, but not a cross-file contract or a money/PII surface on their own. |
| `backend/routes/vad_config_routes.py`, `form_kit_routes.py`, `disclaimer_routes.py` | Route handlers with narrower blast radius than the WS/PDF routes. |
| `backend/main.py`, `backend/dependencies.py` | Wiring/bootstrap -- a break is loud and caught immediately at startup. |

### Low (illustrative -- the default)

Leaf scripts, tests (`backend/tests/`, `scripts/tests/`), isolated utilities
(`backend/services/field_utils.py`), and one-off harness/dev scripts. Anything
not rated above is `low` by default.

> **Frontend.** The frontend (`frontend/src/`) is not yet seeded here. Until it
> is, apply the same criteria by hand: schema-forms client state and the WS
> config (`frontend/src/shared/config.ts`) are the high-risk surfaces (the
> client owns all field state -- see the stateless-architecture standard).

## Related

- [`../../.claude/agents/fresh-eyes-reviewer.md`](../../.claude/agents/fresh-eyes-reviewer.md) -- the self-escalation clause this doc feeds.
- [`../../scripts/pick_review_model.py`](../../scripts/pick_review_model.py) -- the size-only router; the deliberate other half of the split.
- [`stateless-architecture.md`](stateless-architecture.md), [`hipaa-pii-policy.md`](hipaa-pii-policy.md) -- the invariants that make the criterion-3 files high.
