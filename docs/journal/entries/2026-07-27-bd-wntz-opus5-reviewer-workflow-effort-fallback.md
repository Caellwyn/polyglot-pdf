---
title: "Opus 5 as outer reviewer + Workflow fallback for the xhigh spawn 400"
date: 2026-07-27
bead: polyglot-pdf-wntz
tags: [doctrine, review-flow, closeout, models, tooling]
---

# polyglot-pdf-wntz -- Opus 5 reviewer + Workflow fallback for the effort-400

## Why

Two coupled changes, both triggered by the Opus 5 rollout.

**1. A new spawn bug.** Since Opus 5 became the default model, an Agent-tool
spawn of a non-Fable model from a Fable session at `xhigh` effort fails:

```
API Error: 400 output_config.effort 'xhigh' is not supported when thinking is
disabled on this model. Use effort 'high' or below, or enable thinking.
```

Subagents inherit the session's effort setting, and the orchestrator cannot
read that setting -- nothing in context reports it, and no tool exposes it. So
a Fable orchestrator at `xhigh` cannot know in advance that its Opus reviewer
spawn will die. This matters directly to closeout: the outer review IS an Opus
subagent spawn, and the maintainer wants Fable retained as the orchestrator
tier for long-horizon epic work.

**2. Opus 4.8 -> Opus 5.** The maintainer is moving code production to Opus 5
(sessions and subagents), reserving Fable 5 for big-picture planning on complex
features. The live docs still named the outer reviewer "Opus-4.8".

## What shipped

**The effort-400 fallback (the substantive part).** Added at three levels --
`CLAUDE.md` (closeout section), `docs/doctrine/review-flow.md` (outer-review
mechanics), and `.claude/skills/closeout/SKILL.md` (Step 5.6, inline at the
spawn instruction). The rule: spawn via the Agent tool as before; if the spawn
returns that 400 (or a functionally similar effort-unsupported 400), retry the
SAME single spawn wrapped in a **one-agent Workflow** whose `agent()` call
passes `effort: 'high'` explicitly. The Workflow tool's `agent()` exposes an
`effort` option that the Agent tool's schema lacks -- that is the entire
mechanism.

Three guards are stated explicitly because each is a plausible misread:

- **It is a transport failure, not a review failure.** It must not be recorded
  as `BLOCKED`, and it does not escalate to the maintainer.
- **It must not downgrade the reviewer to Sonnet.** The cheaper-tier fallback
  already exists for a genuinely unavailable second Opus; reusing it here would
  silently weaken the gate for a reason unrelated to model availability.
- **Single-agent wrapper ONLY.** Workflow normally requires explicit maintainer
  opt-in for multi-agent orchestration. This standing permission is scoped to
  one agent replacing one blocked spawn -- it is not an opt-in to fan-out.

**Verification.** Confirmed by controlled A/B inside one Workflow run at
session effort `xhigh`: an agent with `{model: 'opus', effort: 'high'}`
returned normally, while an identical `{model: 'opus'}` agent inheriting
`xhigh` died with the 400. Both ran in the same workflow, so the effort
override is the only differing variable.

**Opus-4.8 -> Opus-5 rename**, in current-state/live-process prose only:
`CLAUDE.md`, `AGENTS.md`, `docs/INDEX.md`, `docs/doctrine/{review-flow,
workflow,planning,promotion-tiers,branch-protection-setup}.md`,
`docs/branch-protection-setup.md`, `.claude/prime-closeout-override.md`,
`.claude/skills/closeout/SKILL.md`.

**The reviewer rationale, rewritten.** `review-flow.md` justified the outer
review as a "stronger tier than the Sonnet fresh-eyes and the author." With
Opus 5 authoring the code, the outer reviewer is often the SAME tier as the
author, so that argument no longer holds as written. The gate now rests on
what actually carries it: **independence** (a fresh subagent, no shared
context, prompted adversarially, reading the real diff) plus **two independent
passes having to agree**. Maintainer decision: Opus-5-reviewing-Opus-5 is
accepted -- the prior state was Fable or Opus 4.8 authoring with Opus 4.8
reviewing, so same-tier review is not a regression, and Opus 5 is a
significant upgrade over 4.8.

