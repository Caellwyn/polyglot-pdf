"""Read-only, redacted data-at-rest inventory of the deployed system (bd
polyglot-pdf-uaxt5, sprint 23 workstream A: PF-8's retention half + PF-9).

WHAT THIS IS. For every Firestore collection this app writes, sample N docs
(default small) and print KEY NAMES, value TYPES, and max STRING LENGTH per
key -- never a value -- flagging any key outside that collection's pinned
allowlist. Then list the GCS kit bucket for unexpected top-level objects, and
print both BigQuery telemetry tables' schemas (column names/types, never
row data). This is the LIVE half of the sprint-23 data-at-rest inventory;
the STATIC half (every store the deployed system writes, incl. second
copies and repo-as-a-store) is enumerated in this bead's PR report and in
docs/sprint_23_security-audit_plan.md's workstream-A section.

SHAPE: operator ADC (not the Cloud Run runtime SA -- your own gcloud/
application-default credentials need Firestore/Storage/BigQuery read access
on the target project) and `--project` REQUIRED, pinning the query
deterministically (pre-initializes firebase_admin with this projectId,
which beats the ADC credential's own project resolution -- an env var alone
can silently query the wrong project) -- the same rationale
scripts/read_confirmations.py's own --project flag documents. The
DEAD_PROJECTS refusal and the resolved-project-mismatch check are copied
from scripts/grant_credits.py (and scripts/bootstrap_firm.py, which
originated the --project pattern grant_credits.py itself follows) --
read_confirmations.py carries neither check itself, only the --project
flag's determinism rationale above. Same former-prod project, same reason:
a stale muscle-memory invocation must not hang or half-write -- though this
script never writes at all.

NEVER PRINTS A VALUE. Every collection has a PINNED_ALLOWLISTS entry (the
exact key set its own writer emits, copied from that module's own
allowlist/test -- confirmation_logger.py, credit_ledger.ENTRY_FIELDS,
audit_log.ROW_FIELDS, the firms doc keys pinned in
admin_backend/tests/unit/test_audit_log_shapes.py, links_store /
link_redemptions per backend/tests/unit/test_store_shapes.py, alerts.py).
A collection with NO code-side writer in this repo (authorized_emails --
managed out of band per firestore.rules' own comment) is sampled with an
empty allowlist, so EVERY key it carries is reported as "outside the
allowlist" -- which is the correct, honest answer for an unmanaged store:
there is no pin to compare against, so nothing is silently assumed safe.

WINDOWS NOTE: gcloud/bq are spawned via shutil.which(...) first (mirrors
scripts/verify_service_reachable.py's own rationale) -- a bare "gcloud"
raises WinError 2 on Windows, since CreateProcess resolves a bare name only
to gcloud.exe while the Cloud SDK ships gcloud.cmd. Firestore reads go
through google-cloud-firestore directly (backend/.venv already vendors it),
not firebase_admin's own Firestore accessor, per the bead's own live-run
rule.

EXIT CODES: 0 = ran to completion (regardless of whether any key was
flagged -- the SUMMARY line says whether anything was flagged; grep it, do
not rely on the exit code to mean "clean"); 2 = refused (missing --project,
dead project, project mismatch); 3 = a store could not be reached at all
(the report still prints what it could; this signals "incomplete", not
"clean").

ASCII only.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# The former prod project is DEAD and unreachable (maintainer, 2026-08-14) --
# the SAME refusal scripts/grant_credits.py and scripts/bootstrap_firm.py
# carry, restated here because this is a read-only reporting tool an
# operator might reach for out of the same muscle memory that hits the
# write scripts.
DEAD_PROJECTS = {"polyglot-forms-919f2"}

DEFAULT_SAMPLE_SIZE = 20

# ---------------------------------------------------------------------------
# Pinned per-collection allowlists -- the exact key set THIS repo's own code
# writes, copied from each store's own module/test (never re-derived by
# guessing at the Firestore console). A key outside this set is flagged,
# never silently accepted. An empty tuple means "no code-side writer in this
# repo" -- every key found is then, correctly, outside the (empty) allowlist.
# ---------------------------------------------------------------------------

PINNED_ALLOWLISTS: dict[str, frozenset] = {
    # backend/utils/confirmation_logger.py -- FOUR event shapes share one
    # collection (field_confirmed, disclaimer_accepted, form_session_started,
    # form_session_ended); this is the UNION of all four. The first two are
    # pinned by test_confirmation_firestore_sink.py's own allowlist
    # assertions; `link_jti`/`employee_id`/`section_id` come from
    # log_form_session_start's own event dict (log_form_session_start /
    # log_form_session_end have no equivalent allowlist test today -- found
    # via this script's own live run against polyglot-demo-aa709, which
    # flagged `section_id` before this line was added; a live-verified gap
    # in test coverage, not a live-verified LEAK, since every key here is a
    # metadata id/timestamp/enum, never a value).
    "confirmation_events": frozenset({
        "timestamp", "event", "form_id", "kit_id", "edition_date", "firm_id",
        "form_session_id", "field_id", "field_name", "confirmation_method",
        "language", "timestamp_unix_ms", "script_version", "user_agent",
        "total_fields_confirmed", "completion_status", "expire_at",
        "section_id", "link_jti", "employee_id",
    }),
    # firestore.rules: "entries are managed out of band (Firebase Console /
    # admin tooling)" -- no writer in this repo, so no pin to compare
    # against. Left EMPTY deliberately (see module docstring).
    "authorized_emails": frozenset(),
    # backend/services/firms.py::upsert_firm +
    # admin_backend/routes/firm_routes.py's create/patch routes, pinned in
    # admin_backend/tests/unit/test_audit_log_shapes.py::FIRM_DOC_ALLOWED_KEYS
    # (this same bead).
    "firms": frozenset({
        "name", "contact_email", "allowed_kits", "status", "kind", "plan",
        "balance_credits", "balance_updated_at", "created_at", "updated_at",
    }),
    # backend/services/credit_ledger.py::ENTRY_FIELDS -- the nested
    # firms/{firm_id}/ledger subcollection. Sampled by name below since the
    # CLI takes flat collection ids; the live run walks it per firm.
    "ledger": frozenset({
        "type", "amount", "usd_amount", "firm_kind", "channel",
        "balance_after", "actor", "reason", "link_jti", "kit_id", "ts",
        "period",
    }),
    # backend/services/usage_rollups.py::record_session_end -- the nested
    # firms/{firm_id}/usage/{YYYY-MM[_channel]} subcollection doc. The
    # by_kit/by_employee/by_language maps are keyed on IDENTIFIERS (a kit
    # id, a uid, a spoken-language name) with {sessions, cost_usd} values --
    # this collection's own allowlist covers the TOP-LEVEL field names only
    # (by_kit/by_employee/by_language themselves); the identifier-shaped
    # keys one level down are reported separately by _summarize_docs'
    # nested_keys, never flagged against a closed set (an identifier is
    # expected to vary per doc). links_opened/links_completed are a SECOND
    # writer of this SAME doc (record_link_opened/record_link_completed,
    # called from link_redemptions.py's open_link/complete_link) -- this is
    # the union of both writers' fields, since a real doc carries either or
    # both depending on the month's traffic.
    "firms_usage": frozenset({
        "connections_ended", "sessions_completed", "cost_usd_total",
        "by_kit", "by_employee", "by_language", "kind", "channel",
        "links_opened", "links_completed",
    }),
    # backend/services/usage_rollups.py::record_session_end -- the nested
    # kits/{kit_id}/usage/{YYYY-MM[_channel]} subcollection doc. by_firm is
    # keyed on firm ids (identifiers, reported via nested_keys as above).
    "kits_usage": frozenset({
        "connections_ended", "sessions_completed", "cost_usd_total",
        "by_firm", "kind", "channel",
    }),
    # backend/services/link_metering.py::record_mint -- the nested
    # firms/{firm_id}/link_usage/{YYYY-MM} subcollection doc (billing
    # counter for the per-firm monthly link-mint allowance; NOT abuse
    # prevention, per that module's own docstring -- it counts and
    # reports, never gates a mint).
    "firms_link_usage": frozenset({
        "minted", "updated_at",
    }),
    # backend/services/links_store.py::build_mint_record (base shape, pinned
    # in backend/tests/unit/test_store_shapes.py::
    # LINKS_MINT_RECORD_ALLOWED_KEYS) PLUS mark_opened(), a SECOND writer of
    # this SAME collection (found in bd polyglot-pdf-uaxt5's Opus cross-
    # surface review, the same "a second writer touches this doc" class as
    # link_redemptions' own link_spend.py finding above) -- mark_opened()
    # stamps `opened_at` alongside flipping `status` (already in the base
    # set) from minted to opened on the link's FIRST open. The union is
    # test_store_shapes.py::LINKS_MINT_RECORD_ALLOWED_KEYS_WITH_OPENED,
    # since a real deployed doc can carry it once a client has opened the
    # link.
    "links": frozenset({
        "jti", "firm_id", "kit_id", "employee_id", "credit_cost", "cap_usd",
        "minted_at", "open_deadline", "status", "revoked_by", "revoked_at",
        "expire_at", "opened_at",
    }),
    "links_staging": frozenset({
        "jti", "firm_id", "kit_id", "employee_id", "credit_cost", "cap_usd",
        "minted_at", "open_deadline", "status", "revoked_by", "revoked_at",
        "expire_at", "opened_at",
    }),
    # backend/services/link_redemptions.py::open_link/complete_link (base
    # shape, pinned in backend/tests/unit/test_store_shapes.py::
    # REDEMPTION_RECORD_ALLOWED_KEYS) PLUS backend/services/link_spend.py's
    # record_spend(), a THIRD writer of this SAME collection (imports
    # link_redemptions._collection directly) that adds spend_usd/turns/
    # spend_updated_at -- the union is
    # test_store_shapes.py::REDEMPTION_RECORD_ALLOWED_KEYS_WITH_SPEND, since
    # a real deployed doc can carry either shape depending on whether a paid
    # session has run against it yet.
    "link_redemptions": frozenset({
        "jti", "firm_id", "kit_id", "opened_at", "completed_at",
        "spend_usd", "turns", "spend_updated_at",
    }),
    "link_redemptions_staging": frozenset({
        "jti", "firm_id", "kit_id", "opened_at", "completed_at",
        "spend_usd", "turns", "spend_updated_at",
    }),
    # admin_backend/services/audit_log.py::ROW_FIELDS is the INITIAL write
    # shape (build_row(), pinned by test_audit_log.py) -- but mark_committed
    # / mark_failed (the PENDING-THEN-COMMITTED form's step 2) add
    # `committed_ts` (both) and `error` (mark_failed only) on top of that
    # base afterwards, per that module's own docstring ("update only state
    # (plus error / committed_ts) on a row THIS process just created"). This
    # allowlist is the UNION covering a row at any point in its lifecycle --
    # found via this script's own live run against polyglot-demo-aa709,
    # which flagged `committed_ts` before this line was added.
    "admin_audit_log": frozenset({
        "actor_uid", "actor_email", "action", "target", "before", "after",
        "channel", "request_id", "state", "ts", "committed_ts", "error",
    }),
    # backend/services/runtime_config.py -- a free-form doc keyed on
    # RUNTIME_CONFIG_KEYS (a growing, versioned list read live below rather
    # than hand-copied here, since the whole point of that module is that
    # new keys land there routinely and are already reported by its own
    # known_keys/unknown_keys split).
    "app_config": None,  # sentinel: resolved live from runtime_config
    # backend/services/alerts.py::_write.
    "alerts": frozenset({
        "firm_id", "kind", "level", "ts", "context", "expire_at",
        "acknowledged_by", "acknowledged_at", "emailed_at",
    }),
    # form-kit metadata docs (kit_commercials / usage rollups touch this
    # collection too) -- admin_backend/routes/usage_routes.py's
    # KITS_COLLECTION. No single writer owns the whole doc shape the way
    # firms.py does, so this collection is sampled and reported, but not
    # flagged against a closed allowlist (None has the same "report
    # everything" meaning as an empty frozenset here, kept distinct from
    # app_config's live-resolved case only for readability).
    "kits": None,
}


class DeadProjectError(Exception):
    """The named project is dead; refusing to query it."""


def _resolve_exe(name: str) -> str:
    """shutil.which first (Windows: gcloud.cmd, not gcloud.exe -- see module
    docstring); pass the bare name through unchanged if unresolvable (a
    POSIX host, or PATH genuinely missing it, in which case the subprocess
    call fails informatively rather than this function guessing)."""
    return shutil.which(name) or name


def _run(argv: list) -> "tuple[int, str, str]":
    """Run a subprocess, stdout/stderr captured SEPARATELY (never merged --
    a component-update nag on stderr must never corrupt a stdout parse)."""
    argv = [_resolve_exe(argv[0])] + list(argv[1:])
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        return 127, "", "{}: {}".format(type(exc).__name__, exc)
    return proc.returncode, proc.stdout, proc.stderr


def _init_firebase_admin(project: str) -> None:
    """Pin firebase_admin's resolved project DETERMINISTICALLY. The
    initialize_app(options={"projectId": project}) call mirrors
    scripts/read_confirmations.py's own rationale exactly: firebase_admin
    resolves the project from the ADC CREDENTIAL first, so an env var alone
    can silently query whatever project the operator's gcloud ADC defaults
    to. Must run before any backend module that touches firebase_admin is
    imported. The resolved-project-mismatch check below it (raise on
    `resolved != project`) is copied from scripts/grant_credits.py instead --
    read_confirmations.py does not carry that second check."""
    import firebase_admin

    if not firebase_admin._apps:
        firebase_admin.initialize_app(options={"projectId": project})

    resolved = firebase_admin.get_app().project_id
    if resolved != project:
        raise DeadProjectError(
            "resolved firebase_admin project is {!r}, not {!r} -- refusing "
            "to read the wrong project.".format(resolved, project)
        )


def _firestore_client(project: str):
    """A plain google-cloud-firestore client (NOT firebase_admin's own
    Firestore accessor), per the bead's own live-run instruction. Uses the
    OPERATOR's ADC, same as every read in this script."""
    from google.cloud import firestore

    return firestore.Client(project=project)


