"""scripts/telemetry_bq_setup.py -- the location-derivation and
dataset-scoped-grant helper scripts/setup-telemetry.sh calls instead of
`bq show`/`bq add-iam-policy-binding` (bd polyglot-pdf-vzvio).

WHY A FAKE CLIENT, NOT A REAL BIGQUERY PROJECT. Same reasoning as
admin_backend/tests/unit/test_report_routes.py's `captured_queries` fixture:
no CI job has a live BigQuery project, so every test here monkeypatches
telemetry_bq_setup._client() to return an in-memory fake that implements just
the surface this module calls (get_dataset, list_tables, update_dataset).

ASCII only.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

telemetry_bq_setup = importlib.import_module("scripts.telemetry_bq_setup")


class _FakeDataset:
    def __init__(self, location, access_entries=None):
        self.location = location
        self.access_entries = list(access_entries or [])


class _FakeAccessEntry:
    """Mirrors google.cloud.bigquery.AccessEntry's public shape closely
    enough for this module's equality checks (role/entity_type/entity_id)."""

    def __init__(self, role=None, entity_type=None, entity_id=None):
        self.role = role
        self.entity_type = entity_type
        self.entity_id = entity_id


class _FakeClient:
    """A minimal stand-in for google.cloud.bigquery.Client covering exactly
    the calls telemetry_bq_setup.py makes: get_dataset, list_tables,
    update_dataset. Datasets are keyed by (project, dataset_id).

    `get_dataset_raises` / `list_tables_raises` let a test force a
    NON-"not found" exception out of the corresponding call (e.g. a
    permission error or transient network fault), keyed by
    (project, dataset_id), to pin that such faults are surfaced as an
    ERROR rather than silently treated the same as "the dataset/table
    does not exist"."""

    def __init__(self, datasets=None, tables=None, get_dataset_raises=None,
                 list_tables_raises=None, update_dataset_raises=None):
        # {(project, dataset_id): _FakeDataset}
        self._datasets = dict(datasets or {})
        # {(project, dataset_id): [table_id, ...]}
        self._tables = dict(tables or {})
        # {(project, dataset_id): Exception instance}
        self._get_dataset_raises = dict(get_dataset_raises or {})
        self._list_tables_raises = dict(list_tables_raises or {})
        # A single Exception instance (not keyed) update_dataset raises, if
        # given -- bd polyglot-pdf-k5w16's idempotent-tolerant grant path:
        # a test sets this to simulate the BigQuery API rejecting a WRITE
        # as a duplicate/already-exists access entry (the race or
        # unrecognized-shape case this module's own already_granted
        # snapshot check cannot see coming).
        self._update_dataset_raises = update_dataset_raises
        self.update_dataset_calls = []

    def get_dataset(self, ref):
        key = (ref.project, ref.dataset_id)
        if key in self._get_dataset_raises:
            raise self._get_dataset_raises[key]
        if key not in self._datasets:
            raise LookupError("404 dataset not found: {}".format(key))
        return self._datasets[key]

    def list_tables(self, ref):
        key = (ref.project, ref.dataset_id)
        if key in self._list_tables_raises:
            raise self._list_tables_raises[key]
        return list(self._tables.get(key, []))

    def update_dataset(self, dataset, fields):
        self.update_dataset_calls.append((dataset, fields))
        if self._update_dataset_raises is not None:
            raise self._update_dataset_raises
        # Persist the mutation the way the real client would (the caller
        # already mutated `dataset.access_entries` in place before calling
        # this, so nothing else to do -- but we DO need it discoverable by
        # a later get_dataset() call in tests that grant twice).
        for key, ds in self._datasets.items():
            if ds is dataset:
                return
        # Not previously registered under any key -- nothing to update.


