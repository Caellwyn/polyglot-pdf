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
  TS-toolchain packages across all three npm groups.
- `.github/workflows/ci.yml` -- new `backend-runtime-install` job.
- `tests/test_dependabot_config.py` -- new, pins the exclusion; round 2 added
  the mirrored npm/TS-toolchain enumerated set and four tests.
- `tests/test_ci_security_job.py` -- one named exception for the new job's
  install line.
- `docs/doctrine/promotion-tiers.md` -- voice-harness-gated bump note; round 2
  added the matching npm/TS-toolchain paragraph and stamp update.
- `docs/standards/testing.md` -- Tracks line + current-state prose entry.
