"""Pin the Dependabot deploy-sensitive-package guard (bd polyglot-pdf-lwka0).

Two grouped Dependabot pip batches broke dev's BUILD after landing
(#816/#817/#819/#822, reverted by #830; #865, reverted the same day) --
never a deployed environment: #830's own revert body says "dev does not
build" (the backend pins contradicted each other, so pip install itself
failed with ResolutionImpossible) and #867 (the #865 revert) hit the same
failure shape on the staging verify build's install step, before any deploy
ran. The unit suites never exercise what a bump of these changes (every test CI
runs (-m "not external") stubs the Gemini SDK, none starts uvicorn or the
websockets library, and FastAPI/Starlette run only in-process, via TestClient
or httpx.ASGITransport, never under a real ASGI server), so a real
version bump cannot be validated by the suite -- only by running the voice
harness on the local stack with the new pins and then a manual voice
test-drive on staging. Every one of those PRs was actually RED in the job that
mattered (e.g. #865 failed backend pytest on an unresolvable websockets==
17.1 pin) and was merged by hand anyway -- CI here is informational, not a
merge gate (see docs/standards/testing.md), so this exclusion does not rely
on CI having been green; it stops the bump from being proposed at all. This
test PARSES .github/dependabot.yml (not a text pin) so it survives
reformatting, and fails if any of the five packages is ever removed from the
exclusion, matching CLAUDE.md scar #8 ("enumerate the set before fixing any
of it"): the five packages are enumerated ONCE here and checked as a set,
not as five separate ad hoc assertions that could each be dropped
independently without the test noticing the class shrank.

Mutation-verified: removing any one of the five from either the group's
exclude-patterns or the top-level ignore list fails
test_all_five_packages_are_excluded_from_every_pip_group /
test_all_five_packages_are_fully_ignored.

SCOPE ADDITION 2026-09-23 (same bead, same-day bead-body amendment): the
grouped npm bumps #862 (admin-console), #863 (frontend) and #864
(schema-editor) -- opened together on 2026-09-19 and merged together on
2026-09-23 -- broke all three front-end type-checks on dev the same way --
typescript and @types/node (which pin the TS surface, along with vite and
vitest) landed via an automatic grouped update. Each PR was actually RED in
its matching frontend job (#863 failed `npm run typecheck` with the exact
TS5102 downlevelIteration/baseUrl errors) and was merged by hand anyway --
the unit suites don't type-check against a bumped TS toolchain the way tsc /
vite build do in a real PR, so CI's advisory status (not its color) is why
these landed. All four grouped bumps of that morning (three npm, one pip: #865) were
reverted together in #867, as #830 had reverted the previous four.

FOLLOW-UP SCOPE ADDITION 2026-09-23 (cross-surface review of this same
bead): excluding typescript/vite/vitest alone left @vitest/ui and
@vitest/coverage-v8 (which require an exact matching vitest version via a
peer dependency) and @vitejs/plugin-react (range-coupled to vite's
supported-version range the same way) in the catch-all npm groups.
schema-editor and admin-console pin @vitest/ui and @vitest/coverage-v8
exactly; @vitejs/plugin-react stays on a caret range (^4.3.1 in
schema-editor/admin-console, ^4.3.0 in frontend) but is still coupled to
vite's supported range, so a vitest/vite bump would either drag the excluded
package along anyway or open a red, peer-conflicted PR -- the guard leaked on
its own coupling. @vitest/* and @vitejs/plugin-react are folded into the same
TS_TOOLCHAIN_PACKAGES set below rather than a second constant, so every test
in this file that checks the set automatically covers them too.

SECOND FOLLOW-UP SCOPE ADDITION 2026-09-23 (outer cross-surface review of
this same bead, round 2): frontend/package.json also declares
@vitejs/plugin-react-swc (^4.2.0), the SWC-based variant of
@vitejs/plugin-react, with the identical peerDependencies.vite coupling
(admin-console and schema-editor do not declare it -- they use
@vitejs/plugin-react alone). The first follow-up above added
@vitejs/plugin-react but missed its SWC sibling. Folded into the same
TS_TOOLCHAIN_PACKAGES set, and therefore into the exclude-patterns/ignore
lists of all three npm update entries in dependabot.yml (not just frontend's),
matching how @vitejs/plugin-react itself is already excluded everywhere all
three of which declare it.

THIRD FOLLOW-UP SCOPE ADDITION 2026-09-23 (round-8 outer cross-surface
review): this branch's merge-base predated PR #867, dev's revert of the
#862/#863/#864 TS-toolchain bumps -- so frontend/package.json here still
carried the pre-revert ^6.1.1 / ^4.3.3 versions for @vitejs/plugin-react and
@vitejs/plugin-react-swc when the SECOND FOLLOW-UP note above was written.
Merging origin/dev into this branch picked up the revert; the versions cited
above are now the current (reverted) ones (^4.3.0 / ^4.2.0). The exclusion
mechanism itself was never version-dependent, so this is a prose correction
only, not a behavior change.

The npm tests below mirror the pip tests above exactly: enumerate the
TS-toolchain packages once, then check every npm group and every npm
update's ignore: list against that one set.

Mutation-verified: removing any one package from an npm group's
exclude-patterns or ignore: list fails
test_all_ts_toolchain_packages_are_excluded_from_every_npm_group /
test_all_ts_toolchain_packages_are_fully_ignored_in_every_npm_update.
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

# The enumerated set for the npm side of the same guard (bead-body scope
# addition, 2026-09-23): the TypeScript-toolchain packages that pin the
# compiler/type surface every front-end package builds and tests against.
TS_TOOLCHAIN_PACKAGES = (
    "typescript",
    "@types/node",
    "vite",
    "vitest",
    "@vitest/*",
    "@vitejs/plugin-react",
    "@vitejs/plugin-react-swc",
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


def _npm_updates(config):
    npm_updates = [
        u for u in config["updates"] if u.get("package-ecosystem") == "npm"
    ]
    assert len(npm_updates) == 3, (
        "expected exactly three npm update entries (frontend, schema-editor, "
        "admin-console), found: " + repr(npm_updates)
    )
    return npm_updates


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


def test_all_ts_toolchain_packages_are_excluded_from_every_npm_group():
    """Each npm-ecosystem update's group(s) (frontend, schema-editor,
    admin-console) must exclude every package in the TS-toolchain set -- the
    same shape as the pip test above, so a future regrouping can't silently
    drop the exclusion in any one of the three front-end packages."""
    for update in _npm_updates(_load_dependabot_config()):
        groups = update.get("groups", {})
        assert groups, "npm update '{}' has no groups: at all".format(
            update.get("directory")
        )
        for group_name, group in groups.items():
            excluded = set(group.get("exclude-patterns", []))
            missing = [p for p in TS_TOOLCHAIN_PACKAGES if p not in excluded]
            assert not missing, (
                "npm update '{}' group '{}' is missing exclude-patterns for: "
                "{}".format(update.get("directory"), group_name, missing)
            )


def test_all_ts_toolchain_packages_are_fully_ignored_in_every_npm_update():
    """Each npm-ecosystem update's top-level `ignore:` list must name every
    package in the TS-toolchain set with no `versions:`/`update-types` key,
    i.e. ignore EVERY version -- mirrors test_all_five_packages_are_fully_
    ignored for the pip side."""
    for update in _npm_updates(_load_dependabot_config()):
        ignore_entries = {
            entry["dependency-name"]: entry
            for entry in update.get("ignore", [])
            if "dependency-name" in entry
        }
        missing = [p for p in TS_TOOLCHAIN_PACKAGES if p not in ignore_entries]
        assert not missing, (
            "npm update '{}' ignore: list is missing these packages entirely: "
            "{}".format(update.get("directory"), missing)
        )
        scoped = [
            p for p in TS_TOOLCHAIN_PACKAGES
            if "versions" in ignore_entries[p] or "update-types" in ignore_entries[p]
        ]
        assert not scoped, (
            "npm update '{}': these packages are only PARTIALLY ignored "
            "(versions/update-types scoped the ignore instead of blocking "
            "every version): {}".format(update.get("directory"), scoped)
        )


def test_no_other_npm_update_reintroduces_the_ts_toolchain_ungated():
    """If a fourth npm-ecosystem update entry is ever added, it must not
    group any of the four TS-toolchain packages without the same exclusion --
    mirrors test_no_other_pip_update_reintroduces_the_five_ungated."""
    config = _load_dependabot_config()
    for update in config["updates"]:
        if update.get("package-ecosystem") != "npm":
            continue
        groups = update.get("groups", {})
        ignore_names = {
            entry.get("dependency-name") for entry in update.get("ignore", [])
        }
        for group_name, group in groups.items():
            if group.get("patterns") != ["*"]:
                continue  # a narrowly-scoped group is not the catch-all risk
            excluded = set(group.get("exclude-patterns", []))
            for pkg in TS_TOOLCHAIN_PACKAGES:
                covered = pkg in excluded or pkg in ignore_names
                assert covered, (
                    "npm update '{}' groups '{}' with pattern '*' but does not "
                    "exclude or ignore TS-toolchain package '{}'".format(
                        update.get("directory"), group_name, pkg
                    )
                )
