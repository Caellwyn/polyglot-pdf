---
date: 2026-08-12
bead: polyglot-pdf-amojb
title: "Bug-hunt round 3: sibling provenance, date-string bound coercion, spell-back token leak, sweep ordering, duplicate group option"
sprint: null
tags: [testing, conventions]
---

## Trigger

Third maintainer-requested bug-hunt roundup (round 1: bd oqqxj/ioe8d, 5xhbb,
eh2i, PR #573; round 2: bd 1dz2, fzwp, k3v7, xlvba, cgeh, PR #576). Same
brief: find easy, single-surface beads, bundle a few, close them.

## What shipped

1. **bd polyglot-pdf-amojb**: `scripts/read_kit_revision.py`'s `_resolve`
   counted an UNTRIMMED disambiguated sibling as LOOSE even when it was
   provably exact (`seg_base == base`, no lossy trim). If the plain-base
   archive directory were ever independently removed, the sole surviving
   untrimmed sibling produced a false NOT FOUND for a revision that
   demonstrably IS archived.
2. **bd polyglot-pdf-ondn**: `ValidationRules.min`/`.max` were typed
   `Optional[float]`, but the date-field min/max path was explicitly built
   (bd 3t3l) to accept a date-string bound -- untested through the real
   Pydantic model, which rejected exactly that input.
3. **bd polyglot-pdf-3o2uz**: `spellbackPlayer.ts`'s token-fetch race left
   an uncancelled 10s timer per call on the normal (fast) path.
4. **bd polyglot-pdf-asr2a**: `set_editor_kit_status` validated
   `replaces_kit_id` only after paying for a metered per-language
   translation sweep, so a bad supersede target burned real model calls
   before being refused.
5. **bd polyglot-pdf-pixq**: `_complete_grouped_families` could append two
   options carrying the identical `pdf_field_name` when a family's widget
   list repeated a name (one AcroForm field, multiple widget kids).

## Scar tissue

**1. A safety property proven for one input shape is not proven for the
adversarial one.** The `amojb` fix went through two rounds on the SAME
function, each closing a real gap the previous round opened:

- Round 1: widened a boolean "might be a sibling" check to a tri-state
  ("no"/"loose"/"exact"), reasoning that `seg_base == base` (an untrimmed
  match) is "provable, not a guess" because "no lossy trim was involved."
  That's true about the TEXT -- but the fix trusted text-shape equality as
  if it were proof of PROVENANCE (that this specific segment was actually
  WRITTEN as a sibling of this specific marker). It isn't: an unrelated
  kit's own `edition_date` could coincidentally contain the literal string
  `"<base>--sha256-<12hex>"` -- never written by the sibling-disambiguation
  writer at all -- and would pass the exact same shape check. The inner
  fresh-eyes reviewer reproduced this live: an impostor kit's schema
  silently returned at exit 0 for an unrelated marker, on a tool whose own
  module docstring names "never hand back a confident wrong schema" as the
  single thing it exists to prevent.
- Round 2: closed the actual gap by re-deriving the archived schema's own
  content fingerprint and recomputing what the writer's `sibling_marker`
  call WOULD have produced, comparing byte-for-byte against the real
  segment. Text-shape proves nothing on its own; only re-deriving the value
  from content the writer itself would have hashed proves the segment came
  from a genuine write.

The pattern generalizes: "this input shape can only be produced by our own
writer" is a claim about the SYSTEM'S NORMAL OPERATION, not about the
INPUT SPACE the reader actually has to defend against. A legal-retrieval
tool's own inputs (archive segment names) are attacker-adjacent the moment
anything else can write into the same directory tree (a migration, a
manual `gsutil cp`, an editor typo landing in a marker field) -- "our own
code never produces this" is not the same claim as "nothing else can
produce this."

**2. Widening a type to accept a NEW valid shape can silently break an
OLD valid shape, if the language's own coercion rules interact badly with
a union.** The `ondn` fix widened `Optional[float]` to
`Optional[Union[float, str]]` specifically to accept a date-string bound.
Pydantic's SMART-MODE union resolution picks the first arm that matches
WITHOUT COERCION over a later arm that would need coercion -- so a
numeric-looking string bound (`min: "18"`), which used to be silently
COERCED to `18.0` under the plain-float type, instead matched the `str`
arm verbatim and stayed a string. A defensive `isinstance` guard added in
the same commit (to stop that string from crashing a numeric comparison)
then silently SKIPPED the bound entirely rather than raising -- so the
net effect was "a value that should have been rejected for being under
the minimum is now accepted with zero errors," which is a worse failure
mode than the crash the guard replaced. The fix needed an explicit
`field_validator(mode='before')` that tries numeric coercion FIRST,
falling back to string only when that fails -- restoring the old
coercion behavior for the old valid shape while still accepting the new
one. Widening a type is never "purely additive" when the language's own
resolution order can silently reassign an existing valid value to a
different branch than it used to take.

## Review record

Two inner fresh-eyes rounds (2 gaps found and fixed on the first pass,
NO-GAPS on the second) and one outer Opus cross-surface round (NO-GAPS,
one pre-existing frontend type-declaration gap found and filed separately
rather than folded in). Both inner-round findings were on the SAME two
beads (amojb, ondn) -- the other three (3o2uz, asr2a, pixq) cleared on the
first pass and were spot-checked rather than re-derived on the second,
per the review's own scoping instruction once a diff region is confirmed
byte-identical between rounds.
