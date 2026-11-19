---
date: 2026-11-19
bead: polyglot-pdf-3b6lp
title: "chore(deps): hold PyMuPDF MAJOR bumps in Dependabot; close #923 (2.1)"
tags: [testing, conventions]
---

## Trigger

Dependabot opened #923 (PyMuPDF 1.28.2 -> 2.1) the day after the deliberate
1.28 upgrade (#896, bd k5dnc) removed PyMuPDF from the hold list. PyMuPDF fills
and renders every PDF on the deployed backend, and its last upgrade was done
with a before/after fill comparison. In an open-PR triage the maintainer
approved closing #923 and holding PyMuPDF majors (2026-11-18).

## What shipped

- `.github/dependabot.yml`: a SCOPED ignore on the pip `/backend` entry --
  `dependency-name: "PyMuPDF"`, `update-types: ["version-update:semver-major"]`.
  Minor and patch keep arriving in the `all-pip-backend` batch (the k5dnc
  decision to un-hold PyMuPDF is not reopened).
- `tests/test_dependabot_config.py`: `MAJORS_HELD` plus three tests -- the ignore
  is exactly semver-major (no `versions`, no full ignore); minor/patch still flow
  (not in any pip group's exclude-patterns, not in `HELD_FOR_UPGRADE`); and the
  package is actually pinned in `requirements.txt`. Mutation-verified: removing
  the entry, widening it to a full ignore, scoping it to semver-minor, or adding
  PyMuPDF to the group's exclude-patterns each fail.
- #923 closed with an explanation.
- Fresh-eyes (Haiku) round 1: GAPS-FOUND (1) -- the minor/patch half was unpinned
  (verified by the exclude-pattern mutation). Fixed inline. Its two
  unverifiable notes -- Dependabot name-case matching and whether grouped updates
  honor a per-package update-types ignore -- were settled by repo evidence: the
  earlier full hold spelled it `PyMuPDF` (the manifest spelling, which GitHub's
  docs say to match) and Dependabot honored it (the 2026-11-07 batch #907
  carried other minors but not PyMuPDF 1.24 -> 1.28), so the entry now uses that
  spelling. Grouped-update behavior will be confirmed by the next weekly run.

## Lessons

- A scoped hold has two halves -- what is blocked and what must still flow --
  and a test that pins only the first lets a later edit silently turn it into a
  full hold. Pin both.

## Doc freshness

- `docs/standards/testing.md` (tracks `.github/dependabot.yml` and this test
  file): reviewed, left -- it describes the hold mechanism in general and lists
  no per-package majors-only holds; it was already stale from other files.

## Files touched

- `.github/dependabot.yml` -- scoped PyMuPDF major ignore
- `tests/test_dependabot_config.py` -- MAJORS_HELD + three tests
