---
date: 2026-08-22
bead: polyglot-pdf-0dsv4
title: "fix(audit): the disclaimer acceptance is durable -- and shipped broken first"
sprint: 20
tags: [conventions, testing, doctrine]
---

## Trigger

Filed after the maintainer asked, during the s1iex.7 review, where the
acceptance is saved and how it matches to a session. Tracing it produced an
uncomfortable answer: it was a single structlog line and nothing else, so the
record that a user accepted the LEGAL TERMS aged out with the Cloud Run log
bucket, while the record of what they TYPED into a field went to Firestore AND
a per-session file. Backwards for an evidence trail.

## What shipped

- `log_disclaimer_acceptance()` writes through the same sink the confirmations
  use, keyed on `form_session_id`. No new retrieval path was needed: the
  existing query is already keyed that way, so `read_confirmation_log()`
  returns the acceptance and the confirmations as ONE timestamp-ordered
  session record.
- FAIL-OPEN by design: a sink outage logs and continues. Losing one audit
  record is bad; blocking every user from starting their form is worse.
- `firm_id` written as `None` (maintainer decision): this route carries no auth
  token, so the firm cannot be read here, but the KEY is written so the
  collection has one shape and needs no migration when firm auth lands.
  `firm_of_events()` recovers it from the session's other records meanwhile.
- 12 tests, including an exact-key ALLOWLIST mirroring the one that guards the
  confirmation events, and a pin that the new event cannot match the
  kit-deletion guard.

## Lessons

- **IT SHIPPED COMPLETELY BROKEN, AND EVERY TEST WAS GREEN.** The route handler
  is itself named `log_disclaimer_acceptance`, so
  `from ..utils.confirmation_logger import log_disclaimer_acceptance` was
  SHADOWED by it at import time. The call resolved to the route handler, raised
  `TypeError` on the kwargs, and my own fail-open `except` swallowed it. In
  production it would have logged a failure on EVERY acceptance -- a 100%
  failure rate wearing the costume of transient degradation.
- **A test whose SETUP recreates the bug cannot detect it.** Both route tests
  monkeypatched the shadowed name, so they patched over the defect and passed
  either way. This is a NEW failure mode for me, distinct from a vacuous
  assertion: the assertions were fine. And a mutation test would not have
  helped -- the wiring was never right, so there was nothing to revert. The
  fix that generalizes: patch the collaborator IN ITS OWN MODULE and assert it
  is reached THROUGH the caller, plus a module-level IDENTITY assertion that no
  monkeypatch can satisfy.
- **A fail-open `except` is a place bugs go to hide.** It exists so a sink
  outage cannot block a user -- correct -- but it swallowed a permanent wiring
  error just as quietly. Wiring errors (`TypeError` at the call boundary) now
  log under their own event name, with a note that they fail on every request.
  The reviewer checked the inverse risk too: every call inside the util already
  swallows its own exceptions, so a `TypeError` can only reach the route from a
  signature mismatch -- the split is correctly scoped, not over-broad.
- **Splitting a helper can leave the original dead.** I split `firm_of_events`
  out of `resolve_firm_for_session` and wired only the new one, leaving the
  wrapper unused with two comments pointing readers at unreachable code.
  Deleted, references re-pointed.
- **Refusing to answer beats guessing on an evidence path.** Firm attribution
  originally took the first `firm_id` found. Two firms on one session means
  something is wrong upstream, and returning one would launder a data problem
  into a confident wrong answer. It now logs the conflict and returns None.

## Doc freshness

- `docs/standards/confirmation-and-audit.md`: **UPDATED**. It described the
  acceptance record's CONTENT but never said where it was stored -- which was
  the gap. Now states the sink, the join, the fail-open property, and why
  `firm_id` is None today. Stamp bumped.

## Files touched

- `backend/utils/confirmation_logger.py` (`log_disclaimer_acceptance`, `firm_of_events`)
- `backend/routes/disclaimer_routes.py` (aliased import, fail-open call, split logging)
- `scripts/read_confirmations.py` (firm attribution in `--summary`)
- `backend/tests/unit/test_confirmation_firestore_sink.py`, `test_disclaimer_acceptance_route.py`
- `docs/standards/confirmation-and-audit.md`
- `docs/journal/entries/2026-08-20-bd-0dsv4-durable-acceptance.md` (this entry)