# ---------------------------------------------------------------------------
# The value-shape summary: KEY NAMES, value TYPES, max STRING LENGTH -- and
# THAT IS ALL. No branch here ever holds onto or prints a value.
# ---------------------------------------------------------------------------

def _summarize_docs(docs: list, allowlist: "Optional[frozenset]") -> dict:
    """Reduce a batch of Firestore documents to a redacted shape summary.

    Returns {
        "doc_count": int,
        "keys": {key: {"types": {type_name, ...}, "max_str_len": int|None}},
        "flagged_keys": [key, ...],   # keys outside `allowlist`, sorted
        "nested_keys": {top_level_key: [nested_key_name, ...]},
    }

    `allowlist=None` means "no closed set to check against" -- every key is
    reported in `keys` but `flagged_keys` stays empty (a deliberate
    "reporting only" mode for a collection with no single pinned writer,
    e.g. kits/app_config, so this script does not manufacture false
    positives against a shape it was never told to expect).

    NESTED DICT VALUES, ONE LEVEL DOWN: usage_rollups.py's rollup docs carry
    maps like `by_employee`/`by_language`/`by_kit`/`by_firm` whose KEYS are
    identifiers (an employee uid, a spoken-language name, a kit id, a firm
    id) -- not schema fields. A flat top-level scan would report only
    "by_employee: types=[dict]" and miss that an identifier-shaped string is
    sitting one level down. So for every top-level key whose value is a
    dict, this also collects the NESTED key NAMES (never their values,
    which are always plain counts here) into `nested_keys`, printed
    separately by the caller as "possible identifiers embedded as map keys"
    -- informational, not flagged against any allowlist (an identifier is
    expected to vary per doc; the allowlist question is about the outer
    field name, e.g. "by_employee", which the normal `keys`/`flagged_keys`
    machinery above already covers).
    """
    keys: dict[str, dict[str, Any]] = {}
    nested_keys: dict[str, set] = {}
    for doc in docs:
        data = doc.to_dict() or {}
        for key, value in data.items():
            entry = keys.setdefault(key, {"types": set(), "max_str_len": None})
            entry["types"].add(type(value).__name__)
            if isinstance(value, str):
                cur = entry["max_str_len"] or 0
                entry["max_str_len"] = max(cur, len(value))
            if isinstance(value, dict):
                nested_keys.setdefault(key, set()).update(value.keys())

    flagged: list[str] = []
    if allowlist is not None:
        flagged = sorted(set(keys) - allowlist)

    return {
        # ALWAYS True: a successful summarize (even of zero docs -- an
        # empty collection is not a failure) reached the store and read it.
        # The `reachable` flag is the ONE property every branch of this
        # script's report (Firestore collections, the bucket, BigQuery)
        # checks the SAME way -- see the print loop below, which used to
        # check `"error" in summary` for Firestore but `reachable` for
        # everything else (bd polyglot-pdf-uaxt5, Opus cross-surface review
        # nit).
        "reachable": True,
        "doc_count": len(docs),
        "keys": {
            k: {"types": sorted(v["types"]), "max_str_len": v["max_str_len"]}
            for k, v in keys.items()
        },
        "flagged_keys": flagged,
        "nested_keys": {k: sorted(v) for k, v in nested_keys.items()},
    }


