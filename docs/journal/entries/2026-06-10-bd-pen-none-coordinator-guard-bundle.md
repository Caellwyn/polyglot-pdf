---
date: 2026-06-10
bead: polyglot-pdf-pen
title: "None-coordinator guard + recovery-prompt nits (pen item 1, bpm7)"
tags: [robustness, testing, chore]
---

## Trigger

A second cheap-win cleanup bundle (after the PR #139 ASCII sweep), pulling two
small deferred-nit beads off the ready list. Both are deferred review findings
that were too small to each warrant their own PR cycle.

- **pen** (PR #121 fresh-eyes): three deferred findings; only item (1) is cheap.
- **bpm7** (PR #132 fresh-eyes): three true nits in `test_recovery_prompt.py` +
  `config.py`.

## What shipped

### pen item (1): None-coordinator guard

`CallbackHandler._handle_confirm_field_tool` (`callback_handler.py`) called
`self._request_coordinator.request_next_field_hint()` WITHOUT the
`if self._request_coordinator:` guard that `send_form_update` (same file) has.
`request_coordinator` is a REQUIRED positional, so it is never None in
production -- but a test or racing reconnect that passes None would AttributeError.

**The non-obvious part:** the safe default is NOT "collapse to None". A None hint
takes the `elif not next_hint:` branch -> message `"All fields confirmed."`. An
absent coordinator does not mean the form is complete; reporting completion would
let Gemini wrap the form up early -- exactly the failure class
`bd polyglot-pdf-tks` added the timeout handling to prevent. So the guard collapses
an absent coordinator into the **TIMEOUT** path
(`next_hint_result = HINT_REQUEST_TIMEOUT`), which yields the "could not determine
the next field right now -- do NOT assume the form is complete" message.

Locked by `test_none_coordinator_does_not_signal_completion`, which constructs a
handler with `request_coordinator=None` and asserts the response confirms the field
but does NOT say "All fields confirmed" and does NOT leak the sentinel onto the
wire. Verified (via `git stash` of just the source file) that the test FAILS
without the guard -- it is not a vacuous pass.

**pen items (2) and (3) were split out**, not done here: (2) the adapter
double-response dedup is investigation-gated ("once a live-log confirms whether
both shapes can co-occur in one event"), and (3) is a non-trivial new
CallbackHandler-level integration test. Both moved to a new bead
**polyglot-pdf-ux15** so this bead closes cleanly in one PR (bead/PR contract).

### bpm7: three nits

- (1) `test_recovery_prompt.py`: the ASCII-clean test relied on a bare
  `prompt.encode("ascii")` as its only failure signal. Replaced with an explicit
  `assert all(ord(c) < 128 for c in prompt)` so the check survives a refactor that
  might swallow the exception.
- (2) the `send_context_hint -> _audio_handler` delegation: VERIFIED already
  covered by `test_audio_handler.py::TestContextHint::test_send_context_hint`
  (delegates to `live_ai.send_text_message`) plus the no-live-ai noop. No new test
  needed -- the recovery spec mocks `send_context_hint`, but the delegation itself
  is independently tested.
- (3) `config.py RECOVERY_PROMPT_LEVEL_3`: rewrote the edit-fragile mixed
  single/double-quote concatenated literal into consistent double-quoted lines
  (escape only the two inner speech quotes; apostrophes stay bare). Runtime value
  is byte-identical (verified: len 196, ASCII-only).

## Doc-freshness triage

`closeout_prep` flagged ~12 docs STALE. **All false positives.** The check is an
mtime heuristic. The flags trace to two buckets: (a) files this branch did NOT
touch (`live_ai_gemini.py`, `webFormConnection.ts`, `form_filling_service.py`,
`live_ai_port.py` -- earlier-today churn), and (b) the two files this branch DID
edit, `config.py` and `callback_handler.py`. For (b): the `config.py` change is a
string-literal requoting (byte-identical value) plus a test; the `callback_handler.py`
change is a defensive None-guard that alters NO behavior for any real caller
(coordinator is never None in production). `confirmation-and-audit.md` (which tracks
`callback_handler.py`) documents the `confirmation_method` parsing and the
audit-logging event -- neither of which this change touches; the guard only affects
the next-field-hint request in the never-in-production None case.
`config-deployment.md` does not even mention `RECOVERY_PROMPT_*`. No doc update is
warranted; this note is the prescribed alternative to bumping each doc.

## Verification

- `py_compile` clean on all four edited files.
- Full backend suite: 256 passed, 2 skipped, 3 deselected (external), 0 failures
  (the +1 vs dev's 255 is the new None-coordinator test).
- All four edited files ASCII-clean.

Closes polyglot-pdf-pen, polyglot-pdf-bpm7. Follow-up: polyglot-pdf-ux15.
