---
date: 2026-07-29
bead: polyglot-pdf-icyi
title: "Deterministic widget rects must OWN pdf_position; LLM coords are the no-rect fallback"
tags: [extractor, postmortem, testing]
---

## Trigger

The maintainer extracted a fresh W-7 kit and reported that NO bounding boxes
drew on the schema editor's PDF preview -- except for checkboxes. The previous
two extractions of the same form had drawn them correctly.

Measured immediately: 48 of the 54 fields carried `pdf_position.page = 0`
instead of the required 1-based page. The editor's PDF viewer matches pages
`1..numPages` by exact equality, so page 0 matches no rendered page and the
overlay silently paints nowhere. The 6 fields that DID draw were exactly the
choice fields (5 radio + 1 checkbox_group) -- the ones whose rects come from
the deterministic dump path, which correctly applies `+1`.

First question answered before touching anything: **was this the guidance
staleness gate that had just merged (PR #508)?** No. That PR's only change to
`extract_form.py` was reporting a count of discarded model proposals; it
touched no positioning, page, or overlay code. Confirmed by reading the diff
hunks directly, not the commit subject.

## What shipped

**Root cause was a priority inversion, not a missing guard.** The extraction
contract (`scripts/bakeoff/schema_contract.py` FIELD SHAPE) *asked* the model
for `pdf_position`, and `_has_usable_position` accepted whatever came back as
long as width and height were positive -- it never validated `page`. So the
deterministic dump-rect back-fill only ran as a REPAIR for missing/zero-size
rects and never overwrote a plausible-but-wrong model rect. The same run also
rounded every coordinate (469.2 -> 469).

Evidence that made the diagnosis airtight rather than plausible:

- All 48 broken fields HAD a matching widget with a real rect available -- the
  data was never missing, it was ignored.
- v2 (the previous day, same prompt) carried the SAME 48 model-authored
  integer-rounded rects; it just happened to emit `page: 1`. Pure model
  non-determinism against an unguarded field, not a code regression.
- 486 widgets across all four real kits (w7 69, i-90 195, f1040 199,
  w9-heldout 23) carry non-degenerate rects: 0 degenerate. The deterministic
  path is reliable on AcroForms.

**Maintainer decision (2026-07-29): flip the priority.** Where a widget
resolves, the dump rect wins UNCONDITIONALLY at both field and option level,
and the contract now tells the model NOT to emit `pdf_position` at all --
exactly the treatment `parts`/`sections`/`section_id` already get. Model
coordinates survive ONLY where no widget resolves (the route a future
non-AcroForm/scanned PDF needs, deliberately kept rather than deleted). On
that fallback path a 0-based page is an ordinal counting-scheme difference,
not corrupt data, so `_normalize_model_page_base` shifts every model page up
by one when any is 0. A field with neither a resolvable widget nor a usable
model rect now carries NO `pdf_position` key, instead of a zero-size
placeholder that reads as a real position downstream.

**An unexpected second symptom fixed itself.** Section derivation reads field
positions, so page 0 had been poisoning it too: v3 dumped 48 fields into one
meaningless "Page 0 (top)" bucket that had to be cap-split in half. The fresh
extraction derived the form's actual printed structure -- Name, Applicant's
Mailing Address, Foreign (non-U.S.) Address, Birth Information, Acceptance
Agent's Use ONLY, 8 sections in 1 part. One bug, two visible symptoms.

**Fresh re-extraction (the maintainer chose re-extract over in-place repair,
to see a fresh run in totality):** 54/54 fields on page 1, 0 missing, and
every rect an exact match to the PDF's widget geometry; 21/21 option positions
correct; integer-rounded rects 48 -> 5 (those 5 are integral in the PDF
itself). Guidance coverage improved incidentally (52 vs 51 instructions, 50 vs
43 details), lint warnings 6 -> 5, cost $2.13 vs $2.05.

### Fresh-eyes triage

Two gaps found, **both adopted** (neither deferred):

1. **The contract change would have silently zeroed a bake-off metric.** Raw
   bake-off arms render the same `SCHEMA_CONTRACT` and are scored on their
   DRAFT output, which never goes through the back-fill -- so once the contract
   stopped asking for `pdf_position`, `schema_score._pos_match` would score
   every future arm's absent position as a MISS, pegging the attribute at 0%
   forever and breaking comparability with every historical number. The
   reviewer filed it out-of-scope (bd polyglot-pdf-89ge); I **closed that bead
   and fixed it here instead** -- my diff causes it, so shipping it broken was
   not an option. Absent draft position is now not-applicable (`None`), exactly
   as an absent GOLD position already was. A present-but-wrong position is
   still a miss, so the metric keeps its teeth. This is the same
   scorer-artifact class `test_schema_score_derivation.py` already existed to
   fix for sections (bd mhyt) -- worth knowing that "the contract stopped
   asking for X" always has a scorer half.
2. **An unpinned behavior change at the option level.** Removing the early
   `continue` means an option with a bogus `pdf_field_name` but a plausible
   model rect is now *reported* in `unmatched` where it used to be skipped
   silently. That is the better behavior (a bogus widget name is what the
   unmatched list exists to surface), but it was a real delta with no test --
   now pinned.

Also noted and NOT flagged as blocking: `_complete_grouped_families` appends
options with no `pdf_position` at all (pre-existing, untouched by this diff --
filed by the reviewer as bd polyglot-pdf-tz7a); and the fallback's "any
page==0 -> shift all" rule is form-wide and blunt, but unreachable on AcroForms
and documented as an accepted tradeoff.

The Opus clearing round then found five more, **four adopted**:

3. **The bug this bead exists to kill was still reachable.** A 0-based page
   arriving as `0.0` or `"0"` -- ordinary JSON from a model -- was neither
   normalized nor reported: the gate tested `page == 0` (True for `0.0`, False
   for `"0"`) and the shift loop then required `isinstance(page, int)`. So
   `0.0` tripped the gate WITHOUT shifting and `"0"` did neither, and
   `PDFPosition` coerces both to a bare `0` downstream. Worse, my own comment
   excused the skip as "non-integer page is a different defect; lint names it"
   -- **which is false**: no lint rule reads `pdf_position` at all
   (`manifest_service` and `secretary_context` are its only backend readers and
   both STRIP it). Fixed with `_as_page_int`, which normalizes every integral
   form and writes a real `int`; the false claim is deleted and replaced with
   why.
4. **An aliased position dict shifted twice**, landing two pages off -- the
   mirror image of the very off-the-document hazard the identity-exempt set
   exists to prevent. Collection now dedupes by identity too. Unreachable via
   `json.loads`, but the function is documented as standalone-callable.
5. **The `backfill_option_positions.py` CLI's `--check` exit code inverted.**
   Its change-detector was `fields_filled + options_filled > 0` -- a count of
   DERIVATIONS -- and since every resolvable rect now re-derives, that was
   permanently true: `--check` reported "needs patching" (exit 1) for every
   kit including a fully-positioned one, and the documented exit 0 became
   unreachable. That matters because journal entries record "`--check` exits 0"
   as the passing criterion for kit-position work. Now compares the positions
   themselves; the docstring's idempotence claim was rewritten to say
   idempotent-in-effect (re-derives, computes identical values, writes nothing)
   rather than idempotent-by-skipping.
6. **A coupling test passing vacuously.** `test_contract_advertises_every_scorer_graded_key`
   exists to catch the contract NARROWING below what the scorer grades -- and
   this diff narrows it deliberately. It passed only because the substring
   `pdf_position` survived inside my forbidding comment. Removed from that
   list (with the reason), and replaced by a test asserting the contract
   actively FORBIDS the key.
7. Finding 5 (low, adopted): `pdf_position`'s prohibition lived only as an
   inline comment in the JSON shape block, while `parts`/`sections` get a
   RULES-level bullet -- the surface a model actually follows. Added the
   parallel bullet, so the mirroring the design claims is real.

### One thing the fixes surfaced, deliberately NOT fixed here

Running the corrected CLI over the COMMITTED i-90 kit reports a real
difference, which is the detector working. 115 of the 123 changed positions are
harmless float churn (committed kits store raw PyMuPDF floats like
`293.99798583984375`; the dump rounds to one decimal). But **8 are real moves
of 42-108pt**, all on choice fields with no field-level `pdf_field_name`, whose
field-level rect is defined as "the first option's widget". Example
`p3_checkbox4[1]`: options are `select_no` (real widget x=259.75) then
`select_yes` (x=215.54); the committed rect is 215.54 while a re-derive yields
259.75 -- the new value matches the documented first-option rule, the committed
one does not. Both are real widget rects, so this is arguably a CORRECTION, but
it moves committed data on the rect a choice field's preview paints, and two of
the eight move ~108pt vertically into a different form row. That needs eyes on
the rendered overlay before any kit is rewritten, and this bead rewrote no
committed kit. Filed as **bd polyglot-pdf-ks1y**.

## Lessons

**"Ask the model for a value the computer can compute exactly" is a latent
bug, not a shortcut.** Five numbers per field were being generated instead of
read, and the failure was invisible for two extractions because the model
guessed the right page base by luck. The generalizable rule: if a value is
mechanically derivable from the source artifact, derive it and tell the model
not to emit it. `parts`/`sections` already worked this way in this very
contract -- `pdf_position` was the straggler.

**A test that is internally consistent can still miss a whole class of bug.**
The broken schema was well-formed: valid page key, valid numbers, positive
sizes. Nothing in 2257 tests noticed, because nothing compared the schema
against the PDF it describes. The new real-kit guard does exactly that, with a
0.06pt tolerance -- and getting that number honest took FOUR passes, which is
the more useful lesson. v1 used 0.06 and credited it to "the dump rounds to one
decimal". Round 2 showed the dump rounds to TWO decimals (max 0.005pt), so the
tolerance was ~12x looser than its own stated basis. Tightening to 0.01 then
FAILED on w7, whose committed rects were written by an OLDER one-decimal dump
and sit 0.05pt off. The figures I quoted after THAT were still wrong -- because
i-90 was contributing zero comparisons (below), so its "0.0000pt, raw floats"
was an artifact of measuring nothing. Final MEASURED values, with the guard's own
arithmetic: f1040 0.0000pt/163 fields, i-90 0.0050pt/114, w7 0.0500pt/54. 0.06
was the right ceiling all along -- for a reason I never established until the
fourth try, while the comment asserted three wrong ones.

**The worst find of the whole bead: my regression guard verified NOTHING on the
biggest kit.** It looked up widget rects by exact `pdf_field_name` match, but
i-90's schema stores the XFA LEAF (`P1_Line1_AlienNumber[0]`) while the PDF
widget carries the fully-qualified path
(`form1[0].#subform[0].P1_Line1_AlienNumber[0]`). So **0 of 132 i-90 fields were
compared** -- every one hit the "unresolved widget name" skip -- and the test
passed, green, proving nothing on the largest and most XFA-complex kit in the
repo. The extractor itself resolves these correctly via the suffix-aware
`_match_dump_names`, so my guard was strictly weaker than the code it guards.
Fixed to use the same exact-then-dot-suffix rule (114 real comparisons now), and
a NON-VACUITY FLOOR added: if a kit has positioned fields and none resolve, the
test fails loudly instead of passing quietly.

**Assert that a guard is doing work, not just that it passes.** The vacuous-i-90
guard is the sharpest instance: it compared zero fields and reported success for
two review rounds. A test whose subject can silently become empty needs a floor
("we compared at least one thing") as much as it needs its assertion -- otherwise
green means "nothing was checked" and "everything is correct" indistinguishably.
This is the same failure shape as the vacuous coupling test in round 1, which
passed because a forbidden substring survived inside a comment.

**Mutation-check a regression guard before trusting it.** The first
mutation run passed, which looked like the new guard was useless -- but the
real cause was that the kit which shipped the bug is untracked scratch and does
not exist inside the worktree, so the guard never saw it. Added a second pin
that drives the exact production shape through `_backfill_positions` directly;
reverting the trust inversion now fails 2 tests. A guard whose teeth you have
not verified is decoration.

**"A different layer will catch it" is a claim, not a fact -- check it before
writing it in a comment.** I skipped normalizing a non-`int` page and justified
it with "lint names it". No lint rule reads `pdf_position` at all. The comment
made a reviewer's job harder and would have made a future maintainer's job
worse, because it reads as a deliberate division of responsibility rather than
an oversight. If you cite another layer as the backstop, grep for it.

**Inverting a trust rule silently redefines every change-detector built on it.**
Three separate consumers keyed off "did the back-fill fill anything?" as a proxy
for "is there work to do": the CLI's exit code, its docstring's idempotence
promise, and a coupling test's key list. Making the derivation unconditional
made that proxy permanently true, so all three quietly inverted meaning. When a
"was it needed?" flag becomes "did it run?", search for everyone reading the
flag.

**A marker key stamped onto data leaks.** The first draft tagged deterministic
rects with a `_deterministic_rect` key so the normalization pass could tell
them apart -- and it leaked into every kit and every dict-equality assertion in
the test file. Replaced with an identity set (`id()` of the position dicts),
which writes nothing into the data. Pinned by a test asserting a written
position carries exactly the five real keys.

## Doc freshness

`docs/schema_format.md` updated: `pdf_position` now documents the 1-based page
convention (and that page 0 silently draws nothing), who OWNS the value
(deterministic widget geometry overwrites model output), the no-widget
fallback, and that a field with no derivable position carries no key at all.
Dropped the stale "(for non-fillable PDFs)" qualifier, which described the
fallback as if it were the main case.

The doc-freshness checker also flagged ~20 tier-2 docs as STALE, all
voice/runtime/backend surfaces (auth, context-compression, voice-ai,
terminology, ...). **None track the extraction/authoring files this branch
touched** and all were stale before it; left alone deliberately.

Beads housekeeping: no orphans. Two stale in-progress beads (ah76, btbi) belong
to other sessions' work, not this branch -- not transitioned.

## Files touched

- `scripts/authoring/extract_form.py` -- the inversion: dump rect wins
  unconditionally at field + option level; `_normalize_model_page_base` for the
  no-widget fallback's page base; degenerate placeholders dropped;
  `_has_usable_position` docstring rescoped to "is a MODEL rect worth keeping".
- `scripts/bakeoff/schema_contract.py` -- FIELD SHAPE no longer asks for
  `pdf_position`; says why, and points at `pdf_field_name` as the key that
  matters instead.
- `scripts/schema_score.py` -- absent draft position is not-applicable, not a
  miss (the bake-off half of the contract change).
- `tests/test_extract_form_backfill.py` -- rewrote the two tests that encoded
  the OLD priority; added the dump-wins pins (field + option), the
  fallback-survival + page-shift pins, the real-kit page/geometry guard, the
  mutation pin, the five-keys pin, and the option unmatched-reporting delta.
- `tests/test_schema_score_derivation.py` -- not-asked-is-not-applicable pins.
- `docs/schema_format.md` -- position ownership + page-base documentation.