**Sonnet references** were checked and left alone: they are generic
(`model: sonnet`, "Sonnet re-review"), and the model parameter takes family
names, so they already resolve to Sonnet 5. There were no version-pinned
Sonnet strings to bump.

## What was deliberately NOT changed

**The historical record.** ~40 files under `docs/journal/entries/`,
`docs/research/`, `docs/journal/telemetry/FINAL_REPORT.md`, and
`scripts/bakeoff/FINDINGS.md` say "Opus 4.8" because that is what actually
ran at the time. The journal is this repo's chronological record; rewriting it
would falsify history. An entry stating that a June review ran on Opus 4.8 is
true and stays.

This distinction bit during the work: a blanket `sed` over `review-flow.md`
rewrote two *historical* statements in its header paragraph -- "the Opus-4.8
reviewer that already existed as the Codex fallback" and "the Opus-4.8 reviewer
was introduced under bd n6ks". Both became false as "Opus-5" (Opus 5 did not
exist then). Caught on diff review and fixed: the header now says the Opus
reviewer was introduced under n6ks as Opus 4.8 and moved to Opus 5 under this
bead. Two `stronger tier` mentions describing the bd `bo4m` regression were
likewise left intact -- there, a stronger tier genuinely did catch what Sonnet
missed.

## The fresh-eyes round (what the first draft got wrong)

The pre-PR assessor returned `GAPS-FOUND (8)` on the first draft and was right
about seven of them. The valuable ones were not typos -- they were **rule
conflicts**, the failure mode that matters most when the artifact IS a set of
instructions:

- **The fallback was scoped to the Opus reviewer (Step 5.6) only, but Step 5.5
  spawns subagents first** -- at haiku/sonnet, plus a mandated Opus final round.
  All are non-Fable spawns that die identically. A Fable-at-`xhigh` closeout would
  have blocked at Step 5.5 and never reached the fallback. Fixed by restating the
  rule scope-neutrally: every Agent-tool spawn, any model, **any step**.
- **Two standing rules contradicted the new one.** The skill's "Hard rules"
  (read-before-anything) and Step 5.6's verdict list both say a subagent
  TIMEOUT/ERROR is "a genuine stop -- surface it," and the latter added "there is
  no further fallback," which the new block made false. An orchestrator reading
  top-down would escalate the exact failure this bead exists to absorb. Both now
  carry the effort-400 carve-out.
- **The three copies of the rule were not equivalent** -- the SKILL.md copy (the
  file CLAUDE.md calls the source of truth) was missing the "not a `BLOCKED`
  verdict, does not escalate" clause that the other two had.
- **No terminal branch.** The fallback read as unconditionally curative; combined
  with "do not escalate," an orchestrator whose wrapped retry also failed had no
  instruction, and the nearest one said not to stop. All three copies now end with:
  if the wrapped retry also fails, that IS a genuine stop.
- **A third historical-tense error** at `review-flow.md:135` -- the same sed
  damage as the two already fixed, missed because the initial verification grep
  was too narrow. The reviewer found it; my own check had returned a false
  all-clear.
- **A tier claim that contradicted bd dgoa.** The rewritten rationale still opened
  with "a tier above the Sonnet fresh-eyes that cleared the rubric" -- but dgoa
  requires the *clearing* fresh-eyes round to run on Opus, so the pass that clears
  is not Sonnet. Reworded to drop tier superiority entirely.
