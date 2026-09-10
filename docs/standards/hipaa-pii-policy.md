# HIPAA / PII / PHI logging policy

**Tracks:** backend/utils/log_schemas.py backend/utils/confirmation_logger.py backend/utils/token_file_logger.py backend/utils/dev_file_logger.py backend/routes/pdf_fill_routes.py backend/adapters/live_ai_gemini.py backend/services/callback_handler.py backend/services/request_coordinator.py backend/services/form_filling_service.py backend/routes/websocket_routes.py backend/tests/test_no_pii_logging.py backend/utils/logging.py frontend/src/shared/metrics.ts

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
| Confirmation audit | `backend/utils/confirmation_logger.py` | **Safe** — logs `field_id` + `confirmation_method` + counts only; explicit "never the actual values." The bd z2is Firestore mirror (`confirmation_events` collection, deployed envs) persists the SAME metadata-only event dicts — no value field exists to leak, pinned by an allowlist test on the exact document keys. See [confirmation-and-audit.md](confirmation-and-audit.md). |
| Token / cost | `backend/utils/token_file_logger.py` | **Safe** — token counts + costs only. See [logging-and-cost.md](logging-and-cost.md). |
| Event schemas | `backend/utils/log_schemas.py` + `structured_logger.py` | **Safe by shape** — `TypedDict`s with no value field (`field_id` carries the comment "NEVER include field values!"). `StructuredLogger` IS live: `live_ai_gemini.py` calls `get_structured_logger().log_gemini_api_response(...)` per turn to emit token/cost counts as a JSON line to stdout (bd polyglot-pdf-5c2h) -- safe because the schema has no value slot, not because it's unused. The **usage event v2** envelope (bd polyglot-pdf-wio6m) is the same guarantee widened to every paid call: `_emit_usage` and its three wrappers carry ids, counts, costs and model names only, and `USAGE_CONTEXT_KEYS` has no free-text slot — pinned by `test_usage_event_schema.py::test_no_free_text_slot_in_the_envelope`, so a value/transcript key fails there before it can reach a log line. See [logging-and-cost.md](logging-and-cost.md). |
| Frontend metrics | `frontend/src/shared/metrics.ts` | **Safe** — barge-in / VAD timing metrics held in memory and exposed only on `window.__VFF_METRICS__` for the local tuning UI; never transmitted to the backend or any third party. Header: "NO PII - Only timing and operational metrics." |
| Dev file logger | `backend/utils/dev_file_logger.py` | **Gated** -- with one historical escape hatch now closed. MAY write field values / Gemini messages / tool args, but the FILE sink (`_write_to_file`) is a no-op unless `backend/.env.DEV` exists. `.env*` files are gitignored + dockerignored, so production containers never enable it. Acceptable for local debugging; NEVER ship a container with `.env.DEV`. **bd polyglot-pdf-2m9** added more sinks under the SAME gate: per-turn audio rollups (frame/byte counts -- no audio bytes), session/turn lifecycle, `event_shape` probes (booleans + transcription **lengths**, never text), and -- when `SEND_TRANSCRIPT` is on locally -- input/output **transcription text** (PHI). **bd polyglot-pdf-p84m** closed the one UN-gated sub-sink: `log_error`'s "always output to terminal" write ran regardless of the gate and interpolated `error_message` (= `str(e)`, which can embed a field value) -> Cloud Logging. The terminal line now carries only the `error_type`; the full message stays in the gated file. Lesson: a single un-gated write *inside* an otherwise-gated logger defeats the gate -- audit every sink, not just the module flag (see [the entry](../journal/entries/2026-06-10-bd-wpw.2-sync-confirm-field.md)). |
| Dev console ingest | `backend/routes/dev_console_routes.py` (`POST /dev/console-log`) | **Gated.** Receives the browser console mirror (bd polyglot-pdf-2m9) and writes it via the dev file logger. Console lines MAY contain PHI, so the route returns **404 unless `DEV_LOGGING_ENABLED`** (the `.env.DEV` marker) -- prod never accepts it -- and the frontend (`devConsoleCapture.ts`) only POSTs to a **localhost** backend, never cloud. |
| Disclaimer acceptance | `backend/routes/disclaimer_routes.py` | **Safe** — records `form_session_id` + language + timestamps + `user_agent` + `script_version` (deliberate low-sensitivity retention pending counsel, bd pol2). **DURABLE as of bd polyglot-pdf-0dsv4**: this is no longer log-only — it is written to the `confirmation_events` Firestore collection and the per-session file, so `user_agent` now outlives the log bucket. That sharpens rather than changes the pol2 question: the field was already a deliberate retention, and it is now retained for as long as the evidence trail is. The caller's IP was dropped under bd z2is (an IP is PII under GDPR/CCPA); the exact kwarg set is pinned by an allowlist test so re-adding it must be a reviewed decision. |
| Tool-call console | `backend/services/callback_handler.py` | **Safe.** `on_tool_call` logs the tool name + argument **keys** + count via `_log.info("tool_call_received", …)` — never the argument values. `multiple_fields_sent` logs `fields=` as the field-ID **keys** only — guarded below (`fields=…values()` is flagged) so a regression to the raw value fails the build (`polyglot-pdf-t1c`). The `spoken_name` kwarg remains a standing guard entry (formerly `get_field_value`, retired `polyglot-pdf-p5h2`) against any future spoken-name logging site. `_handle_confirm_field_tool`'s DTI current-field coercion (`polyglot-pdf-h1bn`) logs only the schema-validated `current_field_id`, never the raw model-supplied `field_id` it replaces (that raw id is untrusted tool input and can carry the user's answer if the model swaps args). Full-arg capture for debugging is the `.env.DEV`-gated `_dev_log.log_tool_call`. (A prior bare `print(f"Arguments: {arguments}")` leaked the full args to stdout; removed under `polyglot-pdf-oeq`, and the guard below now covers this file + `print()` sinks.) |
| Exception rendering | `backend/utils/logging.py` | **Safe by processor** -- the ONE place every `.exception(...)` / `exc_info=True` site under `backend/` renders. It runs `pii_safe_exception_processor`, NOT structlog's stock `format_exc_info`, which writes the exception MESSAGE into the JSON output; in this app that message can embed a field value (bd `polyglot-pdf-p84m`, a P0). The processor emits the exception TYPE plus FRAMES (file, line, function -- never locals, never source text) and walks the `__cause__` / `__context__` chain, so a wrapped low-level parse error cannot leak its message either. The message is DROPPED rather than scrubbed: the value is arbitrary user speech, so no pattern covers it. `EXCEPTION_LOGGING_SITES` registers every site; `backend/tests/unit/test_error_shape.py` re-derives the set from the AST and pins the shape, and `test_no_pii_logging.py` carries the sentinel case. See [logging-and-cost.md](logging-and-cost.md). |
| WebSocket close events | `backend/utils/structured_logger.py` (`log_ws_close`) | **Safe by shape** -- carries `close_code` and a `reason_token`, a FIXED identifier chosen by the call site (`budget_exhausted`, `handshake_json_decode`), never a formatted message and never user-derived text. A close reason built from a client-supplied string would be a PII vector, so the token set is fixed in code. |

