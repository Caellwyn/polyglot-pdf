---
date: 2026-06-01
bead: polyglot-pdf-oeq
title: "PII leak: CallbackHandler.on_tool_call prints full tool-call arguments (incl. field values) to stdout"
tags: [security, hotfix, testing]
---

## Trigger

Copilot's round-1 review of the docs-audit PR (#45) flagged that
`CallbackHandler.on_tool_call` *unconditionally* did
`print(f"Arguments: {arguments}")`. For `update_form_fields` / `confirm_field`,
those arguments include field **values** — A-numbers, names, addresses, DOB. On
Cloud Run, stdout → Cloud Run logs, so this was a **live production PII/PHI leak**
violating `docs/standards/hipaa-pii-policy.md`. The docs PR only *documented* the
leak (and filed this P1 bead); this bead fixes the code.

## What shipped

**The fix** (`backend/services/callback_handler.py`): replaced the whole
`print(...)` debug block — which sat directly under a HIPAA-policy comment that
says "Production: NEVER log field values," then violated it — with a compliant
`_log.info("tool_call_received", tool_name=…, arg_keys=sorted(args.keys()),
arg_count=…, session_id=…)`. It logs the tool name + argument **keys** + count,
never the values. Full-argument capture for local debugging was already handled by
the adjacent `_dev_log.log_tool_call`, which is correctly `.env.DEV`-gated — so the
`print` was pure redundant leak, not a needed signal.

**A second leak, found in review** (`backend/adapters/live_ai_gemini.py`): both
Copilot and fresh-eyes caught that the tool-response logging block did
`print(f"Response: {resp.response}")` — dumping the full tool response to stdout.
A `get_field_value` / `get_form_status` response carries field **values**, so this
was the same leak class, arguably worse. Fixed the same way: log `tool` +
`response_chars` + `estimated_tokens` via `self._log.info("tool_response_sent",
…)`, never `resp.response`. (The token-estimate purpose only ever needed the
char count, not the body.)

**The guard** (`backend/tests/test_no_pii_logging.py`): the existing static guard
would not have caught either leak — `GUARDED_FILES` covered `live_ai_gemini.py`
but its scanner matched only `_log.*(...)` **kwargs**, not a positional `print()`.
Extended both axes:
- added `callback_handler.py` to `GUARDED_FILES`;
- added `_scan_print_leaks` — flags a sensitive base name (`arguments`, `value`,
  `text`, `response`, `resp`, …) interpolated into a `print(...)` f-string,
  **including via `.attr`/`[idx]` access** (`{resp.response}`) and across
  **multi-line** print calls (paren-depth tracked like the `_log` scanner). Safe
  metadata (`{tool_name}`, `{response_chars}`) and constant prints don't flag.
  Meta-test `test_guard_catches_print_leaks` pins both leak shapes + the safe and
  near-miss cases (`response_chars`, `pprint(...)`).

**Verification:** proved the guard flags BOTH original leak lines AND passes both
fixes; a full-backend scan with the broadened scanner now finds **zero** remaining
`print()` PII sinks. Backend suite: 168 passed (up from 166 — the two new
meta-tests), 2 skipped.

**Deferred** (`polyglot-pdf-t1c`, P3): fresh-eyes noted two pre-existing
`_log.*` kwargs now in a guarded file — `fields=` (field IDs, policy-safe) and
`spoken_name=` (user-speech-derived label). Filed for a policy decision +
optional guard coverage rather than fixed here (out of scope; not field values).

**Doc:** flipped the `hipaa-pii-policy.md` per-surface row for
`callback_handler.py` from "⚠️ Known leak — oeq" to **Safe**, and updated the
Enforcement section (the guard now covers 3 files + the `print()` shape).

No findings deferred.

## Lessons

A static log-safety guard is only as good as its **sink coverage**: this guard
watched `_log.*` kwargs but not `print()`, so a leak hid in plain sight directly
beneath a correct policy comment. Two generalizable points: (1) audit *every* sink
that reaches stdout (print, `logging.*`, `sys.stderr.write`), not just the project
logger; (2) a policy **comment** next to code is not enforcement — the bare `print`
sat under an explicit "NEVER log field values" banner for who knows how long. The
mechanical guard is what actually holds the line. (Captured in the updated
Enforcement section of `hipaa-pii-policy.md`, which now names the coverage scope
explicitly.)

## Doc freshness

`docs/standards/hipaa-pii-policy.md` — updated the per-surface table + Enforcement
section to current state; stamp already at 2026-06-01 (same-UTC-day edit, no bump
needed). Freshness checker: clean, no STALE docs. No other docs tracked the changed
code; CLAUDE.md unaffected.

## Files touched

- `backend/services/callback_handler.py` — removed the leaking `print()` block;
  replaced with key/count-only `_log.info`
- `backend/adapters/live_ai_gemini.py` — removed `print(f"Response: {resp.response}")`
  tool-response dump; replaced with size-only `_log.info("tool_response_sent", …)`
- `backend/tests/test_no_pii_logging.py` — added callback_handler.py to
  GUARDED_FILES; new `_scan_print_leaks` (attr-access + multi-line aware) + meta-test
- `docs/standards/hipaa-pii-policy.md` — per-surface row → Safe; Enforcement scope
- `docs/journal/entries/2026-06-01-bd-oeq-pii-leak-callbackhandler-on-tool-call-prints-full.md` — this entry
