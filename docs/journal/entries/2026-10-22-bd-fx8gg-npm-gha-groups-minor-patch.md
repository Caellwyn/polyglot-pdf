---
date: 2026-10-22
bead: polyglot-pdf-fx8gg
title: "chore(deps): npm + github-actions Dependabot groups batch only minor+patch; hold the majors reverted in #888"
tags: [testing, conventions]
---

## Trigger

The same incident as bd `polyglot-pdf-niwcu` / `polyglot-pdf-oyi5w`. The
grouped npm Dependabot PRs #880/#884/#885 carried untested majors (React 19,
Tailwind 4, pdfjs-dist 6, react-router 7, jsdom 30). They were merged red and
reverted in #888. Their groups still batched majors, so the next weekly run
(Monday 2026-10-26) would have proposed them again. The niwcu outer review
filed this; the oyi5w review accepted its deferral only if it landed before
that run.

## What shipped

- **All five groups take minor+patch only.** That covers the three npm
  groups and the GitHub Actions group, which join the pip group from niwcu.
  Every group in `.github/dependabot.yml` now carries
  `update-types: [minor, patch]`.
- **Ten reverted packages are HELD.** They are fully ignored and excluded in
  every npm entry until their upgrade bead lands:
  - react, react-dom, @types/react, @types/react-dom and
    @testing-library/react: lhrnq
  - pdfjs-dist: q0i7k
  - tailwindcss: umd8r
  - react-router-dom: vxssq
  - jsdom and @testing-library/jest-dom: 50zcc
- **Tests** (all mutation-verified red):
  - `test_every_group_in_every_ecosystem_batches_only_minor_and_patch`
    replaces the pip-only scope. Removing the GitHub Actions `update-types`
    fails it.
  - `NPM_HELD_FOR_UPGRADE` plus a full-ignore/exclude test. Dropping the
    admin-console pdfjs hold fails it.
  - A test that each held name is declared by some app. A misspelled name
    fails it.

## Lessons

- **Fix the whole set in one go** (CLAUDE.md scar #8). The pip-only fix in
  niwcu left the npm groups exposed to the identical failure. A guard is
  scoped to the property ("no group batches majors"), not to the ecosystem
  where it was first seen.

## Doc freshness

`docs/standards/testing.md`'s Dependabot paragraph now covers every ecosystem
and both held sets.

## Files touched

- .github/dependabot.yml
- tests/test_dependabot_config.py
- docs/standards/testing.md
