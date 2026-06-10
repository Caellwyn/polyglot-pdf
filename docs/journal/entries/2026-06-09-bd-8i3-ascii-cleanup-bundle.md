---
date: 2026-06-09
bead: polyglot-pdf-8i3
title: "ASCII-clean residual non-ASCII + fix stale closeout pytest note (8i3/xev/bm3/o1s)"
tags: [chore, ascii, docs, testing]
---

## Trigger

A cleanup pass bundling four cheap, individually-too-small beads that each
violate scar #6 (ASCII-only in code files, a cp1252 stdout-crash hazard on
Windows) or carry a stale doc note. None warrants its own PR cycle, so they
ship together.

- **8i3** (P2 bug): fresh-eyes (PR #128) flagged pre-existing emoji in
  `backend/services/form_filling_service.py` log f-strings.
- **xev** (P3): pre-Codex-cutover thumbs-up/light-bulb emoji in
  `scripts/pr_review_watcher.py` + its test.
- **bm3** (P3): pass-2 backend non-ASCII residual (test docstrings/comments).
- **o1s** (P3): the closeout SKILL.md pytest note went stale when the root
  `pytest.ini` landed (uov.1).

## What shipped

All changes are NON-BEHAVIORAL -- comments, docstrings, and log-event label
strings only; no control flow, no contracts.

- **8i3**: stripped 4 emoji (door/lock/cycle/check) + 2 em-dashes from log
  strings/comments in `form_filling_service.py` (L196, 362, 384, 404, 440, 455).
  All of `backend/services/` is now ASCII-clean.
- **xev**: stripped 13 cosmetic thumbs-up + 1 light-bulb emoji from
  comments/docstrings in `pr_review_watcher.py` + `tests/test_pr_review_watcher.py`.
  **One functional non-ASCII char was KEPT on purpose**: the curly apostrophe
  (U+2019) in the Codex clean-sentinel `"didn't find any major issues"` at
  `pr_review_watcher.py:270`. That literal is matched (via `p in lo`) against
  GitHub's RENDERED Codex comment, which emits the curly form. ASCII-ing it would
  regress clean-detection. The `xev` bead assumed only ~2 cosmetic emoji; the file
  actually had 14 non-ASCII lines, one of them load-bearing -- the bead
  under-scoped the file.
  - **Fresh-eyes catch (adopted):** the kept curly sentinel was NOT actually
    covered by a test -- every existing fixture used the straight apostrophe. So
    this PR ADDS `test_codex_clean_sentinel_matches_curly_apostrophe`, which pins
    the curly variant via `_is_approval_comment(..., CODEX)`. The test writes the
    curly char as a `’` escape so the test file itself stays ASCII while
    still exercising the non-ASCII match. (The pre-fix claim that "a test pins
    both variants" was wrong at the time written; this change makes it true.)
- **bm3**: stripped em-dashes (5 test files), a UTF-8 BOM at
  `test_live_ai_gemini.py:1`, and the check/cross/minus legend glyphs at
  `test_get_form_status_compact.py:8-10` (-> bracketed ASCII). All of
  `backend/tests/` is now ASCII-clean. Bead items (1) `config.py` and (2)
  `pdf_fill_routes.py` were ALREADY clean (cleaned by intervening PRs); no change
  needed there.
- **o1s**: reworded the `(NOT pytest tests/)` note in
  `.claude/skills/closeout/SKILL.md` -- since the root `pytest.ini` landed a bare
  `pytest` runs BOTH suites; the note now says `backend/tests/` is named for
  SPEED, not to exclude the harness suite.

## Doc-freshness triage

`closeout_prep` flagged 8 docs STALE (context-compression, ai-models,
hipaa-pii-policy, logging-and-cost, risk-rating, stateless-architecture,
voice-and-vad, and the form_filling_service-tracking stateless-architecture).
**All are false positives.** The freshness check is an mtime heuristic: it traced
the flags to `backend/adapters/live_ai_gemini.py` and `backend/ports/live_ai_port.py`,
neither of which this branch touches (their mtimes are earlier-today churn from
other work). The only source file this branch edits is `form_filling_service.py`,
and that edit is a cosmetic ASCII swap in log strings/comments -- it changes no
behavior, contract, or invariant any of those docs describe. No doc update is
warranted; this note IS the prescribed alternative to bumping each doc.

## Verification

- `py_compile` clean on every edited file.
- Full backend suite: 250 passed, 2 skipped, 3 deselected (external), 0 failures.
- `pr_review_watcher` suite: 120 passed -- confirms the kept curly-apostrophe
  sentinel and the emoji-stripped comments leave clean-detection intact.
- Final ASCII scan: `backend/services/` and `backend/tests/` fully clean;
  `pr_review_watcher.py` retains only the one deliberate U+2019 at L270.

Closes polyglot-pdf-8i3, polyglot-pdf-xev, polyglot-pdf-bm3, polyglot-pdf-o1s.
