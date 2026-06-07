---
date: 2026-06-07
bead: polyglot-pdf-h79
title: "Bug-squash bundle: log-filter attach + settings cache + PII guard (h79+efd+t1c)"
tags: [security, review, performance]
---

## Trigger

A bug-squash run: bundle three small, low-risk backend-hygiene beads -- each
surfaced by an earlier fresh-eyes review and deferred as out-of-scope at the time
-- into one PR rather than spending a full review cycle on each. The three:

- **polyglot-pdf-h79** (bug, P3): the `_BinarySuppressFilter` in
  `backend/utils/logging.py` was attached to loggers (root + the named "noisy"
  ones), so it never ran on the module-named structlog records that reach root
  only by propagation -- which is the bulk of backend output. The suppression was
  effectively inert for most logs.
- **polyglot-pdf-efd** (chore, P3): `get_settings()` built a fresh `Settings()`
  on every call; the native-VAD activity-signal guard in `live_ai_gemini.py`
  calls it per speech event.
- **polyglot-pdf-t1c** (chore, P3): `callback_handler.get_field_value` logged the
  user-speech-derived `spoken_name` label to stdout -> Cloud Run, and the
  `multiple_fields_sent` `fields=` kwarg (field-ID keys) was not covered by the
  static PII guard, so a future `.values()` regression would be silent.

## What shipped

**h79 -- filter on the handler, not the loggers.** A `logging.Filter` runs on the
logger/handler it is attached to and on every record that reaches it; a
logger-level filter does NOT run on records that merely propagate up to root. The
fix attaches `_BinarySuppressFilter` to the root `StreamHandler` (created by
`basicConfig`), where it gates every propagated record uniformly, and drops the
now-redundant per-logger `addFilter` on the noisy loggers (their level cap to
WARNING stays). A defensive fallback re-attaches to the root logger if no handler
is present. New test `backend/tests/test_binary_suppress_filter.py` proves a
>2000-char INFO record emitted through a module-named logger is suppressed, an
ERROR-level long record (rendered traceback) is NOT, and short records pass.

**efd -- cache get_settings.** Added `@lru_cache(maxsize=1)` to `get_settings()`
so all callers share one `Settings` instance. Safe against the test suite: tests
that vary config monkeypatch the module attribute (which replaces the function and
bypasses the cache); the few that call `get_settings()` directly read once.
Documented `cache_clear()` for any future env-mutating test in the docstring.

**t1c -- redact spoken_name, extend the guard.** The `get_field_value` response
log now emits `spoken_name_length=len(spoken_name)` instead of the raw label, per
the "log a length, never the value" rule in the PII policy. Extended
`backend/tests/test_no_pii_logging.py`: `spoken_name` is now a sensitive kwarg (the
redacted `_length` form passes the `*_length` safe-RHS while a regression to the
raw value fails), and a new `_FIELDS_VALUES_LEAK` pattern flags `fields=...values()`
while leaving the safe `fields=...keys()` (field IDs are always-safe) alone. The
`fields=` keys form is left as-is (field IDs are policy-safe). Meta-tests added for
all new shapes.

Decisions made autonomously (defended in the merge ping): the t1c policy call
(redact `spoken_name`; keep `fields=` keys; guard both); `lru_cache` over the
hoist-the-flag alternative (the bead listed both; cache is the smaller, suite-safe
change and improves test-robustness); attaching to all root handlers rather than
only the first.

Nothing deferred; no new beads filed.

## Lessons

A Python `logging.Filter` on a logger does NOT see records that reach that logger
by propagation from a child -- only records emitted directly through it. To filter
uniformly (including propagated records), attach the filter to the **handler**.
This is the kind of subtlety that makes a filter look installed but run on almost
nothing. (Captured in the test and the in-code comment; not promoted to a standards
doc as it is a stdlib-logging fact, not a project convention.)

## Doc freshness

- **Bumped** `docs/components/config-deployment.md` -- its "instantiated per-call"
  prose for `get_settings()` was invalidated by the `lru_cache` change; updated to
  describe the cached-singleton behavior + `cache_clear()` for tests.
- **Bumped** `docs/standards/hipaa-pii-policy.md` -- updated the
  `callback_handler.py` row to record the `spoken_name_length` redaction and the
  `fields=` guard, and bumped both `Last updated` stamps.
- **Reviewed and left** the other docs the freshness checker flagged
  (`logging-and-cost.md`, `ai-models.md`, `voice-and-vad.md`, `risk-rating.md`,
  `context-compression.md`, `terminology.md`, `stateless-architecture.md`,
  `confirmation-and-audit.md`, `websocket-routing.md`, `schema-forms.md`, `auth.md`,
  `technical_guide.md`): they were flagged only because `config.py` /
  `callback_handler.py` got fresh mtimes from this branch's edits (and other files
  edited 2026-06-04..06 before this work), not because this diff invalidated their
  current-state prose. None document `get_settings` caching, the binary-suppress
  filter, or the redacted log line.

## Beads housekeeping

The closeout housekeeping audit flagged `polyglot-pdf-hrn` (P1 harness epic) as a
stale in_progress bead (5 days). It is unrelated to this bundle and is an actively
in-progress epic owned elsewhere; transitioning another track's live epic is out of
this PR's scope, so it was left as-is (noted, not transitioned).

## Files touched

- `backend/utils/logging.py` -- attach `_BinarySuppressFilter` to the root handler; drop redundant per-logger filter; comment + fallback (h79).
- `backend/config.py` -- `@lru_cache(maxsize=1)` on `get_settings()`; docstring (efd).
- `backend/services/callback_handler.py` -- redact `spoken_name` to `spoken_name_length` in the `get_field_value` response log (t1c).
- `backend/tests/test_no_pii_logging.py` -- add `spoken_name` sensitive kwarg + `fields=...values()` leak pattern + meta-tests (t1c).
- `backend/tests/test_binary_suppress_filter.py` -- NEW: handler-attachment + suppression behavior tests (h79).
- `docs/components/config-deployment.md` -- cached-settings prose + stamp bump (efd).
- `docs/standards/hipaa-pii-policy.md` -- callback_handler row + stamp bump (t1c).
