---
date: 2026-09-17
bead: polyglot-pdf-k5w16
title: "fix(telemetry): setup-telemetry.sh doubles the serviceAccount: prefix on the sink-writer grant and aborts before creating the views"
sprint: 22
tags: [hotfix, testing]
---

## Trigger

The first `scripts/setup-telemetry.sh polyglot-demo-aa709 <billing table>` run
against the live project, right after PR #850 (bd polyglot-pdf-vzvio, "use the
API for dataset IAM grants") merged, aborted at the sink-writer grant step
with `could not grant roles/bigquery.dataEditor on ... to
serviceAccount:serviceAccount:service-...`. Because the script runs under
`set -e`, the abort happened before the view-creation step -- the actual
point of the run -- ever executed, so the cost/income views still did not
exist on the live project even though the sink's destination table did. The
live grant itself turned out fine (made by hand on 2026-09-14), which is why
nothing downstream had noticed the bug until this run exercised the fresh
code path from PR #850.

## What shipped

Two independent script bugs, both filed under this one bead (its own live
investigation surfaced the second while fixing the first):

1. **The doubled `serviceAccount:` prefix.** `WRITER_IDENTITY` is assigned on
   two different code paths in `scripts/setup-telemetry.sh` -- the re-run
   (sink-already-exists) branch reads it via `gcloud logging sinks describe
   --format=value(writerIdentity)`, which ALREADY returns the
   `serviceAccount:service-...` prefixed form, while the first-run
   (sink-create) branch greps a bare email straight out of `sinks create`'s
   own output. The grant call downstream always assumed the bare-email shape
   (`--member "serviceAccount:$WRITER_IDENTITY"`), which was correct for the
   create branch but doubled the prefix on the re-run branch. Fixed by
   normalising `WRITER_IDENTITY` to a bare email once, right after both
   branches assign it (`WRITER_IDENTITY="${WRITER_IDENTITY#serviceAccount:}"`),
   so every consumer downstream sees one consistent shape regardless of which
   branch ran.

2. **`telemetry_bq_setup.py grant-dataset-role`'s idempotency was
   snapshot-only.** Its existing `already_granted` check only looks at the
   dataset's access-entries list as read at the start of the call, so it
   cannot see a grant made concurrently, or a live entry shaped in a way its
   `_IAM_ROLE_TO_LEGACY_ACCESS_ROLE` mapping does not (yet) recognize.
   `update_dataset` now treats an exception whose message says the entry
   already exists (a "duplicate"/"already exists" API error) as success --
   log and continue -- rather than aborting, matching the bead's own ask for
   an "idempotent-tolerant" grant step. Any other write failure (permission,
   network, malformed member) still aborts loudly.

3. **The "views are late-bound" claim, corrected.** Live investigation while
   fixing the above surfaced a second, unrelated bug: `sql/telemetry_views.sql`'s
   own header comment claimed `bq query` on a view definition does not
   require the underlying table to exist yet ("BigQuery views are
   late-bound"). This is false for `CREATE VIEW` itself -- confirmed live:
   applying `income_month` before the sink's stderr-stream destination table
   existed failed with `404 Not found: Table
   ...run_googleapis_com_stderr`, a hard CREATE-time error, not a
   successfully-created empty view. "Late-bound" is true only for a table
   reference re-resolved at QUERY time, not at CREATE time. Corrected the sql
   file's header, and changed `scripts/setup-telemetry.sh`'s view-application
   step from one combined `bq query` call gated on BOTH sink tables existing,
   to five independent `bq query` calls, each extracted from
   `sql/telemetry_views.sql` and gated on the ONE table it actually reads:
   `cost_by_firm_month`/`cost_by_kit_month`/`cost_by_employee_month` on
   `TELEMETRY_TABLE_STDOUT`, `income_month` on `TELEMETRY_TABLE_STDERR`, and
   `hosting_cost_by_service_month` on `BILLING_EXPORT_TABLE` alone (already
   guaranteed present by an earlier gate). Any view whose source table is
   not there yet is reported as PENDING and the script still exits 0 -- this
   is a normal, expected state on a fresh or partially-warmed-up project, not
   a failure.

Functionally verified end-to-end with stubbed `gcloud`/`bq`/python binaries
on PATH (both the sink-create and sink-update branches, and both the
"only stdout table exists" and "both tables exist" cases), confirming the
exact substituted SQL each view receives and the exit code in each case.

## Lessons

Two of this repo's own scar-tissue patterns recurred here:

- **Two code paths writing the same variable in different shapes is a bug
  waiting for whichever caller only tested one path.** `WRITER_IDENTITY`'s
  create-branch and update-branch shapes diverged silently for as long as
  nothing downstream cared about the exact prefix; the moment a consumer
  assumed one shape, the other branch broke it. General lesson, not specific
  to this script: when a variable is assigned on more than one branch,
  normalise it to one canonical shape right after the branches converge,
  rather than trusting every future consumer to handle both shapes itself.
- **"Late-bound" claims about a platform's query semantics need to be
  verified against the ACTUAL operation, not assumed transitively.** BigQuery
  views genuinely ARE late-bound for query-time re-resolution, and it is easy
  to over-generalize that into "so CREATE VIEW must be late-bound too" --
  they are different operations with different guarantees, and only a live
  run caught the gap.

## Doc freshness

`docs/standards/logging-and-cost.md` (tracks `scripts/setup-telemetry.sh`,
`scripts/telemetry_bq_setup.py`, `sql/telemetry_views.sql`) bumped: new dated
stamp at the top, the "Views" paragraph now describes per-view/per-table
gating instead of implying one combined apply step, and the "IAM" paragraph
now documents both the WRITER_IDENTITY normalisation and the write-path
idempotent-tolerant handling.

`docs/components/admin-service.md` was NOT touched -- it was mid-flight under
a different in-progress bead (polyglot-pdf-e1l5f, collapsing that file's
stacked Last-updated stamps) at claim time, and this bead's actual code
change does not require a change to its content (its two IAM-grant table rows
already correctly attribute both dataset-scoped BigQuery grants to
`scripts/setup-telemetry.sh` without describing the buggy prefix mechanics
this bead fixed).

## Files touched

- `scripts/setup-telemetry.sh` -- WRITER_IDENTITY prefix normalisation; split
  the single combined view-application step into five independent,
  per-table-gated `bq query` calls via new `_extract_view`/`_apply_view`
  helper functions.
- `scripts/telemetry_bq_setup.py` -- `_grant_dataset_role`'s `update_dataset`
  call is now idempotent-tolerant of an "already exists"-shaped write error.
- `sql/telemetry_views.sql` -- corrected the header comment's false
  "views are late-bound at CREATE time" claim.
- `tests/test_setup_telemetry_script.py` -- new/updated tests pinning the
  WRITER_IDENTITY normalisation (presence, position, exact mechanism), the
  per-view/per-table gating, and the pending-views-still-exit-0 contract;
  removed the now-superseded all-or-nothing gate test.
- `tests/test_telemetry_bq_setup.py` -- new tests for the idempotent-tolerant
  write path (an "already exists" error is swallowed; any other error still
  aborts).
- `docs/standards/logging-and-cost.md` -- doc updates described above.
