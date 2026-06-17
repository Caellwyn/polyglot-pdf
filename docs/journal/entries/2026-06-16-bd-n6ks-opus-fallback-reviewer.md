---
date: 2026-06-16
bead: polyglot-pdf-n6ks
title: "Opus-4.8 fallback reviewer when Codex is unavailable"
tags: [closeout, review-flow, pr_review_watcher, fresh-eyes, codex-fallback]
---

# polyglot-pdf-n6ks -- Opus-4.8 fallback reviewer when Codex is unavailable

## What changed

The closeout outer-review loop previously stalled when Codex was unavailable --
either posting "You have reached your Codex usage limits" (ERROR exit 1) or timing
out after the full 20-minute verdict window (TIMEOUT exit 2). Both dead-ended at
"surface to the maintainer," leaving the PR blocked.

This bead adds a three-part fix:

**1. `pr_review_watcher.py` -- acknowledgment phase + NO-ACK state (exit 4)**

New `--ack-timeout-min` flag (default 0 = disabled). When set, the watcher runs a
pre-verdict acknowledgment phase: it polls the Codex trigger comment for an `eyes`
(eyeballs) reaction -- the signal Codex adds when it picks up the work -- before
entering the normal verdict wait. If the `eyes` reaction does not appear within the
window (and no other in-window Codex activity confirms it's working), the watcher
emits `NO-ACK` (exit 4). A quota body during the ack window still routes to ERROR
(exit 1). `--ack-timeout-min 0` (default) is a strict no-op: the ack phase is
entirely skipped, leaving all existing callers and tests unchanged.

New helpers: `_has_ack_reaction`, `_trigger_comment_acked`, `_bot_posted_error_body`,
`_reviewer_has_activity`, `_ack_phase`. The `ReviewerProfile` dataclass gained an
`ack_reaction` field (None for Copilot, "eyes" for Codex). `_EXIT_CODES` updated
to include `"NO-ACK": 4`.

The module docstring now documents NO-ACK in the terminal-state list and exit-code
summary (gap found by fresh-eyes round 1). The `--close-on-clean` help text now
enumerates NO-ACK as a non-firing state (same gap).

**2. `.claude/skills/closeout/SKILL.md` -- Step 7.5 fallback reviewer**

- Hard-rules block updated: "handle all five states; ERROR/TIMEOUT/NO-ACK route to
  Step 7.5 fallback instead of dead-ending at the maintainer."
- Step 6.2 round-1 watch command does NOT carry `--ack-timeout-min` -- round 1's
  trigger is the PR body, not an issue comment, so the eyes reaction is
  unobservable and the ack phase is disabled for round 1. NO-ACK (exit 4) cannot
  occur on round 1.
- Step 7 re-watch command (round 2+) carries `--ack-timeout-min 2`: the trigger is
  an explicit `@codex review` issue comment, so Codex can react to it with eyeballs
  and the ack phase is meaningful. (Originally the re-watch used ambiguous `[...]`
  shorthand -- made explicit by fresh-eyes round 1.)
- New Step 7.5 -- Opus-4.8 fallback reviewer: spawn `fresh-eyes-reviewer` agent
  with `model: opus`, pass bead exit criteria + post-PR diff; loop to NO-GAPS
  (ceiling MAX_FALLBACK_ROUNDS=2); NO-GAPS -> close bead by hand (`bd_safe.py
  close`) and go to Step 8; GAPS-FOUND -> fix + re-spawn; BLOCKED/TIMEOUT/ERROR
  -> surface to maintainer (a subagent failure on the last-resort reviewer is a
  genuine stop).
- Step 8.1/8.2: fallback CLEAN path added to the close-by-hand cases; merge ping
  notes when review went via Opus-4.8 fallback.

**3. Doctrine + agent docs**

- `docs/doctrine/review-flow.md`: flow diagram updated with ack-window note and
  Codex-unavailable -> fallback branch; "no-Codex fallback" bullet replaced with
  active Opus fallback description; two new "Why each choice" bullets added
  (eyeballs ack signal; Opus-4.8 reviewer of last resort with full Codex authority).
- `.claude/agents/fresh-eyes-reviewer.md`: one paragraph added noting it may also
  be spawned post-PR as Opus reviewer-of-last-resort when Codex is unavailable
  (mandate identical, model and timing differ).

## Exit criteria scorecard (fresh-eyes round 2, NO-GAPS)

1. PASS -- `_ack_phase` emits NO-ACK (exit 4) on deadline; proceeds to verdict on
   ack; routes quota body to ERROR; `--ack-timeout-min 0` is a strict no-op.
   All four branches covered by named tests (134 passing, 0 failures).
2. PASS -- SKILL.md Step 7.5 with MAX_FALLBACK_ROUNDS=2, manual close on NO-GAPS,
   and fallback-noted merge ping; Step 7 re-watch carries `--ack-timeout-min 2`
   (round 2+); Step 6.2 round-1 watch omits it (PR-body trigger, no ack phase).
3. PASS -- `should_close` gates on CLEAN (with `_LAST_CLEAN_WAS_REVIEW`) or MERGED
   only; NO-ACK satisfies neither; `test_no_ack_does_not_close_beads` verifies
   end-to-end through `main()`.

## Pre-PR assess loop

- Round 1 (Sonnet fresh-eyes): GAPS-FOUND (2 high-confidence, 1 medium-confidence).
  All three adopted: docstring + help text updated; SKILL.md re-watch command made
  explicit.
- Round 2 (Sonnet fresh-eyes): NO-GAPS. Rubric all-PASS.

## Stale docs note

`closeout_prep.py` flagged 8 tier-2 docs as stale due to source files updated
2026-06-15 by prior PRs (#218, #216). None of those files are within this bead's
surfaces. Not updated here; pre-existing staleness from other beads.

## Stale beads note

`polyglot-pdf-hrn` (4d) and `polyglot-pdf-jf6w` (3d) flagged as stale. Both are
ongoing multi-bead epics; neither is blocked by this bead. Left as-is.

## End-to-end verification note

Live end-to-end (real Codex outage triggering the Opus fallback) is not cheaply
runnable. Test coverage + SKILL.md read-through are the verification surface for
this bead. The SKILL.md Step 7.5 will be exercised autonomously on the next genuine
Codex unavailability.
