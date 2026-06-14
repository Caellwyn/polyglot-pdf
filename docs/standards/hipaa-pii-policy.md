# HIPAA / PII / PHI logging policy

**Tracks:** backend/utils/log_schemas.py backend/utils/confirmation_logger.py backend/utils/token_file_logger.py backend/utils/dev_file_logger.py backend/routes/pdf_fill_routes.py backend/adapters/live_ai_gemini.py backend/services/callback_handler.py backend/tests/test_no_pii_logging.py frontend/src/shared/metrics.ts

*Last updated: 2026-06-14. bd polyglot-pdf-uov.15: the never-logged guard is now deny-by-default across all backend files (test_no_pii_logging_anywhere_in_backend sweep), which caught + fixed two live leaks (spoken_name=, message=). See [../journal/entries/2026-06-14-bd-uov.15-t3-4-extend-pii-never-logged-guard-coverage.md](../journal/entries/2026-06-14-bd-uov.15-t3-4-extend-pii-never-logged-guard-coverage.md).*

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
| Dev file logger | `backend/utils/dev_file_logger.py` | **Gated** -- with one historical escape hatch now closed. MAY write field values / Gemini messages / tool args, but the FILE sink (`_write_to_file`) is a no-op unless `backend/.env.DEV` exists. `.env*` files are gitignored + dockerignored, so production containers never enable it. Acceptable for local debugging; NEVER ship a container with `.env.DEV`. **bd polyglot-pdf-2m9** added more sinks under the SAME gate: per-turn audio rollups (frame/byte counts -- no audio bytes), session/turn lifecycle, `event_shape` probes (booleans + transcription **lengths**, never text), and -- when `SEND_TRANSCRIPT` is on locally -- input/output **transcription text** (PHI). **bd polyglot-pdf-p84m** closed the one UN-gated sub-sink: `log_error`'s "always output to terminal" write ran regardless of the gate and interpolated `error_message` (= `str(e)`, which can embed a field value) -> Cloud Logging. The terminal line now carries only the `error_type`; the full message stays in the gated file. Lesson: a single un-gated write *inside* an otherwise-gated logger defeats the gate -- audit every sink, not just the module flag (see [the entry](../journal/entries/2026-06-10-bd-wpw.2-sync-confirm-field.md)). |
| Dev console ingest | `backend/routes/dev_console_routes.py` (`POST /dev/console-log`) | **Gated.** Receives the browser console mirror (bd polyglot-pdf-2m9) and writes it via the dev file logger. Console lines MAY contain PHI, so the route returns **404 unless `DEV_LOGGING_ENABLED`** (the `.env.DEV` marker) -- prod never accepts it -- and the frontend (`devConsoleCapture.ts`) only POSTs to a **localhost** backend, never cloud. |
| Tool-call console | `backend/services/callback_handler.py` | **Safe.** `on_tool_call` logs the tool name + argument **keys** + count via `_log.info("tool_call_received", …)` — never the argument values. The `get_field_value` response logs `spoken_name_length` (not the user-speech-derived `spoken_name` label) and `multiple_fields_sent` logs `fields=` as the field-ID **keys** only — both are guarded below (`spoken_name` is a sensitive kwarg; `fields=…values()` is flagged) so a regression to the raw value fails the build (`polyglot-pdf-t1c`). Full-arg capture for debugging is the `.env.DEV`-gated `_dev_log.log_tool_call`. (A prior bare `print(f"Arguments: {arguments}")` leaked the full args to stdout; removed under `polyglot-pdf-oeq`, and the guard below now covers this file + `print()` sinks.) |

## Enforcement

Enforcement is **by construction and convention**, backstopped by a **static CI
guard**. By construction: the safe loggers never accept a value parameter, and
`log_schemas.py` has no value field — there is no runtime forbidden-key scrubber,
so the discipline is "don't pass values to a logger." Backstopping that
discipline, `backend/tests/test_no_pii_logging.py` is a source-level AST/grep guard
that scans the `GUARDED_FILES` (`pdf_fill_routes.py`, `live_ai_gemini.py`,
`callback_handler.py`) for two leak shapes and fails the build on a regression:
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
it scanned `>5` files so a broken path glob fails loudly rather than passing
vacuously. The remaining blind spot is the **sink/shape**, not the file set: only
two shapes are detected (kwargs in `_log.*` calls + `print()` f-strings), so a
leak via a different sink (`logging.getLogger`, `sys.stderr.write`) still would
not be caught. Keep new logging on `_log.*` with redacted (`*_length`/`*_count`)
kwargs, and don't read a green guard as proof a non-`_log` sink is clean.

The `dev_file_logger.py` gate is the one deliberate PHI sink, and it is closed in
prod by the absence of `.env.DEV` (auto-detected at import — no manual flag to
forget to flip).

*Last updated: 2026-06-14. bd polyglot-pdf-uov.15: the never-logged guard is now deny-by-default across all backend files (test_no_pii_logging_anywhere_in_backend sweep), which caught + fixed two live leaks (spoken_name=, message=). See [../journal/entries/2026-06-14-bd-uov.15-t3-4-extend-pii-never-logged-guard-coverage.md](../journal/entries/2026-06-14-bd-uov.15-t3-4-extend-pii-never-logged-guard-coverage.md).*
