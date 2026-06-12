---
date: 2026-06-12
bead: polyglot-pdf-c5t
title: "Adopt Live API GoAway handling: detect + forward + dispatch (epic l3a)"
tags: [refactor, testing]
---

## Trigger

Epic l3a (Live API session management) remaining work, picked after the voice
round-trip fixes. The Gemini Live server sends a `GoAway` message (with
`time_left`) before it terminates a connection -- a periodic server lifecycle
reset. The app previously only saw the close AFTER it happened (as
`ConnectionClosed` / `APIError` in the receive loop), so a mid-turn drop was
abrupt. Bumped P3 -> P2 because graceful reconnect is now an active maintainer
ask (mid-section drops on the demo). I hit GoAway `1008`/`1011` closes directly
in this session's probes, so it is current and real.

## What shipped

End-to-end DETECT -> FORWARD -> DISPATCH of the GoAway signal:

- **Adapter** (`live_ai_gemini.py`): the receive loop reads `event.go_away`, logs
  `time_left` (structlog, no PII), and fires a new optional `on_go_away` callback.
  Detection is best-effort and never breaks the loop -- the real close still
  arrives later and takes the existing graceful path. SDK shape verified against
  google-genai 2.8.0: `types.LiveServerGoAway.time_left` is `Optional[str]`.
- **Service + CallbackHandler**: `on_go_away` forwards
  `{"type":"go_away","time_left": ...}` to the client. Wired into the two real
  `set_callbacks` sites (primary + session-restart). Backend stays STATELESS --
  the client owns the reconnect.
- **Frontend** (`webFormConnection.ts`): a `case "go_away"` routes to an optional
  `onGoAway` callback. Unlike `idle_timeout` it does NOT set the no-reconnect flag
  -- a GoAway is a server reset, so reconnect IS wanted.

**Scope = detect + surface.** The pre-emptive-reconnect POLICY (act on the signal:
silent resume vs. user indicator vs. timing off `time_left`) is a genuine UX/product
decision that coordinates with bd vmxx (silent resume) and the bd jf6w
connection-timeout epic, so it was filed as a follow-on: **bd polyglot-pdf-l3a.2**.

**Tests (10 new):** 6 backend (adapter detect->callback incl. the no-callback
logged-only path; CallbackHandler forward incl. null `time_left` / send-failure /
no-websocket) + 4 frontend (dispatch, null time_left, no spurious no-reconnect
flag, no-callback). Backend non-external suite 290 pass (was 284); new FE suite 4
pass.

Fresh-eyes assess: [recorded in the merge ping].

## Lessons

- **`if self._websocket:` is a latent bug for a Starlette WebSocket.** A Starlette
  `WebSocket` is Mapping-like (`__len__`), so an empty one is falsy -- and a
  `MagicMock(spec=WebSocket)` is falsy too, which is how a test caught it. The
  callback guard must be `is not None` ("is a websocket present"), an identity
  check, not truthiness. Applied to the new `on_go_away`; the older callbacks use
  the looser form but happen not to be exercised the same way.
- **Verify SDK message shapes against the installed package, not memory.** Read
  `types.LiveServerMessage.go_away` / `LiveServerGoAway.time_left` off google-genai
  2.8.0 directly before coding, per the repo's genai-docs rule.

## Doc freshness

- Bumped with content: `docs/components/websocket-routing.md` (new GoAway forward
  message, alongside `idle_timeout`), `docs/components/voice-ai.md` (`on_go_away`
  in the `set_callbacks` list).
- Pre-existing staleness left untouched (this branch did not change what they
  describe -- their newer tracked-file mtimes are PR #156's `13:31`/`13:38`):
  `auth.md`, `config-deployment.md`, `context-compression.md`, `schema-forms.md`,
  `tool-call-flow.md`, `ai-models.md`, `confirmation-and-audit.md`,
  `hipaa-pii-policy.md`, `logging-and-cost.md`, `risk-rating.md`,
  `stateless-architecture.md`, `terminology.md`, `testing.md`.

## Files touched

- `backend/adapters/live_ai_gemini.py` -- `_on_go_away` field + `set_callbacks`
  param + receive-loop detection.
- `backend/services/callback_handler.py` -- `on_go_away` WS-forward.
- `backend/services/form_filling_service.py` -- wire `on_go_away` (2 sites).
- `backend/tests/unit/test_live_ai_gemini.py`,
  `backend/tests/test_callback_handler.py` -- 6 backend tests.
- `frontend/src/webFormConnection.ts` -- `onGoAway` callback + `case "go_away"`.
- `frontend/src/webFormConnection.goaway.test.ts` -- new (4 FE tests).
- `docs/components/websocket-routing.md`, `docs/components/voice-ai.md`.
