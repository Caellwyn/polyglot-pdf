"""Python-API helpers for scripts/setup-telemetry.sh (bd polyglot-pdf-vzvio).

WHY THIS EXISTS AS A SEPARATE PYTHON SCRIPT, NOT MORE BASH. Two of
setup-telemetry.sh's steps cannot be done reliably with `bq`/`gcloud` alone
on every operator machine:

  1. LOCATION DERIVATION. BigQuery refuses to create a VIEW that reads a
     table in a different location than the view's own dataset (the
     `hosting_cost_by_service_month` view is exactly this: it reads the
     maintainer's Cloud Billing export table). `bq show` can print a
     dataset's location, but parsing its text/JSON output reliably across
     `bq` versions is exactly the kind of shell-string-wrangling this repo's
     CLAUDE.md warns against when a typed API is one import away -- and the
     google-cloud-bigquery client is ALREADY a backend dependency
     (backend/requirements.txt, used by admin_backend/services/
     bigquery_reports.py and scripts/audit/log_pii_sweep.py the same way).
  2. DATASET-SCOPED IAM GRANTS VIA `bq add-iam-policy-binding`. On at least
     one maintainer machine this exits non-zero because the `bq` shim needs
     CLOUDSDK_PYTHON pointed at an installed Python and the machine's `bq`
     cannot find one -- observed 2026-09-15 aborting setup-telemetry.sh
     before it ever reached the view-creation step. `gcloud` itself does not
     share this failure mode (verified: setup-telemetry.sh's OTHER two
     IAM grants, the sink writer's project just needs `gcloud`, not `bq`),
     so ONLY the `bq add-iam-policy-binding` calls are replaced here, via
     google-cloud-bigquery's Dataset.access_entries -- the exact mechanism
     `bq add-iam-policy-binding` itself calls into on a dataset target (a
     dataset has no separate IAM-policy resource the way a table/project
     does; its ACL IS its `access_entries` list). Both call sites this
     script replaces are dataset-scoped grants (roles/bigquery.dataEditor
     for the sink writer, roles/bigquery.dataViewer for admin-backend-sa);
     the one PROJECT-scoped BigQuery grant (admin-backend-sa's
     roles/bigquery.jobUser) stays on `gcloud projects
     add-iam-policy-binding` in the shell script, since that call never used
     `bq` and gcloud is not implicated in the failure this bead fixes.

Two subcommands:

    python scripts/telemetry_bq_setup.py resolve-location \
        --project <PROJECT_ID> --dataset <DATASET> \
        --billing-table <BILLING_PROJECT.BILLING_DATASET.TABLE>
        Prints the LOCATION setup-telemetry.sh should create/expect the
        telemetry dataset in: the billing table's own dataset location. If
        the telemetry dataset ALREADY EXISTS, HOLDS AT LEAST ONE TABLE, and
        its location differs from the billing dataset's location, exits
        non-zero with a message explaining the mismatch instead of printing
        a location the caller could silently apply against a populated
        dataset it cannot actually match (BigQuery cannot move a dataset
        between locations; the fix is a new dataset name or dropping the
        deployed one, both maintainer calls, not something to guess at
        here). An empty or absent telemetry dataset produces no such
        conflict -- there is nothing in it a mismatched location could
        strand -- so the billing dataset's location is printed either way.

    python scripts/telemetry_bq_setup.py grant-dataset-role \
        --project <PROJECT_ID> --dataset <DATASET> \
        --member <serviceAccount:...> --role <roles/bigquery.xxx>
        Grants ONE dataset-scoped role to ONE member via
        Dataset.access_entries + Client.update_dataset(["access_entries"]),
        replacing a `bq add-iam-policy-binding <dataset>` call. Idempotent:
        an access entry already granting this exact (role, member) pair is
        left as-is rather than duplicated.

Exit codes: 0 success; 1 any failure (missing table/dataset, API error, a
location conflict). Every failure prints a human-readable reason to stderr
first -- setup-telemetry.sh's `set -e` turns a non-zero exit here into an
immediate script abort with that message as the last thing the operator saw.

ASCII only.
"""
from __future__ import annotations

