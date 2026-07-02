---
date: 2026-07-02
bead: polyglot-pdf-o0pc
title: "chore(cleanup): remove dead code, dead config, stale comments across backend/frontend/scripts"
tags: [refactor, conventions]
---

## Trigger

Maintainer-requested codebase cleanup (2026-07-02): "There is a lot of dead
code, dead routes, stale comments, and convoluted patches on patches." Bead
polyglot-pdf-o0pc was filed to authorize the sweep. Method: four parallel
read-only sweep agents (backend, frontend, comments/drift, root/scripts), then
every finding independently re-verified by grep before deletion (per the
verify-claims-against-code scar).

## What shipped

**Deleted (all grep-verified zero non-test references):**

- Frontend: `SimpleTest.tsx`, `TestComponent.tsx` (scaffolding stubs),
  `UserProfile.tsx` (never rendered), `greetingPrompts.ts` (superseded by
  `LanguageSelectionModal`), `vad-tuning/index.ts` (unused export barrel).
- Backend: `utils/vad_metrics.py`, `models/tool_models.py` (tool declarations
  live in `config.py#TOOL_DECLARATIONS`), `models/websocket_models.py` (empty
  file), `cors.json` (CORS is inline in `main.py`), `test_jit_system_e2e.py`
  (manual standalone script; the JIT path is covered by
  `backend/tests/unit/test_jit_schema_loading.py` + `test_ai_context.py` +
  `test_dti.py`).
- Dead `Settings` fields: `PROACTIVE_AUDIO` (always False, plus its dead
  connect branch in `live_ai_gemini.py`), `WS_MAX_OUTBOX`, `PARSER_VERSION`,
  `FORM_KITS_REMOTE_BASE_URL`, `FORM_KITS_REMOTE_TIMEOUT_SEC` -- none read
  anywhere.
- scripts/: 12 orphaned one-off probes (`analyze_sections`, `check_dns`,
  `find_genai_refs`, `fix_schema`, `inspect_client_details`,
  `inspect_genai_connect`, `refactor_callbacks`, `test_empty_tool_call`,
  `test_section_state`, `test_section_switching` (superseded by the pytest
  suite of the same name), `test_gemini_connection`, empty `gen_types.sh`) +
  4 tracked `test_output*.txt` artifacts + `replacements.txt`.

**Moved:** `backend/test_manifest_generation.py` (orphaned at backend root --
never collected since the root `pytest.ini` scoped testpaths, bd uov.1) ->
`backend/tests/unit/test_manifest_service.py` with the import fixed to the
`backend.services.*` style. Its 5 tests cover `manifest_service` helpers no
other suite exercises; the backend count rose 1171 -> 1176.

**Rewritten to current state (comments only, no behavior change):**

- `change_fill_language` (form_filling_service): dropped the never-sent
  `system_update` string, the false "this method is deprecated" note (the
  method IS live -- the frontend sends `change_fill_language` and the mid-
  session switch works via the live `_fill_language` read, bd uogm), and the
  misleading "sending_system_update" log event.
- `callback_handler`: deleted the 22-line commented-out old multi-field
  parser block.
- History-narrating comments fixed in `live_ai_gemini.py` (x3),
  `config.py` (x2), `websocket_routes.py`, `test_tool_contracts.py`;
  untracked TODO removed from `disclaimer_routes.py`.

**Explicitly NOT touched (verified alive or owned elsewhere):**

- `part_*` keys in `manifest_service.py` -- wire-format drift owned by bead
  polyglot-pdf-zun; renaming here would be scope theft.
- `conditional_fields` in form_models -- read by `secretary_context.py` and
  present in the I-90 schemas.
- `scripts/logs.py` + `dev_console_routes.py` -- live dev-console pair
  (bd 2m9); the route is now listed in technical_guide's route table.
- `backend/deploy-new.sh` -- referenced by README.md + DEPLOYMENT.md.
- `planning_documents/` strays -- historical archive area, left as is.

**Assess:** exit-criteria scorecard + fresh-eyes rounds recorded in the PR
body / merge ping per closeout.

## Lessons

- Sweep-agent findings need per-item re-verification: two "dead" candidates
  were alive (`change_fill_language` -- called via the WS message union;
  `deploy-new.sh` -- doc-referenced), and one "intentional standalone" file
  (`test_manifest_generation.py`) was better moved than deleted because its
  coverage was unique. The grep-before-delete discipline caught all three.
- A "deprecated" comment on a method that is still wired into the live
  message union is worse than no comment -- it invites deletion of live code.
  Comments must describe current state (docs/doc-architecture.md rule).

## Doc freshness

- Bumped + edited: `components/config-deployment.md` (removed-settings list;
  fixed the `DISABLE_GEMINI_VAD` row, which claimed `True`/code-constant while
  the code says env-overridable default `false`), `standards/voice-and-vad.md`
  (proactive-audio rule now states the flag is gone),
  `standards/risk-rating.md` (dropped the deleted-siblings note),
  `technical_guide.md` (tunables list; added the dev-only
  `POST /dev/console-log` route row), `scripts/README.md` (removed
  nonexistent `start_testing.*`/`gen_types.sh` sections; added
  `dev-local.ps1`).
- Reviewed + left: the remaining docs flagged STALE by the freshness checker
  (si-reduction, stateless-architecture, terminology, validation-delegation,
  ws-protocol, voice-ai, websocket-routing, tool-call-flow,
  context-compression, jit-schema, auth, pdf-filling, ai-models,
  confirmation-and-audit, hipaa-pii-policy, logging-and-cost). Their tracked
  files were touched by this branch only via comment rewrites / dead-code
  removal (or by earlier branches -- pre-existing staleness); a repo-wide grep
  confirmed none of them reference any removed file or setting, so their
  current-state prose is unaffected.

## Files touched

- Deleted: 5 frontend files, 5 backend files (incl. `cors.json`), 12
  `scripts/` files, 5 root junk files (see What shipped).
- `backend/tests/unit/test_manifest_service.py` -- moved from backend root,
  import fixed.
- `backend/config.py`, `backend/adapters/live_ai_gemini.py`,
  `backend/services/form_filling_service.py`,
  `backend/services/callback_handler.py`,
  `backend/routes/websocket_routes.py`, `backend/routes/disclaimer_routes.py`,
  `backend/tests/contract/test_tool_contracts.py`,
  `backend/scripts/probe_3p1_1007.py` -- dead config/branches + comment
  fixes.
- `docs/components/config-deployment.md`, `docs/standards/voice-and-vad.md`,
  `docs/standards/risk-rating.md`, `docs/technical_guide.md`,
  `scripts/README.md` -- doc alignment.
