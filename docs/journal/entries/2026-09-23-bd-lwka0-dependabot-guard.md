---
date: 2026-09-23
bead: polyglot-pdf-lwka0
title: "chore(ci): keep google-genai/websockets/uvicorn/fastapi/starlette out of Dependabot groups and make CI install the runtime requirements file"
sprint: 22
tags: [testing, doctrine, conventions]
---

## Trigger

Two grouped Dependabot pip batches broke deploys after landing on `dev`:
`#816`/`#817`/`#819`/`#822` (reverted by `#830`) and `#865` (reverted the same
day, a fastapi/starlette major-version jump 0.48 -> 1.6). Every one of these
PRs was actually RED in CI in the job that mattered -- `#865` failed `backend
pytest` outright at the install step, with pip's `ResolutionImpossible` on
`websockets==17.1` -- and was merged by hand anyway: CI on this repo is
informational, not a merge gate (`docs/standards/testing.md`), so this was
never a case of a break with no CI signal at all. The outer cross-surface
review on this same PR corrected an earlier draft of this entry that had
wrongly attributed the breaks to CI being green; the still-open process gap
-- that a red PR can still be merged -- is a separate, maintainer-facing
question filed as bd `polyglot-pdf-9ywia`.
The unit suites stub google-genai, websockets, uvicorn, fastapi and starlette
completely -- every test that touches the Live adapter, the WebSocket
handshake, or the ASGI stack runs against a mock, not the real package -- so a
real version bump of any of these five cannot be validated by the suite at
all regardless of whether CI is red or green for an unrelated reason.
Separately, the verify build installs `backend/requirements.txt` alone in
a clean `python:3.12` image while CI's `backend-tests` job installs
`requirements-dev.txt` (which happens to pull in `requirements.txt`), so
`backend-runtime-install` (below) is a second, isolated signal for an
unresolvable runtime-only dependency set, not a new class of detection CI
previously lacked.

## What shipped

1. `.github/dependabot.yml`'s `all-pip-backend` group now excludes the five
   packages via `exclude-patterns`, and the update entry carries a top-level
   `ignore:` list naming all five with no `versions:` scoping (i.e. every
   version of each is ignored). Together these mean an automatic grouped
   Dependabot PR can never carry a version bump of google-genai, websockets,
   uvicorn, fastapi or starlette again; a bump of one of them is now only
   possible through a human editing the pin by hand.
2. `tests/test_dependabot_config.py` (new) parses the YAML (not a text match)
   and pins the exclusion as a set: every package must be in both the group's
   `exclude-patterns` and the `ignore:` list, and a future second
   pip-ecosystem update entry would need the same guard if it ever groups with
   a `"*"` pattern. Mutation-verified by removing one package from each list in
   turn and confirming the corresponding test fails, then restoring.
3. `ci.yml` gained a `backend-runtime-install` job that installs ONLY
   `backend/requirements.txt` in a fresh runner (no pip cache, no dev extras)
   and imports `backend.main`, mirroring what the deploy image's uvicorn
   process does. This is a second, isolated signal for an unresolvable or
   import-broken runtime dependency set -- the `backend-tests` job's own
   install step already fails on exactly this class today (e.g. `#865`'s
   `ResolutionImpossible` on `websockets==17.1`), it is just mixed in with
   `requirements-dev.txt`'s pins there. `tests/test_ci_security_job.py`'s
   pytest-runner scan gained one named exception for this job's install
   line, since it deliberately never runs pytest and was never meant to be
   one of the lines that test polices.
4. Docs: `docs/doctrine/promotion-tiers.md`'s "Why staging exists" section now
   names the five packages and says a bump of any of them is a deliberate,
   voice-harness-gated bead (staging deploy, run the voice harness against it,
   then ask for a demo deploy) rather than the routine grouped-Dependabot-PR
   path the other four pip/npm groups use. `docs/standards/testing.md`'s
   `Tracks:` line picked up `.github/dependabot.yml` and the new test file,
   with a new current-state prose entry describing both changes.
