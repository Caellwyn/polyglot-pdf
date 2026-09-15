---
date: 2026-09-15
bead: polyglot-pdf-v8l6m
title: "audit(logging): B2 -- the live Cloud Logging + BigQuery PII sweep, in-process, and what the first 30-day run found"
tags: [security-audit, logging, audit-scripts, testing]
---

## Trigger

Sprint 23 (the security + data-leak audit, epic `polyglot-pdf-uijam`, plan
`docs/sprint_23_security-audit_plan.md`), workstream B2, threat actor T3.
B0 stopped the WebSocket credential from reaching the access log and the
request log; B1a/B1b guard the app stream statically. Nothing READ the
live logs back to prove the sinks were clean after the fix, and bd
`polyglot-pdf-yqg`'s "BigQuery field-value scan returns zero" criterion had
never been exercised. A Sonnet builder wrote the detectors, the formatter
and their tests in an isolated worktree; the orchestrator rewrote the
transport, ran the live sweep and the closeout in-session after the
builder's shell commands were found to be opening console windows on the
maintainer's desktop.

## What shipped

`scripts/audit/log_pii_sweep.py`: read-only under the operator's
application-default credentials, `--project` required, refused for the
dead project and when it differs from the active gcloud configuration's
project; refuses `--log-http` and any debug verbosity (case-insensitive)
and a truthy `CLOUDSDK_CORE_LOG_HTTP`; `--retention-days` must be >= 1 (an
empty window would report a false "zero hits").

**The transport is in-process only.** The Cloud Logging `entries.list`
REST endpoint through `google-auth` + `requests` and the `google-cloud-
bigquery` client; the script spawns nothing. Credentials are loaded FROM
the ADC file through the typed constructor for its kind (`authorized_user`
or `service_account`; anything else is refused), never through
`google.auth.default()`, which shells out to `gcloud config get project`
when the ADC file carries no project id -- a property test drives the real
loader on the gcloud-SDK path with `subprocess.Popen` raising, and reverting
to the default lookup fails it with exactly that gcloud command. The project check reads gcloud's
`active_config` + `configurations/config_<name>` from disk. Each of the
three services' three streams (`stdout`, `stderr`,
`run.googleapis.com/requests`) is read in daily windows over the measured
30-day retention, every window walked to the end with page tokens (a busy
day is never truncated; more than 50 pages in one window is reported, not
skipped); HTTP 429 / 5xx and connection-level failures retried three times with
backoff (the read quota is per minute and a full sweep trips it); after the
budget the window is INCOMPLETE, never a raw traceback.

Detectors, deliberately tight: `[?&]token=` in `httpRequest.requestUrl`; a
two-segment JWT; the one-dot link-token shape only inside a URL span (a
bare `key=<40+ chars>` pair counts as URL context); an A-number with explicit
lookarounds (`\b` fails after an underscore); SSN; email; phone in NANP
shape only (optional +1, parenthesised or bare area code, area code and
exchange start with 2-9, separators all-or-none and identical, no word or
hyphen neighbours -- the first live run's two
phone hits were a 10-digit epoch timestamp inside an error message and a
UUID fragment inside a request id, and both shapes are now negative cases);
DOB-shaped dates only in `jsonPayload` string fields -- walked through
nested dicts AND lists (a `fields=list(...)` kwarg carrying answers instead
of keys is the leak the static guard exists for). The same detectors run
over every STRING column each telemetry view's LIVE SCHEMA reports, named
explicitly (never `SELECT *`), every row read (a ceiling of 100000 rows is
reported as TRUNCATED and makes the run INCOMPLETE); a view the project does
not have is ABSENT, not UNREACHABLE, and a view with no string column is
reported as "nothing read", never as clean.

Output is one choke point, `format_report`: counts per (service, logName,
detector, jsonPayload key) plus insertIds and timestamps -- never matched
text -- and every free-text error string (an API error can echo a filter
or a row) passes through `scrub()`, which merges overlapping detector spans
(a JWT is also the head of a link-token shape), redacts each region and
caps the length. Exit 0 ran, 2 refused, 3 a query could not complete.

`tests/test_log_pii_sweep_detectors.py` (97 tests): a positive and a
negative case per detector; the sentinel cannot reach the report through
a Hit, a BigQuery hit, or either error channel; pagination, the 429 retry,
the page ceiling, the connection-failure and token-refresh-failure paths
(the latter not retried), scrub over overlapping spans, the typed ADC-file load, the config-file project read, the
missing-ADC and unknown-kind refusals, the project mismatch refusal, the
window bound, the case-insensitive verbosity guard; the substring pins that
the module never imports `subprocess` or names the google.auth default
lookup; and the property behind them -- the real credential loader and the
entries walker driven with `subprocess.Popen` raising.

## What the first complete run found (2026-09-15, redacted)

