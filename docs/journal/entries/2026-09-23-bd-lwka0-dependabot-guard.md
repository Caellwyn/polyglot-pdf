---
date: 2026-09-23
bead: polyglot-pdf-lwka0
title: "chore(ci): keep google-genai/websockets/uvicorn/fastapi/starlette out of Dependabot groups and make CI install the runtime requirements file"
sprint: 22
tags: [testing, doctrine, conventions]
---

## Trigger

Two grouped Dependabot pip batches landed on `dev` with green CI and broke
deploys anyway: `#816`/`#817`/`#819`/`#822` (reverted by `#830`) and `#865`
(reverted the same day, a fastapi/starlette major-version jump 0.48 -> 1.6).
The unit suites stub google-genai, websockets, uvicorn, fastapi and starlette
completely -- every test that touches the Live adapter, the WebSocket
handshake, or the ASGI stack runs against a mock, not the real package -- so a
real version bump of any of these five cannot be validated by the suite at
all. Separately, the verify build installs `backend/requirements.txt` alone in
a clean `python:3.12` image while CI has only ever installed
`requirements-dev.txt` (which happens to pull in `requirements.txt`), so an
unresolvable runtime-only dependency set had no CI signal before this bead.

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
   process does. An unresolvable or import-broken runtime dependency set now
   fails the PR instead of surfacing only at deploy time.
   `tests/test_ci_security_job.py`'s pytest-runner scan gained one named
   exception for this job's install line, since it deliberately never runs
   pytest and was never meant to be one of the lines that test polices.
4. Docs: `docs/doctrine/promotion-tiers.md`'s "Why staging exists" section now
   names the five packages and says a bump of any of them is a deliberate,
   voice-harness-gated bead (staging deploy, run the voice harness against it,
   then ask for a demo deploy) rather than the routine grouped-Dependabot-PR
   path the other four pip/npm groups use. `docs/standards/testing.md`'s
   `Tracks:` line picked up `.github/dependabot.yml` and the new test file,
   with a new current-state prose entry describing both changes.

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
  deploy-sensitive packages.
- `.github/workflows/ci.yml` -- new `backend-runtime-install` job.
- `tests/test_dependabot_config.py` -- new, pins the exclusion.
- `tests/test_ci_security_job.py` -- one named exception for the new job's
  install line.
- `docs/doctrine/promotion-tiers.md` -- voice-harness-gated bump note.
- `docs/standards/testing.md` -- Tracks line + current-state prose entry.
