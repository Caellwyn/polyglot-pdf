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

## Scar tissue

- **A model-name rename is not a safe find-and-replace in a repo that keeps a
  journal.** The same string is a current-state label in one file and a
  historical fact in another. Separate the two sets before running `sed`, and
  read the resulting diff for tense.
- **The orchestrator cannot introspect its own effort setting.** Any rule
  keyed on "if the session is at xhigh" is unimplementable. Key it on the
  observable error instead -- which is why this shipped as a fallback rather
  than a precondition check.
