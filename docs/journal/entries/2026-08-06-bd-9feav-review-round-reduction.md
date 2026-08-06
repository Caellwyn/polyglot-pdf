---
date: 2026-08-06
bead: polyglot-pdf-9feav
title: "chore(harness): three rules to cut review rounds -- measured, not assumed"
tags: [harness, review, doctrine, testing]
---

## Trigger

The maintainer had two observations that pulled in opposite directions, and both
were sincerely held:

1. **Every session was reporting that the reviews "really earned their keep"** --
   seven of them, including this one. One reported that two Opus reviewers
   *disagreeing* forced a deeper investigation and a better fix.
2. **Development had slowed to a crawl and token burn had quadrupled** (never
   maxing a Max x5 plan -> always maxing a Max x20). PRs that merged in 3-5
   rounds three weeks ago were routinely going 9, 13, even 17.

The maintainer's framing of the open question: *"Is the increase in review rounds
because the coding agents are sloppier, or because the reviewers are more
strict?"* -- Opus and Sonnet had both been upgraded to the 5 series on 2026-07-28,
so either was plausible.

**The signal to distrust first was the one this session was generating.** "The
reviews earned their keep" comes from the agent that just spent the rounds;
concluding they were worthwhile justifies its own token burn. Seven sessions
saying it is seven instances of one bias, not seven confirmations. So: measure.

## What shipped

### The measurement (and why it overturned both hypotheses)

Round counts **fell** after the 5-series upgrade, they did not rise:

| Window | Rounds per PR |
|--------|---------------|
| Jul 28-29 (immediately post-upgrade) | 4, 5, 5, 5, 6, 11 |
| Aug 1-5 (a week later) | 1, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 5, 6, 7, 7 |

So neither "sloppier coders" nor "stricter reviewers" explains the outliers.
Reading the last 40 merged PRs' own bodies (26 state their round counts) showed
what the outliers actually share -- **work type, not model**:

- **#551** (12 + 11 rounds) -- *"Six review rounds each found one more unprotected
  location."*
- **#538** (4 + 11 rounds, 51 findings) -- a copy rewrite, where *"the review
  caught the copy pass itself introducing false claims."*
- **#552** (6 rounds, 19 gaps) -- a sprint plan.
- **#554** -- the docs audit.
- **bd `saxh`** (13 + 4) -- the review rules themselves.

