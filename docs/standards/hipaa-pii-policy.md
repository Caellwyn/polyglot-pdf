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
| Token / cost | `backend/utils/token_file_logger.py` | **Safe, and local-dev only** -- token counts + costs only; the file write is a no-op with `K_SERVICE` set and its one call site is gated on the `backend/.env.DEV` marker (bd `polyglot-pdf-wfgjz`). The per-turn usage banner is one structured `token_usage` event (counts and cost), not a `print()`. See [logging-and-cost.md](logging-and-cost.md). |
| Event schemas | `backend/utils/log_schemas.py` + `structured_logger.py` | **Safe by shape** — `TypedDict`s with no value field (`field_id` carries the comment "NEVER include field values!"). `StructuredLogger` IS live: `live_ai_gemini.py` calls `get_structured_logger().log_gemini_api_response(...)` per turn to emit token/cost counts as a JSON line to stdout (bd polyglot-pdf-5c2h) -- safe because the schema has no value slot, not because it's unused. The **usage event v2** envelope (bd polyglot-pdf-wio6m) is the same guarantee widened to every paid call: `_emit_usage` and its three wrappers carry ids, counts, costs and model names only, and `USAGE_CONTEXT_KEYS` has no free-text slot — pinned by `test_usage_event_schema.py::test_no_free_text_slot_in_the_envelope`, so a value/transcript key fails there before it can reach a log line. See [logging-and-cost.md](logging-and-cost.md). |
| Frontend metrics | `frontend/src/shared/metrics.ts` | **Safe** — barge-in / VAD timing metrics held in memory and exposed only on `window.__VFF_METRICS__` for the local tuning UI; never transmitted to the backend or any third party. Header: "NO PII - Only timing and operational metrics." |
| Dev file logger | `backend/utils/dev_file_logger.py` | **Gated** -- with one historical escape hatch now closed. MAY write field values / Gemini messages / tool args, but the FILE sink (`_write_to_file`) is a no-op unless `backend/.env.DEV` exists. `.env*` files are gitignored + dockerignored, so production containers never enable it. Acceptable for local debugging; NEVER ship a container with `.env.DEV`. **bd polyglot-pdf-2m9** added more sinks under the SAME gate: per-turn audio rollups (frame/byte counts -- no audio bytes), session/turn lifecycle, `event_shape` probes (booleans + transcription **lengths**, never text), and -- when `SEND_TRANSCRIPT` is on locally -- input/output **transcription text** (PHI). **bd polyglot-pdf-p84m** closed the one UN-gated sub-sink: `log_error`'s "always output to terminal" write ran regardless of the gate and interpolated `error_message` (= `str(e)`, which can embed a field value) -> Cloud Logging. The terminal line now carries only the `error_type`; the full message stays in the gated file. Lesson: a single un-gated write *inside* an otherwise-gated logger defeats the gate -- audit every sink, not just the module flag (see [the entry](../journal/entries/2026-06-10-bd-wpw.2-sync-confirm-field.md)). |
| Dev console ingest | `backend/routes/dev_console_routes.py` (`POST /dev/console-log`) | **Gated.** Receives the browser console mirror (bd polyglot-pdf-2m9) and writes it via the dev file logger. Console lines MAY contain PHI, so the route returns **404 unless `DEV_LOGGING_ENABLED`** (the `.env.DEV` marker) **and never when `K_SERVICE` is set** (the deployed-service flag; `tests/test_dockerignore_env_exclusion.py` also pins the `.dockerignore` line that keeps the marker out of the image, bd polyglot-pdf-6088m) -- prod never accepts it -- and the frontend (`devConsoleCapture.ts`) only POSTs to a **localhost** backend, never cloud. |
| Browser console + `sessionStorage` | `frontend/src/**` (`schemaFormState.ts`, `webFormConnection.ts`, `shared/connection.ts`, `pdfFiller.ts`, the form components) | **Safe.** No field value, handshake `current_values` map or credential reaches `console.*`: the value-logging sites are gone and `frontend/src/shared/consoleGuard.test.ts` fails on any console call whose argument identifiers name `fieldValues`, `current_values` or contain `token`/`credential`; `console.log`/`console.debug` are stripped from each app's OWN production bundle by esbuild `pure` (each app now has its own `bundleNoConsoleLog.test.ts` -- frontend, schema-editor, admin-console -- so CI's per-app jobs, which `npm ci` only their own deps, can run them). `webFormConnection.ts`'s `send()` redacts its two not-OPEN/"suspicious" `console.error` branches specifically to `{type, size}` / `{size}` only (those calls are NOT stripped by `pure`, since they are `error` not `log`); this does not describe every `warn`/`error` call in the app. The client's answers (`schema_form_state`) and link credential (`vff_client_link_token`) are wiped from the device automatically -- after a client-link session downloads/prints a completed form (60 s grace), after 10 minutes of inactivity following the WebSocket's own idle timeout (cancellable by any activity, a "Keep my answers" click, a reconnect, or a save -- see schema-forms.md for why the grace is long rather than immediate), and on staff logout -- via `SchemaFormStateManager.clearAllClientState()` (bd polyglot-pdf-8v8i7; see schema-forms.md). |
| Disclaimer acceptance | `backend/routes/disclaimer_routes.py` | **Safe** — records `form_session_id` + language + timestamps + `user_agent` + `script_version` (deliberate low-sensitivity retention pending counsel, bd pol2). **DURABLE as of bd polyglot-pdf-0dsv4**: this is no longer log-only — it is written to the `confirmation_events` Firestore collection and the per-session file, so `user_agent` now outlives the log bucket. That sharpens rather than changes the pol2 question: the field was already a deliberate retention, and it is now retained for as long as the evidence trail is. The caller's IP was dropped under bd z2is (an IP is PII under GDPR/CCPA); the exact kwarg set is pinned by an allowlist test so re-adding it must be a reviewed decision. |
| Tool-call console | `backend/services/callback_handler.py` | **Safe.** `on_tool_call` logs the tool name + argument **keys** + count via `_log.info("tool_call_received", …)` — never the argument values. `multiple_fields_sent` logs `fields=` as the field-ID **keys** only — guarded below (`fields=…values()` is flagged) so a regression to the raw value fails the build (`polyglot-pdf-t1c`). The `spoken_name` kwarg remains a standing guard entry (formerly `get_field_value`, retired `polyglot-pdf-p5h2`) against any future spoken-name logging site. `_handle_confirm_field_tool`'s DTI current-field coercion (`polyglot-pdf-h1bn`) logs only the schema-validated `current_field_id`, never the raw model-supplied `field_id` it replaces (that raw id is untrusted tool input and can carry the user's answer if the model swaps args). Full-arg capture for debugging is the `.env.DEV`-gated `_dev_log.log_tool_call`. (A prior bare `print(f"Arguments: {arguments}")` leaked the full args to stdout; removed under `polyglot-pdf-oeq`, and the guard below now covers this file + `print()` sinks.) |
| Exception rendering | `backend/utils/logging.py` | **Safe by processor** -- the ONE place every `.exception(...)` / `exc_info=True` site under `backend/` renders. It runs `pii_safe_exception_processor`, NOT structlog's stock `format_exc_info`, which writes the exception MESSAGE into the JSON output; in this app that message can embed a field value (bd `polyglot-pdf-p84m`, a P0). The processor emits the exception TYPE plus FRAMES (file, line, function -- never locals, never source text) and walks the `__cause__` / `__context__` chain, so a wrapped low-level parse error cannot leak its message either. The message is DROPPED rather than scrubbed: the value is arbitrary user speech, so no pattern covers it. `EXCEPTION_LOGGING_SITES` registers every site; `backend/tests/unit/test_error_shape.py` re-derives the set from the AST and pins the shape, and `test_no_pii_logging.py` carries the sentinel case. See [logging-and-cost.md](logging-and-cost.md). |
| uvicorn access log | `backend/utils/logging.py` + `Dockerfile` | **Safe (off)** -- uvicorn's access line is the full request target at INFO, and until sprint 23 C2 `/ws/fill` carried its credential in the query string (`?token=`; it rides the first frame now, `?token=` honoured one more deploy cycle), so with the access log on, every voice connection wrote a live Firebase ID token or magic-link token into stdout -> Cloud Logging (bd `polyglot-pdf-6rj0j`, the sprint-23 P0). Two independent guards: the deployed image's CMD passes `--no-access-log`, and `configure_logging()` caps the `uvicorn.access` logger at WARNING for any uvicorn started without the flag. Pinned separately by `tests/test_dockerfile_app_module.py` and `tests/test_logging_access_log.py`. The static guard in `test_no_pii_logging.py` never saw this sink -- it is a server logger, not an app `_log.*` call -- and Cloud Run's own request log still records the URL until the credential leaves it (sprint 23 bead C2). |
| WebSocket close events | `backend/utils/structured_logger.py` (`log_ws_close`) | **Safe by shape** -- carries `close_code` and a `reason_token`, a FIXED identifier chosen by the call site (`budget_exhausted`, `handshake_json_decode`), never a formatted message and never user-derived text. A close reason built from a client-supplied string would be a PII vector, so the token set is fixed in code. |
| WebSocket close reason (wire) | `backend/routes/websocket_routes.py` | **Safe by literal** -- every close on `/ws/fill` sends a wire `reason` from a fixed set of six literals; `test_no_pii_logging.py` resolves each site's expression to its literal and fails on anything else (an f-string, an exception message, a client token), and proves `_close_ws` forwards exactly the stated literal (bd `polyglot-pdf-wfgjz`). |
| Exception messages in log kwargs | every `_log.*` call in `backend/` and `admin_backend/` | **Safe by kwarg** -- an exception's rendered message can embed the value that failed (a `ValueError` from a field validator renders the field value), so `error=str(exc)` is banned by the guard's sensitive-kwarg set (`error`, `err`, `exc`, `detail`, and `traceback`/`tb`/`stack`/`stacktrace` -- a `format_exc()` string ends with the message line; `exc_info=True` is the shape; the error-class names match with any prefix, so `final_error=` is caught too, and every logger spelling and level including `.warn(` is scanned); the sanctioned shape is `error_type=type(exc).__name__` (193 sites rewritten, sprint 23 B1b), and `_log.exception()` gets type + frames from e4dt8's processor. An EXACT per-site allowlist in `backend/tests/test_no_pii_logging.py` covers the one non-client-data exception (the extractor's stderr tail), pinned against the tree. The sweep now covers BOTH services. |
| `/health` payload | `backend/main.py`, `admin_backend/main.py` | **Safe by shape** -- status + the two Firestore probes (public backend; a failed probe reports the exception CLASS, never the Firestore message) / status + service + `app_module` (admin); no model id, audio rate, upload limit, provider flag or key-presence bit, pinned by exact key sets in both health tests (sprint 23 B1b). |
| 422 response body | `backend/utils/validation_errors.py` (both apps) | **Safe by handler** -- FastAPI's default 422 echoes each error's `input` (the client's value) and `ctx`; the installed handler returns `loc` + `type` + `msg` only, and for a custom validator's `value_error` / `assertion_error` (whose text pydantic renders verbatim, and which route validators interpolate the submitted value into) `msg` is replaced by the generic phrase. A sentinel posted into a malformed body -- both a type mismatch and an in-type, out-of-range value -- is asserted absent from the response, and `app.debug` is pinned False (bd `polyglot-pdf-wfgjz`, PF-3). |
| Deployed verbosity floor | `backend/utils/logging.py` + `backend/config.py` + `backend/routes/websocket_routes.py` | **Safe by floor** -- with `K_SERVICE` set the root level never drops below INFO whatever `LOG_LEVEL` says, `LIVE_DEV_TRANSCRIPTS` / `LIVE_DEV_AUDIO_DUMP` are forced off, and the `SEND_TRANSCRIPT` harness knob is ignored; a source scan allows a read of any verbosity / debug env name only inside a `K_SERVICE`-gated statement (bd `polyglot-pdf-wfgjz`). |
| Ledger `reason` (operator free text) | `admin_backend/routes/credit_routes.py`, `backend/services/credit_ledger.py` | **Safe by bound + omission** -- the credit-adjust `reason` is capped at 500 characters at both doors (`REASON_MAX_LENGTH`, every ledger writer incl. the CLI) and the `admin_credits_adjusted` log line carries ids and the amount only; the text lives in `firms/*/ledger` and `admin_audit_log.after`, never in a log line. The sibling site on `set_firm_kind` is `polyglot-pdf-e8wzz`. Pinned by `test_audit_log_shapes.py` + `test_credit_ledger.py`. |
| Admin audit log `before`/`after` | `admin_backend/services/audit_log.py` | **Safe by shape** -- the per-route `before`/`after` key sets are pinned exactly for every route family that writes `admin_audit_log` (credit, firm, user x3, sweep, link, kit, config, alert) and two completeness tests make the set self-enumerating; no client-data key exists in any row. `target` is a free-form string that may carry a staff email (by design; noted in `security-posture.md`). Pinned by `test_audit_log_shapes.py`. |

## Enforcement

The live half of enforcement is `scripts/audit/log_pii_sweep.py`: a
read-only, in-process sweep of the three services' app streams and
Cloud Run request logs plus the BigQuery views with tight detectors
(credential in a URL, JWT, A-number, SSN, email, phone, DOB), reporting
counts and ids and never a matched value. Its last run and the
static guards it complements are listed in
[security-posture.md](security-posture.md).

Enforcement is **by construction and convention**, backstopped by a **static CI
guard**. By construction: the safe loggers never accept a value parameter, and
`log_schemas.py` has no value field — there is no runtime forbidden-key scrubber,
so the discipline is "don't pass values to a logger." Backstopping that
discipline, `backend/tests/test_no_pii_logging.py` is a source-level AST/grep guard
that scans the `GUARDED_FILES` (`pdf_fill_routes.py`, `live_ai_gemini.py`,
`callback_handler.py`, `request_coordinator.py`, `form_filling_service.py`,
`websocket_routes.py`, and the text-model adapter `text_ai_gemini.py`;
`secretary_context.py` has no log call and sits under the deny-by-default sweep
below) for two leak shapes and fails the build on a regression:
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
rather than passing vacuously. The remaining blind spot is the **sink/shape**, not the file set: the
guard's call-start pattern matches `_log.*(...)` calls, `print()` f-strings, and
(since bd polyglot-pdf-2k2os widened it to close a gap the usage-event-v2
emitters opened) `get_structured_logger().log_text_ai_usage(/log_tts_usage(/
log_gemini_api_response(` -- but a leak via any OTHER sink (`logging.getLogger`,
`sys.stderr.write`, a future `get_structured_logger()` method this list does not
yet name) still would not be caught. One member of that blind spot is now closed by construction
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

*Last updated: 2026-09-16 (bd polyglot-pdf-bwevj, sprint 23 C2: the access-log row -- the WebSocket credential no longer rides the URL.)*

*Last updated: 2026-09-16 (bd polyglot-pdf-2kbo0, sprint 23 B1b: two new per-surface rows -- the exception-message kwarg class (`error=str(exc)` banned on both services, `error_type=type(exc).__name__` sanctioned, exact per-site allowlist) and the trimmed `/health` payloads.)*

*Last updated: 2026-09-16 (bd polyglot-pdf-wfgjz, sprint 23 B1a: three new per-surface rows -- the value-free 422 handler on both apps, the wire close-reason literal set, and the deployed verbosity floor -- the token/cost row now says local-dev only, and the text-model adapters joined GUARDED_FILES.)*
