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

**The guard** (`backend/tests/test_no_pii_logging.py`): the existing static guard
would not have caught this — `GUARDED_FILES` listed only `pdf_fill_routes.py` +
`live_ai_gemini.py`, and its scanner matched `_log.*(...)` **kwargs**, not a
positional `print()` f-string. Extended both axes:
- added `callback_handler.py` to `GUARDED_FILES`;
- added `_scan_print_leaks` — flags a sensitive identifier (`arguments`, `value`,
  `text`, `field_values`, …) interpolated into a `print(...)` f-string, while
  leaving safe-metadata interpolations (`{tool_name}`, `{arg_count}`) and constant
  prints alone. Meta-test `test_guard_catches_print_leaks` pins the exact bd-oeq
  shape plus the safe cases.

**Verification:** proved the guard flags the original leak line AND passes the fix;
a full-backend scan with the new scanner found **zero** remaining `print()` PII
sinks (this was the only one). Backend suite: 168 passed (up from 166 — the two new
meta-tests), 2 skipped.

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
- `backend/tests/test_no_pii_logging.py` — added callback_handler.py to
  GUARDED_FILES; new `_scan_print_leaks` + meta-test
- `docs/standards/hipaa-pii-policy.md` — per-surface row → Safe; Enforcement scope
- `docs/journal/entries/2026-06-01-bd-oeq-pii-leak-callbackhandler-on-tool-call-prints-full.md` — this entry
