---
date: 2026-08-28
bead: polyglot-pdf-vuxco, polyglot-pdf-w85gd, polyglot-pdf-in8il
title: "docs: fix 3 named citation-drift beads, found 6 more of the same bug by sweeping the same files"
tags: [docs, ws-protocol, technical_guide]
---

## Trigger

Three independently-filed beads, each naming one drifted line citation in a
tier-2 doc (`docs/technical_guide.md` / `docs/standards/ws-protocol.md`),
all caused by the same root pattern this repo has hit before (`bd
polyglot-pdf-vdcm4`'s citation re-anchor sweep, `bd polyglot-pdf-0fbpa`'s
`webFormConnection.ts` re-verify): a code insertion above a cited line
shifts every citation below it, and nothing catches a citation that still
lands INSIDE the file (just on the wrong code) -- only `scripts/
check_doc_freshness.py`'s past-EOF/blank-line check, which cannot detect
this class of drift.

- `polyglot-pdf-vuxco`: `set_editor_kit_status`'s dump consumer misattributed
  to `widget_picker.py` (it actually feeds `schema_lint.py`'s `lint_schema`;
  a DIFFERENT `_load_kit_dump` call site feeds `widget_picker.py`).
- `polyglot-pdf-w85gd`: `schemaFormState.ts:999` cited for
  `getJITHandshakePayload`, which actually starts at `:1015`.
- `polyglot-pdf-in8il`: four `callback_handler.py` send-site citations
  (`form_updated`/`transcript`/`turn_complete`/`go_away`), all off by ~14
  lines from an earlier insertion.

Also closed during this same sweep as already-resolved (no diff needed):
`polyglot-pdf-ki32y` (the Firestore-sink `_firestore_write` vs.
`_submit_firestore_write` misattribution) -- fixed by an earlier PR (#659)
before this bead was picked up.

## Enumerate the set (CLAUDE.md scar tissue #7)

Fixing the three named citations, then grepping the SAME two files for every
other `schemaFormState.ts:[0-9]+` / `callback_handler.py:[0-9]+` citation
(rather than trusting the bead's own named line list) found six more that
were ALSO drifted, none named by any open bead:

- `technical_guide.md:343`: a second, separate `callback_handler.py:242`
  citation for the same `form_updated` send site `in8il` already named
  elsewhere in the same file.
- `technical_guide.md:291`: `full_schema`'s JIT send site cited at `:1054`,
  actually at `:1070`.
- `technical_guide.md:272`: `getJITHandshakePayload` cited at `:999` in a
  SECOND location (technical_guide.md, not just ws-protocol.md's `w85gd`
  row) -- actually `:1015`.
- `technical_guide.md:469`: `form_number`/`kit_id`/`edition_date`'s JIT send
  sites cited at `:1075`/`:1088`/`:1089` -- actually `:1091`/`:1104`/`:1105`.
- `ws-protocol.md:284-285`: `previous_spoken_names`/`form_title`'s JIT send
  sites cited at `:1090`/`:1068` -- actually `:1106`/`:1084`.

Every citation NOT re-verified by hand (only grepped for the string, not
checked against the real function/line) would have shipped this fix with
6 of 9 total drifted citations in these two files still wrong -- exactly
the "found one more per round" trap CLAUDE.md warns about, avoided here by
doing the full grep-and-verify pass before opening the PR rather than after
a reviewer found the next one.

## What shipped

All 9 drifted citations corrected, re-anchored to function/symbol names
(matching the convention `bd polyglot-pdf-vdcm4` established) rather than
raw line numbers where the surrounding prose already names the function.
Left the several dozen tier-3 (journal/audit) citations of the same files
untouched -- those are dated historical records, not current-state docs,
and are `bd polyglot-pdf-t1j5l`'s separate scope.

## Lessons

A bead naming ONE drifted citation in a file is a strong signal to grep that
WHOLE file for the same citation shape before fixing just the named
instance -- the same insertion event that drifted one citation typically
drifted several others nobody has filed a bead for yet.

## Files touched

- `docs/technical_guide.md` -- 6 citations re-anchored (2 already covered by
  named beads' scope, 4 found by the sweep).
- `docs/standards/ws-protocol.md` -- 3 citations re-anchored (1 named,
  2 found by the sweep).