def inventory_collection(
    db, collection_name: str, *, sample_size: int, allowlist,
) -> dict:
    """Sample up to `sample_size` docs from `collection_name` and summarize.

    A collection that does not exist (0 docs) is reported honestly as
    empty, never conflated with a read failure -- see the CLI's own
    exit-code note.
    """
    docs = list(db.collection(collection_name).limit(sample_size).stream())
    return _summarize_docs(docs, allowlist)


def inventory_subcollection(
    db, *, parent_collection: str, subcollection: str, allowlist,
    parent_sample_size: int, child_sample_size: int,
) -> dict:
    """Sample a handful of PARENT docs (firms, kits), then a handful of
    SUBCOLLECTION docs per parent, and summarize the UNION -- the shape is
    the same across every parent (every firm's ledger entry looks the same
    shape-wise; every firm's usage rollup does too), so sampling several
    parents just guards against one parent's doc being unrepresentative.

    Generalized from the original ledger-only sampler (bd polyglot-pdf-
    uaxt5, Opus cross-surface review finding: the inventory omitted
    firms/{id}/usage, kits/{id}/usage and firms/{id}/link_usage -- three of
    the four SUBCOLLECTION-suffixed stores this repo's backend/services/
    writes into. `grep -rn "SUBCOLLECTION" backend/services/` finds
    EXACTLY four: credit_ledger.LEDGER_SUBCOLLECTION ("ledger", already
    inventoried), usage_rollups.USAGE_SUBCOLLECTION ("usage", mounted under
    BOTH firms and kits), and link_metering._USAGE_SUBCOLLECTION
    ("link_usage", firms only) -- so this generalization plus the three new
    call sites below make the subcollection inventory COMPLETE.
    """
    parent_docs = list(
        db.collection(parent_collection).limit(parent_sample_size).stream())
    all_children = []
    parent_ids_sampled = []
    for parent_snap in parent_docs:
        parent_ids_sampled.append(parent_snap.id)
        children = list(
            db.collection(parent_collection).document(parent_snap.id)
            .collection(subcollection).limit(child_sample_size).stream()
        )
        all_children.extend(children)
    summary = _summarize_docs(all_children, allowlist)
    summary["{}_sampled".format(parent_collection)] = parent_ids_sampled
    return summary