5. Round-2 fresh-eyes fix (same PR): the bead body's same-day NOTES amendment
   ("SCOPE ADDITION 2026-09-23") asked for the same treatment for the
   TypeScript toolchain after `#862`/`#863`/`#864` (grouped npm bumps in
   admin-console, frontend and schema-editor) broke all three front-end
   type-checks on `dev` the same morning and were reverted together in
   `#867`. That addition had shipped unaddressed in the first round.
   `.github/dependabot.yml` now excludes typescript, `@types/node`, vite and
   vitest from all three npm groups' `exclude-patterns` and from each npm
   update's `ignore:` list, the same belt-and-suspenders shape as the five
   pip packages. `tests/test_dependabot_config.py` gained a matching
   enumerated set (`TS_TOOLCHAIN_PACKAGES`) and four tests mirroring the pip
   tests exactly, mutation-verified by removing one package from an npm
   group's `exclude-patterns` and from an npm update's `ignore:` list in
   turn and confirming each corresponding test fails, then restoring.
   `docs/doctrine/promotion-tiers.md` gained a matching paragraph and stamp
   update noting the npm-side gate.
6. Round-3 outer cross-surface review fix (same PR): the outer reviewer
   traced all four handoff contracts plus the two round-1 contracts and
   found one GAP (Finding 1) plus two pre-existing/nit findings it filed as
   beads rather than fixing here.
   - **Adopted:** Finding 1 -- corrected the "landed on dev with green CI"
     claim everywhere it appeared (`.github/dependabot.yml` x2,
     `tests/test_dependabot_config.py` x2, `docs/doctrine/promotion-tiers.md`
     x2 plus the "Why staging exists" prose, `docs/standards/testing.md`'s
     stamp, `.github/workflows/ci.yml`'s `backend-runtime-install` comment,
     and this journal entry's Trigger and item 3). Verified independently
     against `gh pr checks` for every cited PR (`#816`/`#817`/`#819`/`#822`/
     `#865`/`#862`/`#863`/`#864`): each had a RED job in the suite that
     should have caught the break, and was merged by hand anyway -- CI here
     is informational (`docs/standards/testing.md`), not a merge gate, so
     the corrected claim is that CI already caught these and the real gap is
     that a red PR can still merge (a maintainer process question, filed as
     bd `polyglot-pdf-9ywia`, not fixed in this bead).
   - **Deferred (filed as beads, not fixed here):** Finding 2, the
     `backend-runtime-install` job importing only `backend.main` and missing
     `admin_backend.main` (which the same image and requirements file also
     serve) -- filed as bd `polyglot-pdf-3kaqw`. Finding 3, the
     `docs/standards/security-posture.md` supply-chain row not reflecting
     that nine packages (including the internet-facing fastapi, starlette,
     uvicorn, websockets) now get no Dependabot signal at all -- filed as bd
     `polyglot-pdf-01kiz`. Both are nits against pre-existing text, not
     regressions this bead introduced.
   - **Rejected:** none -- every GAP finding was actionable and adopted; no
     finding was refuted.
7. Round-4 outer cross-surface review fix (same PR, a later review pass after
   the npm-scope addition landed): the reviewer traced the npm-scope
   contracts and found two more GAPs.
   - **Adopted:** Finding 1 (blocker) -- `@vitest/ui` and `@vitest/coverage-v8`
     require an EXACT matching `vitest` version via a peer dependency, and
     `@vitejs/plugin-react` is version-coupled to `vite` the same way;
     schema-editor and admin-console pin all three exactly (verified via
     `node -e "...package.json).peerDependencies"` against the installed
     `node_modules`). Excluding only `vite`/`vitest` left Dependabot free to
     bump the peer-locked packages alone, reproducing the same red,
     peer-conflicted-lockfile PR shape this whole guard exists to stop. Added
     `"@vitest/*"` and `"@vitejs/plugin-react"` to `exclude-patterns` and
     `ignore:` in all three npm groups in `.github/dependabot.yml`, and folded
     both into the existing `TS_TOOLCHAIN_PACKAGES` tuple in
     `tests/test_dependabot_config.py` (not a second constant), so every
     existing test against that set covers them automatically. Mutation-
     verified by removing `@vitest/*` from one npm group's `exclude-patterns`
     and, separately, from one npm update's `ignore:` list, confirming each
     failure and restoring.
   - **Adopted:** Finding 2 (doc-accuracy GAP) -- `docs/doctrine/
     promotion-tiers.md` said the pip-package batches "broke the deployed
     `/ws/fill` handshake" and that the npm bumps landed "the morning after"
     the pip exclusion. Both are false: verified via `gh pr view 830/867
     --json body` (both revert bodies say "dev does not build" -- a pip
     `ResolutionImpossible` and front-end type-check failures, never a
     deployed break) and `gh pr view 862/863/864 --json createdAt,mergedAt`
     (all three created together on 2026-09-19, merged within 4 minutes of
     each other on 2026-09-23 -- the same day as, not the morning after, the
     pip exclusion in this same PR). The same "broke deploys after landing on
     dev" phrasing was also in `.github/dependabot.yml`'s comment and
     `tests/test_dependabot_config.py`'s docstring; corrected all three
     together (CLAUDE.md scar #8) to say `dev`'s build/typecheck broke, never
     a deployed environment.
   - **Rejected:** none.
   - Two more findings from this round (a nit about the `ci.yml` job-name
     parity overstatement and website-routing.md mis-citation, and a
     pre-existing branch-protection doc claim) were already filed by the
     reviewer as `polyglot-pdf-em0bf` and `polyglot-pdf-cn6v7`; no new bead
     needed.
8. Round-5 outer cross-surface review fix (same PR): the reviewer traced all
   eight contracts (the four handoff items plus the four already covered by
   rounds 1-4, plus the stale-branch-base question) and found one GAP.
   - **Adopted:** Finding 1 -- `docs/standards/testing.md`'s round-2 dated
     entry said the npm/TS-toolchain guard added "four tests" and named only
     "typescript, `@types/node`, vite and vitest"; round 4 had folded
     `@vitest/*` and `@vitejs/plugin-react` into the same `TS_TOOLCHAIN_PACKAGES`
     tuple and the npm side has always had three tests (not four), so both
     counts were wrong. Corrected the sentence to name all six packages and
     say "three tests". Prose-only; no test or production-code change, so it
     does not re-run the outer review per CLAUDE.md ("only a BEHAVIORAL fix
     voids a clear").
   - **Rejected:** none.
   - Two more findings from this round (the `@vitejs/plugin-react-swc`
     peer-coupling gap, and two comment-accuracy nits about "four" vs "six"
     TS-toolchain packages and the duplicate-install-line allowlist wording)
     were filed by the reviewer as `polyglot-pdf-ld4o0` and
     `polyglot-pdf-88tcg`; both pre-exist as open beads, not fixed here.
9. Round-6 outer cross-surface review fix (same PR): the reviewer traced all
   nine changed contracts plus the plan contracts and core rules and found
   one GAP.
   - **Adopted:** Finding 1 (blocker) -- `docs/doctrine/promotion-tiers.md`
     said schema-editor and admin-console "pin all three exactly" (referring
     to `@vitest/ui`, `@vitest/coverage-v8` and `@vitejs/plugin-react`). That
     is wrong for `@vitejs/plugin-react`: verified via `git show
     origin/dev:schema-editor/package.json` and `admin-console/package.json`
     -- both declare `"@vitejs/plugin-react": "^4.3.1"`, a caret range, not
     an exact pin. Only `@vitest/coverage-v8` and `@vitest/ui` are exact at
     `4.0.7`. The reason for excluding `@vitejs/plugin-react` still holds
     (its supported-vite-versions range still couples it to vite), so the
     exclusion logic was not wrong -- only the "exactly" claim was. Corrected
     the same overclaim in three places: `docs/doctrine/promotion-tiers.md`'s
     "Why staging exists" paragraph, `tests/test_dependabot_config.py`'s
     module docstring (the round-4/FOLLOW-UP-SCOPE-ADDITION paragraph), and
     `.github/dependabot.yml`'s comment ("version-coupled to vite the same
     way" -> "range-coupled to vite's supported-version range the same
     way"). Docs/comment-only; no behavioral or test-assertion change, so no
     new mutation-verification applies. Re-ran the full root-level suite
     (2061 passed, 94 skipped) and the full backend suite (3890 passed, 195
     skipped, 4 deselected) from the worktree -- both green, matching the
     prior baseline.
   - **Rejected:** none.
   - No new nits surfaced this round; the reviewer's "Not new" list
     (`ld4o0`, `3kaqw`, `01kiz`, `em0bf`, `88tcg`, `cn6v7`) already covers
     every other outstanding item, so no new nits bead was filed.

## Lessons

The bead names a real, general pattern worth restating: a mock proves the
tests pass, not that a real dependency bump is safe (this rhymes with CLAUDE.md
scar #7's IAM-envelope lesson -- a mock cannot tell you the real thing is
forbidden or, here, broken). When a dependency's own behavior is what a test
suite fundamentally cannot exercise (a live network protocol, a vendored SDK
every test stubs), grouping it into an automatic update pipeline is itself the
bug, independent of any specific bad bump. The fix here is process-level
(Dependabot config + a CI parity check), not a one-off revert, per the bead's
own framing ("fix the process, not the instance").

## Doc freshness

- `docs/standards/testing.md`: bumped (new dated entry, `Tracks:` line
  widened). Pre-existing on the `check_doc_freshness.py` stacked-stamp
  allowlist (bd polyglot-pdf-4iyi6 tracks collapsing it to one stamp
  repo-wide); this bead adds one more dated entry in the file's existing
  convention rather than attempting that unrelated consolidation.
- `docs/doctrine/promotion-tiers.md`: bumped (new parenthetical clause on the
  existing single stamp, plus a new paragraph in "Why staging exists").
- No other tier-2 docs track `.github/dependabot.yml` or `.github/workflows/
  ci.yml`; none needed review beyond the two above.

## Review outcomes

Recorded in the closeout ping.

## Files touched

- `.github/dependabot.yml` -- exclude-patterns + ignore: for the five
  deploy-sensitive packages, plus (round 2) the same for the four
  TS-toolchain packages across all three npm groups; round 4 added
  `@vitest/*` and `@vitejs/plugin-react` to close the peer-dependency gap,
  plus a comment-wording fix ("broke deploys" -> "broke dev's build"); round
  6 fixed the comment's "@vitejs/plugin-react is version-coupled to vite"
  overclaim to "range-coupled".
- `.github/workflows/ci.yml` -- new `backend-runtime-install` job.
- `tests/test_dependabot_config.py` -- new, pins the exclusion; round 2 added
  the mirrored npm/TS-toolchain enumerated set and four tests; round 4 folded
  `@vitest/*`/`@vitejs/plugin-react` into `TS_TOOLCHAIN_PACKAGES` and fixed the
  same "broke deploys" docstring wording; round 6 fixed the docstring's "pin
  all three of these exactly" overclaim (only `@vitest/ui` and
  `@vitest/coverage-v8` are exact; `@vitejs/plugin-react` is a caret range).
- `tests/test_ci_security_job.py` -- one named exception for the new job's
  install line.
- `docs/doctrine/promotion-tiers.md` -- voice-harness-gated bump note; round 2
  added the matching npm/TS-toolchain paragraph and stamp update; round 4
  corrected the false "broke the deployed /ws/fill handshake" and "morning
  after" claims and added the peer-dependency-package note; round 6 fixed the
  "pin all three exactly" overclaim (`@vitejs/plugin-react` is a caret range,
  not an exact pin).
- `docs/standards/testing.md` -- Tracks line + current-state prose entry.