## Enforcement

Enforcement is **by construction and convention**, backstopped by a **static CI
guard**. By construction: the safe loggers never accept a value parameter, and
`log_schemas.py` has no value field — there is no runtime forbidden-key scrubber,
so the discipline is "don't pass values to a logger." Backstopping that
discipline, `backend/tests/test_no_pii_logging.py` is a source-level AST/grep guard
that scans the `GUARDED_FILES` (`pdf_fill_routes.py`, `live_ai_gemini.py`,
`callback_handler.py`, `request_coordinator.py`, `form_filling_service.py`,
`websocket_routes.py`) for two leak shapes and fails the build on a regression:
(1) sensitive **log kwargs** (`value`, `values`, `selected_value`, `text`,
`text_preview`, `transcript`, `sample`, `system_instruction`, …) carrying a
non-metadata value in a `_log.*(...)` call; and (2) a sensitive variable
(`arguments`, `value`, `text`, `field_values`, …) interpolated into a **positional
`print(...)` sink**. It is a static check, not a runtime scrubber.

The guard is **deny-by-default across the backend**: alongside the labelled
per-file `GUARDED_FILES` tests, `test_no_pii_logging_anywhere_in_backend` sweeps
EVERY non-test / non-probe / non-script backend `.py` with the same detectors, so
a value-handling logger in a brand-new module is covered the moment it lands — no
`GUARDED_FILES` edit required (`polyglot-pdf-uov.15`). The sweep self-checks that
it scanned `>=20` files (the backend has ~40 production modules; the floor is a
gross-undercount tripwire, not a tight bound) so a broken path glob fails loudly
rather than passing vacuously. The remaining blind spot is the **sink/shape**, not the file set: only
two shapes are detected (kwargs in `_log.*` calls + `print()` f-strings), so a
leak via a different sink (`logging.getLogger`, `sys.stderr.write`) still would
not be caught. One member of that blind spot is now closed by construction
rather than by the grep: the **exception message**, which reached Cloud Logging
through structlog's renderer from call sites that look perfectly clean in source
(`self._log.exception("tool_callback_error", tool=tool_name)` has no sensitive
kwarg to grep for). That leak is shut at the PROCESSOR -- see the
Exception-rendering row above -- because a source-level guard is structurally
blind to a leak that happens at render time. Keep new logging on `_log.*` with redacted (`*_length`/`*_count`)
kwargs, and don't read a green guard as proof a non-`_log` sink is clean.

The `dev_file_logger.py` gate is the one deliberate PHI sink, and it is closed in
prod by the absence of `.env.DEV` (auto-detected at import — no manual flag to
forget to flip).

*Last updated: 2026-09-09 (bd polyglot-pdf-wio6m: the usage event v2 envelope
carries ids, counts, costs and model names only -- no free-text slot, pinned by a
schema test. bd polyglot-pdf-e4dt8: the exception MESSAGE no longer reaches any
log -- `pii_safe_exception_processor` replaces `format_exc_info` for every
exception-logging site under `backend/`, and WebSocket closes carry a fixed
reason token rather than prose).*
