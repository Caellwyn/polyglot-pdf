---
date: 2026-08-27
bead: polyglot-pdf-98dsq
title: "docs(request_coordinator): request_spellback docstring no longer claims the model stays parked"
tags: [voice, spellback]
---

## Trigger

`request_spellback()`'s docstring claimed the model stays parked and
generates nothing while its tool response is held open for spell-back
playback. bd `polyglot-pdf-kvrfq` wire-verified this false on 2026-08-26:
under user barge-in pressure the native-audio model keeps emitting further
`name_spellback` calls while earlier ones are unanswered, and those queue
behind the backend's blocked receive loop. `kvrfq` corrected the
equivalent claim in `docs/components/voice-ai.md` and
`docs/standards/voice-and-vad.md`, but this backend docstring in an
untouched file still asserted the refuted design assumption.

## What shipped

- `request_spellback()`'s docstring rewritten to state the wire-verified
  queueing behavior, pointing at `voice-ai.md`'s `name_spellback` bullet
  for the full explanation.
- `test_spellback_tool.py`'s module docstring, found to make the same
  claim while enumerating the set, fixed the same way.
- Two more live instances found during review (`callback_handler.py`,
  `audioSpellbackHold.test.ts`) filed as bd `polyglot-pdf-u83oe` rather
  than folded in here.

## Lessons

**A wire-verified correction to one doc doesn't correct every restatement
of the same claim.** `kvrfq` fixed the primary docs (`voice-ai.md`,
`voice-and-vad.md`) but a docstring in a completely different, untouched
file kept asserting the old design assumption -- and grepping for the
claim's exact phrasing surfaced two MORE live instances beyond the one
this bead named. A design correction needs the same set-enumeration
discipline as any other repeated fact (CLAUDE.md scar #7): grep for the
refuted claim's phrasing across the whole tree, not just the file the
bead names.

## Files touched

- `backend/services/request_coordinator.py` -- docstring corrected
- `backend/tests/unit/test_spellback_tool.py` -- module docstring corrected
