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
  One functional non-ASCII value remains in play: the curly apostrophe (U+2019) in
  the Codex clean-sentinel `"didn't find any major issues"` at
  `pr_review_watcher.py:270`. That sentinel is matched (via `p in lo`) against
  GitHub's RENDERED Codex comment, which emits the curly form -- so the matched
  VALUE must stay curly. The `xev` bead assumed only ~2 cosmetic emoji; the file
  actually had 14 non-ASCII lines, one of them load-bearing -- the bead
  under-scoped the file.
  - **My first attempt got the fix half-right, and review corrected it.** I
    initially KEPT a literal U+2019 in the source, reasoning "load-bearing -> must
    stay non-ASCII." That conflated *the matched value must be curly* with *the
    source byte must be non-ASCII*. A Python `’` escape produces a
    byte-identical runtime value while keeping the source ASCII -- so the literal
    was never necessary.
  - **Fresh-eyes (round 1)** caught that the curly sentinel had NO test coverage
    (every fixture used the straight apostrophe). Adopted: this PR adds
    `test_codex_clean_sentinel_matches_curly_apostrophe`, pinning the curly variant
    via `_is_approval_comment(..., CODEX)`, with the curly char written as a
    `’` escape so the test file stays ASCII.
  - **Codex (round 2)** then flagged that the SOURCE literal at L270 still violated
    scar #6 and could be escaped the same way. Adopted: L270 is now
    `"didn’t find any major issues"` (escape), so `pr_review_watcher.py`
    is fully ASCII with the runtime match unchanged. Net result: ZERO non-ASCII in
    any code file; the curly match is preserved purely via escapes and pinned by a
    test.
- **bm3**: stripped em-dashes (5 test files), a UTF-8 BOM at
  `test_live_ai_gemini.py:1`, and the check/cross/minus legend glyphs in the
  `test_get_form_status_compact.py` module docstring. (Codex round 2 noted the
  first ASCII rendering -- `[confirmed]`/`[unconfirmed]` brackets -- could read as
  literal wire tokens; reworded to name the real wire values `"confirmed"` /
  `"unconfirmed"` and to state that empty fields are omitted entirely.) All of
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
- `pr_review_watcher` suite: 121 passed (was 120; the +1 is the new
  curly-apostrophe sentinel test) -- confirms the sentinel and the emoji-stripped
  comments leave clean-detection intact.
- Final ASCII scan: ALL edited code files are now fully ASCII, including
  `pr_review_watcher.py`. (Round 2: Codex correctly flagged that keeping a literal
  U+2019 at L270 still violated scar #6; the curly char is now written as a
  `’` escape, which yields a byte-identical runtime VALUE while keeping
  the source ASCII. So the earlier "one deliberate non-ASCII char remains" framing
  no longer applies -- there is zero non-ASCII left.)

Closes polyglot-pdf-8i3, polyglot-pdf-xev, polyglot-pdf-bm3, polyglot-pdf-o1s.