import argparse
import sys

# BigQuery's dataset ACL (Dataset.access_entries) predates IAM-style role
# strings. For a userByEmail entity, the server normalizes whatever role it
# was granted with down to one of the three legacy access roles below --
# confirmed 2026-09-17 against a live dataset's ACL (a grant originally made
# via `bq add-iam-policy-binding --role roles/bigquery.dataViewer` reads
# back over the API as {"role": "READER", "userByEmail": "..."}), and
# documented in google-cloud-bigquery's own AccessEntry docstring ("READER",
# "WRITER", "OWNER" are the only legal `role` values for a
# userByEmail-shaped entity). Comparing an IAM-style role string (what
# setup-telemetry.sh passes on the command line) directly against
# entry.role therefore never matches a real, previously-granted entry --
# only this normalized form does. Extend this mapping if a future caller
# grants a different dataset-scoped role; an unmapped role is a hard error
# (see _grant_dataset_role) rather than a silent skip of the idempotency
# check.
_IAM_ROLE_TO_LEGACY_ACCESS_ROLE = {
    "roles/bigquery.dataViewer": "READER",
    "roles/bigquery.dataEditor": "WRITER",
    "roles/bigquery.dataOwner": "OWNER",
}


def _client(project):
    """A google.cloud.bigquery.Client scoped to `project`, or None with a
    message on stderr.

    Lazy-imported like every other BigQuery call site in this repo
    (admin_backend/services/bigquery_reports.py, scripts/audit/
    log_pii_sweep.py) so importing this module never requires the library
    or ambient credentials to be resolvable -- only actually calling a
    subcommand does.

    `project` MUST be passed through explicitly (both call sites pass
    args.project, the --project the caller already gave on the command
    line) rather than left for bigquery.Client() to resolve on its own.
    Without it, a bare bigquery.Client() falls back to
    google.auth.default()'s ambient project lookup, which (a) raises
    EnvironmentError outright when no ambient project is configured --
    reintroducing the exact ambient-environment dependency this script
    exists to remove -- and (b) on Windows can shell out to
    `gcloud.cmd config get-value project` to find one
    (google/auth/_cloud_sdk.py's get_project_id), an extra subprocess this
    script has no reason to risk when the caller already supplied the
    project. scripts/audit/log_pii_sweep.py's _bq_client makes the same
    argument for the same reason.
    """
    try:
        from google.cloud import bigquery
    except ImportError as exc:
        print(
            "ERROR: google-cloud-bigquery is not importable: {}".format(exc),
            file=sys.stderr,
        )
        return None
    try:
        return bigquery.Client(project=project)
    except Exception as exc:  # noqa: BLE001 -- surfaced to the operator, not swallowed
        print(
            "ERROR: could not construct a BigQuery client: {}".format(exc),
            file=sys.stderr,
        )
        return None


