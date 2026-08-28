---
date: 2026-08-27
bead: polyglot-pdf-vdcm4
title: "docs+test(freshness): re-anchor stale websocket_routes.py citations, catch blank-line citation drift"
tags: [doc-freshness]
---

## Trigger

Every `websocket_routes.py:<line>` / `confirmation_logger.py:<line>`
citation in `docs/standards/ws-protocol.md` and `docs/technical_guide.md`
had drifted -- the SAME doc drifting the SAME way a second time: bd
`polyglot-pdf-x82ii` fixed identical drift on 2026-08-17, and further code
motion in `websocket_routes.py` re-drifted every citation by 60-140 lines
since.

## What shipped

- Every drifted citation re-anchored to a symbol/arm name instead of a new
  line number -- immune to the "code inserted above it" drift that hit this
  doc twice.
- `check_code_citations()` (`scripts/check_doc_freshness.py`) extended to
  also flag a single-line citation landing on a blank line, not just
  past-EOF drift (bd `vdcm4`'s exit criterion 2's "or is blank" clause,
  previously unimplemented).
- Three more pre-existing blank-line citations the new checker surfaced
  were fixed in-flight; three more pre-existing, out-of-scope drift
  instances found along the way were filed as follow-up beads
  (`polyglot-pdf-vuxco`, `polyglot-pdf-x6dq1`, `polyglot-pdf-in8il`)
  rather than folded into this bead.

## Lessons

**A "fix the citations" bead is not done when the grep for the citation
SYNTAX comes back empty -- it needs a grep for every syntax a citation can
take.** Four review rounds each found a real gap my own prior sweep missed,
and the gaps came in two distinct shapes:

1. **Colon-only tunnel vision.** My first enumeration grepped
   `file\.py:[0-9]+` and declared victory once that pattern returned
   nothing -- but a WHOLE additional table of citations used prose syntax
   ("at line N", "(lines N-M)", no colon at all) and was invisible to that
   pattern. The fix: after any "citation fixed" claim, re-grep for every
   phrasing a human might have written, not just the one the tooling
   happens to parse.
2. **A duplicate-named symbol is not a durable anchor by itself.** Replacing
   a stale line number with a bare function/arm name (`watchdog_task`,
   `ping`, `stats`) is only an improvement if that name is unique in the
   file -- three review rounds caught disambiguation failures where the
   SAME name was reused across three different WebSocket handlers
   (`ws_echo`/`ws_audio`/`_handle_fill_session`). A symbol-name fix needs
   its own uniqueness check, the same way a line-number fix needs its own
   bounds check.

**Extending a mechanical checker mid-bead can surface debt from files you
never intended to touch -- fix it anyway, or ship a checker that immediately
breaks CI.** Adding blank-line detection to `check_code_citations()` found
a live blank-line citation in a completely unrelated doc
(`validation-delegation.md`, citing `backend/config.py`). Leaving it
unfixed would have meant the new checker shipped already red on `dev`. The
narrow fix (re-anchor the one citation) was made without touching that
doc's own deliberately-frozen `*Last updated*` stamp -- a prior bead had
explicitly left that stamp stale because the doc needs a FULL content
re-verification, not a drive-by citation fix, and bumping the stamp here
would have silently cleared a real signal.

## Files touched

- `docs/standards/ws-protocol.md` -- citations re-anchored, stamp bumped
- `docs/technical_guide.md` -- citations re-anchored, stamp bumped
- `docs/standards/validation-delegation.md` -- one citation fixed, stamp
  deliberately left frozen
- `scripts/check_doc_freshness.py` -- blank-line detection added to
  `check_code_citations()`
- `tests/test_doc_freshness.py` -- two new mutation-verified tests
