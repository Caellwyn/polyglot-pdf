---
date: 2026-08-05
bead: polyglot-pdf-ofh6
title: "chore(harness): one Opus review pass, with inner/outer split by job"
tags: [harness, review, doctrine]
---

## Trigger

The review harness had become the bottleneck it was built to prevent. A
review-worthy PR required a **minimum of three serial Opus passes**, all running
the *same* agent prompt on the *same* diff:

1. the inner fresh-eyes loop's guaranteed-Opus final round (`SKILL.md` clause 5);
2. the Opus outer review, primary; and
3. a second independent confirming Opus pass on the identical diff.

Worse, **any** fix invalidated prior clears and re-ran passes -- so one adopted
finding late in a cycle could cost three Opus passes, each of which tended to
surface another finding.

The maintainer reported the measured cost: **14 hours across 9 review cycles in a
single day**, with token burn quadrupled (never maxing a Max x5 subscription ->
always maxing a Max x20) while throughput slowed to a crawl. Sessions were being
consumed chasing nits and pre-existing journal errors rather than shipping.

The maintainer's framing, which set the direction: *"Opus should NOT be a drudge,
it's like the senior engineer... We are abusing Opus by making it do menial checks
that sonnet or Haiku could do cheaper and faster."* That is not a new principle
here -- [`planning.md`](../../doctrine/planning.md) already said expensive models
run at decision gates only and **never bug-hunt**. The three-pass flow violated the
repo's own tiering rule. This change enforces it.

## What shipped

Two beads, one PR. **3+ Opus passes -> 1.**

### bd polyglot-pdf-ofh6 -- collapse the passes

- **Deleted clause 5**, the guaranteed-Opus round of the INNER loop. The inner
  loop's `NO-GAPS` is now terminal at whatever model the diff-size router picked.
