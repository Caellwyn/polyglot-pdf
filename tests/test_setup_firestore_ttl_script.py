"""scripts/setup-firestore-ttl.sh's declared TTL set (Epic 2 bead A1).

This is an OPERATOR script -- no deploy pipeline runs it, and no CI step
executes gcloud -- so the only mechanical guard available is pinning the
SHIPPED SCRIPT TEXT: the field name every policy targets, the exact set of
collections that get a policy, and (just as load-bearing) which
Admin-SDK-only collections deliberately do NOT get one (admin_audit_log and
deployments must be retained; link_redemptions/link_redemptions_staging's
retention policy is a separate, deliberate decision this bead does not
touch).

These tests read the ACTUAL shipped script text, not a reimplementation, so
a regression -- an accidentally-added or accidentally-dropped collection,
or a field-name typo -- fails here rather than only being caught when an
operator runs it against a real project.

ASCII only.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "setup-firestore-ttl.sh"

# THE SET this bead's script must declare a TTL policy for. Mirrors the
# ADMIN_SDK_ONLY_COLLECTIONS enumerate-the-set pattern in
# backend/tests/unit/test_firestore_rules_text.py -- extend THIS list (and
# the script's own TTL_COLLECTIONS array) together when a later bead adds
# another expire_at-bearing collection.
EXPECTED_TTL_COLLECTIONS = {"links", "links_staging", "alerts"}

# Collections that are Admin-SDK-only (or otherwise TTL-eligible-looking)
# but must NOT appear in the script's TTL set -- named explicitly so a
# regression that adds one of these by mistake is caught by name, not just
# by the total-set assertion below.
MUST_NOT_BE_TTLD = {
    "admin_audit_log",  # the audit trail must outlive any one link/alert
    "deployments",  # Epic 4, low-volume, no storage-cost pressure to reap
    "link_redemptions",  # separate collection, separate retention decision
    "link_redemptions_staging",
    "firms",
    "kits",
}


def _script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _gcloud_invocation_block(text: str) -> str:
    """The gcloud invocation inside the for-loop (between the `for` line
    and the matching closing `done`), so the flag-uses-the-loop-variable
    check below is scoped to the real command, not to the trailing NOTE
    line that also mentions --collection-group as example text."""
    match = re.search(
        r'for collection in "\$\{TTL_COLLECTIONS\[@\]\}"; do(.*?)\ndone',
        text, re.DOTALL)
    assert match, "the TTL_COLLECTIONS for-loop was not found in the script"
    return match.group(1)


def test_script_exists_and_starts_with_a_shebang():
    """Executable-bit is not a portable check here: git tracks the sibling
    setup scripts (setup-gcp-project.sh, setup-admin-service.sh) as mode
    100644 in THIS repo, and Windows filesystem stat() never reports S_IXUSR
    regardless of chmod -- so a mode assertion would fail for every script,
    including the pre-existing ones, not just a real regression. The
    shebang is what actually determines how `bash scripts/foo.sh` or a
    direct `./scripts/foo.sh` invocation behaves."""
    assert SCRIPT.exists(), "scripts/setup-firestore-ttl.sh is missing"
    text = _script_text()
    assert text.startswith("#!/bin/bash"), (
        "scripts/setup-firestore-ttl.sh must start with a #!/bin/bash shebang"
    )


def test_every_ttl_update_targets_the_expire_at_field():
    """Every gcloud invocation in the script must target `expire_at` -- a
    different field name per collection would defeat the one-field-name
    auditability the module docstring argues for. Mutation: change one
    `fields ttls update expire_at` to a different field name -- red."""
    text = _script_text()
    invocations = re.findall(
        r"gcloud firestore fields ttls update (\S+)", text)
    assert invocations, "expected at least one 'fields ttls update' invocation"
    for field in invocations:
        assert field == "expire_at", (
            f"a TTL invocation targets {field!r}, not expire_at")


def test_the_declared_ttl_collections_array_matches_the_expected_set():
    """The bash array TTL_COLLECTIONS is the ONE list this script loops
    over. Mutation: add or remove an entry from the TTL_COLLECTIONS array in
    the script -- red."""
    text = _script_text()
    match = re.search(
        r"TTL_COLLECTIONS=\((.*?)\)", text, re.DOTALL)
    assert match, "TTL_COLLECTIONS array not found in the script"
    declared = set(re.findall(r'"([^"]+)"', match.group(1)))
    assert declared == EXPECTED_TTL_COLLECTIONS, (
        f"TTL_COLLECTIONS array {declared} does not match the expected set "
        f"{EXPECTED_TTL_COLLECTIONS}"
    )


def test_the_gcloud_invocation_uses_the_loop_variable_not_a_hardcoded_name():
    """The --collection-group flag inside the for-loop must reference
    $collection (the loop variable bound to each TTL_COLLECTIONS entry), not
    a hardcoded literal -- a hardcoded value would apply the SAME
    collection's TTL policy on every iteration regardless of what
    TTL_COLLECTIONS contains, silently decoupling the array (pinned by the
    test above) from what the script actually does. Mutation: replace
    --collection-group="$collection" with a literal, e.g.
    --collection-group="links" -- red."""
    block = _gcloud_invocation_block(_script_text())
    assert re.search(r'--collection-group="\$collection"', block), (
        "the --collection-group flag inside the for-loop does not reference "
        "$collection -- it may be hardcoded"
    )
    # And no other --collection-group flag with a DIFFERENT literal value
    # sits inside the same loop body (that would mean two competing
    # invocations, one of them dead).
    literal_flags = re.findall(r'--collection-group=(?!"\$collection")\S+', block)
    assert not literal_flags, (
        f"found hardcoded --collection-group flag(s) inside the loop: "
        f"{literal_flags}"
    )


def test_retained_collections_never_appear_in_the_declared_set():
    """The negative half: admin_audit_log, deployments, and the
    link_redemptions collections must NEVER appear in TTL_COLLECTIONS.
    Mutation: add "admin_audit_log" to the TTL_COLLECTIONS array -- red."""
    text = _script_text()
    match = re.search(r"TTL_COLLECTIONS=\((.*?)\)", text, re.DOTALL)
    assert match
    declared = set(re.findall(r'"([^"]+)"', match.group(1)))
    overlap = declared & MUST_NOT_BE_TTLD
    assert not overlap, (
        f"the following collections must be RETAINED (no TTL) but appear "
        f"in TTL_COLLECTIONS: {sorted(overlap)}"
    )


def test_script_is_idempotent_by_construction():
    """No `set -e`-defeating guard is needed if the underlying gcloud
    command is itself idempotent -- but the script must still declare
    `set -e` so a genuine failure (bad project id, missing permission)
    stops the loop rather than silently continuing to the next collection.
    Mutation: remove `set -e` -- red."""
    text = _script_text()
    assert re.search(r"^set -e\s*$", text, re.MULTILINE), (
        "scripts/setup-firestore-ttl.sh must declare 'set -e'"
    )


def test_script_requires_a_project_id_argument():
    """Mutation: drop the PROJECT_ID empty-check / exit 1 -- an operator
    running this with no argument would otherwise pass an empty
    --project="" to gcloud, which fails opaquely instead of with a usage
    message. Red if the guard is removed."""
    text = _script_text()
    assert re.search(r'if\s*\[\s*-z\s*"\$PROJECT_ID"\s*\]', text)
    assert "exit 1" in text