@pytest.fixture
def fake_bigquery(monkeypatch):
    """Patches the `google.cloud.bigquery` names telemetry_bq_setup.py
    imports lazily (TableReference, DatasetReference, AccessEntry) with real
    upstream classes (safe -- they do no network I/O to construct) and
    patches telemetry_bq_setup._client to return a _FakeClient the test
    configures.

    The fake records every `project` it was called with
    (`client_holder["project_calls"]`) so tests can pin that _client is
    always invoked with the operator's --project (bd polyglot-pdf-vzvio
    cross-surface review round 5: production code used to call a bare
    bigquery.Client() with no project=, silently depending on an ambient
    default project instead of the one the caller already supplied on the
    command line)."""
    client_holder = {"project_calls": []}

    def _fake_client(project):
        client_holder["project_calls"].append(project)
        return client_holder.get("client")

    monkeypatch.setattr(telemetry_bq_setup, "_client", _fake_client)

    def _set(client):
        client_holder["client"] = client

    _set.project_calls = client_holder["project_calls"]
    return _set


def _run(monkeypatch, fake_client_setter, client, argv):
    fake_client_setter(client)
    return telemetry_bq_setup.main(argv)


# ---------------------------------------------------------------------------
# resolve-location
# ---------------------------------------------------------------------------


