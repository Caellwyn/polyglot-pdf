# Sprint 7 -- Secretary build (ask_secretary tool + agent: research -> production)

> Parent feature bead: **polyglot-pdf-jnjj.45** (a sub-feature of epic
> `polyglot-pdf-jnjj`, "SI reduction via task delegation"). Epic plan:
> `~/.claude/plans/stateless-tinkering-zebra.md` (maintainer-approved 2026-06-13).
> This sprint plan refines jnjj.45's slice of that epic into an approved rubric +
> child-bead tree. Maintainer-approved 2026-06-27.

## The Why (user-facing outcome)

The voice assistant ("principal") cannot look up a past answer or find another
field without carrying the whole 132-field form in its expensive per-turn
context. The **secretary** -- a cheap text model holding the form catalog + the
client's current answers -- lets a thin principal "buzz" it in plain language
("what previous name did they give?") and get back a short, correct prose answer.
This restores navigation while keeping the principal tiny (the epic's core cost
lever). The secretary already PASSED its feasibility gates as offline probes
(Gate 1 RECALL, jnjj.26/PR #240; Gate 2 LATENCY, jnjj.27/PR #245); this sprint is
the bridge from "proven in probes" to "runs in a live session."

## Key design decisions (maintainer-approved 2026-06-27)

1. **Catalog handoff = full schema at handshake.** The browser sends the whole
   form schema once at connect; the backend caches it in-session (schema is not
   PII; rebuilt from the handshake on reconnect -- the stateless invariant holds)
   and renders the cacheable catalog itself. Chosen over "browser renders catalog
   per ask" because it matches the validated request shape exactly and keeps the
   per-ask wire payload small.
2. **The secretary is a TEXT model (`generate_content`), not the Live model.**
   Every `ask()` resends the FULL system instruction + full context -- there is
   no server-side conversation memory and no incremental update. Implicit caching
   (charged at ~1/10 rate) fires ONLY if the TOP of the context is byte-identical
   call-to-call. So the request is strictly
   `[static SECRETARY_SI + value-free catalog]` (the byte-stable, cacheable
   prefix -- NEVER mutated within a session) `+ [APPEND-ONLY tail: current values
   + shown/applicability + the prose query]`.
3. **Context shape = ship the validated renderers as-is.** The static catalog
   emits, per field: `id | spoken_name | (form label) | type | options | help`.
   The fresh tail emits, per field: `id: value | shown`. The catalog's detail
   (esp. `help.instructions`) is what Gate 1 proved makes the cheap model pick
   the RIGHT field (it disambiguates the 5 near-identical "name" fields); because
   the catalog is cached, trimming it saves the first call only. Any trim
   (enum-heavy option lists, etc.) is a deferred, evidence-driven follow-up, NOT
   in this sprint. Catalog ~8.4k tok (cached); tail ~1.5k tok (fresh).
4. **Reuse, do not reinvent:** `secretary_context.py` renderers
   (`render_static_catalog` / `render_values_tail`), the `SECRETARY_SI` /
   secretary-prompt structure from the probes, and `TextAIGemini._generate`
   (which already does the stable-prefix + fresh-tail concatenation and the
   model-fallback chain). `ask()` is implemented ON TOP of `_generate`.

## Exit rubric

| # | Criterion | Verify |
|---|-----------|--------|
| 1 | The live model can call `ask_secretary(prose query)` in a REAL I-90 session (not a probe) and get back a correct prose answer about the current form, end-to-end. | Run `/voice-harness` on the I-90 with a scripted query needing a secretary lookup (e.g. "what previous name did they give?"); observe the principal emit `ask_secretary` and speak back a correct answer. |
| 2 | `TextAIGemini.ask()` is implemented (no longer a stub), using the validated byte-stable `[SI+catalog]` prefix + append-only `[values+shown+query]` tail, with PII-safe logging (field ids/counts/latency only; NEVER values/prose/answers). | Read `text_ai_gemini.py:ask`; grep its log calls for any value/prose/answer payload (must find none); a unit test asserts the prefix is byte-identical across two calls whose values differ. |
| 3 | The blocking secretary call is guarded against the measured tail latency (interim timeout here; the full graceful-filler is jnjj.43) so a slow lookup cannot hang the conversation. | Read the handler; confirm an `asyncio.wait_for` timeout + fail-open path (returns "" / "ask the user directly") exists and is unit-tested. |

Rubric-change log: none yet (created 2026-06-27).

## Child-bead tree (MECE)

| Child | Scope | `metadata.surfaces` (write) | Inherits | Parallelizable |
|-------|-------|------------------------------|----------|----------------|
| **jnjj.45a** | Promote the secretary renderers from `backend/scripts/` to a production module (`backend/services/secretary_context.py`); keep the probe imports working. No behavior change. | `backend/services/secretary_context.py`, `backend/scripts/secretary_context.py`, `backend/scripts/probe_secretary_recall.py`, `backend/scripts/probe_secretary_latency.py` | 2 | with .45b |
| **jnjj.45b** | Implement `TextAIGemini.ask()`: byte-stable `[SI+catalog]` prefix + append-only `[values+shown+query]` tail via `_generate`; PII-safe logging; fail-open `""`. | `backend/adapters/text_ai_gemini.py`, `backend/tests/unit/test_text_ai_gemini.py` | 2 | with .45a |
| **jnjj.45c** | Wire the `ask_secretary` tool: declaration (`config.py`), dispatch (`callback_handler.on_tool_call`), `FormFillingService.handle_ask_secretary` (uses the cached full schema, requests the values+shown tail, calls `ask()` under `asyncio.wait_for`), and inject `text_ai` via `dependencies.py`. | `backend/config.py`, `backend/services/callback_handler.py`, `backend/services/form_filling_service.py`, `backend/dependencies.py`, `backend/tests/test_callback_handler.py` | 1, 3 | after a+b |
| **jnjj.45d** | Client catalog + `shown`: send the full schema at handshake; backend ingests/caches it; add `shown` (`shouldShowField`) to the `form_state_response` round-trip; extend `request_coordinator` if a dedicated request is needed. | `frontend/src/schema-forms/state/schemaFormState.ts`, `frontend/src/webFormConnection.ts`, `backend/routes/websocket_routes.py`, `backend/services/request_coordinator.py` | 1 | independent |

- **.45a + .45b** are parallel (disjoint surfaces).
- **.45c** depends on a + b (needs the production renderer module + the
  implemented `ask()`).
- **.45d** is independent backend/frontend wiring but is required for criterion-1
  end-to-end (.45c's handler consumes the catalog + shown that .45d delivers).
- PR bundling (likely a+b+c as a backend bundle, d as the FE/wire change) is a
  closeout-time decision, not fixed here.

## Out of scope (explicitly)

- **Trimming the catalog** (enum-heavy option lists, dropping help text) -- a
  deferred, evidence-driven follow-up; ship the validated renderers as-is.
- **The graceful "please hold" filler** on a slow lookup -- that is **jnjj.43**
  (this sprint ships only an interim timeout + fail-open).
- **The principal half** (thin-principal SI, `switch_to_field` nav acting on a
  secretary answer) -- jnjj.36 and the DTI work, separate.
- **Explicit (vs implicit) caching** -- deferred to scale (jnjj.41); this sprint
  relies on implicit caching only.
- **The model-fallback chain** -- already shipped in `TextAIGemini` (jnjj.42).
