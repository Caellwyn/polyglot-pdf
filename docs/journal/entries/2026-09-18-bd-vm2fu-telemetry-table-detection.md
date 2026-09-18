---
date: 2026-09-18
bead: polyglot-pdf-vm2fu
title: "fix(telemetry): setup-telemetry.sh detects sink tables through the python client, not a silently-empty bq ls"
sprint: 22
tags: [hotfix, testing]
---

## Trigger

Seen 2026-09-18 on a live re-run of `scripts/setup-telemetry.sh` after PR
#857 (bd polyglot-pdf-k5w16) landed: with the network up and the sink table
`run_googleapis_com_stdout` confirmed present through the python
`bigquery.Client.list_tables` call, the script still printed "stdout table
(usage events) does not exist yet" and reported `cost_by_firm_month` /
`cost_by_kit_month` / `cost_by_employee_month` as PENDING, while its `bq
query` step for `hosting_cost_by_service_month` succeeded in the same run.
The old detection line, `TELEMETRY_TABLES_CSV=$(bq ls --project_id=...
--format=csv "$DATASET" 2>/dev/null | tail -n +2)`, redirects `bq`'s stderr
to `/dev/null` and then treats an EMPTY result as "no tables yet" -- which
is indistinguishable from "the `bq` CLI itself failed to list at all" (on
this machine the `bq` shim under the gcloud-bundled Python printed an
issue-tracker boilerplate and returned nothing; earlier a DNS blip produced
the same empty result). The script already requires a python interpreter
with `google-cloud-bigquery` installed (for LOCATION derivation and the
dataset-scoped IAM grants, bd polyglot-pdf-vzvio), so table detection
should go through that same client instead of shelling out to `bq ls`.

## What shipped

- `scripts/telemetry_bq_setup.py` gained a third subcommand, `list-tables
  --project P --dataset D`, printing one table id per line via
  `bigquery.Client.list_tables`. A real API error (permission denied,
  dataset not found, network fault) prints an `ERROR:` line to stderr and
  exits 1 -- it never prints an empty list on failure, which is exactly the
  ambiguity the old `bq ls` pipeline had. A genuinely empty dataset (zero
  tables, confirmed via a successful API call) prints nothing and exits 0,
  same as a real `bq ls` on an empty dataset would.
- `scripts/setup-telemetry.sh`'s table-detection block now calls
  `telemetry_bq_setup.py list-tables` instead of `bq ls`, wrapped in an
  `if ! ... ; then ... exit 1; fi` guard so a real API error aborts the
  script with a clear message rather than falling through to empty
  `TELEMETRY_TABLE_STDOUT`/`TELEMETRY_TABLE_STDERR` and silently reporting
  every gated cost view PENDING. The per-view gating from bd
  polyglot-pdf-k5w16 (each view applies independently based on which
  source table it actually needs) is unchanged.
- Nothing about the sink filter, the IAM grants, or the view-application
  logic changed -- this bead is scoped to the detection mechanism only.

## Lessons

CLAUDE.md scar #7 ("a mock cannot tell you the real dependency is
forbidden") has a shell-pipeline cousin: a shell pipeline that redirects
stderr to `/dev/null` and reads only stdout cannot tell "the command
produced no output because there is genuinely nothing to report" from "the
command failed silently and produced no output for that reason instead."
Any script gating behavior on a shelled-out CLI's stdout should either
check the exit code explicitly or (when a typed client for the same API is
already a dependency, as here) go through that client so a failure surfaces
as an exception rather than an ambiguous empty string.

## Doc freshness

- `docs/standards/logging-and-cost.md` (Tracks: `scripts/setup-telemetry.sh`,
  `scripts/telemetry_bq_setup.py`, ...) -- updated the "sink lands rows in
  TWO destination tables" paragraph to describe `list-tables` instead of
  `bq ls`, and added a new `*Last updated:*` stamp for this bead. (Doc
  freshness checker flags this file as already carrying multiple stacked
  `*Last updated:*` stamps -- pre-existing across many tier-1/tier-2 docs
  in this repo, not introduced or worsened by this bead; left as a
  known, already-flagged issue rather than fixed here, per CLAUDE.md's
  "enumerate the set before fixing any of it" scar tissue -- a wholesale
  stamp-consolidation pass across every affected doc is out of scope for
  this P2 bug bead.)
- `docs/technical_guide.md` -- updated the BigQuery Producer paragraph's
  description of how `${TELEMETRY_TABLE_STDOUT}`/`${TELEMETRY_TABLE_STDERR}`
  are read back. No stamp (this doc carries none by design).

## Files touched

- `scripts/telemetry_bq_setup.py` -- new `list-tables` subcommand + docstring.
- `scripts/setup-telemetry.sh` -- table-detection block now calls
  `telemetry_bq_setup.py list-tables`, aborts on failure; updated comments.
- `tests/test_telemetry_bq_setup.py` -- four new tests for `list-tables`
  (prints table ids, empty dataset exits 0 with no output, API error exits
  1 with no stdout, project passthrough), mutation-verified.
- `tests/test_setup_telemetry_script.py` -- replaced the `bq ls`-based
  discovery test with a python-client-based version, plus a negative pin
  that `bq ls` is no longer invoked, plus a pin that a list-tables failure
  aborts the script. Mutation-verified.
- `docs/standards/logging-and-cost.md`, `docs/technical_guide.md` -- prose
  updated to describe the new detection mechanism.
