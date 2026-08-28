---
date: 2026-08-27
bead: polyglot-pdf-29uf2
title: "docs(pdf-filling): repair 26 mojibake sequences in docs/components/pdf-filling.md"
tags: [doc-freshness]
---

## Trigger

`docs/components/pdf-filling.md` contained 17 occurrences of a UTF-8
em-dash double-encoded through cp1252, rendering as a garbled
three-character run instead of an em-dash. 16 were pre-existing; a 17th
was added by a since-merged PR matching the surrounding, already-corrupt
style.

## What shipped

All 17 em-dash mojibake instances replaced with plain ASCII ` --`,
matching the file's existing separator style. While enumerating the set
(a broadened byte-level scan, not just the one named sequence), found a
SECOND, distinct mojibake pattern: 9 occurrences of a double-encoded
rightwards arrow, fixed the same way with ` ->`.

## Lessons

**"Fix the 17 named instances" and "fix every instance of this defect
class" are different tasks -- do the second one even when only the first
was asked for.** The bead named one specific byte sequence and one count.
A narrow scan for exactly that sequence would have left the file with a
second, unrelated-looking corruption right next to the fixed text. The
bead's own instruction ("the whole file should be checked for other
double-encoded runs") anticipated this; a byte-level scan for the general
double-encoding SIGNATURE (not just the one reported sequence) is what
actually finds a defect's siblings, the same enumerate-before-fixing
discipline this repo applies to prose claims and citations.

**A byte-for-byte reconstruction is a stronger verification than spot-
checking, and it's cheap for a mechanical fix.** Rather than sampling a
few of the 26 fixed sites, reconstructing the base file's mojibake with
the same replacement rule and diffing the result against the working
copy proves the ENTIRE file changed only in the intended way -- no
missed site, no accidental wording change, no spacing artifact anywhere,
not just at the sampled locations.

## Files touched

- `docs/components/pdf-filling.md` -- 26 mojibake sequences repaired