def inventory_app_config(db) -> dict:
    """app_config/{channel} -- resolved live against RUNTIME_CONFIG_KEYS
    rather than a hand-copied constant (see PINNED_ALLOWLISTS' own comment).
    """
    from backend.services.runtime_config import RUNTIME_CONFIG_KEYS

    docs = list(db.collection("app_config").stream())
    return _summarize_docs(docs, frozenset(RUNTIME_CONFIG_KEYS))


# ---------------------------------------------------------------------------
# GCS bucket listing -- object PATHS only, never content.
# ---------------------------------------------------------------------------

def inventory_bucket(bucket: str) -> dict:
    """`gcloud storage ls -r` the kit bucket. Reports counts per top-level
    prefix (<kit>/, _archive/, _drafts/) and any object whose path does not
    fall under a recognized prefix, flagged as unexpected. Never prints an
    object's CONTENT -- paths only, which are kit ids and filenames, not
    client data (form-kit schemas/PDFs carry no user answers by design)."""
    code, out, err = _run(
        ["gcloud", "storage", "ls", "-r", "gs://{}/**".format(bucket)])
    if code != 0:
        return {"reachable": False, "error": err.strip() or "gcloud exit {}".format(code)}

    known_prefixes = ("_archive/", "_drafts/")
    counts: dict[str, int] = {"_archive/": 0, "_drafts/": 0, "<kit>/": 0}
    unexpected: list[str] = []
    prefix = "gs://{}/".format(bucket)
    for line in out.splitlines():
        line = line.strip()
        if not line or not line.startswith(prefix) or line.endswith("/"):
            continue
        rel = line[len(prefix):]
        if rel.startswith(known_prefixes):
            counts[rel.split("/", 1)[0] + "/"] += 1
        elif "/" in rel:
            counts["<kit>/"] += 1
        else:
            unexpected.append(rel)

    return {
        "reachable": True,
        "counts": counts,
        "unexpected_top_level_objects": sorted(unexpected),
    }


