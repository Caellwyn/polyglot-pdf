"""Pin the Dependabot deploy-sensitive-package guard (bd polyglot-pdf-lwka0).

Two grouped Dependabot pip batches landed on dev with green CI and broke
deploys anyway (#816/#817/#819/#822, reverted by #830; #865, reverted the same
day): the unit suites stub google-genai, websockets, uvicorn, fastapi and
starlette completely, so a real version bump of any of them cannot be
validated by the suite at all -- only by running the voice harness against a
deployed staging environment. This test PARSES .github/dependabot.yml (not a
text pin) so it survives reformatting, and fails if any of the five packages
is ever removed from the exclusion, matching CLAUDE.md scar #8 ("enumerate the
set before fixing any of it"): the five packages are enumerated ONCE here and
checked as a set, not as five separate ad hoc assertions that could each be
dropped independently without the test noticing the class shrank.

Mutation-verified: removing any one of the five from either the group's
exclude-patterns or the top-level ignore list fails test_all_five_packages_are_
excluded_from_every_pip_group / test_all_five_packages_are_fully_ignored.
"""
import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPENDABOT_PATH = REPO_ROOT / ".github" / "dependabot.yml"

# The enumerated set (CLAUDE.md scar #8): every deploy-sensitive backend
# package this bead's Dependabot guard must keep out of automatic grouped
# updates. Add to THIS tuple, not to an inline list at a call site, so the
# next addition is covered everywhere this test checks.
DEPLOY_SENSITIVE_PACKAGES = (
    "google-genai",
    "websockets",
    "uvicorn",
    "fastapi",
    "starlette",
)


def _load_dependabot_config():
    return yaml.safe_load(DEPENDABOT_PATH.read_text(encoding="utf-8"))


def _pip_backend_update(config):
    pip_updates = [
        u for u in config["updates"]
        if u.get("package-ecosystem") == "pip" and u.get("directory") == "/backend"
    ]
    assert len(pip_updates) == 1, (
        "expected exactly one pip/backend update entry, found: " + repr(pip_updates)
    )
    return pip_updates[0]


def test_dependabot_yaml_is_well_formed():
    config = _load_dependabot_config()
    assert config["version"] == 2
    assert config["updates"], "dependabot.yml has no updates: list"


def test_all_five_packages_are_excluded_from_every_pip_group():
    """Each pip-ecosystem update's group(s) must exclude every package in the
    enumerated set -- not just the all-pip-backend group by name, so a future
    regrouping (splitting the group, renaming it) can't silently drop the
    exclusion."""
    update = _pip_backend_update(_load_dependabot_config())
    groups = update.get("groups", {})
    assert groups, "pip/backend update has no groups: at all"
    for group_name, group in groups.items():
        excluded = set(group.get("exclude-patterns", []))
        missing = [p for p in DEPLOY_SENSITIVE_PACKAGES if p not in excluded]
        assert not missing, (
            "group '{}' is missing exclude-patterns for: {}".format(group_name, missing)
        )


def test_all_five_packages_are_fully_ignored():
    """The top-level `ignore:` list (not just the group exclusion) must name
    every package in the enumerated set with no `versions:` key, i.e. ignore
    EVERY version -- a scoped ignore (e.g. only major versions) would still
    let a grouped batch bump these across a minor/patch boundary."""
    update = _pip_backend_update(_load_dependabot_config())
    ignore_entries = {
        entry["dependency-name"]: entry
        for entry in update.get("ignore", [])
        if "dependency-name" in entry
    }
    missing = [p for p in DEPLOY_SENSITIVE_PACKAGES if p not in ignore_entries]
    assert not missing, "ignore: list is missing these packages entirely: " + repr(missing)
    scoped = [
        p for p in DEPLOY_SENSITIVE_PACKAGES
        if "versions" in ignore_entries[p] or "update-types" in ignore_entries[p]
    ]
    assert not scoped, (
        "these packages are only PARTIALLY ignored (versions/update-types "
        "scoped the ignore instead of blocking every version): " + repr(scoped)
    )


def test_no_other_pip_update_reintroduces_the_five_ungated():
    """If a second pip-ecosystem update entry is ever added (e.g. a future
    admin_backend/requirements.txt), it must not group any of the five
    packages without the same exclusion -- guards against the fix being
    scoped to only the /backend entry that exists today."""
    config = _load_dependabot_config()
    for update in config["updates"]:
        if update.get("package-ecosystem") != "pip":
            continue
        groups = update.get("groups", {})
        ignore_names = {
            entry.get("dependency-name") for entry in update.get("ignore", [])
        }
        for group_name, group in groups.items():
            if group.get("patterns") != ["*"]:
                continue  # a narrowly-scoped group is not the catch-all risk
            excluded = set(group.get("exclude-patterns", []))
            for pkg in DEPLOY_SENSITIVE_PACKAGES:
                covered = pkg in excluded or pkg in ignore_names
                assert covered, (
                    "pip update '{}' groups '{}' with pattern '*' but does not "
                    "exclude or ignore deploy-sensitive package '{}'".format(
                        update.get("directory"), group_name, pkg
                    )
                )
