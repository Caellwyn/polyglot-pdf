---
tags: [bug-hunt, testing, readiness-stamp, form-models, schema-editor, deploy, authoring]
beads: [polyglot-pdf-ucjlu, polyglot-pdf-9ec2u, polyglot-pdf-93p8, polyglot-pdf-wjes, polyglot-pdf-pnye, polyglot-pdf-qk97]
surfaces: [backend/routes, backend/models, schema-editor, scripts]
---

# Bug-hunt round 7: publish-path stamp parity, FormField min/max widening, malformed-options crash, deploy hints, gutter-column repair

Seventh round of the ongoing bug-hunt bead roundup (rounds 1-6: PRs #573,
#576, #578, #581, #583, #585). Five beads, one closed as a duplicate.

1. **Publish-path readiness re-stamp hardcoded `verified=True`** (bd
   ucjlu). Round 6's bd kwh3t fixed the SAVE path's stamp to honestly
   report `verified=False` when a kit's AcroForm dump read fails (not just
   when it's absent); the PUBLISH path's own re-stamp was never updated to
   match, so publishing a kit immediately after saving it silently
   overwrote the save's honest stamp with a confident, dishonest one.
2. **`FormField.min`/`.max` narrower than its own nested sibling** (bd
   9ec2u). `ValidationRules.min`/`.max` (round 3) and the frontend TS type
   (round 4) were both widened to accept a date-string bound; the
   top-level `FormField.min`/`.max` was never touched and stayed
   float-only -- currently dormant, but a landmine for any future
   direct-construction caller.
3. **`hasUncoveredStructuralError` threw on malformed `options`** (bd
   93p8, duplicate-closes bd wjes). The backend mirror already degraded
   gracefully on a non-array `options` value and on an array containing
   null/non-object entries; the frontend threw, blanking the whole review
   strip instead of showing a degraded count for one field.
4. **Deploy script hints were actively wrong** (bd pnye). Both post-deploy
   hints in `deploy-form-kit.sh` referenced an env-var flag and an
   auth-gated route that had both changed meaning since an earlier fix
   (bd z2is).
5. **A gutter-marker detector rejected an entire clustered column the
   moment any marker repeated within it** (bd qk97), losing a genuine
   adjacent gutter along with an offending legend.

## Scar tissue

### qk97 took three review rounds to actually close -- the position-based
### first attempt was wrong twice, in ways only live reproduction caught

This bead is the clearest recent example of "the first fix is correct but
not the whole fix." The initial approach (split a clustered column at a
y-order discontinuity, then re-derive the final marker list via an
x-tolerance re-scan of every candidate) passed all 31 existing tests and
its own two new tests -- but the inner fresh-eyes review reproduced, by
actually running the code, two real defects the tests never exercised:

1. **The split never fires when gutter and legend share the exact same
   x_right and interleave while staying monotonic overall** -- a case the
   bead's OWN description named as real ("a form whose left and right
   gutters share an x_right ... produces repeated texts within one
   column"), but the shipped test's synthetic shape (two different
   x_right values 2.4pt apart) happened to route around it, because
   column-BUILDING sorts by x1 first and segregates the two token streams
   into separate blocks before the y-split ever runs.
2. **The x-tolerance re-scan re-admitted markers from a run that was JUST
   dropped for repetition**, whenever the dropped run's x1 fell within
   tolerance of a surviving run's band -- which is exactly what the
   shipped test's own fixture did (legend at 302.4, gutter band at 300,
   tolerance 2.5). The stderr diagnostic correctly said "dropped 1 column
   run" while the actual return value still contained all 9 markers, not
   the intended 6 -- the fix's own narration and its own output
   disagreed, and no test asserted the FULL return value, only a
   position-filtered subset.

Both defects trace to the same root choice: reaching for a POSITION-based
mechanism (where do the tokens sit, in what order) for what is
structurally a VALUE-based distinction (which specific text repeats).
Redesigning around rejecting only the repeating TEXT VALUES -- keep every
marker whose text is not among the column's repeating set, return that
kept list directly with no second re-filter pass -- closed both defects at
once and is what the bead's own first-listed option suggested from the
start. The lesson: when a fix's own test only checks a NARROWED view of
the output (a position-filtered subset, one direction of a two-direction
case), that narrowing is itself worth suspecting -- it is often hiding
exactly the case a fuller assertion would have caught immediately.

A THIRD round then found the new regression test itself over-claiming: its
docstring promised a per-page marker-SET guard, but the assertion actually
summed counts across the whole document into one scalar -- weaker than
both the bead's own exit-criterion wording and the test's own docstring.
Replaced with a per-page SHA-256 fingerprint of each page's sorted marker
tuples, and confirmed (via a live mutation-verify against the real
production function) that it genuinely catches a same-total-different-
distribution change the scalar sum would have missed.

### The outer review's contract-tracing again found a sibling instance of
### an already-fixed pattern, one file over

`hasUncoveredStructuralError` (bd 93p8) was fixed to degrade instead of
throw on malformed `options`; the bead's own description named
`statusFromFindings` as the OTHER throwing path on the same render chain,
but only the one function actually got fixed. The outer review traced this
and found `checkFieldComplete` (in a different file,
`schema-editor/src/utils/validation.ts`) still throws on the identical two
malformed shapes, on a WIDER blast radius than the fixed function (the
field list and PDF overlay render paths, not just the review strip).
Filed as `polyglot-pdf-8bjdx` rather than folded in -- correctly, since
this round's own diff never touched that file and pulling it in would
have re-opened a closed review cycle for an unrelated function.

## Process notes

- Three full review-and-fix cycles on the same PR before it cleared: the
  first found 3 BLOCKING gaps (all in `qk97`), the second found 1 more
  (the test's own overclaim), the third confirmed clean. All were live-
  reproduced, not just reasoned about -- every finding included an actual
  run of the code showing the wrong output.
- The outer review found two more gaps via contract tracing outward, both
  confirmed genuinely pre-existing (unchanged on `origin/dev` before this
  branch) and correctly filed as separate beads (`polyglot-pdf-8bjdx`,
  `polyglot-pdf-8lh77`) rather than expanding an already-large PR.
- Total across rounds 1-7: 38 beads closed (37 fixed + 1 duplicate-closed)
  over 7 merged PRs (#573, #576, #578, #581, #583, #585, and this one).