Run 2026-09-15 ~22:06-22:12 UTC, project `polyglot-demo-aa709`, 30-day
window, exit 0 (every window completed after retries), 332 s, one process,
no child process (a guard that raises on any spawn was active). Re-run on
the shipped code after the review-round changes (~22:24-22:28 UTC, 282 s,
same guard): identical hit groups and counts. The BigQuery half was re-run
once more after the outer review (2026-09-15 ~22:55 UTC, 7 s) because the
first runs had swept ZERO cells: a name allowlist of expected columns
matched none of the deployed view's output aliases, and "no detector hit"
was printed for a table nothing had been read from. The schema-driven
version read the view's three string columns and three rows: zero hits.

| service | stream | detector | count | first | last |
|---|---|---|---|---|---|
| polyglot-backend | requests | ws_token_in_url | 79 | 2026-08-17T22:18Z | 2026-09-14T19:29Z |
| polyglot-backend | requests | jwt | 73 | 2026-08-18T21:27Z | 2026-09-09T22:54Z |
| polyglot-backend-staging | requests | ws_token_in_url | 14 | 2026-09-01T21:12Z | 2026-09-13T00:32Z |
| polyglot-backend-staging | requests | jwt | 13 | 2026-09-01T21:12Z | 2026-09-08T23:22Z |
| polyglot-admin | any | any | 0 | | |
| all three | stdout / stderr | any | 0 | | |
| BigQuery `hosting_cost_by_service_month` (3 rows; month, gcp_service, resource_name) | | any | 0 | | |
| BigQuery four other views | | | ABSENT | | |

Every jwt hit is a subset of the ws_token hits (a Firebase ID token riding
`?token=`); the remaining ws_token hits are client link tokens.

**Post-fix hits (epic criterion 2):** fix timestamps are the staging deploy
2026-09-13T00:28:47Z, the demo deploy 2026-09-14T19:14:51Z, and the `_Default`
sink exclusion `ws-token-in-url` 2026-09-14T19:28:21Z (all on bd
`polyglot-pdf-6rj0j`). Four hits fall after their service's deploy, all
`ws_token_in_url` in the request log, and all four are the orchestrator's
own B0 test-drive probes with a bogus token (no credential): staging
2026-09-13T00:32:36Z (four minutes after the staging deploy, before the
exclusion existed); demo 2026-09-14T19:21:35Z (between the deploy and the
exclusion) and 2026-09-14T19:29:08Z x2 (47 s after the exclusion was
written, inside its propagation lag). Disposition: false positive by
content, and the exclusion has held since -- zero request-log hits on any
service from 2026-09-14T19:29:09Z to the sweep time, 26+ hours. No app-stream
hit on any service in the whole window; no BigQuery hit.

**Residue (before the fix):** 75 demo + 13 staging request-log rows carrying a
`?token=` credential, dated 2026-08-17 to 2026-09-14T19:21Z. B0's ASK 2 was
decided 2026-09-14 as ACCEPT THE RESIDUE (option C): every link record was a
`budget_exhausted` stub with no minted link inside the window, and Firebase ID
tokens expire within an hour; the rows age out with the 30-day bucket
retention (the last one on 2026-10-14).

## Review record

REVIEW_RECORD

## Lessons

- **On this machine, anything that shells out to gcloud pops a console
  window -- including `google.auth.default()`.** The first version spawned
  `gcloud logging read` per day (~180 windows in a 30-day sweep) and made
  the maintainer's desk unusable; the hidden launcher hides only its direct
  child. In-process HTTPS + the client library, credentials from the ADC
  file, is the only shape that opens nothing, and a test now pins that the
  module never imports `subprocess` or calls the default lookup.
- **A tool's error stream is where the tool says it is, and error text is
  an output channel.** The builder's bq branch read stderr only ("Not
  found" is on stdout); and INCOMPLETE/UNREACHABLE lines carried raw API
  text past the redaction guarantee until `scrub()` closed that channel.
- **Page limits hide hits; page tokens do not.** `--limit 1000` per day
  silently dropped everything past the cap on a busy day; the REST call is
  walked to the end.
- **"No hit" must say what was read.** The BigQuery allowlist drifted from
  the views' output aliases and the sweep reported a clean scan of zero
  cells; the outer reviewer found it by following the column list OUT into
  `sql/telemetry_views.sql`. Columns now come from the live schema, the
  report prints row and column counts, and an empty column set is its own
  line.
- **A detector's first live run is its adversarial review.** Two phone hits
  were an epoch timestamp and a UUID fragment; the NANP rule (area code and
  exchange start with 2-9) removes both classes without weakening real
  matches, and each became a negative case first.

## Doc freshness

Bumped: none required by the surfaces. `docs/standards/hipaa-pii-policy.md`'s
Enforcement section is workstream G's to point at the sweep, per the plan.

## Files touched

- scripts/audit/log_pii_sweep.py -- the sweep (new)
- tests/test_log_pii_sweep_detectors.py -- detector, redaction, refusal and transport pins (new)
- docs/journal/entries/2026-09-15-bd-v8l6m-log-pii-sweep.md -- this entry
