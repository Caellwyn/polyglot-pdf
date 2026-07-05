---
date: 2026-07-05
bead: polyglot-pdf-dgoa
title: "Harden fresh-eyes review: trace-consumers rule + Opus final round + two-reviewer Codex-down gate"
tags: [doctrine, review]
---

## Trigger

Maintainer-directed, same session as the fine-print fix (bd polyglot-pdf-bo4m).
That fix, as first written, shipped a cross-file interaction regression: it
appended a note after the `(field_id: ...)` marker in a voice hint, which broke
an UNTOUCHED backend stripper (`field_utils.py`, end-anchored on that marker
being last), re-exposing the dx7 "reads field IDs aloud" bug on every
note-bearing field. TWO Sonnet fresh-eyes rounds cleared it `NO-GAPS`; only the
stronger outer review (Opus, standing in because Codex was quota-exhausted)
caught it. The maintainer asked: we should always have exhaustive fresh-eyes
until no issues -- what safeguards do we add? They selected all three below.

The miss was NOT "too few rounds" -- more Sonnet rounds reading the same diff
would have kept returning `NO-GAPS`. It was (a) reviewer scope (the broken code
was in a file the diff never touched, invisible to a hunk reader) and (b)
reviewer capability + the single-point fallback. The three safeguards target
exactly those.

## What shipped (three safeguards, all doctrine/process -- no app code)

1. **Trace-consumers rule** (`.claude/agents/fresh-eyes-reviewer.md`, "What to
   look for"). The reviewer mandate now REQUIRES, for every changed
   string/format/wire-shape/signature/contract, grepping for its consumers
   (which are NOT in the diff), opening those files, and confirming each still
   works against the new shape -- BEFORE rendering `NO-GAPS`. The bo4m regression
   is cited inline as the motivating class. A "the changed lines look correct"
   pass that skipped the trace is defined as INCOMPLETE.

2. **Opus final round** (closeout Step 5.5.b, new loop-stop clause 5). The
   diff-size router (`pick_review_model.py`) still routes EARLIER rounds cheaply
   (haiku/sonnet) -- unchanged, so the A/B cost accounting for early rounds
   stands. But a `NO-GAPS` is terminal only when the clearing round ran on
   **Opus**: if the clearing round was haiku/sonnet, re-spawn the same reviewer
   at `model: opus` on the unchanged diff and require ITS verdict to be
   `NO-GAPS`. One guaranteed strong-tier pass at the end. (No extra pass when the
   diff already routed to Opus or `CLAUDE_CODE_SUBAGENT_MODEL` forces it.)

3. **Two-reviewer Codex-down gate** (closeout Step 7.5). When Codex is
   unavailable (ERROR/TIMEOUT/NO-ACK) the Opus fallback is the ONLY adversarial
   gate, so one pass is a single point of failure -- the exact path PR #312
   relied on. The gate is now met only when TWO independent reviews (the primary
   looped Opus review + a second independent confirming review -- fresh Opus, or
   fresh Sonnet if a second Opus is unavailable) BOTH return `NO-GAPS` on the
   IDENTICAL final diff. A fix found by either invalidates both clears and
   re-runs both. The merge ping records that two reviews cleared it + names the
   second reviewer's model.

Doctrine (`docs/doctrine/review-flow.md`) updated to current state: flow
diagram, three "Why each choice" rationale bullets, the Assess-layer fallback
bullet (was "ONE looped Opus"), and the fresh-eyes-specifics summary. Tier-1
`CLAUDE.md`'s auto-merge gate description updated (the Codex-down clear now
requires two reviews; the final fresh-eyes round runs on Opus).

## Design decisions I made (and why they're mine, not escalations)

- **The Opus final round is an ORCHESTRATION rule, not a `pick_review_model.py`
  change.** The picker's contract is "diff size in, model name out" for the
  routed rounds; forcing the last round to Opus is a loop-stop property the
  closeout loop enforces, so the picker stays a pure zero-token router and the
  A/B arm-B experiment on early rounds is undisturbed. Editing the picker to
  emit "opus on the last round" would have coupled a stateless size-router to
  loop state it doesn't have.
- **The second Codex-down reviewer defaults to a fresh Opus, Sonnet only as a
  fallback-to-the-fallback.** Two Opus passes is the strongest available
  independent check; Sonnet is allowed only when a second Opus can't be spawned,
  so the gate never stalls. Independence (a fresh spawn, no shared context) is
  the load-bearing property, not the tier.
- **One bead, one PR for all three.** They are one coherent change to the same
  review flow; splitting would triple the review overhead for tightly-coupled
  doctrine edits. (Confirmed with the maintainer.)

## Doc freshness

- **Bumped:** `docs/doctrine/review-flow.md` (the doc these safeguards live in;
  `*Last updated:*` -> 2026-07-05 with the three changes summarized).
- **Updated (tier-1):** `CLAUDE.md` auto-merge gate description.
- **Left as-is:** `docs/journal/telemetry/FINAL_REPORT.md` -- a point-in-time
  telemetry archive of a past experiment, not current-state doctrine; retconning
  it would falsify the historical record.

## Files touched

- `.claude/agents/fresh-eyes-reviewer.md` -- trace-consumers mandate.
- `.claude/skills/closeout/SKILL.md` -- Step 5.5.b Opus-final-round clause;
  Step 7.5 two-reviewer gate + the reworked `NO-GAPS` branch.
- `docs/doctrine/review-flow.md` -- current-state doctrine + rationale.
- `CLAUDE.md` -- tier-1 auto-merge gate description.
- `docs/journal/entries/2026-07-05-bd-dgoa-fresh-eyes-hardening.md` -- this entry.
