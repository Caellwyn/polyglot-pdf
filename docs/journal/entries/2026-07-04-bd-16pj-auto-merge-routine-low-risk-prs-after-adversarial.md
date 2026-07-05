---
date: 2026-07-04
bead: polyglot-pdf-16pj
title: "Auto-merge routine low-risk PRs after adversarial-review CLEAN; reserve maintainer merge for consequence-bearing changes"
tags: [doctrine, harness]
---

## Trigger

Maintainer product-owner directive (2026-07-04), given while revisiting the
AI auto-merge permissions during the hrn.17 closeout. Rationale in the maintainer's
words: no bugs have shipped, review quality is high, and they want the
product-manager seat, not the engineering-lead seat -- so routine merges should
stop needing a human click. Two connected asks: (1) auto-merge routine low-risk
PRs that a separate adversarial model cleared; (2) stop asking "should I run
closeout?". Filed as bead 16pj during the hrn.17 session and picked up as its own
PR so the policy change is reviewable in isolation.

## What shipped

The merge boundary moved from an **unconditional** "always ping the maintainer to
merge" to a **conditional fork**. The orchestrator now runs `gh pr merge` itself
when ALL of: (a) an adversarial reviewer cleared the diff (Codex CLEAN, or the
Opus-4.8 fallback `NO-GAPS`); (b) CI/required checks green; (c) the PR is NOT
consequence-bearing. A consequence-bearing PR still pings the maintainer.

**Consequence-bearing** is the maintainer's exact 5-part boundary: proves the
bead's direction impossible / substantially changes an approved plan; affects
operational cost; affects user-facing features; risks downstream disruption;
needs substantial multi-surface rework. This is deliberately the SAME line as the
step-2 escalation triggers -- the merge boundary and the escalation boundary are
one line, so there is one consequence test to reason about, not two.

Force-push, `--force-with-lease`, and `bd dolt push --force` stay hard-barred on
the NEVER list regardless of review state.

Also removed the "should I run closeout?" ask: if the bead is complete and
fresh-eyes is no-gap, closeout just runs.

Encoded across the whole doctrine surface for consistency (the bead named 3 files;
it took 11, because a rule stated in one place but contradicted in another is worse
than not stating it):
- `.claude/settings.json`: `gh pr merge` moved deny -> allow; added `gh pr checks`.
- `CLAUDE.md`: NEVER-list item rewritten; new "Auto-merge vs. maintainer merge"
  rule; no-closeout-ask rule.
- `.claude/skills/closeout/SKILL.md`: Step 8 forks auto-merge vs ping; preamble +
  frontmatter reconciled.
- `.claude/skills/next-bead/SKILL.md`, `.claude/prime-closeout-override.md`,
  `.claude/agents/closeout-runner.md`, `docs/doctrine/{review-flow,promotion-tiers}.md`,
  `.github/workflows/ci.yml`, `scripts/closeout_finish.py`: reconciled to the fork.
- `tests/test_closeout_skill.py`: the regression test that pinned the old
  "never run gh pr merge" contract rewritten to pin the new fork (both arms present,
  consequence-bearing gate present, old blanket ban absent, force-push still barred).

**The closeout-runner subagent keeps its merge restriction** -- but reworded. Merge
is an orchestrator judgment call (consequence-bearing or not); the mechanical
runner never makes judgment calls, so it never merges. That is role-scoping, not
the old "nobody merges" policy.

## Lessons

- **A policy stated once but described in ten places needs all ten reconciled, or
  the contradictions ARE the bug.** Two adversarial fresh-eyes rounds found 11
  stale "ping only / manual merge is the only gate" statements across docs, skills,
  a CI comment, a script docstring, and a test -- every one a *description* of the
  old endpoint that survived the *rule* change. For a doctrine edit, a repo-wide
  grep for every phrasing of the old rule is part of the change, not a nicety.
- **A regression test that pins doctrine wording will fail LOUD when the doctrine
  changes -- that is the test working, not a nuisance.** `test_closeout_skill.py`
  pinned "never run gh pr merge"; the rule change made it red. The fix is to
  re-point the test at the NEW contract (and verify it still discriminates old vs
  new -- fresh-eyes confirmed it fails against dev's pre-change text), not to
  delete the guard.
- **A skill's frontmatter `description` escapes body-only regression tests.** The
  stale "the only thing it never does is the final merge" line lived in the
  `description:` field, which `test_closeout_skill.py` deliberately does not scan.
  Doctrine-in-frontmatter needs its own eyes.

## Doc freshness

- Bumped `docs/doctrine/promotion-tiers.md` and `docs/doctrine/review-flow.md`
  `Last updated:` stamps to 2026-07-04 (both had current-state merge-rule edits).
- CLAUDE.md (tier-1) updated in place, current-state only (no history chain; the
  lineage is this journal entry).

## Files touched

- `.claude/settings.json` -- merge permission deny -> allow; added gh pr checks.
- `CLAUDE.md` -- auto-merge rule + no-closeout-ask rule.
- `.claude/skills/closeout/SKILL.md` -- Step 8 fork; preamble + frontmatter.
- `.claude/skills/next-bead/SKILL.md` -- closeout-endpoint reference reconciled.
- `.claude/prime-closeout-override.md` -- merge lines reconciled.
- `.claude/agents/closeout-runner.md` -- merge restriction reworded as role-scoping.
- `docs/doctrine/review-flow.md` -- flow diagram + prose + fallback path reconciled.
- `docs/doctrine/promotion-tiers.md` -- "The merge gate" section rewritten.
- `.github/workflows/ci.yml` -- merge-gate comment reconciled.
- `scripts/closeout_finish.py` -- docstring merge-boundary note reconciled.
- `tests/test_closeout_skill.py` -- regression test + module docstring updated.
- `docs/journal/entries/2026-07-04-bd-16pj-...md` -- this entry.
