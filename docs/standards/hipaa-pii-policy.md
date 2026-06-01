# HIPAA / PII / PHI logging policy

**Tracks:** backend/utils/log_schemas.py backend/utils/confirmation_logger.py backend/utils/token_file_logger.py backend/utils/dev_file_logger.py backend/routes/pdf_fill_routes.py backend/adapters/live_ai_gemini.py backend/services/callback_handler.py backend/tests/test_no_pii_logging.py frontend/src/shared/metrics.ts

*Last updated: 2026-06-01*

This is an immigration-form app: it handles A-numbers, names, addresses, and dates
of birth. Those are PII/PHI. Anything emitted at INFO/WARNING reaches stdout →
Cloud Run logs (and, once the BigQuery sink lands — see
[logging-and-cost.md](logging-and-cost.md) Phase 5 — that pipeline too) and is
**always** emitted, not gated by debug. This doc is the one canonical home for
what may and may not be logged.

## The rule

**NEVER log a field value, transcript text, or any user-entered content** — at any
log level used in production.

**ALWAYS-safe to log:** field IDs, field/value *types*, *counts*, lengths,
timestamps, section IDs, language codes, model names, token counts, costs, and
anonymized metadata. Reference a value by its `field_id`; never by its contents.

When you need to prove "data is flowing," log a length or a type — never the value.

## Per-surface status

| Surface | File | Status |
|---------|------|--------|
| Confirmation audit | `backend/utils/confirmation_logger.py` | **Safe** — logs `field_id` + `confirmation_method` + counts only; explicit "never the actual values." See [confirmation-and-audit.md](confirmation-and-audit.md). |
| Token / cost | `backend/utils/token_file_logger.py` | **Safe** — token counts + costs only. See [logging-and-cost.md](logging-and-cost.md). |
| Event schemas | `backend/utils/log_schemas.py` + `structured_logger.py` | **Safe by shape** — `TypedDict`s with no value field (`field_id` carries the comment "NEVER include field values!"). `StructuredLogger` consumes them but emits nothing yet (its one non-test reference is a dead import). See [logging-and-cost.md](logging-and-cost.md). |
| Frontend metrics | `frontend/src/shared/metrics.ts` | **Safe** — barge-in / VAD timing metrics held in memory and exposed only on `window.__VFF_METRICS__` for the local tuning UI; never transmitted to the backend or any third party. Header: "NO PII - Only timing and operational metrics." |
| Dev file logger | `backend/utils/dev_file_logger.py` | **Gated.** MAY write field values / Gemini messages / tool args, but is a no-op unless `backend/.env.DEV` exists. `.env*` files are gitignored + dockerignored, so production containers never enable it. Acceptable for local debugging; NEVER ship a container with `.env.DEV`. |
| Tool-call console | `backend/services/callback_handler.py` | **⚠️ Known leak — `polyglot-pdf-oeq`.** `on_tool_call` *unconditionally* `print()`s the full tool-call `arguments` dict (`update_form_fields`/`confirm_field` args include field **values**) to stdout → Cloud Run logs. This violates the rule and is NOT caught by the guard below (which scans only `_log.*` kwargs in two other files). The adjacent `_dev_log.log_tool_call` is correctly `.env.DEV`-gated; the bare `print` is not. Tracked for removal under `polyglot-pdf-oeq`. |

## Enforcement

Enforcement is **by construction and convention**, backstopped by a **static CI
guard**. By construction: the safe loggers never accept a value parameter, and
`log_schemas.py` has no value field — there is no runtime forbidden-key scrubber,
so the discipline is "don't pass values to a logger." Backstopping that
discipline, `backend/tests/test_no_pii_logging.py` is a source-level AST/grep guard
that scans `pdf_fill_routes.py` and `live_ai_gemini.py` for sensitive log kwargs
(`value`, `values`, `selected_value`, `text`, `text_preview`, `transcript`,
`sample`, `system_instruction`, …) carrying a non-metadata value and fails the
build on a regression. It is a static check, not a runtime scrubber.

The guard's coverage is **narrow**: only those two files (`GUARDED_FILES`), and
only **keyword-argument** log calls (`kwarg=<rhs>`) — it does **not** scan other
modules or positional sinks like `print(f"... {arguments}")`. So it would not have
caught the `callback_handler.py` tool-call leak in the table above; don't read a
green guard as proof the whole codebase is clean.

The `dev_file_logger.py` gate is the one deliberate PHI sink, and it is closed in
prod by the absence of `.env.DEV` (auto-detected at import — no manual flag to
forget to flip).

*Last updated: 2026-06-01*
