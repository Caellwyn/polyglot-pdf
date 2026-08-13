---
tags: [bug-hunt, testing, schema-forms, pdf-view, schema-editor, readiness-stamp]
beads: [polyglot-pdf-rctj, polyglot-pdf-1utg, polyglot-pdf-hbfky, polyglot-pdf-87zbs, polyglot-pdf-kwh3t]
surfaces: [frontend/schema-forms, frontend/pdf-view, schema-editor, backend/routes]
---

# Bug-hunt round 6: alias-lookup asymmetries, deleted-open-kit stale pane, rounded-100% green bar, dump-blind verified stamp

Sixth round of the ongoing bug-hunt bead roundup (rounds 1-5: PRs #573,
#576, #578, #581, #583). Five beads, all confirmed-live single-surface bugs.

1. **`getCurrentSectionFields` vs `findSectionIdForField` alias asymmetry**
   (bd rctj). The function that pages continuous-mode UI to a field's
   section already matched across `[]`-alias bracket variants; the function
   that then renders that section's fields did not, so a field could be
   correctly paged-to and then appear missing.
2. **`FieldEditPopover` click-to-edit read exact-key only** (bd 1utg). The
   overlay preview already read a field's value via the alias-aware
   `readFieldEntryWithAlias` helper (bd 7sdc); the click-to-edit popover
   right next to it used a bare exact-key read, opening blank for a field
   the overlay itself showed as filled.
3. **Deleting the OPEN kit left a stale editor pane** (bd hbfky). The
   hosted schema editor's `RemoteCatalogue` was never wired to the
   `clearOpenKit` callback its sibling `FormCatalogue` already receives for
   exactly this purpose.
4. **A 199-of-200 kit rendered a green 100% review bar** (bd 87zbs). Both
   catalogue cards keyed the bar's color on the ROUNDED percentage
   (`Math.round(199/200*100) === 100`) instead of the exact reviewed/total
   ratio already available in the same stamp.
5. **The save-time readiness stamp claimed `verified=True` on a dump read
   FAILURE** (bd kwh3t). `_load_kit_dump` collapses "no dump ever existed"
   and "dump exists but is corrupt/unreadable" to the same `None`, so
   `_stamp_readiness` couldn't tell a genuinely dump-less lint from one that
   silently ran dump-blind because the read failed.

## Scar tissue

### "Enumerate the set" caught two MORE pre-existing gaps this round didn't
### introduce, and both got correctly filed rather than folded in

The outer cross-surface review, tracing bead rctj's fix outward, found that
`getCurrentSectionFields` was not the only `section.fields` -> `schema.fields`
exact-match join in `schemaFormState.ts` -- three siblings
(`isSectionValid`, `extractSectionFields`, `getPreviousSpokenNames`) do the
identical join and were never widened. `isSectionValid` is the highest-
consequence of the three: a bracket-mismatched REQUIRED field could
silently drop out of its own section's field list, letting the section
validate as complete with a real required question unanswered -- the
inverse of the bug this round fixed. Separately, tracing bead kwh3t's fix
outward found that the PUBLISH path's own readiness re-stamp
(`POST /kits/{kit_id}/status`) still hardcodes `verified=True` unconditionally,
so publishing a kit whose save just correctly stamped `verified=False`
(this round's fix) immediately overwrites it back to a false "checked"
claim -- the two stamp writers now actively disagree.

Both are genuinely pre-existing (confirmed unchanged on `origin/dev` before
this branch), not something this round's fixes introduced, and both were
correctly filed as separate beads (`polyglot-pdf-js8n0`,
`polyglot-pdf-ucjlu`) rather than pulled into this PR -- properly fixing
either needs its own scoped, mutation-verified change, not a same-PR
tack-on. This is the third round in a row where the outer review's
contract-tracing has found a sibling instance of the exact pattern a bead
fixed, sitting one function away, unwidened. The lesson holds: a single
fixed call site is never proof the SET is closed; only a grep across the
whole file (or, better, a test asserting the complete list of sites) is.

### A test can correctly mirror its sibling and still not mutation-prove
### the exact thing it was asked to guard

The inner review flagged `FormCatalogue.test.tsx` as missing the
"genuinely-complete-stays-green" regression guard its sibling
`RemoteCatalogue.test.tsx` already had. Added it, mutation-verified against
a BROAD "always yellow" mutation (correctly reddened) -- but the literal,
narrow `pct === 100` mutation the bead's own bug was phrased as does NOT
redden this specific test, because at exactly 200/200,
`Math.round(200/200*100) === 100` is true under both the buggy and the
fixed predicate. The two predicates are mathematically indistinguishable at
that one boundary point; only the 199/200 case (already covered by a
sibling test) actually distinguishes them. This is not a defect in the new
test -- it faithfully mirrors what it was asked to mirror -- but it is a
reminder that "mutate the fix and confirm red" needs the RIGHT mutation,
not just A mutation, and that a regression guard aimed at "still recognizes
true completion" is answering a different question than "still rejects the
false-positive," even when both tests use the same 100%-adjacent fixture
shape.

## Process notes

- Two rounds of both review layers this time: the inner fresh-eyes review's
  first pass found two non-blocking test-coverage-symmetry gaps (both in
  already-correct code, not code defects), closed in a same-PR follow-up
  commit, then reconfirmed NO-GAPS. The outer review's single pass found
  two pre-existing, out-of-scope gaps via contract tracing and filed them
  rather than expanding scope -- correctly, since this PR's own diff
  introduced neither and properly fixing either is its own unit of work.
- Total across rounds 1-6: 32 beads closed over 6 merged PRs (#573, #576,
  #578, #581, #583, and this one).
