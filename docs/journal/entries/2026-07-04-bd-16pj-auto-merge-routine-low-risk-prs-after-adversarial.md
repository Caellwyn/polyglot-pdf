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

Three connected doctrine changes (all from maintainer directives during this
session), plus the review fixes they surfaced.

**(A) The merge boundary** moved from an **unconditional** "always ping the maintainer to
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

**(B) The review loop is now OUTCOME-based, no round cap** (second maintainer
directive, same session). The former hard ceilings -- `MAX_REVIEW_ROUNDS = 2`
(Codex), `MAX_FALLBACK_ROUNDS = 2` (Opus fallback), `MAX_FRESH_EYES_ROUNDS = 3`
(pre-PR fresh-eyes) -- are retired. The loop now stops on OUTCOME, not iteration
count: keep looping while any finding is a correct blocker; stop (= CLEAN / NO-GAPS)
only when every remaining finding is incorrect (refuted, with the reason recorded)
or a true nit (filed as a bead). The maintainer's rationale: once closeout can merge
independently, code quality -- not iteration budget -- is the bar, and a long
back-and-forth to get it right is a feature. Pure outcome-based with NO
non-convergence backstop (maintainer's explicit call); a genuinely stuck finding
that can neither be fixed nor honestly refuted/deferred escalates via the normal
step-2 rule, not a round count. The ceiling was doctrine-only (no code enforced it),
so this is SKILL.md + review-flow.md edits plus a superseded-pointer on the sprint-1
plan.

**(C) Fixes the review itself surfaced** (this PR ate its own dogfood -- Codex +
the Opus fallback reviewed it and found real bugs in the auto-merge design):
- **Merge race:** the auto-merge command now captures the reviewed head SHA
  (`gh pr view --json headRefOid`) and merges with `gh pr merge --match-head-commit`,
  so a push landing between the clear and the merge FAILS rather than merging an
  unreviewed head.
- **`--admin` deny was a no-op.** The first attempt used `Bash(gh pr merge:* --admin:*)`
  -- but Claude Code's Bash matcher treats `:*` as TRAILING-only, so a mid-pattern
  colon is literal and that rule matched nothing; `gh pr merge 301 --admin` slipped
  straight to the allow rule. Verified via claude-code-guide, then replaced with
  space-wildcard forms (`gh pr merge --admin *`, `gh pr merge * --admin *`,
  `gh pr merge *--admin*`) that catch `--admin` in any position. Filed
  `polyglot-pdf-kibf` for the stronger PreToolUse-hook tokenizer (wildcard flag
  matching is fragile in general).
- **Allowlisted `gh pr view`** (the SHA-capture needed it; otherwise the
  "autonomous" merge path would hit a permission prompt).
- **Reconciled more stale endpoints** Codex/fallback found beyond the fresh-eyes
  sweeps: `CLAUDE.md:84`, `planning.md`, `promotion-tiers.md` intro,
  `docs/standards/testing.md:193` (an auto-loadable tier-2 doc). Out-of-scope
  Copilot-era staleness in `docs/branch-protection-setup.md` filed as
  `polyglot-pdf-8jf1`.

## Lessons

- **A security-interlock permission pattern must be VERIFIED, not assumed.** The
  `--admin` deny looked right (`Bash(gh pr merge:* --admin:*)`) but was a silent
  no-op: Claude Code's Bash matcher only honors `:*` as a TRAILING wildcard, so a
  colon mid-pattern is a literal character and the rule matched nothing. A denied
  operation you never test is a denied operation you don't actually have. When a
  settings rule is the thing standing between an agent and a checks-bypassing
  `--admin` merge, confirm the matcher behavior (claude-code-guide / the docs) and
  ideally test the evasion forms -- do not eyeball it. Space-wildcards
  (`gh pr merge * --admin *`) match a flag in arbitrary position; `:*` cannot.
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
