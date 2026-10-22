---
date: 2026-10-22
bead: polyglot-pdf-niwcu
title: "fix(deps): pin back #882's breaking/deploy-sensitive backend bumps; group only minor+patch pip updates"
tags: [hotfix, testing, security]
---

## Trigger

The maintainer reported the staging deploy failing. The Cloud Build
`polyglot-verify` build for `dev` at `f05eacc` failed 12 backend tests, so no
per-commit verify record existed and every deploy target refused to run. The
failed `polyglot-backend-demo` build at the same commit was the same gate
refusing.

## What shipped

**Cause.** Dependabot PR `#882` bumped 19 backend packages in one group. It
was merged with its `backend pytest` check RED, one minute before the
unrelated model-migration PR `#886`. The 12 failures reproduced identically on
`d8c9441fb` (dev before `#886`) in a clean venv built from `#882`'s pins:

- **structlog 23 -> 26: a real PII leak, 6 tests.** The full traceback,
  exception message included, reached the log output.
- **pytest-asyncio 0.21 -> 1.4: test harness only, 6 tests.** It no longer
  provides an implicit event loop.

**Fix.**

- **Pin-back.** These go back to their exact pre-`#882` versions:
  - test tooling: pytest, pytest-asyncio, pytest-cov;
  - structlog;
  - the majors the suite cannot validate: firebase-admin 6->7,
    google-cloud-storage 2->3, librosa 1.0 with soundfile, and PyMuPDF.

  The twelve minor/patch bumps stay.
- **Root cause.** The `all-pip-backend` Dependabot group now carries
  `update-types: [minor, patch]`, so a major arrives as its own PR. A new test
  in `tests/test_dependabot_config.py` pins this. It was mutation-verified red
  for a missing key, an empty list, and an added `major`.

**Each package's real upgrade is its own bead and PR:**

- `6wkzi` structlog: a `PiiSafeBoundLogger` fix.
- `oy37r` pytest stack: an explicit event-loop fixture.
- `k5dnc` PyMuPDF: fill fidelity compared, plus the move off the `fitz` name.
- `m9h4w` librosa.
- `d5rsx` firebase-admin and storage.
- `zmlgd` was filed to drop librosa/soundfile from the runtime image, since
  no deployed code imports them.

**Verification.**

- A clean venv from the new pins passes `pip check`.
- closeout_prep's full run: 6,763 passed, 0 failed.
- A separate clean-venv run showed 1 failure. It was a Windows MAX_PATH
  artifact: charset-normalizer's compiled module would not load from the
  long scratch path. Through a short junction it passes.

**Review.**

- **Fresh-eyes (Haiku), 2 rounds.** Round 1 found:
  - a miscounted comment ("four majors", actually seven);
  - a test that accepted `update-types: []`.

  Both were adopted. Round 2 left only the "single green run" evidence item,
  which prep's run closed.

## Lessons

- **A green local suite is not evidence about a dependency bump you never
  installed.** My migration branch predated `#882`, so its 6,762 passes ran
  on the old pins, and the break only showed in Cloud Build. When a deploy
  fails on a merge commit, rebuild a clean venv from that commit's
  requirements before suspecting the code.
- **structlog >= 24 changed what `.exception()` does at the stdlib boundary.**
  It now attaches the live exception to the LogRecord, so any stdlib
  Formatter prints the message. A PII guard written as a processor cannot see
  that, and only the end-to-end handler-output tests caught it.
- **Long scratch paths break compiled wheels on Windows.** Build throwaway
  venvs behind a short junction (`C:\...\Temp\vX`).

## Doc freshness

- `docs/standards/testing.md`: added the Dependabot minor+patch policy to the
  body as current state. The stacked stamps were left as found (pre-existing).
- `docs/doctrine/promotion-tiers.md`: reviewed; its Dependabot text describes
  the voice-path exclusions, which are unchanged.
- Unrelated stale in-progress bead `h06sv` was left untouched.

## Files touched

- backend/requirements.txt, backend/requirements-dev.txt: the pin-back
- .github/dependabot.yml: `update-types: [minor, patch]` on the pip group
- tests/test_dependabot_config.py: the new group test
- docs/standards/testing.md: Dependabot policy paragraph
