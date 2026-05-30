---
date: 2026-05-30
bead: polyglot-pdf-hjo
title: "[P1][SECURITY] Production logs leak PII/PHI: field values + user transcript at INFO -> Cloud Run/BigQuery"
tags: [security, hotfix, testing]
---

## Trigger

`bd polyglot-pdf-hjo`. Surfaced while researching `b11` (the hipaa-pii-policy
doc): an exploration of the actual logging code found that the repo's stated
policy ("NEVER log field values/PII/PHI") was **contradicted by the code** —
several INFO/WARNING-level log calls emitted real user data. INFO/WARNING are
always emitted in production, and the backend logs to stdout → Cloud Run →
BigQuery, so for an immigration-form app (A-numbers, names, addresses, DOB)
these were **live HIPAA/PII violations**, not hypotheticals. The maintainer
chose to fix the code now (prod is contained — low/no real PII traffic yet) so
the policy doc would describe reality.

## What shipped

Redacted **13 log sites** across two payload-handling files to metadata-only
(field IDs / `*_length` / `*_type` / `*_count`), preserving debuggability while
removing the value:

**`backend/routes/pdf_fill_routes.py`** — the worst offender, `pdf_fill_sample_values`
(INFO), literally logged the first 5 `field_id:VALUE` pairs ("DEBUG: …to verify
data is coming through", but at INFO). Now logs `sample_field_ids`. Also fixed
`radio_selected` / `radio_option_not_found` / `checkbox_*` which logged `value=`,
`selected_value=`, `target_value=`, `original_value=`, `selected_values=`, and
the `available_options` set → all reduced to ids / counts / types.

**`backend/adapters/live_ai_gemini.py`** — `GEMINI_TRANSCRIPT_RECEIVED` logged
`text_preview=transcription.text[:50]` (the first 50 chars of **user speech** —
e.g. "My alien number is A0…"); dropped, kept `text_length`. Five `message=text[:N]`
slices in `send_client_content` / `TEXT_MESSAGE_SENT` / queue-flush (user-turn
and instruction text) → `message_length`.

**`tests/test_no_pii_logging.py`** (new) — a **source-grep guard** over the two
files: it fails if any value/transcript-logging pattern returns, so a regression
trips a test rather than silently leaking to BigQuery. Placed in the repo-level
`tests/` (not `backend/tests/`, which has collection issues) because it's a
static scan needing no backend import. It immediately earned its keep — caught a
**multi-line** `radio_selected` `value=value,` leak that the single-line manual
sweep had missed.

**Verified SAFE, no change** (documented for the `b11` doc): `confirmation_logger.py`
(ids/names/methods, explicit NO-PII), `token_file_logger.py` (counts/costs),
frontend `metrics.ts` (local-only, never transmitted), `log_schemas.py` (TypedDict
excludes values, "NEVER include field values!"), `disclaimer_routes.py`
(session/lang/ts + ip/user_agent — fingerprinting, not PHI). `dev_file_logger.py`
intentionally logs PHI but is gated by `.env.DEV` (gitignored, absent in prod).

Full suite: **152 pass** (incl. the 3 new guard tests).

Nothing deferred.

## Lessons

- **Document reality, not intent — and verify the intent against the code.** The
  repo *had* a "never log PII" policy and several loggers that honored it, which
  made it easy to assume the whole codebase did. Writing the policy doc forced an
  audit of the actual `_log.*` calls, which is where the violations hid. A policy
  doc is worth little until something *enforces* it — hence the grep guard, which
  turns the policy into a test.
- **Static grep guards beat runtime mocks for "never log X" rules.** The guard
  needs no backend import (so it dodges the `backend/tests/` collection breakage),
  runs in milliseconds, and catches multi-line log calls a human sweep misses.
  The trade-off — it can't catch a value logged under a *new* kwarg name — is
  acceptable for a regression fence on known sites; widen the pattern list as new
  log shapes appear.
- **INFO is production.** A comment saying "DEBUG: …" on an `_log.info(...)` call
  is not debug-gated — it ships. Don't trust the comment; check the level.

## Doc freshness

`check_doc_freshness.py`: "No docs to check" (the tier-2 `standards/` doc that
will *track* these files — `hipaa-pii-policy.md`, `bd b11` — isn't written yet;
it's the next bead and will carry the `**Tracks:**` line for
`pdf_fill_routes.py` / `live_ai_gemini.py` logging). No existing tracked doc
covers these files, so nothing went stale.

## Files touched

- `backend/routes/pdf_fill_routes.py` — redacted 9 value-logging sites to ids/counts/types.
- `backend/adapters/live_ai_gemini.py` — dropped transcript `text_preview`; 5 `message=text[:N]` → `message_length`.
- `tests/test_no_pii_logging.py` — new source-grep guard (+ meta-test).
- `docs/journal/entries/2026-05-30-bd-hjo-…md` — this entry.
