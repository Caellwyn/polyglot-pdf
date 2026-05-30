---
date: 2026-05-30
bead: polyglot-pdf-e9v
title: "[P1] form_filling_service.py syntax-broken on dev+main (botched merge dup) — crashes /ws/fill"
tags: [hotfix, postmortem, testing]
---

## Trigger

Bead `polyglot-pdf-e9v`, surfaced while investigating `od1` during the PR #16
docs review. `backend/services/form_filling_service.py` did not parse
(`SyntaxError` ~line 224) on **both** `origin/dev` and `origin/main`. Root
cause: merge `2966c48` ("Merge branch shared-audio-stream and resolve
conflicts") resolved a conflict in `send_disclaimer_message()` by **keeping
both sides** and deleting the conflict markers, duplicating six lines — the
duplicated `.format()` kwargs (two `disclaimer_text=` in one call with no
separating comma) are the actual `SyntaxError`.

## What shipped

**The fix** ([`form_filling_service.py`](../../../backend/services/form_filling_service.py)):
removed the 6 kept-both-sides lines from `send_disclaimer_message()` — one
copy each of the docstring `disclaimer_text` line, the `if not self._live_ai`
guard + its `_log.warning`, the two `DISCLAIMER_INITIATING_MESSAGE.format()`
kwargs, and the `_log.info` line. Net diff: −6, +0 — exactly the +6 the merge
added to this file.

**Blast radius (why it was latent, not loud):** `dependencies.py` imports
`FormFillingService` lazily inside the `get_form_filling_service` factory, so
`import backend.main` succeeds and the app boots. The factory only runs on the
first `/ws/fill` connection — so a real connection would have crashed on
disclaimer send. The un-importable module also broke pytest **collection** for
every test importing it, silently disabling ~29 tests.

**No production impact (confirmed):** the demo Cloud Run image is built from
the local working tree (`deploy-all.sh` → `gcloud builds submit`, not a git
checkout of a branch), and the live demo works — so the running artifact has a
valid file. The break is latent on the branches; the next deploy from
dev/main, or the first `/ws/fill` disclaimer-send against that code, would
crash. Severity stays P1 (branch correctness) with no live outage.

**Verification (against the worktree copy):** `py_compile` OK, `import` OK,
collection 120 → **149** with **0 collection errors** (the 5 previously
un-collectable test files revived: `test_disclaimer_flow`,
`test_empty_tool_call_validation`, `test_idle_timeout`, `test_jit_schema_loading`,
`test_section_switching`). Full suite: 138 passed, 9 failed, 2 skipped.

**Re-scan for other kept-both-sides damage:** the merge also touched
`VoiceOverlay.tsx`, `VoiceOverlayMobile.tsx`, `LanguageSelectionModal.tsx`.
Scanned the two named in the merge message for duplicate adjacent statements —
none. Repo-wide conflict-marker grep — only in `test_output*.txt` dumps and a
release doc's example diff, no source. The damage was confined to this one file.

**Triage of the 9 collect-but-fail tests (none caused by this change):**
- **3 → `od1`** (already tracked; e9v blocks it): `WS_IDLE_TIMEOUT_SEC == 60`
  asserts vs actual `120`. These are the asserts `od1` describes; they were
  silently not running because this file broke collection.
- **5 → [`0rx`](#)** (filed, discovered-from e9v): rotted unit tests that went
  dead in Dec and drifted against later code — `test_callback_handler` (×3, the
  `_handle_complete_section` → `_handle_switch_section` sections-canon rename),
  `test_jit_schema_loading::test_update_includes_next_field_schema`,
  `test_websocket_fill_web::test_websocket_schema_initializes_session`. `0rx`
  also covers a hygiene fix: the tracked, test-mutated
  `logs/confirmations/fss_test_12345.jsonl`.
- **1 → [`4cm`](#)** (filed, discovered-from e9v, parented to AI-model epic
  `9nl`): `test_live_ai_gemini_real_connection` — the API key works (socket
  connects) but the server returns `1008` rejecting cascade model
  `gemini-live-2.5-flash-preview` (the `MODEL_LIVE` default). Dormant because
  `USE_NATIVE_AUDIO=True`, but the cascade fallback name is stale.

**Tooling fix shipped in the same PR:** the `/closeout` skill assumed a
repo-root `venv/` and `pytest tests/`; this repo's interpreter is
`backend/.venv` in the **main repo only** (worktrees have none) and tests are
under `backend/tests/`. Rewired the skill to resolve the interpreter via the
git common dir (works from any worktree) and corrected the pytest invocation.

## Lessons

- **A conflict "resolved" by keeping both sides leaves no markers but breaks
  the file** — and a lazy import can hide it from boot and from `import`-smoke
  checks, so it surfaces only on the first real request *and* silently kills
  test collection. After any merge that resolved conflicts, `py_compile` /
  collect the touched files, don't just boot the app.
- **`gcloud builds submit` builds from the local tree, not a branch** — so
  "main is broken" does not imply "prod is broken." Confirm what the running
  artifact was built from before assigning outage severity.
- **A broken module that blocks pytest *collection* silently disables every
  test that imports it** — a green-looking run can be hiding dozens of tests
  that never ran. Watch the collected-count, not just pass/fail.

## Doc freshness

`check_doc_freshness.py`: no tier-2 docs to check yet (`docs/components/` and
`docs/standards/` are still empty under the docs-reorg epic). No component doc
tracks `form_filling_service.py` yet, so nothing to bump. No CLAUDE.md change.

## Files touched

- `backend/services/form_filling_service.py` — removed 6 duplicated lines in `send_disclaimer_message()`.
- `.claude/skills/closeout/SKILL.md` — aligned venv/test paths with this repo (separate commit).
- `docs/journal/entries/2026-05-30-bd-e9v-...md` — this entry.
