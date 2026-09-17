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

    def __init__(self, datasets=None, tables=None, get_dataset_raises=None, list_tables_raises=None):
        # {(project, dataset_id): _FakeDataset}
        self._datasets = dict(datasets or {})
        # {(project, dataset_id): [table_id, ...]}
        self._tables = dict(tables or {})
        # {(project, dataset_id): Exception instance}
        self._get_dataset_raises = dict(get_dataset_raises or {})
        self._list_tables_raises = dict(list_tables_raises or {})
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
    configures."""
    client_holder = {}

    def _fake_client():
        return client_holder.get("client")

    monkeypatch.setattr(telemetry_bq_setup, "_client", _fake_client)

    def _set(client):
        client_holder["client"] = client

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
    assert exit_code == 0
    assert len(dataset.access_entries) == 1
    assert client.update_dataset_calls == []
    assert "already has" in capsys.readouterr().out


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
