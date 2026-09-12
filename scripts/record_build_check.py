"""Record a per-SHA verify result in Firestore build_checks/{sha}.

Run by cloudbuild.yaml's `verify` target as its LAST step, under the Cloud
Build service account's ADC. Every DEPLOY target's FIRST step then reads the
same document and refuses to run without a success record for its SHA -- so
five deploy targets for one commit pay ONE test run rather than five, and a
commit whose suites failed cannot be deployed by any route (bash or the admin
console), because the gate lives in the build rather than in a wrapper.

Two subcommands, because the gate needs both halves:

    record --sha <sha> --status success --build-id <id>
    require --sha <sha>

`require` exits 1 when the document is missing, when its status is anything
but "success", or when Firestore cannot be read at all. It fails CLOSED on
purpose: a gate that waves a deploy through because it could not check is not
a gate. The failure message names the exact remedy (run the verify target for
this SHA first), because it is read in a build log by someone who has no
shell on the machine.

The document is NOT the audit trail of a deploy -- `deployments/{id}` is
(bead 4.3). This collection answers one question: have this commit's suites
passed? It therefore carries no channel and no target.
"""

from __future__ import annotations

import argparse
import datetime
import sys

COLLECTION = "build_checks"
STATUS_SUCCESS = "success"


def _client(project: str | None):
    """A Firestore client, imported lazily.

    google.cloud.firestore is a runtime dependency of the build step, not of
    the test suite -- importing at module scope would make every test in
    tests/test_cloudbuild_yaml.py depend on a package CI does not install.
    """
    from google.cloud import firestore  # noqa: PLC0415

    return firestore.Client(project=project) if project else firestore.Client()


def record(sha: str, status: str, build_id: str, project: str | None) -> int:
    doc = {
        "status": status,
        "build_id": build_id,
        # Timezone-aware UTC: a naive timestamp read back in another zone is a
        # silently wrong answer to "when did this commit pass?".
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "sha": sha,
    }
    _client(project).collection(COLLECTION).document(sha).set(doc)
    print("[record_build_check] {}/{} = {}".format(COLLECTION, sha, status))
    return 0


def require(sha: str, project: str | None) -> int:
    try:
        snap = _client(project).collection(COLLECTION).document(sha).get()
    except Exception as exc:  # noqa: BLE001 -- fail closed on ANY read failure
        print(
            "[record_build_check] could not read {}/{}: {}".format(
                COLLECTION, sha, exc
            ),
            file=sys.stderr,
        )
        print(
            "[record_build_check] REFUSING to deploy: the verify gate could "
            "not be checked, and an unchecked gate is not a gate.",
            file=sys.stderr,
        )
        return 1

    if not snap.exists:
        print(
            "[record_build_check] no {}/{} record -- run the verify target "
            "for this SHA first:".format(COLLECTION, sha),
            file=sys.stderr,
        )
        print(
            "[record_build_check]   gcloud builds triggers run polyglot-verify "
            "--sha={} --region=us-central1".format(sha),
            file=sys.stderr,
        )
        return 1

    status = (snap.to_dict() or {}).get("status")
    if status != STATUS_SUCCESS:
        print(
            "[record_build_check] {}/{} status is {!r}, not {!r} -- this "
            "commit's suites did not pass, so it must not deploy.".format(
                COLLECTION, sha, status, STATUS_SUCCESS
            ),
            file=sys.stderr,
        )
        return 1

    print("[record_build_check] verify gate OK for {}".format(sha))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    rec = sub.add_parser("record", help="write the verify result for a SHA")
    rec.add_argument("--sha", required=True)
    rec.add_argument("--status", default=STATUS_SUCCESS)
    rec.add_argument("--build-id", required=True)
    rec.add_argument("--project", default=None)

    req = sub.add_parser("require", help="refuse unless a SHA verified")
    req.add_argument("--sha", required=True)
    req.add_argument("--project", default=None)

    args = parser.parse_args(argv)
    if args.command == "record":
        return record(args.sha, args.status, args.build_id, args.project)
    return require(args.sha, args.project)


if __name__ == "__main__":
    raise SystemExit(main())
