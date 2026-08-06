---
date: 2026-08-05
bead: polyglot-pdf-1bsx
title: "feat(beads): tier routing + a Haiku adversarial review for docs-only PRs"
tags: [harness, doctrine, review]
---

## Trigger

Follow-on to PR #549 (bd `ofh6`/`0arm`), which collapsed the review harness from
three serial Opus passes to one. Three threads converged into this PR:

1. **The gap #549's own Opus reviewer flagged.** Retiring the inner loop's
   guaranteed-Opus round removed the ONLY adversarial look a docs-only PR ever got
   -- the Step 5.6 gate skipped them entirely. Maintainer's call: *"I'm fine with
   docs not getting a full opus review. Let's give docs only changes a single
   adversarial haiku review, though."* (bd `saxh`)
2. **The routing layer the whole exercise was aimed at.** The maintainer's goal is
   to get from 4-6 concurrent sessions down to *2 epics + 1 bug session + 1
   perpetual cheap nit-cleanup session*. That last one only works if beads say
   which model should pick them up: *"if the reviewers can classify which tier
   model should pick up a bead... that will really help get the right model to the
   right jobs."* (bd `1bsx`)
3. **A stale reference** #549's Opus pass found and filed rather than fixing
   inline -- itself a demonstration of that PR's new non-behavioral carve-out.
   (bd `l6df`)

## What shipped

### bd polyglot-pdf-saxh -- the review gate becomes a THREE-way fork

Was a skip/run binary. Now:

- **source diff** -> ONE looped Opus cross-surface review (unchanged)
- **docs-only diff** -> ONE looped adversarial **Haiku** review (new)
- **trivial diff** -> no adversarial pass; fresh-eyes `NO-GAPS` is the record

New [`.claude/agents/docs-reviewer.md`](../../../.claude/agents/docs-reviewer.md)
(`model: haiku`). **Purpose-written rather than reusing `cross-surface-reviewer` at
a cheaper model** -- that agent's entire framing is "follow contracts into untouched
consumers," which is meaningless on a diff that changes no runtime contract. The
docs reviewer instead hunts the failure classes prose actually has: claims that
contradict the code they document (it *opens the cited source to check* -- the
highest-value thing it does), stale or broken cross-references, doc-vs-doc conflict,
a `*Last updated:*` bump with no real prose review, and history smuggled into a
current-state doc. Explicitly NOT a contract trace, NOT a rubric re-score, NOT a
style critic (markdown is exempt from the ASCII rule).

**Auto-merge was deliberately NOT widened.** A Haiku-cleared docs PR now has a real
adversarial review and so arguably satisfies auto-merge condition (a) -- but that is
a product/autonomy call, not a side effect of this bead. It still pings; the
question is surfaced to the maintainer instead of assumed.

### bd polyglot-pdf-1bsx -- tier + work-class routing

Two CLOSED enums on every bead's metadata, documented in the new
[`docs/standards/bead-tiers.md`](../../standards/bead-tiers.md):

- `tier`: `haiku` | `sonnet` | `opus` | `fable`
- `work_class`: `docs-nit` | `comment-align` | `cross-surface` | `local-bug` |
  `needs-plan` | `mechanical`

**`fable` is a DIFFERENT JOB, not a higher rung.** Three of the four are a
capability ordering; `fable` is long-horizon planning that should never write code,
while Opus is equally good at code and does cross-surface work. Without that stated
plainly, reviewers file `fable` when they mean "hard," and a hard refactor lands in
the planning queue and stalls. Disambiguator: *"what does done look like?"* -- a
merged diff is haiku/sonnet/opus by blast radius; an approved plan or research
conclusion is `fable`.

**The escalation/de-escalation asymmetry is deliberate.** Above tier -> release
**with notes** and bump the tier (a bare unclaim just gets re-claimed by the next
same-tier runner, which is the ping-pong the notes prevent). Below tier -> **just do
it**, or delegate to a cheap subagent; do NOT release. By the time you know a bead
is easy you have already loaded its context, so releasing throws that away and makes
a cheaper session re-derive it. Administration that outweighs the saving is not a
saving. No calibration notes either -- explicitly declined by the maintainer as
overhead with no consumer.

**Epic-scale reclassification must be LOUD:** re-tier to `fable`, don't halt if
non-blocking, but return it to the orchestrator, which must surface it emphatically
in its end-of-session summary as its own flagged item.

### bd polyglot-pdf-l6df

`closeout-runner.md:12` called itself the counterpart to "the `fresh-eyes-reviewer`
agent" when there are now two judging reviewers. Prose only -- the runner never
spawns a reviewer (its STOP list forbids it).

## Lessons

- **A closed enum needs a verified consumer before it is worth writing down.** The
  enum's own justification ("a bad value breaks the batching query") presupposes a
  query exists. It was worth checking rather than assuming: `bd list` turns out to
  support `--metadata-field key=value` (repeatable) and `--has-metadata-key`
  natively, so no `jq` pipeline is needed. That command is now named in the standards
  doc -- an enum whose only consumer is hypothetical is exactly the "overhead with no
  consumer" this same PR declined for calibration notes. Verified end-to-end on a
  throwaway bead, **both directions**: `surfaces` survived alongside the new keys
  (the `--metadata`-REPLACES trap), the query returned the bead, and a wrong-tier
  query returned nothing.
