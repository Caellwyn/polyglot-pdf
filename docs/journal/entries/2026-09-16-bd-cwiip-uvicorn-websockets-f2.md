---
date: 2026-09-16
bead: polyglot-pdf-cwiip
tags: [security, deps, websocket, sprint-23]
surfaces: [backend/requirements.txt]
---

# F2: uvicorn 0.24 -> 0.53, websockets 13/14 -> 16.1.1, harness-gated

Sprint 23 workstream F2 (`docs/sprint_23_security-audit_plan.md`, PF-7's
uvicorn half). Its own bead because this exact bump broke the `/ws/fill`
handshake once: with uvicorn + websockets 14 the sync Vertex `Depends`
blocked the event loop ~9 s before `accept()`. That cause was fixed since
(bd `4hnyq`: the per-connection service builds its adapters in a thread),
and the grouped Dependabot attempt (#822) that tried this bump blind was
reverted (#830) for a different reason -- it also bumped `google-genai`,
whose pin needs `websockets<17`, against a `websockets>=17` line.

## What changed

`backend/requirements.txt`: `uvicorn[standard]==0.24.0` -> `0.53.0`;
`websockets>=13,<15` -> `==16.1.1` (the highest release under
`google-genai==2.8.0`'s `websockets<17.0` constraint; exact-pinned like the
rest of the file). No source change. The Dockerfile CMD, `--no-access-log`
and the logging config are unchanged; what DOES change underneath them, traced
by the outer review: uvicorn's `--ws auto` now selects its sans-io websockets
protocol class instead of the legacy one (same accept/close/reason/receive
semantics for everything this app does; it ignores `ws_max_queue`, which the
app never set, and hardcodes a 10 s close timeout), and the `[standard]` extra
no longer installs `wsproto` (so that `noisy_loggers` entry is dead:
`polyglot-pdf-kq042`). `ws_max_size` (16 MB) and the 20 s ping defaults are
byte-identical to 0.24; `/ws/fill` rides on that keepalive.

## Verification

- **The voice harness, end to end, on the new pins** (criterion 2): the
  local stack (`uvicorn 0.53.0` / `websockets 16.1.1` confirmed from the
  running interpreter; demo-mode frontend; the harness mock user), driven
  from the in-app browser per `tests/e2e/voice-harness/RUNBOOK.md`.
  `runCycle` on the i-90's first field (`a_number`; the runbook's example id
  is from an older kit revision): **PASS** -- first question heard, fill of
  `1234567` in 827 ms, the verify question, confirm (post-yes, authoritative
  `ssConfirmed`), advance to `uscis_account`. The backend log shows the
  Gemini session ready in ~3 s, `update_form_fields` and `confirm_field`
  tool calls applied, zero ERROR lines. (Two earlier passes in the same
  session filled the field too but the harness watched the stale field id;
  the clean run above is the recorded one.)
- `pip-audit -r backend/requirements.txt`: **clean on uvicorn and
  websockets** (criterion 1). It reports `starlette 0.48.0` (PYSEC-2026-248/
  249/1942/2280/2281, fixed in 0.49.1 / 1.1 / 1.3) -- that is
  `polyglot-pdf-5r456` (the starlette/fastapi bump, harness-gated the same
  way), not this bead; noted on that bead.
- Full backend suite on the new pins (both services + repo-level, `-m "not
  external"`): 6518 passed, 287 skipped -- the same skip count as the last
  run on this base, and no test skips on a uvicorn or websockets version
  (grepped); the warning count fell from ~390 to 93, the legacy websockets
  API deprecations gone with the old line.

## Review record

Fresh-eyes (Sonnet) round 1: criteria PASS as recorded; the one gap was the
suite placeholder above, filled once the suite finished; its runbook note
(the plan's listed surface) is in. Opus cross-surface round 1: NO-GAPS.
It traced both pins plus the two consequences above, the google-genai 2.8.0
Live client's use of the websockets API (all five calls resolve in 16.1.1;
the harness PASS is the empirical evidence for that leg), the Starlette
wrapper (close reasons under the 123-byte cap, `receive_text` on a binary
frame, disconnect codes), the deploy path (one pin list, no constraints
file; Dependabot groups pip) and every uvicorn invocation. One latent
PRE-EXISTING finding was folded in because it sits on the sprint's P0 sink:
uvicorn logs `<client> - "WebSocket <path?query>" [accepted]` at INFO on
`uvicorn.error` (not `uvicorn.access`, so `--no-access-log` does not cover
it), and until `?token=` is retired that line carries a live credential; the
`uvicorn.error` entry in `noisy_loggers` was its only, unpinned guard --
`tests/test_logging_access_log.py` now pins it (red with the entry removed).
The reviewer's caveat stands: nothing here ran under uvloop (Windows), so
the Linux path is covered by the read of the installed source and by the
staging deploy, which exists for exactly this.

## Files

`backend/requirements.txt`.