- **An over-claim about tiering.** The draft asserted "code production moved to
  Opus 5" as settled fact, but the canonical tiering table (`planning.md:137`,
  CLAUDE.md) still says Sonnet for execution. Rather than unilaterally rewrite the
  tiering doctrine (a maintainer call, not this bead's scope), the claim was
  softened to the conditional that is actually true: "when the author ran on Opus,
  the outer reviewer is the same tier."

Every finding was verified against the files before being acted on rather than
taken on faith. That mattered in one case in the reviewer's favour: my first
check of finding 4 used too narrow a grep and appeared to refute it, and only a
wider read confirmed the reviewer was right. The lesson cuts both ways -- verify
the reviewer, but verify your own refutation just as hard.

**Round 2 found four more, and the sharpest one was a regression in my own fix.**
Restating the fallback as "EVERY spawn ... **in Step 5.5 AND Step 5.6**" let the
trailing clause silently re-narrow the leading "every" -- and closeout has a THIRD
spawn the enumeration missed: the Haiku `closeout-runner` that drives the
mechanical tail at Step 6, which is instructed to stop back on any tooling error.
So the fix for "a spawn site outside the rule's scope" recreated the identical
defect one step later: a Fable-at-`xhigh` closeout would now clear both reviews
and then block at the tail. The scope is now stated as "any model, any step,"
with the three sites named illustratively rather than as the bound. Round 2 also
caught that the F7 softening had patched the body of `review-flow.md` while its
header still carried the unconditional "when code production moved to Opus 5"
claim, and that the three copies of the rule had drifted apart again on scope
(SKILL.md narrow, CLAUDE.md and review-flow.md broad) -- the same
non-equivalence round 1 flagged, reintroduced by the edit meant to fix it.

**The generalizable lesson: an enumeration inside a universal claim is a scope
bug waiting to happen.** "Every X, in A and B" reads as universal and behaves as
a whitelist. When a rule is meant to be unbounded, name the instances as examples
("including ..."), never as the boundary -- and when the same rule is duplicated
across files, re-diff all copies after every edit, because each fix is a fresh
chance for them to diverge.

The `scripts/` docstrings (finding 5) were outside the bead's enumerated file list but
inside criterion 2's wording, and are current-state prose, so they were renamed
too, along with stale comments in `tests/test_closeout_skill.py`.
`tests/test_pr_review_watcher.py:1456` was deliberately left saying "Opus-4.8" --
it describes the retired Codex-era fallback, which genuinely was 4.8.

## Review record

**Fresh-eyes assess loop: 3 rounds to `NO-GAPS`** (final clearing round on Opus,
per bd dgoa). Round 1: `GAPS-FOUND (8)`, 7 adopted. Round 2: `GAPS-FOUND (4)`, all
4 adopted -- including the regression that round 1's own fix introduced. Round 3:
`NO-GAPS`, all three exit criteria PASS. The round-3 pass independently
enumerated every delegation point in the closeout skill to confirm no fourth
spawn site exists, and verified that neither delegated agent
(`closeout-runner`, `fresh-eyes-reviewer`) can nest a spawn -- neither has the
Agent tool.

**Outer Opus review: SKIPPED under the Step 5.6 review-worthiness gate.** The
diff touches three non-`.md` files (`scripts/closeout_finish.py`,
`scripts/swarm_config.py`, `tests/test_closeout_skill.py`), but every changed
line is a comment, a docstring, or one assertion *message* -- zero executable
statements, so the diff cannot introduce a runtime/logic regression. The
fresh-eyes `NO-GAPS` is this change's review record.

Full backend suite: 1314 passed, 1 skipped. Closeout-skill + harness-ledger
suites: 61 passed. The three edited `.py`/test files were byte-verified
ASCII-clean (CLAUDE.md scar #6).

## Scar tissue

- **A model-name rename is not a safe find-and-replace in a repo that keeps a
  journal.** The same string is a current-state label in one file and a
  historical fact in another. Separate the two sets before running `sed`, and
  read the resulting diff for tense.
- **The orchestrator cannot introspect its own effort setting.** Any rule
  keyed on "if the session is at xhigh" is unimplementable. Key it on the
  observable error instead -- which is why this shipped as a fallback rather
  than a precondition check.
- **Never bound a universal rule with an enumeration.** "Applies to every spawn,
  in Step 5.5 and Step 5.6" reads universal but behaves as a whitelist, and it
  missed the Step 6 `closeout-runner`. Write "at any step (including A, B, C)",
  not "in A and B".
- **A rule duplicated across N files needs an N-way diff after EVERY edit.** This
  rule lives in CLAUDE.md, review-flow.md, and the closeout skill. Round 1 found
  them non-equivalent on the escalation clause; the round-1 fix made them
  non-equivalent on scope instead. Each edit is a fresh chance to diverge.
