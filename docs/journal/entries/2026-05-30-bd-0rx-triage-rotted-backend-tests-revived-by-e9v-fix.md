---
date: 2026-05-30
bead: polyglot-pdf-0rx
title: "Triage rotted backend tests revived by e9v fix + remove tracked test-mutated confirmations log"
tags: [testing, refactor, conventions]
---

## Trigger

Bead `polyglot-pdf-0rx`, discovered-from `e9v`. When the e9v fix restored
`form_filling_service.py` to a parseable state, pytest collection jumped 120 →
149 and 5 tests that had been silently un-collected since Dec 2025 came back —
red, because the code evolved underneath them while they weren't running. 0rx is
the triage: for each, decide whether the **test** is stale or the **code** is
wrong, plus a hygiene fix for a tracked, test-mutated confirmation log.

## What shipped

Each of the 5 revived tests triaged individually (fix-test vs fix-code):

- **`test_get_form_status_routes_to_handler`** — *fix test.* The
  `get_form_status` response key changed `field_values` → `state` (ultra-compact
  format, `callback_handler.py:358`). Assertion updated.
- **`test_complete_section_sends_form_update`** — *delete.* The
  `complete_section` tool was deliberately removed (frontend auto-detects section
  completion); its routing and handler are gone. The test asserted a tool that
  can no longer be called. `test_unknown_tool_returns_empty_dict` already covers
  the fall-through.
- **`test_set_tool_handlers`** — *finish a half-done removal (code + tests).* The
  `handle_complete_section` handler was already commented out in `CallbackHandler`
  but the param was still threaded through `set_tool_handlers` as a dead no-op.
  Removed it end-to-end: the param + its init, the prod caller in
  `form_filling_service.set_tool_handlers`, the DEPRECATED
  `handle_complete_section` method, the commented-out routing/handler stubs, and
  all 5 test call sites + the stale `_handle_complete_section` assertion.
- **JIT `next_field_schema`** (`test_update_includes_next_field_schema`) —
  *fix test (intentional design change, confirmed with maintainer).* JIT schema
  delivery was moved off `update_form_fields` onto `confirm_field` to save Gemini
  tokens (`update_form_fields` now always passes `next_field_schema=None`;
  `confirm_field` calls the getter at `callback_handler.py:435`). Rewrote the
  failing test as `test_confirm_field_includes_next_field_schema` (asserts the
  getter fires on `confirm_field`) and added
  `test_update_does_not_include_next_field_schema` to lock in that update never
  calls it. Coverage of the feature is preserved, not deleted.
- **`test_websocket_schema_initializes_session`** — *fix test.* `/ws/fill` is
  auth-gated (required `token` `Query` param + `verify_token`, commit `aa66f45`
  per AUTH_AND_PROFILES_PLAN). The test predates auth. It now passes
  `?token=test-token` and patches `verify_token`, matching the canonical pattern
  in `test_websocket_ephemeral.py`.

**Confirmation-log hygiene** (the second half of 0rx): `confirmation_logger.py`
hardcoded `CONFIRMATION_LOG_DIR = Path("logs/confirmations")` and `mkdir`'d it at
import; `test_section_switching` (via `confirm_field`) appended real audit JSONL
to the **tracked** `logs/confirmations/fss_test_12345.jsonl` on every run,
dirtying the tree. Fix: made the dir env-overridable (`CONFIRMATION_LOG_DIR`) and
resolved per-write (prod behavior unchanged); added `backend/tests/conftest.py`
with an autouse fixture pointing it at `tmp_path`; `git-rm`'d the tracked file
and gitignored `logs/confirmations/`. Verified `git status` stays clean after a
full pytest run.

No new out-of-scope findings to defer — the related work (`od1` idle-timeout,
`4cm` cascade model, `8x5` restart_gemini_session, `m85` main-promotion) was
already filed during the e9v sprint.

## Lessons

- **A revived test that's red isn't necessarily a bug** — when a test was
  silently un-collected for months (here: a broken import upstream), it rots
  against the code that moved on without it. Triage each fix-test-vs-fix-code on
  its own evidence; deleting a test for an intentionally-removed feature and
  rewriting one for an intentionally-moved feature are both legitimate outcomes.
- **Half-removed code is a trap a dead test hides.** `complete_section` was
  "removed" by commenting out the body but leaving the param threaded through the
  signature and 6 call sites — invisible while the test didn't run. Finish
  removals end-to-end, or the next reader can't tell dead from live.
- **Tests must never write into tracked paths.** A module-level
  `Path(...).mkdir()` resolved against cwd will silently write into the repo when
  tests run from the root. Env-overridable dirs + an autouse `tmp_path` fixture
  keep the suite hermetic — added as a standing rule (see Doc freshness).

## Doc freshness

`check_doc_freshness.py`: no tier-2 docs to check (`docs/components/` and
`docs/standards/` are still empty under the docs-reorg epic `gfb`). When
`docs/standards/testing.md` lands (`jh8`), it should carry the
"no test writes into tracked paths; use env-overridable dirs + tmp_path" rule
from this entry. No CLAUDE.md change.

## Files touched

- `backend/services/callback_handler.py` — dropped dead `handle_complete_section` param/init + commented stubs.
- `backend/services/form_filling_service.py` — removed the dead caller arg + the DEPRECATED `handle_complete_section` method.
- `backend/utils/confirmation_logger.py` — env-overridable, per-write `CONFIRMATION_LOG_DIR`.
- `backend/tests/conftest.py` — new; autouse fixture isolating confirmation logs to tmp_path.
- `backend/tests/test_callback_handler.py` — updated `get_form_status`/`set_tool_handlers` tests, removed obsolete `complete_section` test.
- `backend/tests/unit/test_jit_schema_loading.py` — rewrote the JIT test to `confirm_field`, added the negative-path test, dropped dead param.
- `backend/tests/unit/test_websocket_fill_web.py` — token + `verify_token` patch.
- `backend/tests/unit/test_field_validation_responses.py` — dropped dead param from `set_tool_handlers` call.
- `.gitignore` — ignore `logs/confirmations/`.
- `logs/confirmations/fss_test_12345.jsonl` — deleted (was a tracked test artifact).
