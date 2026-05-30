---
date: 2026-05-30
bead: polyglot-pdf-8x5
title: "restart_gemini_session passes 4 non-existent callback methods -> AttributeError on every WS restart"
tags: [hotfix, testing]
---

## Trigger

`bd polyglot-pdf-8x5`, discovered from `polyglot-pdf-e9v` (the syntax-broken
`form_filling_service.py` on dev+main that crashed `/ws/fill`). Surfaced
2026-05-30 by fresh-eyes review of PR #19. Pre-existing on origin/dev; **not**
introduced by the e9v dedup — it was latent because the module did not import
until e9v, so this code path had never run in prod or in tests.

`FormFillingService.restart_gemini_session` called
`self._live_ai.set_callbacks(...)` with four handlers that do not exist on the
class — `handle_form_update`, `handle_transcript`, `handle_audio`,
`handle_tool_call` (grep `def handle_form_update` etc. → empty). It also
`await`ed `set_callbacks`, which is a **synchronous** method. Either bug raises
the moment the method body reaches that line.

## What shipped

**Reachability:** `websocket_routes.py:463` calls `restart_gemini_session` on a
client `restart_gemini_session` message, wrapped in a `try/except` that logs
`restart_gemini_session_failed`. So the restart **failed silently** rather than
crashing the socket — any feature relying on mid-session Gemini restart (e.g. a
section switch or language change that triggers a restart) was broken on this
path with no surfaced error.

**`backend/services/form_filling_service.py`** — rewrote the `set_callbacks`
call in `restart_gemini_session` to mirror the working session-creation call
(`form_filling_service.py:155`):
- `self.handle_*` → `self._callback_handler.on_form_update` /`.on_transcript`
  /`.on_audio` /`.on_tool_call` (the real bound methods).
- Dropped the erroneous `await` — `set_callbacks` is `def`, not `async def`.
- `on_transcript` is now passed **unconditionally** (previously nulled when
  `_send_transcript` was false); whether transcripts are emitted is gated by
  `enable_transcripts=self._send_transcript`, matching the creation path. This
  is the adapter's contract (`live_ai_gemini.py:262`).
- Added a guard: if `self._callback_handler is None` at restart, raise
  `RuntimeError` loudly rather than registering bad callbacks.

**`backend/tests/unit/test_restart_gemini_session.py`** (new, 4 tests) — the
regression coverage the bead asked for. A `MagicMock` `live_ai` keeps
`set_callbacks` **synchronous**, so a re-introduced `await` fails the test
(awaiting a MagicMock return raises `TypeError`); a real `CallbackHandler` lets
the tests assert the registered callbacks are identity-equal to the handler's
`on_*` methods. Also covers the transcripts-disabled gating, the
already-active no-op, and the missing-handler guard. **Verified the tests
reproduce the original `AttributeError: 'FormFillingService' object has no
attribute 'handle_form_update'`** when the fix is reverted.

Nothing deferred.

## Lessons

- A `try/except` around an effectful call (`websocket_routes.py:467`) turned a
  hard `AttributeError` into a **silent feature outage**. The broad catch was
  doing its job (don't crash the socket) but masked code that had literally
  never executed. Latent-but-reachable code under a broad catch is exactly what
  a unit test that *invokes the method with a mock* would have caught — and now
  does.
- When two call sites do "the same thing" (session create vs. restart), drift
  between them is a standing hazard. The restart path was written against a
  stale handler-naming scheme and never reconciled. The fix makes restart a
  faithful mirror of creation; a shared private helper would prevent future
  drift but was out of scope here.

## Doc freshness

`check_doc_freshness.py`: "No docs to check" (`docs/components/` +
`docs/standards/` are still the empty starter skeleton under the docs-reorg
epic `polyglot-pdf-gfb`). No tier-1/tier-2 doc covers this internal method yet.

## Files touched

- `backend/services/form_filling_service.py` — `restart_gemini_session` registers the real `CallbackHandler.on_*` callbacks, drops the erroneous `await`, always passes `on_transcript`, guards a missing handler.
- `backend/tests/unit/test_restart_gemini_session.py` — new; 4 tests asserting correct callback registration + sync call + gating + guard.
- `docs/journal/entries/2026-05-30-bd-8x5-restart-gemini-session-passes-4-non-existent.md` — this entry.
