---
date: 2026-09-01
bead: polyglot-pdf-m63hv
title: "docs(confirmation-and-audit): 'THREE cases' undercounts a four-item list"
tags: [docs]
---

## What was wrong

`docs/standards/confirmation-and-audit.md:168` said
`kit_has_confirmation_records` "still raises rather than returning False
in THREE cases", introducing a numbered list at lines 171-188 that
actually has FOUR items: sink disabled, query failed, a record with
`kit_id` stored as null, and a LEGACY record that omits `kit_id`
entirely. The code agrees with the list, not the count: verified four
`raise ConfirmationCheckUnavailable` sites in
`backend/utils/confirmation_logger.py` (lines 980, 1026, 1047, 1060).

Pre-existing (not introduced by bd `polyglot-pdf-6zhaf`, whose docs
commit rewrote the surrounding paragraph and carried the stale count
forward verbatim without noticing item 4 had already been appended by an
earlier bead).

## Fix

Changed "THREE cases" to "FOUR cases". Left the nearby, unrelated,
CORRECT count at line 200 ("Three checks, and the first two are
EXHAUSTIVE") untouched -- it counts Firestore QUERIES, a different
subject, and is accurate. Also checked the file's other two count words
("Three parts", "Three, in rising order of size") -- both correctly
count their own lists (3 items each); out of this bead's scope regardless.

## Testing

Docs-only, single-word change. `scripts/check_doc_freshness.py`'s
code-citation check stays clean.
