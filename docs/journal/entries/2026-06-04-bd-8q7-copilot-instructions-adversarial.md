---
date: 2026-06-04
bead: polyglot-pdf-8q7
title: "Tighten + sharpen .github/copilot-instructions.md (no-commit rule + adversarial review)"
tags: [review, harness, doctrine]
---

## Trigger

The maintainer caught GitHub Copilot's code-review bot **committing its own code
changes** to a PR instead of purely commenting. The standing
`.github/copilot-instructions.md` had only a single weak "Do NOT commit changes
yourself" line buried near the bottom, and -- separately -- gave Copilot **zero**
guidance on how to actually review. Two asks: (1) tighten the comment-only rule so
the bot stops editing the repo, and (2) make the review more adversarial, modeled
on this repo's `fresh-eyes-reviewer` agent, so Copilot hunts harder for bugs.

## What shipped

A full rewrite of `.github/copilot-instructions.md`, restructured into five
scannable sections ordered so the changed behavior is read first:

1. **One-line role frame** -- "REVIEW-ONLY, COMMENT-ONLY."
2. **Never commit (highest priority)** -- hoisted to the top and hardened from one
   line into an explicit enumerated prohibition (commit/push/rebase/merge/amend/any
   edit, not even a one-liner) plus a "STOP and write a comment instead"
   self-interrupt. Cross-references the Codex sibling rule in `AGENTS.md`.
3. **How to review -- hunt hard for bugs** (NEW) -- injects the fresh-eyes model:
   "pretend you have never seen this codebase"; read FULL files not just hunks; an
   explicit hunt list (logic bugs, broken assumptions, dead code, missing error
   paths, inconsistencies, misnamed things, comment/code contradictions,
   off-by-one/boundary); a hard look at external/metered/destructive side effects;
   "be specific with a how-to-verify, not vague"; don't flag pure style.
4. **Repo-specific high-value bug surfaces** (NEW) -- cp1252/non-ASCII crash (a
   correctness bug here, not style), server-side PII/PHI logging, google-genai
   wiring as high-risk, section-vs-part terminology.
5. **Signalling contract (compressed)** -- the verbose, 3x-repeated LGTM
   justification prose collapsed to one statement, with every load-bearing watcher
   signal preserved verbatim: exact `LGTM`, every-round top-level comment, assign
   `@caellwynai-josh` on `dev` findings, `main` = no-assign.

**The binding constraint** is GitHub's 4,000-char read cutoff for Copilot
code-review instruction files: anything past 4,000 chars is invisible to the
reviewer. The old file (2,436 chars) had room, but adding the no-commit hardening +
the adversarial section required compressing the signalling prose to fit. Final
file is **3,315 chars** (685 margin) and **0 non-ASCII bytes**. Compression was
verified safe against `scripts/pr_review_watcher.py`: `_is_exact_lgtm` (the exact
`LGTM` matcher) and the dev/main assign classification both survive, and the
watcher accepts `LGTM` from either a review body or an issue comment (Surface 3),
so the dropped surface-routing sentence cost nothing.

**Review verdict: review-skipped (fresh-eyes only).** The diff touches a single
non-executable config/prose file (`.github/copilot-instructions.md`) that cannot
introduce a runtime/logic regression, so per the closeout Step-6 gate Copilot was
not requested. Fresh-eyes ran regardless (it costs no Copilot credit).

**Fresh-eyes triage (Sonnet, one pass):**

- **Adopted (1):** fresh-eyes flagged that the rewrite dropped the old file's
  explicit "use a formal Approve review if the platform allows, else an issue
  comment" guidance, leaving Copilot pointed only at the issue-comment path. I
  first verified this was NOT a live blocker -- both the "Defend Dev" and "Defend
  Production" rulesets have `required_approving_review_count: 0`, so a bare `LGTM`
  issue comment already merges fine and the watcher reads either surface. But the
  Approve-review line is strictly-better future-proofing (if a ruleset ever
  requires a review) and cost ~120 chars against a 566-char budget, so I restored
  a compact version of it.
- **Acknowledged, no change (1):** fresh-eyes caught that this journal entry was
  uncommitted when it reviewed. That was timing, not a defect -- closeout commits
  the journal in Step 5, after the fresh-eyes pass; it ships in this PR.
- **Rejected (2):** (a) the "assign @caellwynai-josh" framing -- fresh-eyes noted
  the *watcher* never reads PR assignment. Correct, but the file's instruction
  ("assign so the follow-up agent picks it up") is accurate as written; only an
  overstatement in my draft PR framing, not a file defect. (b) "exact LGTM is
  stricter than `_is_exact_lgtm`" -- fresh-eyes itself recommended not flagging
  this; being stricter than the matcher is safe by design.
- **Deferred (0):** none.

## Lessons

- **Copilot custom-instruction files have a hard 4,000-char read cutoff** -- only
  the first 4,000 chars influence the review. Highest-priority instructions must
  come early AND the whole file must fit; verbose justification prose is the first
  thing to compress. (This is a GitHub platform limit, not a repo rule.)
- **The collision guard's "no surfaces declared" path conservatively collides with
  everything.** A freshly-created bead with no `metadata.surfaces` is treated as
  UNKNOWN and aborts the claim against any in-flight bead. The fix is to *declare
  the surface* (`bd update <id> --metadata '{"surfaces":[...]}'`), not to bypass
  with `--no-surface-check` -- declaring it both clears the false positive and
  records the real write target. (This was the PR #65/#64-class trap, dodged.)

## Doc freshness

- `.github/copilot-instructions.md` is the doc that changed (it is itself the
  artifact, not a tracked doc with a `**Tracks:**` line).
- The freshness checker flagged several `docs/components/*.md` and
  `docs/standards/*.md` as STALE (voice-ai, config-deployment, ai-models,
  hipaa-pii-policy, logging-and-cost, risk-rating, confirmation-and-audit,
  voice-and-vad). **All of these track `backend/` files** (live_ai_gemini.py,
  callback_handler.py) changed by OTHER work on `dev` on 2026-06-03. **This PR
  touches no backend files**, so per the closeout Step-2 rule they were already
  stale before this branch and are left untouched here.
- `AGENTS.md` (the Codex reviewer sibling) already carries the same comment-only
  rule, so it needed no change.

## Files touched

- `.github/copilot-instructions.md` -- full rewrite (no-commit hardening +
  adversarial review section + repo bug surfaces + compressed signalling contract).
