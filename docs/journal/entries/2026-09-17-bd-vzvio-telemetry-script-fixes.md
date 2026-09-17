---
date: 2026-09-17
bead: polyglot-pdf-vzvio
title: "fix(telemetry): setup-telemetry.sh -- match the billing dataset's location, substitute the sink table names, grant via the API not bq"
sprint: 22
tags: [conventions, testing]
---

## Trigger

Filed 2026-09-15 after the maintainer ran `scripts/setup-telemetry.sh` for
real (Epic 3 bead E3.6's script, bd `polyglot-pdf-rd3s8`). Three problems
surfaced: (1) the script hard-codes `LOCATION=us-central1` for the
`polyglot_telemetry` dataset, but the maintainer's Cloud Billing export
dataset lives in the US multi-region, and BigQuery refuses to create a view
(`hosting_cost_by_service_month`) that reads a table in a different location
than its own dataset -- the orchestrator had to recreate the (empty)
telemetry dataset by hand to unblock it; (2) the bug report also named a
sink-table-substitution gap, but tracing the ACTUAL shipped script showed
that half already fixed by two earlier follow-on beads (`polyglot-pdf-f7f0h`,
`polyglot-pdf-ih428`) -- `${TELEMETRY_TABLE_STDOUT}`/`${TELEMETRY_TABLE_STDERR}`
are already substituted independently and views are already skipped with a
`[NOTE]` when either sink table is missing, so this bead's scope narrowed to
the two problems still live; (3) the `bq add-iam-policy-binding` step exits
non-zero on the maintainer's machine because the `bq` shim needs
`CLOUDSDK_PYTHON` pointed at an installed Python, aborting the script (via
`set -e`) before the views were ever applied.

## What shipped

New `scripts/telemetry_bq_setup.py`, a small Python CLI the bash script
shells out to for the two operations that needed the `google-cloud-bigquery`
API instead of `bq`/`gcloud` text-parsing:

- `resolve-location --project P --dataset D --billing-table T` reads the
  billing table's own dataset location via `Client.get_dataset` and prints
  it. If the telemetry dataset ALREADY exists, ALREADY holds tables, and its
  location differs from the billing dataset's, it refuses (exit 1, message on
  stderr) rather than printing a location the operator cannot actually apply
  to a populated dataset -- BigQuery cannot move a dataset between locations.
  An absent or EMPTY telemetry dataset is not a conflict (nothing in it would
  be stranded), so those paths print the billing location either way.
- `grant-dataset-role --project P --dataset D --member M --role R` grants one
  dataset-scoped IAM role via `Dataset.access_entries` +
  `Client.update_dataset(["access_entries"])` -- the same mechanism `bq
  add-iam-policy-binding` itself uses on a dataset target, so this is a
  drop-in replacement, not a workaround. Idempotent: a role already granted
  to the exact member is left alone rather than duplicated.