def _resolve_location(args: argparse.Namespace) -> int:
    from google.cloud import bigquery

    client = _client(args.project)
    if client is None:
        return 1

    try:
        billing_table_ref = bigquery.TableReference.from_string(
            args.billing_table, default_project=args.project
        )
    except ValueError as exc:
        print(
            "ERROR: --billing-table {!r} is not a valid "
            "PROJECT.DATASET.TABLE reference: {}".format(
                args.billing_table, exc
            ),
            file=sys.stderr,
        )
        return 1

    billing_dataset_ref = bigquery.DatasetReference(
        billing_table_ref.project, billing_table_ref.dataset_id
    )
    try:
        billing_dataset = client.get_dataset(billing_dataset_ref)
    except Exception as exc:  # noqa: BLE001
        print(
            "ERROR: could not read the billing dataset {}: {}".format(
                billing_dataset_ref, exc
            ),
            file=sys.stderr,
        )
        return 1

    billing_location = billing_dataset.location

    telemetry_dataset_ref = bigquery.DatasetReference(
        args.project, args.dataset
    )
    try:
        from google.api_core import exceptions as gexc
    except ImportError as exc:
        print(
            "ERROR: google-api-core is not importable: {}".format(exc),
            file=sys.stderr,
        )
        return 1

    try:
        telemetry_dataset = client.get_dataset(telemetry_dataset_ref)
    except (LookupError, gexc.NotFound):
        # The telemetry dataset does not exist yet -- nothing to conflict
        # with, so the billing dataset's own location is simply where it
        # should be created. LookupError is what this module's own test
        # fake raises for "not found" (the test file avoids depending on
        # the real google-cloud-bigquery client for its fixtures);
        # gexc.NotFound is what the real API raises. Anything else (a
        # permission error, a transient network fault, ...) is NOT "the
        # dataset doesn't exist" and must not be treated as though it
        # were -- that would silently print a location without ever
        # having confirmed there is no conflicting, already-populated
        # dataset to protect.
        print(billing_location)
        return 0
    except Exception as exc:  # noqa: BLE001 -- surfaced, not swallowed
        print(
            "ERROR: could not read telemetry dataset {}: {}".format(
                telemetry_dataset_ref, exc
            ),
            file=sys.stderr,
        )
        return 1

    # The telemetry dataset already exists. If it is EMPTY, a location
    # mismatch strands nothing -- recreating it in the billing dataset's
    # location is exactly what the caller (setup-telemetry.sh) does next,
    # and this bead's own bug report is that path having to be done by
    # hand today. Only refuse when there is real content that a location
    # change cannot carry over.
    try:
        has_tables = next(iter(client.list_tables(telemetry_dataset_ref)), None) is not None
    except Exception as exc:  # noqa: BLE001 -- surfaced, not a raw traceback
        print(
            "ERROR: could not list tables in telemetry dataset {}: {}".format(
                telemetry_dataset_ref, exc
            ),
            file=sys.stderr,
        )
        return 1
    if has_tables and telemetry_dataset.location != billing_location:
        print(
            "ERROR: telemetry dataset {} already exists in location {!r} "
            "and already holds tables, but the billing dataset {} is in "
            "location {!r}. BigQuery cannot create a view that reads "
            "across locations, and an existing dataset cannot be moved. "
            "Either drop and recreate {} in {!r} (data loss for anything "
            "already in it), or pick a different --dataset name for a "
            "fresh telemetry dataset in {!r}.".format(
                telemetry_dataset_ref,
                telemetry_dataset.location,
                billing_dataset_ref,
                billing_location,
                telemetry_dataset_ref,
                billing_location,
                billing_location,
            ),
            file=sys.stderr,
        )
        return 1

    print(billing_location)
    return 0