# ---------------------------------------------------------------------------
# BigQuery telemetry tables -- SCHEMA only (column names/types), never rows.
# ---------------------------------------------------------------------------

def _bq_unreachable_hint(detail: str) -> str:
    """A one-line, current-state hint appended to a failed `bq` call.

    A local `bq.cmd` shim resolves its own Python interpreter, and on a
    machine with a broken/placeholder `python3.14` earlier on PATH (e.g. a
    Windows Store alias) `bq` fails with a "python3.14: command not found"
    -shaped message even though a perfectly good interpreter is available.
    Setting CLOUDSDK_PYTHON to that interpreter fixes it without touching
    PATH.
    """
    if "python3.14" in detail or "not found" in detail.lower():
        return (
            detail
            + " -- if this says python3.14 was not found, set CLOUDSDK_PYTHON "
            "to a working interpreter (e.g. the backend venv's python.exe) "
            "and retry."
        )
    return detail


def inventory_bigquery_table(project: str, dataset: str, table: str) -> dict:
    code, out, err = _run([
        "bq", "show", "--format=prettyjson", "--project_id", project,
        "{}:{}.{}".format(project, dataset, table),
    ])
    if code != 0:
        detail = err.strip() or "bq exit {}".format(code)
        return {"reachable": False, "error": _bq_unreachable_hint(detail)}

    import json

    try:
        parsed = json.loads(out)
    except json.JSONDecodeError as exc:
        return {"reachable": False, "error": _bq_unreachable_hint(
            "unparseable bq output: {}".format(exc))}

    fields = parsed.get("schema", {}).get("fields", [])
    return {
        "reachable": True,
        "columns": [
            {"name": f.get("name"), "type": f.get("type")} for f in fields
        ],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only, redacted data-at-rest inventory of the "
        "deployed system (Firestore collections, the GCS kit bucket, "
        "BigQuery telemetry tables). Never prints a stored value."
    )
    parser.add_argument(
        "--project", required=True,
        help="target GCP/Firebase project (deterministic: pre-initializes "
        "firebase_admin with this projectId, per scripts/read_confirmations.py's "
        "own rationale, AND asserts the resolved app project matches, per "
        "scripts/grant_credits.py's own guard)",
    )
    parser.add_argument(
        "--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE,
        help="docs to sample per collection (default {})".format(
            DEFAULT_SAMPLE_SIZE),
    )
    parser.add_argument(
        "--bucket", default=None,
        help="the form-kit GCS bucket name (defaults to "
        "<project>-form-kits, this repo's naming convention)",
    )
    parser.add_argument(
        "--bq-dataset", default="polyglot_telemetry",
        help="BigQuery dataset holding the telemetry tables",
    )
    parser.add_argument(
        "--bq-tables", nargs="+",
        default=["cost_by_firm_month", "cost_by_kit_month",
                "cost_by_employee_month", "income_month",
                "hosting_cost_by_service_month"],
        help="BigQuery telemetry table/view names to inspect -- the "
        "sql/telemetry_views.sql views admin_backend/services/"
        "bigquery_reports.py reads, plus the billing-export view "
        "(live-verified against polyglot-demo-aa709, bd polyglot-pdf-uaxt5: "
        "as of this run only hosting_cost_by_service_month exists there -- "
        "the cost_by_*_month/income_month views and their underlying "
        "TELEMETRY_TABLE_STDOUT/STDERR sink tables have not been deployed "
        "to that project yet, so this script reports them UNREACHABLE, "
        "which is the correct, honest answer, not a script defect)",
    )
    parser.add_argument(
        "--skip-bucket", action="store_true",
        help="skip the GCS bucket listing (Firestore + BigQuery only)",
    )
    parser.add_argument(
        "--skip-bigquery", action="store_true",
        help="skip the BigQuery schema checks (Firestore + bucket only)",
    )
    return parser


