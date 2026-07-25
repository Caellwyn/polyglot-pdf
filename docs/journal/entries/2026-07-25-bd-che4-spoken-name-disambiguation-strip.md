---
date: 2026-07-25
bead: polyglot-pdf-che4
title: "Strip extraction disambiguation counters off voice-facing spoken_names"
tags: [extractor, conventions]
---

## Trigger

Found during bd tupu.2 live verification (2026-07-23): the i-90's two Alien
Registration Number fields carry spoken_names "alien registration number 1"
/ "... 2" -- the LLM extractor's disambiguation counter for two boxes whose
PDF name is identical. The voice model reads the stray digit aloud, and now
(spoken_names are translated) in every language.

Maintainer reframing (2026-07-25, memory
`spoken-name-is-voice-facing-no-disambiguation`) settled the fix direction:
spoken_name is VOICE-MODEL-facing, and that model -- by context-management
design -- sees only the CURRENT field. It does not know an a-number 2
exists, so the trailing "1" conveys nothing; disambiguation that a
multi-field model (the secretary) needs belongs in help.instructions, not
the spoken name. So che4 is simply REMOVE the counter (duplicate
spoken_names are fine -- the voice model never sees two at once); relocating
disambiguation into instructions waits for the instructions-improvement work.

## What shipped

- **`schema_repair._strip_spoken_name_disambiguation`** (new deterministic,
  idempotent pass, wired into `repair()` beside `_migrate_top_level_required`
  -- both independent of the slug/condition machinery). It strips a bare
  trailing integer from a spoken_name ONLY when it belongs to a CLUSTER: two
  or more fields whose spoken_names share the same base and differ only by
  that trailing integer. So the i-90 alien-number pair is stripped, while a
  SEMANTIC trailing number that no sibling disambiguates is spared -- proven
  against the real f1040 cases: "Line 12d you born before 1961" (a year, and
  lone), "Filed pursuant to 301.9100-2" (a regulation cite the space-
  delimited pattern never even matches). This makes the fix an
  extraction-time GUARD too: a new form with the same duplicate-name shape is
  normalized automatically (the pass runs at extraction step 4 and via the
  editor Repair-all).
- **i-90 kit data fixed through the pass**: both fields' spoken_names became
  "alien registration number"; their now-stale suffixed translations were
  cleared and re-baked (17 languages, live ~$0.10, all verified clean). A
  full before/after field diff confirms the repair touched ONLY those two
  fields (nothing else in the shipped kit moved -- it was already
  normalized).
- **Stale-translation hardening** (fresh-eyes on this bead): the pass also
  DROPS a stripped field's now-stale `spoken_name_translations` (the digit
  rode the translation too), so a repair-only caller with no bake step can
  never ship a digit-bearing translation -- the re-bake refills them, and
  absent a re-bake the runtime live-translates. Idempotent on the shipped
  i-90 (cluster already gone -> no strip -> 17 translations preserved).
- Tests: 6 pins (cluster strip, semantic-number spared, lone-counter spared,
  idempotency, stale-translation clear, untouched-field translations kept).
  Full backend + scripts suites green; i-90 translation lint sweep 0.
- Fresh-eyes triage: Opus round 1 NO-GAPS with one low-confidence note (the
  repair/re-bake coupling was unenforced) -- ADOPTED as the hardening above,
  turning a documented caller-obligation into an automatic guarantee.

## Lessons

- "Fix the data" and "guard at extraction" are the SAME fix when the guard is
  a deterministic idempotent repair pass: applying `repair()` to the shipped
  kit both cleans the data AND is the mechanism that prevents recurrence, and
  the before/after diff is the proof the pass is surgical.
- The cluster requirement (a sibling must share the base) is what makes
  digit-stripping safe -- it distinguishes a bookkeeping counter from a
  semantic number without a hand-maintained allowlist.

## Verification note

The bead's "a scripted run's greeting asks without the stray digit" was
satisfied by data proof rather than a live voice-harness run: the greeting
reads `spoken_name` verbatim (no transformation between the kit value and
what is spoken), and the kit now carries no trailing digit in the
spoken_name or any of its 34 translations (asserted directly). A live
harness run would exercise the unchanged greeting-render path, not this
change.

## Doc freshness

- No tier-1/tier-2 doc tracks `schema_repair.py` or the spoken-name suffix
  behavior; the new pass is documented in its own docstring. Reviewed, left.

## Files touched

- `backend/services/schema_repair.py` -- _strip_spoken_name_disambiguation + wiring + `import re`
- `form-kits/i-90/schema.json` -- 2 spoken_names stripped + their translations re-baked
- `tests/test_schema_repair.py` -- 4 pins
