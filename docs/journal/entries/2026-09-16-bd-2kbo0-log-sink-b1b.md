---
date: 2026-09-16
bead: polyglot-pdf-2kbo0
tags: [security, logging, pii, health, sprint-23]
surfaces: [backend/tests/test_no_pii_logging.py, backend/main.py, admin_backend/main.py, backend/services/validation_handler.py]
---

# B1b: the exception-message kwarg class, banned on both services; /health says nothing about the config

Sprint 23 workstream B1b (`docs/sprint_23_security-audit_plan.md`, PF-2 P1
and the `/health` half of PF-10). Sequenced after B1a (`wfgjz`, the shared
guard file) and after `e4dt8` (the exception processor: type + frames, never
the message, for `_log.exception()`). This bead adds only what that
processor cannot see: a plain `_log.warning(..., error=str(exc))` carries
the rendered exception message past it, and a `ValueError` raised by a
field validator renders the field VALUE.

## What was found (scar #8: the whole set, before any fix)

- An AST walk over every `_log.*` call in `backend/` and `admin_backend/`
  (production files only) found **199** error-class kwargs: 193 of exactly
  one shape, `error=str(<name>)` (`exc` 140, `e` 51, two one-offs), spread
  over **45 files**; 4 `message=<literal>` (safe); 2 `detail=last_line[:400]`
  in the editor's extractor route. The line-level grep the plan quoted
  ("178 lines") under-counted because 51 of the calls put the kwarg on its
  own line.
- `validation_handler.py:138`, the site the plan named first, is a
  `_log.exception(...)` call -- and the guard's call matcher did not include
  `.exception(` at all, nor the `log.` / `logger.` spellings **38** calls in
  the tree use. Both holes were found by a mutation (below), not by reading.
- The one suite failure the rename produced (a test asserting `error="boom"`)
  exposed a sibling class: three sites logged `traceback.format_exc()` as a
  `traceback=` kwarg, and a formatted traceback ENDS with the message line --
  the processor never sees it. All three now pass `exc_info=True` instead
  (frames + type from e4dt8's processor); `traceback`/`tb`/`stack`/
  `stacktrace` join the banned kwargs.
- The fresh-eyes round found two more holes of the same class in the guard:
  the `.warn(` spelling (three `self._log.warn(..., error=str(e))` sites in
  the adapter, invisible to a matcher that listed only `warning`), and the
  ``-after-underscore trap (`final_error=str(e)` never matched
  `error=`). The matcher now includes `warn`, and the error-class kwargs
  (`error`, `err`, `exc`, `traceback`) match with ANY prefix; `error_type=`
  and `error_count=` still do not, because `=` must follow the word. The
  same round caught the two health probes returning `f"error: {e}"` --
  the Firestore message, verbatim, on an unauthenticated route -- now the
  class name only, pinned in the sink and firms probe tests; a stdout
  `print(f"Final error: {str(e)}")` in the adapter's retry loop (stdout IS
  Cloud Logging); and the `EXCEPTION_LOGGING_SITES` register, which the
  three `exc_info` conversions had to join (its pin went red on the full
  suite, as designed).
- Widening the sweep to `admin_backend/` caught one pre-existing leak there:
  `deploy_webhook.py` logged an unparsable Pub/Sub timestamp verbatim
  (`value=value`).

## What changed

- **193 sites rewritten** to the sanctioned `error_type=type(<name>).__name__`
  by a one-off AST-span rewriter (the keyword node's source span is replaced
  in place so nothing else in the 45 files moves; every file re-parsed
  before it was written). Diagnostic cost: those lines now carry the
  exception CLASS, not its text; `_log.exception()` sites still get the
  frames from e4dt8's processor.
- **The guard** (`backend/tests/test_no_pii_logging.py`): `error`, `err`,
  `exc`, `detail` join `_SENSITIVE_KWARGS` (the `_SAFE_RHS` rule already
  admits literals and `type(`/`len(` wrappers, and `error_type=` is a
  different kwarg name, so the sanctioned shape passes); the call matcher
  now recognises `_log` / `log` / `logger`, bare or on `self`, at every
  level including `.exception(`; the anywhere-sweep walks BOTH services and
  a new test pins that; an EXACT per-site allowlist
  (`_ERROR_KWARG_ALLOWLIST`, file + kwarg text + reason) covers the two
  extractor-stderr `detail=` sites (a blank form PDF, never client data),
  and `test_allowlisted_error_sites_still_exist` fails on a stale entry;
  the meta-test gained the ban/allow pairs for the new class.
- **`/health`**: the public backend returns `status` + the two Firestore
  probes and nothing else (no model ids, audio rates, upload limit, chunk
  size, provider flag, key-presence bit); the `Settings` dependency and its
  three imports went with it. The admin `/health` stays `status` + `service`
  + `app_module` (identity a deploy must confirm; none of it is a model id,
  rate, limit or flag). Both pinned by exact key sets, and the public one
  by a banned-substring scan.
- Docs: two per-surface rows in `hipaa-pii-policy.md`; the `/health` route
  row and the `GEMINI_API_KEY` row in `technical_guide.md`; `ai-models.md`
  no longer says `vertexai` is surfaced on `/health`; `logging-and-cost.md`'s
  probe paragraph now states the whole payload. The uniform rename touched
  45 tracked files, so the freshness check flagged the docs that track
  them; each was re-read against the diff and acked with the reason.

