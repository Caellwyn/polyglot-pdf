---
date: 2026-06-09
bead: polyglot-pdf-pjd1
title: "fix(watcher): Codex <details> footer breaks clean-signal classification"
tags: [harness, review, testing]
---

## Trigger

On PR #133 (bd 8k8) Codex's round-3 re-review was genuinely clean -- "Codex
Review: Didn't find any major issues. Hooray!" -- but `pr_review_watcher.py`
classified it COMMENTS, so the deterministic `--close-on-clean` never fired and
the bead had to be closed by hand. The maintainer asked for a deterministic
clean signal the watcher reliably recognizes (e.g. `LGTM`), so a clean Codex
round is never misread again.

## What shipped

**Root cause (verified against the live PR #133 payload):** Codex's clean comment
carries an auto-appended "About Codex in GitHub" `<details>` footer that the
GitHub app adds -- the reviewer agent does not control it. That footer broke
clean detection two ways: (a) it is multi-paragraph and >200 chars, so it
defeated the approval-SHAPE gate (`_is_approval_shaped`) and the "no major
issues" clean sentinel never rode to CLEAN; and (b) its prose ("If Codex has
suggestions...") contains a change-ask trigger word, so it tripped
`_has_change_ask` and the round read as COMMENTS. The 👍 reaction path saves it
when present, but Codex did not add the reaction that round.

**Fix (mirrors the existing `_strip_quotes` precedent):**
- `_strip_details_footer` removes `<details>...</details>` blocks before every
  prose heuristic -- applied in `_is_approval_comment` (internally), the
  issue-comment-round prose, `_extract_findings` Surface-3's change-ask gate, and
  the review-body change-ask gate.
- `_has_leading_lgtm` recognizes a deterministic `LGTM` lead line even when a
  human-readable summary follows it (the whole-body `_is_exact_lgtm` rejected
  that case). It is gated in `_is_approval_comment` on the absence of a change-ask,
  so `LGTM, but please fix X` cannot ride to CLEAN.
- `AGENTS.md` now instructs Codex to lead a clean summary with the `LGTM` token
  (plus the canonical 👍), and documents the footer-strip caveat.

**Tests (red-first):** a repro of the exact PR #133 round-3 body (footer + no
reaction) now classifies CLEAN end-to-end through `watch()`; false-CLEAN guards
cover a real change-ask in visible prose and the `LGTM, but...` case. 116 watcher
tests pass (110 prior + 6 new).

Fresh-eyes triage: recorded in the merge ping (this entry predates the review
rounds).

## Lessons

- **Pin clean detection to a structural signal, not free prose.** The Codex
  prose ("Hooray!", footer text) is unbounded NL the watcher can't chase
  word-by-word -- the durable fix is stripping the known boilerplate block and
  recognizing a fixed lead token, the same discipline `_is_exact_lgtm` /
  `_strip_quotes` already use. Generalizes to any bot whose host wraps comments
  in boilerplate. (Recorded in the local memory `copilot-watch-classify-by-inline-findings`.)
- **A deterministic-token instruction must match what the matcher accepts.** The
  first draft told Codex to "lead with LGTM, summary can follow," but
  `_is_exact_lgtm` required the *whole* body to be LGTM -- so the watcher had to
  grow `_has_leading_lgtm` for the instruction to be honored. Verify the
  instruction against the code before shipping the doc.

## Doc freshness

`check_doc_freshness.py` reported all tracked docs fresh. `AGENTS.md` (the Codex
context file) was edited in this PR as part of the fix, not as a freshness bump.
No tier-1/tier-2 docs track `scripts/pr_review_watcher.py`.

## Files touched

- `scripts/pr_review_watcher.py` -- `_strip_details_footer` + `_has_leading_lgtm`;
  applied at all four classification surfaces.
- `tests/test_pr_review_watcher.py` -- 6 new tests (footer strip, leading-LGTM,
  end-to-end repro, false-CLEAN guards).
- `AGENTS.md` -- review section: lead clean summaries with `LGTM`; footer caveat.