def main(argv: "Optional[list]" = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.project in DEAD_PROJECTS:
        print(
            "project {} is DEAD and unreachable (maintainer 2026-08-14); "
            "refusing.".format(args.project),
            file=sys.stderr,
        )
        return 2

    try:
        _init_firebase_admin(args.project)
    except DeadProjectError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    incomplete = False
    report: dict[str, Any] = {"project": args.project, "collections": {}}

    try:
        db = _firestore_client(args.project)
    except Exception as exc:  # noqa: BLE001 -- report, do not crash
        print(
            "FAILED to open a Firestore client: {}. Nothing Firestore-side "
            "could be inspected.".format(exc),
            file=sys.stderr,
        )
        db = None
        incomplete = True

    # Collections handled specially below (nested subcollections walked
    # per-parent, or a live-resolved allowlist) rather than through the
    # flat inventory_collection() loop.
    _SPECIAL_CASED = frozenset({
        "app_config", "ledger", "firms_usage", "kits_usage",
        "firms_link_usage",
    })

    if db is not None:
        for coll_name, allowlist in PINNED_ALLOWLISTS.items():
            if coll_name in _SPECIAL_CASED:
                continue
            try:
                report["collections"][coll_name] = inventory_collection(
                    db, coll_name, sample_size=args.sample_size,
                    allowlist=allowlist,
                )
            except Exception as exc:  # noqa: BLE001
                report["collections"][coll_name] = {
                    "reachable": False, "error": str(exc),
                }
                incomplete = True

        # The four SUBCOLLECTION-suffixed stores (grep-confirmed complete --
        # see inventory_subcollection's own docstring): firms/*/ledger,
        # firms/*/usage, kits/*/usage, firms/*/link_usage.
        for report_name, parent_collection, subcollection, allowlist_key in [
            ("firms/*/ledger", "firms", "ledger", "ledger"),
            ("firms/*/usage", "firms", "usage", "firms_usage"),
            ("kits/*/usage", "kits", "usage", "kits_usage"),
            ("firms/*/link_usage", "firms", "link_usage", "firms_link_usage"),
        ]:
            try:
                report["collections"][report_name] = inventory_subcollection(
                    db, parent_collection=parent_collection,
                    subcollection=subcollection,
                    allowlist=PINNED_ALLOWLISTS[allowlist_key],
                    parent_sample_size=min(args.sample_size, 5),
                    child_sample_size=args.sample_size,
                )
            except Exception as exc:  # noqa: BLE001
                report["collections"][report_name] = {
                    "reachable": False, "error": str(exc),
                }
                incomplete = True

        try:
            report["collections"]["app_config"] = inventory_app_config(db)
        except Exception as exc:  # noqa: BLE001
            report["collections"]["app_config"] = {
                "reachable": False, "error": str(exc),
            }
            incomplete = True

    if not args.skip_bucket:
        bucket = args.bucket or "{}-form-kits".format(args.project)
        report["bucket"] = inventory_bucket(bucket)
        if not report["bucket"].get("reachable"):
            incomplete = True

    if not args.skip_bigquery:
        report["bigquery"] = {}
        for table in args.bq_tables:
            result = inventory_bigquery_table(
                args.project, args.bq_dataset, table)
            report["bigquery"][table] = result
            if not result.get("reachable"):
                incomplete = True

    # ---- print the redacted report -------------------------------------
    print("=== data-at-rest inventory: project {} ===".format(args.project))
    any_flagged = False
    for coll_name, summary in report["collections"].items():
        # `reachable` is the ONE flag every branch of this report checks
        # the same way -- Firestore collections, the bucket, and BigQuery
        # alike (bd polyglot-pdf-uaxt5, Opus cross-surface review nit: this
        # used to check `"error" in summary` here specifically).
        if not summary.get("reachable"):
            print("  [{}] UNREACHABLE: {}".format(
                coll_name, summary.get("error")))
            continue
        flagged = summary.get("flagged_keys", [])
        any_flagged = any_flagged or bool(flagged)
        print("  [{}] {} doc(s) sampled".format(coll_name, summary["doc_count"]))
        for key, info in sorted(summary["keys"].items()):
            marker = " <-- OUTSIDE ALLOWLIST" if key in flagged else ""
            print("      {}: types={} max_str_len={}{}".format(
                key, info["types"], info["max_str_len"], marker))
        if flagged:
            print("      FLAGGED KEYS: {}".format(flagged))
        nested = summary.get("nested_keys") or {}
        for outer_key, inner_names in sorted(nested.items()):
            print("      {}.<key> names seen (identifiers, never "
                 "values): {}".format(outer_key, inner_names))

    if "bucket" in report:
        b = report["bucket"]
        if b.get("reachable"):
            print("  [bucket] counts={} unexpected={}".format(
                b["counts"], b["unexpected_top_level_objects"]))
            if b["unexpected_top_level_objects"]:
                any_flagged = True
        else:
            print("  [bucket] UNREACHABLE: {}".format(b.get("error")))

    if "bigquery" in report:
        for table, result in report["bigquery"].items():
            if result.get("reachable"):
                print("  [bigquery.{}] columns={}".format(
                    table, result["columns"]))
            else:
                print("  [bigquery.{}] UNREACHABLE: {}".format(
                    table, result.get("error")))

    print("=== SUMMARY: {} ===".format(
        "KEYS OR OBJECTS OUTSIDE ALLOWLIST FLAGGED ABOVE" if any_flagged
        else "no keys outside any pinned allowlist"))
    if incomplete:
        print(
            "=== INCOMPLETE: at least one store could not be reached -- "
            "this is NOT a clean report ===", file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