## Verification

- Scar #9: nineteen mutations, one interpreter each, all RED after the
  guard fix: an exception-message print restored; the print scanner's
  error idents removed; a `reason=str(exc)` site restored; the links probe's message
  restored; the exception-site register's own AST backstop narrowed back
  to `backend/` (the second fresh-eyes round noticed it walked one service
  while the sibling sweep now walks two; it walks both now, pinned); a `.warn(` site reverted; `final_error=str(e)` restored; each
  probe's `f"error: {e}"` restored; a file dropped from the exception-site
  register; the websocket route's `format_exc()` traceback restored; a backend site reverted to `error=str(exc)` (the
  `validation_handler.py` P1 site -- GREEN on the first run, which is how
  the `.exception(` hole was found); an admin site reverted; the webhook
  `value=value` restored; `models` added back to the public `/health`;
  `max_upload_mb` added to the admin `/health`; the allowlisted extractor
  site changed under a live allowlist entry; the sweep narrowed to
  `backend/` only. The guard's own meta-test covers the ban/allow pairs.
- Full suite (both services + repo-level): 6509 passed, 287 skipped on the
  fresh-eyes-cleared state of this commit (it was amended after each review
  round; the reviewed states differ by the review fixes listed here), and
  re-run once more after the outer round's fixes: 6510 passed, 287 skipped, 5 deselected, 92 warnings.

Fresh-eyes (Sonnet, read-only): round 1 found the exception-site
register missing the two `exc_info` conversions (the full suite's one red
test), the `.warn(` spelling and the `final_error=` underscore trap in the
guard, the two probes' verbatim Firestore message on `/health`, and a
stdout print of an exception message; round 2: NO-GAPS, carrying four
follow-ups -- the stacked doc stamps (already bd `dfxet`), five WebSocket
error envelopes that send `str(e)` to the client (filed `polyglot-pdf-x7685`),
the register's backstop walking one service (fixed here), and a Firestore
exception message logged under the kwarg name `unverifiable` (filed
`polyglot-pdf-h5529`). The admin audit log's raw `mark_failed(error=str(exc))`
is `polyglot-pdf-lvwvy`. Opus cross-surface: round 1 found the same class
under `reason=str(exc)` (three sites plus a stdout print -- fixed here as
`reason_type`), the inline `structlog.get_logger().warning(` spelling the
matcher still missed (matched now, meta-tested), the third probe helper
(`links_store_status`) still returning the Firestore message (class now,
pinned), a stale comment naming the deleted `gemini_api_key_present` field,
the register's scope sentences in two docs, and the scripts carve-out in
the walker (by path part now). The wider `reason=` kwarg family (twelve
non-literal sites: exception `.reason` tokens, an operator free-text
`body.reason`, a model-supplied `ack.get("reason")`) is a per-site
enumeration of its own, filed as `polyglot-pdf-6inaj`. Round 2 closed all
of round 1 and found the PRINT side of the same set: the guard's
print-sink list (`_SENSITIVE_IDENTS`) had never been given the error
class, and five production prints rendered an exception message to
stdout (the adapter's retry loop twice, the field builder, the two dev
file loggers' own failure lines) -- all class-only now, the list carries
`e`/`exc`/`err`/`error`/`last_exc`/`tb`/`traceback`, and the scanner
exempts the `{type(x).__name__}` shape; plus the README's two sentences
and two `config.py` comments that still said `/health` reports the key
presence bit or the model, and the `_PREFIXED_KWARGS` asymmetry (`detail`,
`tb`, `stack`, `stacktrace` now prefix-tolerant too). Round 3 (confirmation) closed all of round 2 and found one more scope
sentence in `logging-and-cost.md` still naming one service (fixed) plus
four nits filed: three precision gaps in the guard itself
(`polyglot-pdf-o2uyn`: the per-line RHS read that forced the two literal
reformats, the allowlist's substring match, the class-only exemption's
tail) and a pre-existing rationale sentence in `validation-delegation.md`
(`polyglot-pdf-68shs`). NO-GAPS on the prose fix.

## Lessons

- **A mutation that stays green is the finding.** The bead's headline site
  was a `_log.exception()` call, and the guard had never matched that
  level; reading the guard did not show it, reverting the site did.
- **Enumerate by AST, not by grep, when the kwarg can sit on its own
  line.** The grep count was 178; the AST count was 199.
- **Widening a sweep is itself a finding generator.** Adding
  `admin_backend/` surfaced a leak on the first run.

## Files

`backend/tests/test_no_pii_logging.py`, `backend/main.py`,
`backend/tests/unit/test_health.py`, `admin_backend/tests/unit/test_admin_health.py`,
`admin_backend/routes/deploy_webhook.py`, 45 production files (the rename),
`docs/standards/hipaa-pii-policy.md`, `docs/technical_guide.md`,
`docs/standards/ai-models.md`, `docs/standards/logging-and-cost.md`,
`docs/freshness/*.ack`, `backend/utils/logging.py` (the register),
`backend/utils/confirmation_logger.py`, `backend/services/firms.py`.
