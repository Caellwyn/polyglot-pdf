# HIPAA / PII / PHI logging policy

**Tracks:** backend/utils/log_schemas.py backend/utils/confirmation_logger.py backend/utils/token_file_logger.py backend/utils/dev_file_logger.py frontend/src/shared/metrics.ts

*Last updated: 2026-05-30*

This is an immigration-form app: it handles A-numbers, names, addresses, and dates
of birth. Those are PII/PHI. Anything emitted at INFO/WARNING reaches stdout →
Cloud Run → BigQuery and is **always** emitted (not gated by debug). This doc is
the one canonical home for what may and may not be logged.

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

## Enforcement

Enforcement today is **by construction and convention**, not by a runtime
scrubber: the safe loggers simply never accept a value parameter, and
`log_schemas.py` has no value field. There is no automatic forbidden-key
stripping layer — the discipline is "don't pass values to a logger," backed by the
per-surface review above and the known-leak tracking below.

The `dev_file_logger.py` gate is the one deliberate PHI sink, and it is closed in
prod by the absence of `.env.DEV` (auto-detected at import — no manual flag to
forget to flip).

## Known leaks (being fixed)

Several INFO/WARNING logs (in `backend/routes/pdf_fill_routes.py` and
`backend/adapters/live_ai_gemini.py`) still emit actual user data — field-value
samples, and the first characters of a user-speech transcript. These are real
production violations, tracked and being remediated under **`polyglot-pdf-hjo`**
(P1 security). The fix makes the code match this policy: log `field_id` +
length/type, never the value or a `text_preview`. This doc codifies the rule; that
bead fixes the code.

*Last updated: 2026-05-30*