- **A pinning test that matches "the word" instead of "the claim" is not a pin --
  and this trap recurs at every layer.** Writing the three-way-fork test, two
  assertions matched OTHER legitimate sites (the PR-body review-record line and the
  Step 6.2 ping list) rather than the operative gate, so a mutation widening the skip
  arm back to docs-only passed when it should have failed. This is the **third**
  occurrence in two PRs -- the same failure mode bit the `behavioral` pin in #549,
  then bit its own fix one layer down. The reliable form is: pin the operative
  sentence's own wording, and mutation-verify by editing THAT sentence alone, never
  by a global find-replace (a global replace proves nothing, because it changes every
  site the loose assertion might be matching).
- **When a change closes a gap another change opened, say so in both places.** The
  three-way fork only makes sense against the history of the guaranteed-Opus round
  being retired. Recording *why* the gate is three-way (in `review-flow.md`'s gate
  bullet and its dateline) keeps a future reader from "simplifying" it back to a
  binary and silently reopening the gap.
- **When the same defect class survives your fix TWICE, change the MECHANISM, not
  the instance.** This bead cost **six** inner review rounds, and rounds 4, 5 and 6
  each defeated a test written in the round before -- every time live-reproduced by
  the reviewer. My fixes were: add more verbs to the regex; widen its literal infix;
  then handle noun-first word order. All three escapes shared one root I kept not
  seeing -- the test was **matching** prose rather than **enumerating** it, and a
  substring allowlist let a sentence quote an allowed fragment verbatim while
  asserting the opposite. Replacing the mechanism (enumerate every candidate
  sentence with no denial test at all; exact whole-sentence equality against an
  allowlist generated from the real file) held against all 17 earlier escapes at
  once. **The tell:** each fix was "add another alternation"; each new repro
  differed from the last only in wording; and I could list cases the test caught but
  not state a property it held. Promoted to
  [`docs/standards/testing.md`](../../standards/testing.md#change-the-mechanism)
  with its two corollaries -- generate expectations from the real artifact (2 of my
  5 hand-typed allowlist entries described sentences that did not exist), and verify
  a mutation actually APPLIED before trusting green (2 of mine silently no-op'd on a
  line-wrap mismatch and "passed" while testing nothing).
- **Prefer a NATURAL scope over a tuned constant -- then STOP and name what you are
  not covering.** The mechanism swap above was not the end of it. The rebuilt pin
  was defeated twice more on *scope* rather than vocabulary: single-sentence
  matching lost to an `e.g.` mid-sentence split, and a two-sentence sliding window
  lost to a three-sentence phrasing. Each fix was a bigger N, and each invited the
  phrasing just outside it. What held was dropping N entirely and scoping to the
  **paragraph** -- the unit the prose itself uses for one claim. But the next round
  escaped *that* with a blank-line split, which is when the real lesson landed:
  **every scope has an adjacent-scope escape, so a prose heuristic cannot be made
  evasion-proof, and iterating toward one is the same trap in a new costume.** The
  discriminating question is *what failure am I actually defending against?* Here it
  is DRIFT -- a maintainer updating one statement of a rule and missing another --
  and all three real regressions (`git show origin/dev:CLAUDE.md` lines 89, 218,
  470) were single in-paragraph sentences in ordinary vocabulary, because whoever
  edits a rule is by definition describing it. Every escape found from that point on
  was *constructed by a reviewer trying to evade the check*; none had occurred
  naturally. So the remaining two shapes became **accepted, pinned limits**
  (`UNENUMERABLE_BY_DESIGN` + `test_known_limit_still_holds`, which fails if a limit
  ever closes) rather than two more rounds. Promoted to
  [`docs/standards/testing.md`](../../standards/testing.md#change-the-mechanism).
- **The loop-stop rule has no "you are not converging" clause.** It stops on
  outcome (no correct blocker remains), which is right, but nothing says *"the same
  class has now beaten you twice -- change approach"* or *"you are defending against
  constructed evasion rather than the real failure mode."* That absence is what
  stretched this PR to ten rounds; the rounds themselves were all finding real
  defects, and the reviewer was right every time. Worth considering as a future
  harness change rather than a rule I invent here.

## Doc freshness

- **New:** [`docs/standards/bead-tiers.md`](../../standards/bead-tiers.md) (with a
  `**Tracks:**` line, so the freshness gate polices it going forward). Indexed in
  [`docs/standards/README.md`](../../standards/README.md) and
  [`docs/INDEX.md`](../../INDEX.md).
- **Updated:** [`docs/doctrine/review-flow.md`](../../doctrine/review-flow.md)
  (dateline, flow diagram, review-worthiness-gate bullet, merge-decision paragraph,
  reviewer inventory), [`docs/doctrine/workflow.md`](../../doctrine/workflow.md) (the
  tier/work_class declaration bullet), `CLAUDE.md` (scar-tissue #2 + the auto-merge
  condition).
- **Reviewed and deliberately LEFT:** the 24 pre-existing STALE tier-2 docs, filed as
  bd `polyglot-pdf-2j8w`. This branch touches no `backend/`/`frontend/`/`.github/`
  file, so none of them is this PR's doing -- the same pre-existing rule #549
  introduced, applied again.

## Files touched

- `.claude/agents/docs-reviewer.md` (**new**, `model: haiku`)
- `.claude/agents/closeout-runner.md`, `.claude/agents/fresh-eyes-reviewer.md`,
  `.claude/agents/cross-surface-reviewer.md`
- `.claude/skills/closeout/SKILL.md`, `.claude/skills/next-bead/SKILL.md`
- `CLAUDE.md`
- `docs/standards/bead-tiers.md` (**new**), `docs/standards/README.md`, `docs/INDEX.md`
- `docs/doctrine/review-flow.md`, `docs/doctrine/workflow.md`
- `tests/test_closeout_skill.py`