def _grant_dataset_role(args: argparse.Namespace) -> int:
    from google.cloud import bigquery

    client = _client(args.project)
    if client is None:
        return 1

    dataset_ref = bigquery.DatasetReference(args.project, args.dataset)
    try:
        dataset = client.get_dataset(dataset_ref)
    except Exception as exc:  # noqa: BLE001
        print(
            "ERROR: could not read dataset {}: {}".format(dataset_ref, exc),
            file=sys.stderr,
        )
        return 1

    # A member string is one of "user:...", "serviceAccount:...",
    # "group:...", "domain:...", or "specialGroup:..." -- the same value
    # `bq add-iam-policy-binding --member=` takes. AccessEntry's entity_type
    # names the FIRST of these that the entity_id's own value determines;
    # every member setup-telemetry.sh passes here is a service account.
    if not args.member.startswith("serviceAccount:"):
        print(
            "ERROR: --member must be a serviceAccount: principal (got "
            "{!r}) -- this helper only supports the grants "
            "setup-telemetry.sh makes.".format(args.member),
            file=sys.stderr,
        )
        return 1
    entity_id = args.member[len("serviceAccount:"):]

    # The BigQuery API normalizes an IAM-style role to the legacy
    # READER/WRITER/OWNER form for a userByEmail entity (see the
    # _IAM_ROLE_TO_LEGACY_ACCESS_ROLE comment above) -- a live,
    # previously-granted entry's `role` is NEVER the IAM string this
    # script is invoked with. Fail loudly on a role this module does not
    # know how to normalize, rather than silently comparing the raw IAM
    # string and never matching a real entry (the bug this mapping
    # fixes): a false 'not yet granted' means the idempotency guarantee
    # this helper exists to provide silently does not hold, appending a
    # duplicate access entry on every re-run.
    legacy_role = _IAM_ROLE_TO_LEGACY_ACCESS_ROLE.get(args.role)
    if legacy_role is None:
        print(
            "ERROR: --role {!r} is not one this helper knows how to "
            "check for idempotency (known: {}). Add it to "
            "_IAM_ROLE_TO_LEGACY_ACCESS_ROLE first -- comparing the raw "
            "IAM role string against a live access entry's `role` would "
            "never match, defeating idempotency.".format(
                args.role, sorted(_IAM_ROLE_TO_LEGACY_ACCESS_ROLE)
            ),
            file=sys.stderr,
        )
        return 1

    existing = list(dataset.access_entries)
    already_granted = any(
        entry.role in (legacy_role, args.role)
        and entry.entity_type == "userByEmail"
        and entry.entity_id == entity_id
        for entry in existing
    )
    if already_granted:
        print(
            "{} already has {} on {} -- nothing to do.".format(
                args.member, args.role, dataset_ref
            )
        )
        return 0

    new_entry = bigquery.AccessEntry(
        role=args.role, entity_type="userByEmail", entity_id=entity_id
    )
    dataset.access_entries = existing + [new_entry]
    try:
        client.update_dataset(dataset, ["access_entries"])
    except Exception as exc:  # noqa: BLE001
        # IDEMPOTENT-TOLERANT (bd polyglot-pdf-k5w16). The already_granted
        # check above compares against the dataset SNAPSHOT this process
        # just read -- it cannot see a grant made concurrently (a second
        # operator, or a retried run racing this one) between that read and
        # this write, nor a live access entry shaped in a way this module's
        # own _IAM_ROLE_TO_LEGACY_ACCESS_ROLE mapping does not (yet)
        # recognize. BigQuery's API reports that case back as an ordinary
        # exception from update_dataset, not a distinct type, so detect it
        # by message text (the "already exists" / "duplicate" wording the
        # API uses for a conflicting access entry) and treat it as success
        # instead of aborting -- this bead's own live finding was exactly an
        # abort HERE, under `set -e`, leaving the view-creation steps after
        # it never run even though the grant itself was fine. Any OTHER
        # error (a real permission failure, a malformed member, a network
        # fault) still aborts loudly -- only the "it's already granted"
        # shape is swallowed.
        msg = str(exc).lower()
        if "already exists" in msg or "duplicate" in msg:
            print(
                "{} already has {} on {} (reported by the API on write) "
                "-- continuing.".format(args.member, args.role, dataset_ref)
            )
            return 0
        print(
            "ERROR: could not grant {} on {} to {}: {}".format(
                args.role, dataset_ref, args.member, exc
            ),
            file=sys.stderr,
        )
        return 1

    print("Granted {} on {} to {}.".format(args.role, dataset_ref, args.member))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    resolve = sub.add_parser(
        "resolve-location",
        help="Print the LOCATION to use for the telemetry dataset, derived "
        "from the billing export table's own dataset.",
    )
    resolve.add_argument("--project", required=True)
    resolve.add_argument("--dataset", required=True)
    resolve.add_argument("--billing-table", required=True)
    resolve.set_defaults(func=_resolve_location)

    grant = sub.add_parser(
        "grant-dataset-role",
        help="Grant one dataset-scoped BigQuery IAM role to one member "
        "via the API, replacing `bq add-iam-policy-binding`.",
    )
    grant.add_argument("--project", required=True)
    grant.add_argument("--dataset", required=True)
    grant.add_argument("--member", required=True)
    grant.add_argument("--role", required=True)
    grant.set_defaults(func=_grant_dataset_role)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