Ordinary single-behavior code fixes (#530, #528, #542, #517, #513, #532) ran 1-3
rounds throughout the same window. **The variable is enumerable-set work and
prose.** Three rules follow from that.

### Rule 1 -- ENUMERATE THE SET BEFORE FIXING ANY OF IT (CLAUDE.md scar tissue #7)

When a finding is an *instance* of something -- one write site, one restatement of
a rule, one stale citation -- enumerate every member **mechanically** before fixing
any of them, then pin the **set** rather than the instance. In every outlier above
the first fix was *correct*; it just was not the whole set, so the reviewer found
the remainder one per round. The tell: a new finding differs from the last only in
*location* or *wording*.

### Rule 2 -- DOC FINDINGS SPLIT BY TIER (closeout triage + all three reviewer agents)

Maintainer directive: *"We need to get deployable code out the door, not wait for
3 hours for iterative improvements to a doc journal entry that no one will ever
read."* A prose finding re-opens the review loop; that is how a shippable PR
becomes a three-hour round-trip.

- **Tier 3 (journal, research, plans) -> ALWAYS file.** Never a gap.
- **Tier 1/2, a WRONG claim about the code -> blocker, fix before `NO-GAPS`.**
- **Tier 1/2, merely UGLY -> file.**

**This rule took two maintainer corrections, and both mattered.** My first draft
carved out "a doc statement that changes what an agent does." The maintainer:
*"that's too vague. Claude agents tend to be very conservative in their
interpretations."* Exactly right -- a predictive test resolved conservatively means
everything blocks, so the carve-out would have swallowed the rule. The test is now
mechanical: *which file* and *wrong-or-ugly*, both of which have answers.

The second correction was sharper still: *"shouldn't 'why we changed this'
actually live in tier 3? do I have my tier definitions wrong?"* The maintainer had
them right and I had them wrong. `doc-architecture.md` section 3 is explicit --
tier 1/2 are CURRENT STATE ONLY, history and rationale live in the tier-3 journal.
My draft said those files "also carry rationale, file those findings," which would
have told reviewers to shrug at exactly the content the tier system forbids --
**legitimising a violation instead of flagging it.** Corrected, plus a note that
history *found* in a tier-1/2 doc is itself a violation to file.

### Rule 3 -- TEST THE TESTS (CLAUDE.md scar tissue #8 + `testing.md`)

Prove a new test FAILS before trusting that it passes. Explicitly the **author's**
job: a reviewer finding a vacuous test is a round paid for avoidably. PR #540's
reviewer reverted an entire route and **6 of 7 tests still passed**, then defeated
the remaining guard with a one-token mutation. Mutate the real path, confirm the
mutation actually applied, mutate per parametrization, restore and re-verify.

## Lessons

- **Distrust the self-report of the agent that did the work.** "The reviews earned
  their keep" was *true* (they caught two real defects in bd `saxh`, including a
  widened merge permission) and *misleading* (thirteen of those rounds were one
  problem in thirteen paraphrases, generated by the author). Both halves are
  needed; a session reporting only the first is not lying, it is
  self-justifying. The maintainer was right to push, and the data was right to
  overturn both of our stories.
- **A rule aimed at agents must be MECHANICAL, not predictive.** "Might this change
  what an agent does?" is a judgment call under uncertainty, and this repo's own
  escalation doctrine tells agents to resolve uncertainty conservatively -- so a
  vague carve-out reliably becomes *no* carve-out. "Which file is it, and is the
  claim wrong or just ugly?" has an answer. This generalizes well beyond doc
  triage.
- **Rule 1 failed on the PR that introduced rule 1, and that is the most useful
  thing here.** The bead said "both reviewer agents" when there are THREE, and the
  one omitted (`docs-reviewer`) is the arm the rule most exists to protect. Written
  from recall, not enumeration -- the exact failure the rule describes. The
  round-1 reviewer caught it, and the fix was to enumerate *mechanically* (every
  `.claude/agents/*.md` with a `NO-GAPS` verdict; every `SKILL.md` that triages
  findings) rather than to recall harder. A rule you can state and still violate in
  the same breath is a rule worth having; it also means **stating it is not
  enough** -- the enumeration has to be an executed step, not an intention.
- **Check a rule against the spec it depends on, not against memory.** The
  tier-definition error would have shipped a doc rule that contradicted
  `doc-architecture.md`. One `grep` settled it.

## Doc freshness

- **Bumped:** [`docs/standards/testing.md`](../../standards/testing.md) -- the
  TEST THE TESTS practice now leads the TDD cadence under a linkable anchor.
  Stamp merged three same-day updates into ONE line with no `Prior:` chain (the
  2zk3 audit banned synonym chains).
- **Reviewed and left:** the twelve open beads from the bd `saxh` epic, including
  five files that still describe the outer review as Opus-only (`opak`, `d2bm`,
  `qia8`, `vreq`, `wx7j`). Verified still-valid on `dev` rather than assumed -- a
  first grep suggested two were fixed, but reading the text showed both mention
  Haiku only for the *inner* loop. They are a natural first batch for the cheap
  tier-routed runner.

## Files touched

- `CLAUDE.md` (scar tissue #7 + #8)
- `.claude/skills/closeout/SKILL.md` (the triage rule)
- `.claude/agents/fresh-eyes-reviewer.md`, `.claude/agents/cross-surface-reviewer.md`
- `docs/standards/testing.md`
