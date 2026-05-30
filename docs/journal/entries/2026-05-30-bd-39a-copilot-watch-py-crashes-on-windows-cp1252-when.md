---
date: 2026-05-30
bead: polyglot-pdf-39a
title: "Quick wins: fix copilot_watch Windows crash + drop deprecated gemini-2.5-pro ref"
tags: [hotfix, conventions]
---

## Trigger

Bundled two low-risk quick wins into one PR (per maintainer request):

- **`polyglot-pdf-39a`** (P2 bug) — `scripts/copilot_watch.py` crashed with
  `UnicodeEncodeError` on Windows whenever a Copilot review body contained an
  emoji (observed `💡`, U+1F4A1). It crashed in `_emit`'s `print(detail)` *after*
  already classifying the verdict, so the caller saw a bogus `RESULT: ERROR`.
  Found live this session while running the watcher on PR #12/#13.
- **`polyglot-pdf-252`** (P3 chore) — `backend/config.py` had a fully
  commented-out LLM-normalizer block naming `gemini-2.5-pro` (on the June-2026
  deprecation track). The normalizer has no adapter and is deprecated.

## What shipped

**`scripts/copilot_watch.py`** — root cause: Windows default stdout is cp1252.
Two layers of defense:
1. At module load, reconfigure `sys.stdout`/`sys.stderr` to `utf-8` with
   `errors="replace"` (guarded for streams that reject `reconfigure`). Fixes
   *every* print in the script, not just the one that crashed.
2. New `_safe_print()` wraps `print()` and, on `UnicodeEncodeError`, re-encodes
   through the stream's own codec with `errors="replace"` — so even if the
   reconfigure failed (detached/redirected stream), the `RESULT:` contract line
   is always emitted. `_emit` now routes through `_safe_print`.

Verified end-to-end: re-ran the watcher against PR #13 (whose Copilot comment
contained the `💡` that crashed it before) — it now runs to a clean terminal
verdict instead of dying. Note: that run classified a *later* re-review of #13 as
`ERROR` ("Copilot encountered an error"), which is the correct classification of
a real Copilot error event — and the whole point is the watcher reported it
instead of crashing. (#13 itself merged fine on its earlier LGTM.)

**`backend/config.py`** — removed the dead commented normalizer block and the
now-meaningless module-level "(LLM normalizer settings live on Settings...)"
note, replacing the block with a one-line removal marker. No live reference to a
deprecated model remains (grep-confirmed).

**Tests** — `tests/test_copilot_watch.py`: added `test_emit_does_not_crash_on_
emoji_detail` and `test_safe_print_handles_unencodable_via_fallback`. Suite: 137
passed (was 135).

## Lessons

- **Any agent-facing script that prints third-party text on Windows must force
  UTF-8 stdout.** cp1252 is the default and third-party content (reviews, commit
  messages, API bodies) routinely carries emoji/CJK. The failure is nasty
  because it crashes *after* the real work, masquerading as a different error
  (here, a false `ERROR` verdict). Reconfigure-at-startup + a print wrapper is
  the belt-and-suspenders pattern. Candidate for a `docs/standards/` rule once
  that doc system exists.

## Doc freshness

`check_doc_freshness.py`: "No docs to check" (components/ + standards/ empty
skeleton). Nothing to bump.

## Files touched

- `scripts/copilot_watch.py` — UTF-8 stdout reconfigure + `_safe_print` fallback; `_emit` routes through it.
- `tests/test_copilot_watch.py` — two regression tests for the emoji/encoding crash.
- `backend/config.py` — removed dead `gemini-2.5-pro` normalizer block + stale module comment.
- `docs/journal/entries/2026-05-30-bd-39a-copilot-watch-py-crashes-on-windows-cp1252-when.md` — this entry.