def test_resolve_location_prints_billing_dataset_location_when_telemetry_dataset_absent(
    fake_bigquery, capsys
):
    """Mutation: return the telemetry dataset's OWN location instead of the
    billing dataset's when the telemetry dataset does not exist -- red (there
    is nothing to read a location FROM if the dataset was never created)."""
    from google.cloud import bigquery

    client = _FakeClient(
        datasets={
            ("billing-proj", "billing_ds"): _FakeDataset(location="US"),
        }
    )
    fake_bigquery(client)
    exit_code = telemetry_bq_setup.main(
        [
            "resolve-location",
            "--project", "polyglot-demo",
            "--dataset", "polyglot_telemetry",
            "--billing-table",
            "billing-proj.billing_ds.gcp_billing_export_resource_v1_ABC123",
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out.strip()
    assert out == "US"


def test_resolve_location_uses_billing_location_when_telemetry_dataset_empty(
    fake_bigquery, capsys
):
    """An EXISTING but EMPTY telemetry dataset in a DIFFERENT location is not
    a conflict -- nothing in it would be stranded by treating the billing
    dataset's location as authoritative. Mutation: refuse whenever the
    locations differ, regardless of whether the dataset holds tables -- red
    (this is exactly the by-hand recreation this bead's bug report
    describes)."""
    client = _FakeClient(
        datasets={
            ("billing-proj", "billing_ds"): _FakeDataset(location="US"),
            ("polyglot-demo", "polyglot_telemetry"): _FakeDataset(location="us-central1"),
        },
        tables={("polyglot-demo", "polyglot_telemetry"): []},
    )
    fake_bigquery(client)
    exit_code = telemetry_bq_setup.main(
        [
            "resolve-location",
            "--project", "polyglot-demo",
            "--dataset", "polyglot_telemetry",
            "--billing-table",
            "billing-proj.billing_ds.gcp_billing_export_resource_v1_ABC123",
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out.strip()
    assert out == "US"


def test_resolve_location_refuses_when_populated_dataset_location_mismatches(
    fake_bigquery, capsys
):
    """THE headline case (the bug report's actual failure): a telemetry
    dataset that already holds tables in a location DIFFERENT from the
    billing dataset must refuse, not silently print a location that cannot
    actually be applied to the live dataset. Mutation: drop the has_tables
    check (refuse unconditionally on any mismatch, even an empty dataset) or
    drop the refusal (always print the billing location) -- either is red
    against one of this test or the empty-dataset test above."""
    client = _FakeClient(
        datasets={
            ("billing-proj", "billing_ds"): _FakeDataset(location="US"),
            ("polyglot-demo", "polyglot_telemetry"): _FakeDataset(location="us-central1"),
        },
        tables={
            ("polyglot-demo", "polyglot_telemetry"): ["cost_by_firm_month"],
        },
    )
    fake_bigquery(client)
    exit_code = telemetry_bq_setup.main(
        [
            "resolve-location",
            "--project", "polyglot-demo",
            "--dataset", "polyglot_telemetry",
            "--billing-table",
            "billing-proj.billing_ds.gcp_billing_export_resource_v1_ABC123",
        ]
    )
    assert exit_code == 1
    err = capsys.readouterr().err
    assert "ERROR" in err
    assert "us-central1" in err
    assert "US" in err


def test_resolve_location_succeeds_when_locations_already_match(
    fake_bigquery, capsys
):
    """A populated telemetry dataset whose location ALREADY matches the
    billing dataset is not a conflict -- prints that (shared) location.
    Mutation: refuse whenever the dataset holds tables, regardless of
    whether locations match -- red."""
    client = _FakeClient(
        datasets={
            ("billing-proj", "billing_ds"): _FakeDataset(location="US"),
            ("polyglot-demo", "polyglot_telemetry"): _FakeDataset(location="US"),
        },
        tables={
            ("polyglot-demo", "polyglot_telemetry"): ["cost_by_firm_month"],
        },
    )
    fake_bigquery(client)
    exit_code = telemetry_bq_setup.main(
        [
            "resolve-location",
            "--project", "polyglot-demo",
            "--dataset", "polyglot_telemetry",
            "--billing-table",
            "billing-proj.billing_ds.gcp_billing_export_resource_v1_ABC123",
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out.strip()
    assert out == "US"


def test_resolve_location_surfaces_non_notfound_error_reading_telemetry_dataset(
    fake_bigquery, capsys
):
    """A get_dataset failure that is NOT "not found" (a permission error, a
    transient network fault, ...) must NOT be treated the same as "the
    telemetry dataset doesn't exist yet" -- that would silently print the
    billing location without ever having confirmed there is no conflicting,
    already-populated dataset in a different location to protect. Mutation:
    widen the except back to a bare `except Exception` around the
    get_dataset call -- red (this would then print the billing location and
    exit 0 instead of erroring)."""
    client = _FakeClient(
        datasets={
            ("billing-proj", "billing_ds"): _FakeDataset(location="US"),
        },
        get_dataset_raises={
            ("polyglot-demo", "polyglot_telemetry"): PermissionError("access denied"),
        },
    )
    fake_bigquery(client)
    exit_code = telemetry_bq_setup.main(
        [
            "resolve-location",
            "--project", "polyglot-demo",
            "--dataset", "polyglot_telemetry",
            "--billing-table",
            "billing-proj.billing_ds.gcp_billing_export_resource_v1_ABC123",
        ]
    )
    assert exit_code == 1
    err = capsys.readouterr().err
    assert "ERROR" in err
    assert "polyglot_telemetry" in err


def test_resolve_location_surfaces_error_listing_tables_in_telemetry_dataset(
    fake_bigquery, capsys
):
    """A list_tables failure on an existing telemetry dataset must be
    surfaced as an ERROR, not left to propagate as a raw traceback and not
    silently treated as "no tables". Mutation: drop the try/except around
    the has_tables lookup -- red (an unhandled exception instead of a
    clean ERROR: line, contradicting this module's own documented
    "every failure prints a human-readable reason first" contract)."""
    client = _FakeClient(
        datasets={
            ("billing-proj", "billing_ds"): _FakeDataset(location="US"),
            ("polyglot-demo", "polyglot_telemetry"): _FakeDataset(location="us-central1"),
        },
        list_tables_raises={
            ("polyglot-demo", "polyglot_telemetry"): TimeoutError("deadline exceeded"),
        },
    )
    fake_bigquery(client)
    exit_code = telemetry_bq_setup.main(
        [
            "resolve-location",
            "--project", "polyglot-demo",
            "--dataset", "polyglot_telemetry",
            "--billing-table",
            "billing-proj.billing_ds.gcp_billing_export_resource_v1_ABC123",
        ]
    )
    assert exit_code == 1
    err = capsys.readouterr().err
    assert "ERROR" in err
    assert "polyglot_telemetry" in err


def test_resolve_location_rejects_a_malformed_billing_table_argument(
    fake_bigquery, capsys
):
    """A --billing-table that is not PROJECT.DATASET.TABLE must fail loudly,
    not raise an unhandled traceback. Mutation: remove the try/except around
    TableReference.from_string -- red (an operator typo becomes a stack
    trace instead of a one-line message)."""
    fake_bigquery(_FakeClient())
    exit_code = telemetry_bq_setup.main(
        [
            "resolve-location",
            "--project", "polyglot-demo",
            "--dataset", "polyglot_telemetry",
            "--billing-table", "not-a-valid-reference",
        ]
    )
    assert exit_code == 1
    assert "ERROR" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# grant-dataset-role
# ---------------------------------------------------------------------------


def test_grant_dataset_role_adds_a_new_access_entry(fake_bigquery, capsys):
    """The headline replacement for `bq add-iam-policy-binding`: a role not
    already present is appended to access_entries and update_dataset is
    called with ["access_entries"]. Mutation: forget to call update_dataset,
    or pass the wrong fields list -- red."""
    dataset = _FakeDataset(location="US", access_entries=[])
    client = _FakeClient(datasets={("polyglot-demo", "polyglot_telemetry"): dataset})
    fake_bigquery(client)

    exit_code = telemetry_bq_setup.main(
        [
            "grant-dataset-role",
            "--project", "polyglot-demo",
            "--dataset", "polyglot_telemetry",
            "--member", "serviceAccount:admin-backend-sa@polyglot-demo.iam.gserviceaccount.com",
            "--role", "roles/bigquery.dataViewer",
        ]
    )
    assert exit_code == 0
    assert len(dataset.access_entries) == 1
    entry = dataset.access_entries[0]
    assert entry.role == "roles/bigquery.dataViewer"
    assert entry.entity_type == "userByEmail"
    assert entry.entity_id == "admin-backend-sa@polyglot-demo.iam.gserviceaccount.com"
    assert len(client.update_dataset_calls) == 1
    updated_dataset, fields = client.update_dataset_calls[0]
    assert updated_dataset is dataset
    assert fields == ["access_entries"]
    assert "Granted" in capsys.readouterr().out


def test_grant_dataset_role_is_idempotent(fake_bigquery, capsys):
    """A role already granted to this exact member must not be duplicated,
    and must not call update_dataset again -- an operator re-running
    setup-telemetry.sh on an already-provisioned project must not spam
    redundant writes. Mutation: drop the already_granted check -- red (the
    entry count would double on a second run)."""
    from google.cloud import bigquery

    existing_entry = bigquery.AccessEntry(
        role="roles/bigquery.dataViewer",
        entity_type="userByEmail",
        entity_id="admin-backend-sa@polyglot-demo.iam.gserviceaccount.com",
    )
    dataset = _FakeDataset(location="US", access_entries=[existing_entry])
    client = _FakeClient(datasets={("polyglot-demo", "polyglot_telemetry"): dataset})
    fake_bigquery(client)

    exit_code = telemetry_bq_setup.main(
        [
            "grant-dataset-role",
            "--project", "polyglot-demo",
            "--dataset", "polyglot_telemetry",
            "--member", "serviceAccount:admin-backend-sa@polyglot-demo.iam.gserviceaccount.com",
            "--role", "roles/bigquery.dataViewer",
        ]
    )
def test_grant_dataset_role_is_idempotent_against_a_real_api_shaped_entry(
    fake_bigquery, capsys
):
    """Regression for the live-verified bug (fresh-eyes round on bd
    polyglot-pdf-vzvio, 2026-09-17): a real, previously-granted access entry
    round-tripped through the actual BigQuery API is NEVER stored with the
    IAM-style role string this script is invoked with -- the server
    normalizes a userByEmail entity's role down to the legacy
    READER/WRITER/OWNER form (confirmed live against a real dataset's ACL:
    a grant originally made via `bq add-iam-policy-binding --role
    roles/bigquery.dataViewer` reads back as
    {"role": "READER", "userByEmail": "..."}). The OTHER idempotency test
    above constructs its existing entry with role="roles/bigquery.dataViewer"
    directly, which is NOT what a real dataset ever contains and was
    (unintentionally) masking this bug. Mutation: revert the
    _IAM_ROLE_TO_LEGACY_ACCESS_ROLE normalization and compare
    `entry.role == args.role` directly -- red (already_granted is always
    False against this real-shaped entry, so update_dataset gets called and
    a duplicate access entry is appended on every re-run)."""
    from google.cloud import bigquery

    existing_entry = bigquery.AccessEntry(
        role="READER",
        entity_type="userByEmail",
        entity_id="admin-backend-sa@polyglot-demo.iam.gserviceaccount.com",
    )
    dataset = _FakeDataset(location="US", access_entries=[existing_entry])
    client = _FakeClient(datasets={("polyglot-demo", "polyglot_telemetry"): dataset})
    fake_bigquery(client)

    exit_code = telemetry_bq_setup.main(
        [
            "grant-dataset-role",
            "--project", "polyglot-demo",
            "--dataset", "polyglot_telemetry",
            "--member", "serviceAccount:admin-backend-sa@polyglot-demo.iam.gserviceaccount.com",
            "--role", "roles/bigquery.dataViewer",
        ]
    )
    assert exit_code == 0
    assert len(dataset.access_entries) == 1
    assert client.update_dataset_calls == []
    assert "already has" in capsys.readouterr().out


def test_grant_dataset_role_is_idempotent_for_data_editor_against_a_real_api_shaped_entry(
    fake_bigquery, capsys
):
    """Same regression as above, for the OTHER role setup-telemetry.sh
    grants (roles/bigquery.dataEditor, for the log sink's writer identity) --
    a real WRITER-shaped entry must also be recognized. Mutation: an
    incomplete _IAM_ROLE_TO_LEGACY_ACCESS_ROLE mapping (e.g. only
    dataViewer -> READER) -- red for this role specifically, even though
    the dataViewer case above would stay green, which is exactly the
    per-parametrization trap this repo's testing doctrine warns about."""
    from google.cloud import bigquery

    existing_entry = bigquery.AccessEntry(
        role="WRITER",
        entity_type="userByEmail",
        entity_id="telemetry-sink-writer@gcp-sa-logging.iam.gserviceaccount.com",
    )
    dataset = _FakeDataset(location="US", access_entries=[existing_entry])
    client = _FakeClient(datasets={("polyglot-demo", "polyglot_telemetry"): dataset})
    fake_bigquery(client)

    exit_code = telemetry_bq_setup.main(
        [
            "grant-dataset-role",
            "--project", "polyglot-demo",
            "--dataset", "polyglot_telemetry",
            "--member", "serviceAccount:telemetry-sink-writer@gcp-sa-logging.iam.gserviceaccount.com",
            "--role", "roles/bigquery.dataEditor",
        ]
    )
    assert exit_code == 0
    assert len(dataset.access_entries) == 1
    assert client.update_dataset_calls == []
    assert "already has" in capsys.readouterr().out


def test_grant_dataset_role_rejects_an_unmapped_role(fake_bigquery, capsys):
    """A --role this module has no legacy-form mapping for must fail loudly
    rather than silently comparing the raw IAM string (which would never
    match a real entry, defeating idempotency without any error at all).
    Mutation: drop the legacy_role is None check -- red (no error, and the
    role would be silently compared as a raw IAM string forever)."""
    dataset = _FakeDataset(location="US", access_entries=[])
    client = _FakeClient(datasets={("polyglot-demo", "polyglot_telemetry"): dataset})
    fake_bigquery(client)

    exit_code = telemetry_bq_setup.main(
        [
            "grant-dataset-role",
            "--project", "polyglot-demo",
            "--dataset", "polyglot_telemetry",
            "--member", "serviceAccount:admin-backend-sa@polyglot-demo.iam.gserviceaccount.com",
            "--role", "roles/bigquery.admin",
        ]
    )
    assert exit_code == 1
    assert dataset.access_entries == []
    assert client.update_dataset_calls == []
    err = capsys.readouterr().err
    assert "ERROR" in err
    assert "roles/bigquery.admin" in err


def test_grant_dataset_role_rejects_a_non_service_account_member(fake_bigquery, capsys):
    """This helper only supports the grants setup-telemetry.sh makes, all of
    which are service accounts -- refuse anything else rather than silently
    mis-parsing it as an email. Mutation: drop the startswith check -- red
    (a "user:..." member would be granted with the wrong entity semantics
    with no error)."""
    dataset = _FakeDataset(location="US", access_entries=[])
    client = _FakeClient(datasets={("polyglot-demo", "polyglot_telemetry"): dataset})
    fake_bigquery(client)

    exit_code = telemetry_bq_setup.main(
        [
            "grant-dataset-role",
            "--project", "polyglot-demo",
            "--dataset", "polyglot_telemetry",
            "--member", "user:someone@example.com",
            "--role", "roles/bigquery.dataViewer",
        ]
    )
    assert exit_code == 1
    assert dataset.access_entries == []
    assert "ERROR" in capsys.readouterr().err


def test_grant_dataset_role_is_idempotent_tolerant_on_an_already_exists_write_error(
    fake_bigquery, capsys
):
    """bd polyglot-pdf-k5w16's second requirement: when the already_granted
    SNAPSHOT check misses a grant that the API itself reports already
    exists (a race with a concurrent grant, or a live access-entry shape
    this module's own _IAM_ROLE_TO_LEGACY_ACCESS_ROLE mapping does not
    recognize), update_dataset raising an "already exists"-shaped error
    must be treated as SUCCESS (log and continue), not an aborted script --
    this is exactly the live failure this bead was filed for: an abort at
    the grant step under `set -e` left every view uncreated even though
    the underlying grant was fine. Mutation: remove the "already exists" /
    "duplicate" detection and let update_dataset's exception always fall
    through to the ERROR branch -- red (exit_code would be 1 instead of 0,
    and no "-- continuing." message would be printed)."""
    dataset = _FakeDataset(location="US", access_entries=[])
    client = _FakeClient(
        datasets={("polyglot-demo", "polyglot_telemetry"): dataset},
        update_dataset_raises=Exception(
            "409 Already Exists: access entry for "
            "admin-backend-sa@polyglot-demo.iam.gserviceaccount.com "
            "already exists"
        ),
    )
    fake_bigquery(client)

    exit_code = telemetry_bq_setup.main(
        [
            "grant-dataset-role",
            "--project", "polyglot-demo",
            "--dataset", "polyglot_telemetry",
            "--member", "serviceAccount:admin-backend-sa@polyglot-demo.iam.gserviceaccount.com",
            "--role", "roles/bigquery.dataViewer",
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "continuing" in out.lower()


def test_grant_dataset_role_still_fails_loudly_on_an_unrelated_write_error(
    fake_bigquery, capsys
):
    """The idempotent-tolerant path above must NOT swallow every write
    failure -- only the specific "it's already granted" shape. A real
    permission error, network fault, or any other update_dataset failure
    must still abort with an ERROR line, exactly as before this bead.
    Mutation: widen the "already exists" detection to match on any
    Exception regardless of message -- red (this test's PermissionError,
    which contains neither "already exists" nor "duplicate", would then be
    swallowed as success instead of surfaced as ERROR)."""
    dataset = _FakeDataset(location="US", access_entries=[])
    client = _FakeClient(
        datasets={("polyglot-demo", "polyglot_telemetry"): dataset},
        update_dataset_raises=PermissionError(
            "403 caller does not have bigquery.datasets.update permission"
        ),
    )
    fake_bigquery(client)

    exit_code = telemetry_bq_setup.main(
        [
            "grant-dataset-role",
            "--project", "polyglot-demo",
            "--dataset", "polyglot_telemetry",
            "--member", "serviceAccount:admin-backend-sa@polyglot-demo.iam.gserviceaccount.com",
            "--role", "roles/bigquery.dataViewer",
        ]
    )
    assert exit_code == 1
    err = capsys.readouterr().err
    assert "ERROR" in err
    assert "could not grant" in err.lower()


def test_grant_dataset_role_fails_loudly_when_dataset_missing(fake_bigquery, capsys):
    """A dataset that does not exist yet must produce a clear error, not an
    unhandled exception -- setup-telemetry.sh's `set -e` turns this straight
    into an aborted run either way, but the operator needs to know WHY.
    Mutation: let the LookupError propagate uncaught -- red (still aborts,
    but with a traceback instead of an ERROR: line)."""
    client = _FakeClient(datasets={})
    fake_bigquery(client)

    exit_code = telemetry_bq_setup.main(
        [
            "grant-dataset-role",
            "--project", "polyglot-demo",
            "--dataset", "polyglot_telemetry",
            "--member", "serviceAccount:admin-backend-sa@polyglot-demo.iam.gserviceaccount.com",
            "--role", "roles/bigquery.dataViewer",
        ]
    )
    assert exit_code == 1
    assert "ERROR" in capsys.readouterr().err



# ---------------------------------------------------------------------------
# _client project passthrough (bd polyglot-pdf-vzvio cross-surface review
# round 5)
# ---------------------------------------------------------------------------


def test_resolve_location_passes_project_through_to_client(fake_bigquery):
    """_client must be constructed with the operator's --project, not left
    to resolve an ambient default project on its own -- the whole point of
    this script is to stop depending on the operator's ambient environment.
    Mutation: change the resolve-location call site back to a bare
    `_client()` -- red (fake_bigquery's fake raises TypeError on a bare
    call now that _client takes a required `project` argument, and even if
    it did not, project_calls would be empty instead of ["polyglot-demo"])."""
    client = _FakeClient(
        datasets={("billing-proj", "billing_ds"): _FakeDataset(location="US")},
    )
    fake_bigquery(client)
    exit_code = telemetry_bq_setup.main(
        [
            "resolve-location",
            "--project", "polyglot-demo",
            "--dataset", "polyglot_telemetry",
            "--billing-table",
            "billing-proj.billing_ds.gcp_billing_export_resource_v1_ABC123",
        ]
    )
    assert exit_code == 0
    assert fake_bigquery.project_calls == ["polyglot-demo"]


def test_grant_dataset_role_passes_project_through_to_client(fake_bigquery):
    """Same passthrough contract as resolve-location, for the other
    subcommand. Mutation: change the grant-dataset-role call site back to a
    bare `_client()` -- red."""
    dataset = _FakeDataset(location="US", access_entries=[])
    client = _FakeClient(datasets={("polyglot-demo", "polyglot_telemetry"): dataset})
    fake_bigquery(client)
    exit_code = telemetry_bq_setup.main(
        [
            "grant-dataset-role",
            "--project", "polyglot-demo",
            "--dataset", "polyglot_telemetry",
            "--member", "serviceAccount:admin-backend-sa@polyglot-demo.iam.gserviceaccount.com",
            "--role", "roles/bigquery.dataViewer",
        ]
    )
    assert exit_code == 0
    assert fake_bigquery.project_calls == ["polyglot-demo"]


def test_client_constructs_with_explicit_project_not_ambient_default():
    """Unmocked unit test of _client itself (not the CLI): it must call
    bigquery.Client(project=...) rather than a bare bigquery.Client(),
    which would fall back to google.auth.default()'s ambient project
    lookup. Confirmed on a real install: a bare bigquery.Client() with no
    resolvable ambient project raises
    "EnvironmentError: Project was not passed and could not be determined
    from the environment." -- reintroducing the exact ambient-environment
    dependency this script exists to remove, even though --project was
    already given on the command line.
    Mutation: change `bigquery.Client(project=project)` back to
    `bigquery.Client()` inside telemetry_bq_setup._client -- red (this test
    asserts the constructor call received project= explicitly via a spy)."""
    import unittest.mock as mock

    calls = []

    class _SpyClient:
        def __init__(self, *args, **kwargs):
            calls.append((args, kwargs))

    with mock.patch("google.cloud.bigquery.Client", _SpyClient):
        client = telemetry_bq_setup._client("polyglot-demo")

    assert client is not None
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == ()
    assert kwargs.get("project") == "polyglot-demo", (
        "bigquery.Client() was not called with project='polyglot-demo' -- "
        "got args={!r} kwargs={!r}".format(args, kwargs)
    )