- **Deleted the second confirming outer pass.** One Opus `NO-GAPS` is the gate.
  Two runs of an identical prompt at an identical model on an identical diff are
  independent in *context* but not in *perspective* -- they share blind spots. The
  property that mattered (independence from the author's framing) is fully
  preserved by one pass.
- **Narrowed `ambiguous = blocker`** to the diff's OWN behavior. The old wording
  ("if you cannot confidently say this is purely cosmetic and changes no
  behavior") swallowed the entire nit category, because almost every finding has
  *some* conceivable edge. The test now asks *"am I unsure whether this diff
  behaves correctly?"*, not *"can I imagine any edge case anywhere?"*
- **Added the pre-existing test:** a finding that reproduces UNCHANGED on
  `origin/dev` is **filed as a bead, never fixed here**, regardless of severity.
  Checkable, not a judgment call (`git show origin/dev:<path>`).
- **Added the non-behavioral carve-out:** only a BEHAVIORAL fix voids a clear.
  Filing a bead, editing a comment, or writing a journal sentence no longer
  re-runs a heavy Opus pass. The fear of exactly that is what pushed reviewers to
  fix nits inline instead of filing them.
- The triage rule is stated **once** (Step 5.6) and cross-referenced from Step
  5.5, so the cheap loop stops chasing pre-existing findings too -- otherwise the
  churn simply moves one layer down.

### bd polyglot-pdf-0arm -- split the reviewer by job

Previously both layers spawned the SAME agent file with the SAME mandate, so Opus
re-hunted local bugs the cheap loop had already cleared.

- **New [`.claude/agents/cross-surface-reviewer.md`](../../../.claude/agents/cross-surface-reviewer.md)**
  (`model: opus`) owns the **blast radius**: it starts from the inner loop's
  `## Changed contracts` list and follows each contract OUT into consumers in
  untouched files. It is told explicitly that finding no local bug is not a
  failure.
- **[`fresh-eyes-reviewer.md`](../../../.claude/agents/fresh-eyes-reviewer.md)**
  keeps the local diff (rubric + in-diff bugs) and now **ENUMERATES** every changed
  contract instead of tracing it. *That single edit is what stops the two tiers
  doing the same work.*
- **Surface boundaries are POINTED AT, never inlined.** The outer prompt directs
  the reviewer to [`technical_guide.md`](../../technical_guide.md) and the relevant
  [`components/*.md`](../../components/). An inlined checklist would be a second
  copy that rots as the app evolves; the tracked doc is the single source of truth.
- Rejected: one agent file with two modes. Opus would load the full inner mandate
  and then be told to ignore it -- and models do not reliably ignore in-context
  instructions. That redundancy is precisely what was being paid for 3x. Splitting
  also makes the frontmatter `model:` honest (it said `sonnet` while every outer
  call overrode it) and removes the Haiku self-escalation clause from the outer
  path.

### The safeguard that was KEPT and hardened

bd `polyglot-pdf-dgoa` added three review-hardening safeguards after the bd
`polyglot-pdf-bo4m` regression. Two are superseded here. **The third -- the
trace-into-consumers mandate -- is retained and made STRICTER**: the outer reviewer
may not render `NO-GAPS` until it has traced every enumerated contract **and named
the consumer file(s) it opened**. Cutting passes did not weaken the gate: the trace
moved from one bullet among many in a shared general-purpose prompt to the *entire
stated purpose* of a dedicated agent, with the list-to-trace handed to it so it is
never left underived.

### Files the original plan missed

A repo-wide sweep caught four live references the initial edit list did not cover.
The important one: **[`.claude/prime-closeout-override.md`](../../../.claude/prime-closeout-override.md)
is injected into EVERY session by the `bd prime` SessionStart hook** -- leaving it
would have re-taught the retired three-pass flow at every startup, silently
undoing the change. Also the `pick_review_model.py` and `closeout_finish.py`
docstrings (both described deleted behavior -- and by this PR's own new rule, a
comment contradicting behavior is not a nit), and the `test_closeout_skill.py`
module docstring.

Resolved a pre-existing drift as a side effect: `planning.md`'s tiering table
assigned fresh-eyes to the Sonnet tier while later rules forced Opus. The table now
matches the flow.

### Deferred / filed, not fixed

- **bd polyglot-pdf-2j8w** -- 24 stale tier-2 docs. All verified PRE-EXISTING
  (this branch touches zero `backend/`/`frontend/`/`.github/` files; the stale
  stamps predate source commits already on `origin/dev` from PRs #545/#546). Filed
  rather than fixed, with a note that it needs per-surface decomposition and that
  `technical_guide.md` collides with bd `polyglot-pdf-n18q`.
- **bd polyglot-pdf-1bsx** (tier + work-class bead metadata), **n18q** (the surface-
  contract map), **wtte** (wiring it into closeout), **6a2n** (sweeping local memory
  of retired-flow claims) -- all filed, none in this PR.

## Lessons

- **A doc/prompt duplicated in two places will drift; point at the tracked copy
  instead.** The first draft of the outer reviewer inlined a hand-listed set of
  surface crossings from memory. Codifying a remembered list would have baked
  whatever was misremembered into every future review, and a *wrong* checklist is
  worse than a generic instruction because it reads as authoritative. Pointing at
  `technical_guide.md` (which the freshness gate already polices) makes the
  boundary list drift-proof by construction.
- **A self-certified freshness stamp is only as honest as the step that reviews
  it.** `check_doc_freshness.py` trusts each doc's `*Last updated:*` line by design
  (it must, or a same-sprint code+doc change false-flags). That is benign for
  env-var docs; it becomes dangerous the moment a doc carries contracts, because a
  date bump turns the gate green while shipping a stale map. Recorded in bd
  polyglot-pdf-wtte, which pairs a "review, don't re-stamp" rule with widening the
  `Tracks:` line so contract files actually trip the gate.
- **When cutting a safeguard, name which one you are keeping and why.** Two of the
  three bd dgoa safeguards were retired here. Stating in the doctrine *which*
  remains (the trace), *why* it is the load-bearing one (it caught bo4m), and *what
  compensates* for the removals (a hard gate + the enumeration handoff) keeps the
  next reader from re-litigating -- or from quietly restoring the cost.
- **Mutation-verify a replaced assertion in both directions.** Swapping a positive
  pin (`"two independent" in body`) for a negative one (`not in body`) can leave a
  test that passes for the wrong reason. Three mutations were run -- reinstating
  the retired phrase, neutralizing `behavioral`, and collapsing the outer agent
  path back to `fresh-eyes-reviewer.md` -- each reddening the intended test, then
  restored with a residue check.

## Doc freshness

- **Bumped/rewritten:** [`docs/doctrine/review-flow.md`](../../doctrine/review-flow.md)
  (dateline + flow diagram + the whole "why each choice" rationale set; the bd bo4m
  prose is preserved verbatim but re-headed to the OUTER reviewer and repointed at
  the new agent file) and [`docs/doctrine/planning.md`](../../doctrine/planning.md)
  (the stale tiering table + the Assess cross-reference).
- **Reviewed and deliberately LEFT:** the 24 STALE tier-2 docs the freshness
  checker flagged. Every one is pre-existing -- this branch changes no
  `backend/`, `frontend/`, or `.github/` file, so none was caused by it. Filed as
  bd **polyglot-pdf-2j8w** instead of expanding this diff, which is exactly the
  pre-existing rule this PR introduces, applied to itself.
- Neither doctrine doc carries a `**Tracks:**` line, so the freshness script does
  not police them -- worth noting as a gap in the gate's coverage (candidate for
  the docs audit, not filed here).

## Files touched

- `.claude/agents/cross-surface-reviewer.md` (**new**, `model: opus`)
- `.claude/agents/fresh-eyes-reviewer.md`
- `.claude/skills/closeout/SKILL.md`
- `.claude/prime-closeout-override.md`
- `CLAUDE.md`
- `docs/doctrine/review-flow.md`
- `docs/doctrine/planning.md`
- `scripts/pick_review_model.py` (docstring only -- no logic change; it already
  emitted only `haiku`/`sonnet`)
- `scripts/closeout_finish.py` (docstring only)
- `tests/test_closeout_skill.py`