`scripts/setup-telemetry.sh` now reads `BILLING_EXPORT_TABLE` (arg 2) near
the top of the script, before the dataset is created (a dataset's location is
fixed at creation time, so this could not stay at its old read point, deep in
the view-application step). When given, it calls `resolve-location` and uses
the derived location; when absent, it still defaults to `us-central1` (there
is nothing to derive a location from on a first, argument-less run). Both
dataset-scoped `bq add-iam-policy-binding` calls (the sink writer's
`dataEditor`, `admin-backend-sa`'s `dataViewer`) are replaced with
`grant-dataset-role` calls. `admin-backend-sa`'s project-level `jobUser` grant
is untouched -- it was always `gcloud projects add-iam-policy-binding`, which
never used `bq` and was not implicated in the failure.

A Windows-Git-Bash python-interpreter probe (`find_telemetry_python`,
matching `deploy-form-kit.sh`'s `find_manifest_python` shape: try `python3`,
`python`, `py`, in order, requiring each candidate to actually RUN `-c
"pass"` rather than merely exist -- Windows ships a `python3`
App-Execution-Alias stub that `command -v` finds but that cannot execute)
resolves the interpreter that runs the new helper.

## Fresh-eyes round 2 (cross-surface review)

Adopt/reject/defer breakdown from the outer cross-surface review's single
GAPS-FOUND finding plus its lower-confidence observations:

- **ADOPTED (fixed):** `_resolve_location`'s telemetry-dataset `get_dataset`
  lookup (`scripts/telemetry_bq_setup.py`) caught bare `Exception`, so a
  permission error or transient network fault on an EXISTING, populated,
  location-mismatched dataset was silently treated the same as "the dataset
  does not exist yet" -- printing the billing location and exiting 0 instead
  of refusing, defeating the conflict-refusal exit criterion in exactly the
  scenario it exists to catch. Narrowed to `except (LookupError,
  gexc.NotFound)` (matching both the test fake's `LookupError` and the real
  API's `google.api_core.exceptions.NotFound`), with a new `except Exception`
  branch that prints an `ERROR:` line and exits 1 for everything else,
  mirroring the established pattern already used in
  `scripts/audit/log_pii_sweep.py`'s `_bq_table_schema`. Two new tests pin
  this: a non-`NotFound` `get_dataset` failure must exit 1 with an `ERROR:`
  message, not print the billing location; both were mutation-verified
  (widening the except back to bare `Exception` turns the first test red;
  removing the try/except around `list_tables` turns the second red).
- **ADOPTED (fixed):** the same function's `client.list_tables(...)` call had
  no exception handling at all, contradicting the module's own docstring
  promise that "every failure prints a human-readable reason to stderr
  first" -- an API error there would have propagated as a raw traceback.
  Wrapped in the same try/except-and-report-ERROR shape as the rest of the
  module; pinned by the second new test above.
- **DEFERRED (filed as a bead, not fixed here):** the reviewer's low-confidence
  coverage observation that no test pins `find_telemetry_python`'s
  existence/correctness directly in `scripts/setup-telemetry.sh` (only its
  call site is checked) -- filed as `polyglot-pdf-vxmny` (chore(nits):
  deferred review nits from polyglot-pdf-vzvio). Low risk (the function is
  copied verbatim from the proven `find_manifest_python` precedent) and
  purely a test-rigor gap, not a suspected bug, so it did not warrant a
  behavioral fix in this round.
- **NOT RE-LITIGATED (reviewer's own disclosure, no action needed):** the
  reviewer could not independently re-run the `google-cloud-bigquery`- and
  `firebase_admin`-dependent suites in its ambient environment; this round
  re-ran the full backend suite (3871 passed, 195 skipped), the root suite
  (2016 passed, 94 skipped), `tests/test_telemetry_bq_setup.py` (11 passed,
  including the 2 new tests), and `admin_backend/tests/unit/
  test_admin_sa_iam_envelope.py` (13 passed) directly from this worktree,
  confirming the builder's earlier counts and the reviewer's own re-derived
  contract checks. `AccessEntry(entity_type="userByEmail", ...)` was already
  independently verified by the reviewer against the installed
  `google-cloud-bigquery` source and was not re-checked here.

## Lessons

A bug report's own enumerated problem list is not itself proof the CURRENT
shipped code still has all of them -- two earlier follow-on beads
(`polyglot-pdf-f7f0h`, `polyglot-pdf-ih428`) had already fixed the
sink-table-substitution half of this report's problem (2) between when the
report was filed and when this bead was worked. Reading the actual script
text against the report line by line (rather than assuming the report's list
maps 1:1 onto remaining work) found the real, narrower scope: only the
location hard-code and the `bq` IAM calls were still live.

A CLI tool that "just works" locally can still be broken on another
operator's machine for reasons a mock cannot surface (CLAUDE.md scar #7's
IAM-envelope lesson, generalized past IAM specifically): `bq`'s Python-shim
resolution is an environment dependency no unit test exercises, and the
`google-cloud-bigquery` SDK -- already a backend dependency used the same way
in two other places in this repo -- sidesteps it entirely for operations the
SDK actually supports (dataset-level ACLs). When a shell-out to a CLI tool is
replaceable by a typed API call already vendored in the repo, prefer the API:
it fails the same way in CI, in a test, and on every operator's machine,
where a CLI's own dependency resolution does not.

## Doc freshness

`docs/standards/logging-and-cost.md`: new paragraph on location derivation
in the "BigQuery telemetry sink + cost/income views" section; the IAM
paragraph corrected to name `telemetry_bq_setup.py grant-dataset-role`
instead of `bq add-iam-policy-binding`; Tracks line extended with
`scripts/telemetry_bq_setup.py`; Last-updated annotation extended (moved to
the top of the stack so `check_doc_freshness.py`'s first-match parse picks it
up).

`docs/technical_guide.md`: Surface contract 25's producer paragraph updated
for both the location-derivation and API-based-grant changes, plus a
drive-by correction of a stale claim that `BILLING_EXPORT_TABLE` is a
required argument (the shipped script has always treated it as optional,
skip-and-exit-0 when absent -- `tests/test_setup_telemetry_script.py` already
pinned this; only the doc's prose had drifted).

`admin_backend/tests/unit/test_admin_sa_iam_envelope.py` is not on this
bead's declared `metadata.surfaces` list, but it independently pinned `bq
add-iam-policy-binding` for the dataset-scoped `dataViewer` grant (a second,
undeclared member of the same "tests asserting the bq-invocation shape" set
-- CLAUDE.md scar #8). Enumerated by grepping the whole repo for
`bq add-iam-policy-binding` / `setup-telemetry` mentions rather than trusting
the bead's surface list to be complete, and updated in the same PR so it does
not go red.

## Files touched

- `scripts/telemetry_bq_setup.py` (new) -- the `resolve-location` /
  `grant-dataset-role` API helper.
- `scripts/setup-telemetry.sh` -- reads `BILLING_EXPORT_TABLE` early, derives
  `LOCATION` from the billing dataset when given, replaces both dataset-scoped
  `bq add-iam-policy-binding` calls with the new helper.
- `tests/test_telemetry_bq_setup.py` (new) -- pins the helper's location
  match/mismatch/absent-dataset cases, grant idempotency, non-service-account
  rejection, and missing-dataset error, against a fake BigQuery client.
- `tests/test_setup_telemetry_script.py` -- replaces the location/IAM-grant
  tests the script text no longer satisfies (`test_dataset_name_and_
  location_are_pinned` split into `test_dataset_name_is_pinned` +
  two new location-derivation tests; `test_writer_identity_gets_
  dataeditor_on_the_dataset`, `test_admin_sa_gets_jobuser_and_dataviewer`,
  `test_all_four_iam_grants_are_present` rewritten for the API-call shape).
- `admin_backend/tests/unit/test_admin_sa_iam_envelope.py` -- 
  `test_telemetry_script_grants_jobuser_project_wide_and_dataviewer_on_dataset`
  rewritten for the same API-call shape (see Doc freshness above for why this
  undeclared-surface file needed the update).
- `docs/standards/logging-and-cost.md`, `docs/technical_guide.md` -- see Doc
  freshness above.

All new/changed tests were mutation-verified: each production behavior
(the `has_tables` location-conflict check, the `grant-dataset-role`
idempotency check, the `LOCATION` derivation branch, the `bq
add-iam-policy-binding` -> API-helper swap in the shell script, and -- round
2 -- the narrowed `except (LookupError, gexc.NotFound)` on the telemetry
dataset lookup and the new try/except around `list_tables`) was reverted to
its pre-fix shape and the corresponding test observed to fail, then restored.
Full backend suite (3871 passed, 195 skipped), root suite (2016 passed, 94
skipped), `tests/test_telemetry_bq_setup.py` (11 passed), and
`admin_backend/tests/unit/test_admin_sa_iam_envelope.py` (13 passed) all
re-run clean after round 2's fix; tree left clean.

## Fresh-eyes round 3 (cross-surface review)

The outer review's round-3 pass returned `GAPS-FOUND (1)`, flagging exit
criterion 2 (dataset grants no longer use `bq`) as failing "as a practical
matter": it claimed `_grant_dataset_role`'s `bigquery.AccessEntry(role=args.role,
entity_type="userByEmail", entity_id=entity_id)` pairs an IAM-role string
(`roles/bigquery.dataViewer` / `roles/bigquery.dataEditor`) with the wrong
entity type -- arguing `userByEmail` only accepts the legacy `READER`/
`WRITER`/`OWNER` roles, and an IAM-role string requires `entity_type=
"iamMember"` with the member's full `serviceAccount:...` string, not the
bare email `entity_id` already stripped at line 248. The finding was based on
the vendored `google-cloud-bigquery` SDK's own `AccessEntry` class docstring,
whose one worked example (`AccessEntry('OWNER', 'userByEmail', ...)`) pairs
`userByEmail` with a legacy role, plus the two Python client-library methods'
docstrings describing `iamMember` and `userByEmail` as parallel-but-distinct
entity kinds -- reasonable evidence, but not the authoritative source for
what the wire API itself validates.

- **REFUTED (no code change):** checked the finding against BigQuery's own
  REST API discovery document (`bigquery.datasets.get`'s `Dataset.access[]`
  schema, fetched live from `https://bigquery.googleapis.com/discovery/v1/
  apis/bigquery/v2/rest`) rather than the client library's docstrings one
  level removed from it. The discovery doc's `role` field description is
  unambiguous and entity-type-agnostic: "This field will accept any of the
  above [legacy] formats, but will return only the legacy format" -- i.e. an
  IAM role string like `roles/bigquery.dataViewer` is accepted for ANY
  entity type, including `userByEmail`, and the server normalizes it back to
  `READER`/`WRITER`/`OWNER` on read. `userByEmail`'s own description
  ("Maps to IAM policy member `user:EMAIL` or `serviceAccount:EMAIL`")
  confirms it explicitly supports service accounts via the bare email --
  exactly what `entity_id` already holds after the `serviceAccount:` prefix
  is stripped at line 248. `iamMember` is documented only as the catch-all
  for "some other type of member that appears in the IAM Policy but isn't a
  user, group, domain, or special group" -- not the field to use for a plain
  service-account grant, which `userByEmail` already covers correctly. A
  Google-documented sample payload matches the code under review exactly:
  `{"role": "roles/bigquery.dataViewer", "userByEmail":
  "service-account@project.iam.gserviceaccount.com"}`. The reviewer's own
  "How to verify" section flagged this as unverified-but-high-confidence,
  pending a live-API check it could not run; that check is what this round
  did, against the authoritative schema rather than a docstring example, and
  it comes out the other way. `_grant_dataset_role` and its idempotency
  check are therefore correct as shipped; exit criterion 2 stands as PASS.
  Findings 2 (the `find_telemetry_python` coverage nit) and 3 (fake-client
  return-type fidelity) were already dispositioned in round 2 / already
  filed (`polyglot-pdf-vxmny`) and needed no new action. Finding 4 (the
  module docstring's "the exact mechanism `bq add-iam-policy-binding` itself
  calls into" claim) was contingent on Finding 1; since Finding 1 is
  refuted, the docstring's claim stands as accurate and needed no edit.
- **Verification:** full backend suite (3871 passed, 195 skipped) and root
  suite (2016 passed, 94 skipped) re-run clean from this worktree -- same
  counts as round 2, confirming no regression from this round (no production
  code changed). No new bead filed: both out-of-scope items already on
  record from round 2 (`polyglot-pdf-vxmny`, `polyglot-pdf-cl3qp`) remain the
  correct home for anything still open, and this round's findings were
  either refuted or already covered.

Review outcomes recorded in the closeout ping.
