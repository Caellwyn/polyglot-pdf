---
date: 2026-07-28
bead: polyglot-pdf-a1xt
title: "Field<->widget assignment: two review surfaces for the error class no gate could see"
tags: [extractor, authoring, form-kits, testing, correctness]
---

## Trigger

A bug-hunting pass on bd `polyglot-pdf-lha9` (four f1040 Line 1a-1d fields
claiming widgets that resolve to nothing). Verifying it uncovered that the four
unresolvable claims were the visible tip of a much larger, SILENT problem: the
whole page-1 income block was shifted, each field claiming a real, fillable
widget that belongs to a different printed line. Filed as bd
`polyglot-pdf-3ave` (P0), which remains open for the data fix.

## The error class, and why nothing caught it

A field claims a widget that is real, fillable, and claimed exactly once -- it
just belongs to a DIFFERENT printed line than the field means. Values land on
the wrong line of a tax return: on the shipped f1040, `fld_9` (total income)
writes into the printed Line 6a Social Security box.

This is the THIRD shipped instance:

| bead | form | what | how it was found |
|---|---|---|---|
| `13vo` | i-90 | ethnicity options on the OPPOSITE boxes | visual QA, by accident |
| `ivh9` | w7/w7-2 | off-by-one through name/address/id | a prototype, by accident |
| `3ave` | f1040 | page-1 shift through Line 11 | this lint investigation |

Every existing gate is structurally blind to it:

- `_check_dump_coverage` + the `l1a9` ledger catch UNCLAIMED and HALLUCINATED
  widgets. A mis-assigned widget is neither -- coverage reads 100%.
- `schema_lint`'s dump rules catch multiclaim and unresolvable claims. A shift
  that is a clean permutation trips neither.
- `scripts/schema_score.py` MATCHES a draft field to its gold counterpart BY
  `pdf_field_name` (Pass 1a/1b), so the claim is the matching KEY, not a scored
  dimension. A draft reproducing a shifted gold scores as agreement. f1040's
  gold IS the corrupted kit, so scoring a fresh extraction against it would
  reward reproducing the corruption.

`ivh9` had already named the mechanism: *"The shift ORIGINATED at two real
fillable widgets that no field models."* One unmodeled widget, and everything
downstream slides.

## What shipped

Two surfaces. Neither fixes kit data; they make the class DETECTABLE.

**1. `scripts/authoring/check_line_binding.py`** -- grades a draft against the
form's own printed gutter line markers ("1a", "2b", "11a"). No gold, no model,
deterministic, ~1s. If a field says line 2b and its widget sits on the row
printed "1g", that is reported with both numbers.

**2. `scripts/authoring/overlay_field_guesses.py`** -- draws the extractor's own
guess (`spoken_name` by default) onto the widget each field claims, for human or
vision-model review. Three states are visually distinct, because they are three
different bugs: a normal claim (red), a widget NO field claims (blue, a coverage
gap), and a widget claimed by MORE THAN ONE field (orange, flagged `!!` with
every claimant drawn). Note the DIRECTION -- `prior_extractor/pdf_annotator.py`
draws WIDGET NAMES as grounding INPUT; this draws the model's OUTPUT, so the
drawing is the thing under review.

Multiclaim detection mirrors `schema_lint`'s `_check_dump_claims` exactly, keying
claims on `(owner field id, kind)`. That rule has **two** ERROR branches and
**one** carve-out, and all three must be reproduced or the orange flag lies:
- ERROR: more than one DIFFERENT field claims the widget;
- ERROR: more than one OPTION of the same field claims it (selecting one would
  tick both -- lint's own test calls this "the shipped-f1040 class of bug");
- BENIGN: field-level plus a SINGLE option of the same field (the groups-of-one
  convention, a standalone checkbox restating its widget in both places).

An option dict carrying its own `id` is excluded by object IDENTITY, not by id
string -- option ids are short generic slugs (`yes`, `other`), so a string match
dropped genuine top-level fields with colliding ids.

**Exit codes (`check_line_binding`):** `0` verified-clean, `1` mismatches, `2`
usage/IO error, `3` ABSTAINED. Abstention is deliberately NOT `0` -- a caller
gating on `rc == 0` must never read "I checked nothing" as "it is clean", and
`--require-verified` folds `3` into a hard failure for CI. The rendered text
matches: an abstained run leads with `ABSTAINED:`, never `OK:`.

## Measured

Fresh extractions of both forms, $0 (local `claude-opus-4-8` CLI,
`--no-translate-options --no-enrich-guidance`).

| schema | oracle findings |
|---|---|
| shipped f1040 (corrupt) | 20 |
| fresh f1040 extraction | 5 |
| a corrected binding | 0 |

f1040 improved from **0/22** amount-column widgets correct (shipped, 2026-07-02)
to **18/26** (fresh) -- the entire Line 1a-4b shift is fixed. The residual is two
off-by-one clusters (lines 5-6, 8-11a), each beginning where a CHECKBOX row
interrupts the amount column.

W-7 was re-scored DOWNWARD by the overlay. "20/22" was measured against the
`ivh9` answer key, which covers only the name/address/id run. The overlay reaches
the signature block, which carries its own separate shift:
`applicant_phone_number` on the DATE box, `applicant_signature_date` on the PHONE
box, the agent phone/fax pair on the EIN/PTIN row. Confirmed against the
hand-corrected gold (`f1_42=applicant_phone` there), so it is a real regression.

## The two surfaces are complementary; neither is sufficient

The f1040 residual was found ONLY by the oracle. BOTH W-7 defects were found
ONLY by the overlay -- W-7 prints no gutter markers, so the oracle abstains on it
entirely. A gate running one without the other has a live blind spot.

## Decisions (defended)

- **Abstention is loud.** A form the oracle cannot verify prints "NOT a clean
  bill of health", never OK. Silence that reads as success is how this class
  stayed hidden for three incidents.
- **A gutter marker must sit in a recurring column AND that column must carry
  VARIED marker texts.** Both conditions are load-bearing, and it took two tries
  to get right:
  - v1 used proximity alone and read f1040's "1 Rollover 2 QCD 3" checkbox legend
    as "line 3" -- three false positives.
  - v2 added the recurring-column rule, which killed those. But the Opus outer
    review proved the rule did not do what its own docstring claimed: the
    legend's `'1'` (x_right 278.0) and `'2'` (x_right 357.2) each recur on three
    rows, clear the threshold, and **were** still returned as markers. No false
    finding fired only by coincidence: under v2 those legend markers WERE paired
    with the legend checkboxes, and the options are labelled "1 Rollover" /
    "2 QCD", so the parsed line happened to EQUAL the legend numeral. (My first
    write-up of this said the widgets were "claimed at option level, which the
    oracle does not read" -- that reason was itself wrong, and outer-review pass 2
    disproved it; see the option-level finding below.)
  - v3 adds `_GUTTER_MIN_DISTINCT`: a gutter numbers successive rows, so its
    tokens vary (`2a`, `3a`, `4a`); a legend column repeats one token.

  Worth recording what did NOT work, because it looks obvious: **leftmost-column
  wins is wrong.** f1040 has TWO legitimate gutters -- the left row numbers at
  x~101-105 and the amount column at x~495-500 -- and the legend sits *between*
  them, so a position rule drops the amount column and takes f1040 from 20
  findings to 0. Position cannot discriminate here; repetition can.

  Pinned by a test that asserts the marker set directly (not just "no finding
  claims line 3", which was the accidental survivor) and that BOTH gutters
  survive, so the position rule cannot be reintroduced.
- **Dropped the `*_extra` heuristic** originally proposed. Checking the drafts
  showed `widgets_backfilled: 0` on both forms -- the deterministic backfill never
  fired, so those fields were LLM inventions, not backfill artifacts. An id-shape
  heuristic would have been form-specific and brittle; the printed-marker signal
  is structural.
- **Filed the tooling as its own bead (`a1xt`) rather than folding it into
  `3ave`.** `3ave` is a data fix on a kit; this is detection machinery. Bundling
  them would have made the PR close a bead whose data work is not done.
- **Did NOT fix the f1040 data.** Maintainer direction: f1040 is a test-set form,
  not production and not training ground truth, and the priority is the
  extraction pipeline over hand-patching one form. A partial rebinding was
  attempted and REVERTED -- fixing only `lha9`'s four fields collides with the
  shifted `1e`-`1h` fields and leaves the kit linting worse than baseline.

## Three rounds of pre-PR review, and what they caught

The fresh-eyes loop found real bugs in this diff three times, every time in the
detection machinery itself -- and twice the bug was introduced by the PREVIOUS
round's fix:

- **Round 1** -- the overlay's `_claims` used `setdefault`, so a widget claimed
  by two fields drew only the FIRST label and rendered identically to a clean
  one. The tool built to surface assignment defects was hiding the one defect
  shape it could see directly. Also: the oracle exited `0` when it had verified
  NOTHING, contradicting its own "NOT a clean bill of health" text.
- **Round 2** -- the round-1 multiclaim fix was itself wrong. Counting raw labels
  flagged two shapes `schema_lint` explicitly sanctions (groups-of-one; an option
  carrying its own `id`), so a legal schema rendered orange. A false alarm on the
  headline signal is worse than no signal: a reviewer who learns the flag lies
  discounts the true positives too. Ownership is now keyed on the owning field,
  mirroring `_check_dump_claims`. Round 2 also caught the docstring promising
  "2 = usage/IO error" while an unreadable `--pdf` raised a raw traceback, and
  the abstention text still LEADING with `OK:`.

- **Round 3** -- the round-2 fix OVER-corrected. Keying on the owning field alone
  collapsed *two options of the SAME field* into one entry, but `schema_lint`
  raises `dump-widget-multiclaim` for that shape too -- its own test calls it
  "the shipped-f1040 class of bug" (selecting one option would tick both
  widgets). So the fix for a false positive created a false NEGATIVE on a
  separately-tested defect class. The rule has TWO error branches (different
  fields; two options of one field) and exactly ONE carve-out (field + a single
  option); claims are now keyed on `(owner, kind)` to mirror all three. Round 3
  also found the option-dict exclusion keyed on the id STRING rather than object
  identity -- so a genuine field named `yes` or `other` was dropped entirely,
  rendering its widget as a false coverage gap -- plus two more unguarded IO
  paths (`--json`, `--png-dir`), one of which printed its OK line *before*
  crashing.

- **Round 4** -- a reserved-word collision in the round-3 key space. `kind` was
  `"field"` for a field-level claim but `str(value)` for an option, so an option
  whose value is literally `"field"` produced the same key and OVERWROTE the
  field-level entry, collapsing an option+option ERROR into a benign-looking
  single claim. Nothing else catches that shape: `"field"` is a legal option slug,
  so no lint rule fires on the value, while lint *does* raise
  `dump-widget-multiclaim` for the binding. Now keyed on the option's INDEX
  (`option[<idx>]`) -- the same key space lint uses, collision-free by
  construction; `value` is display only.

The lesson worth keeping: a detector's false-positive behavior needs the same
adversarial scrutiny as its true positives, and "mirrors an existing rule" is a
claim to verify against that rule -- **all of its branches, and its key space** --
not an assertion to make in a comment. All three later rounds landed on that one
sentence: round 2 because the carve-outs were not read, round 3 because only one
of the two ERROR branches was, round 4 because the key space was re-derived
instead of copied. Each fix was locally reasonable and still wrong. The cheap
prevention is an equivalence sweep: run both implementations over a set of shapes
and assert they agree, rather than reasoning about whether they should. That sweep
is now `test_an_option_valued_field_does_not_collide_with_the_field_level_key`
plus its siblings; it agrees with live `lint_schema` on all five probed shapes.

## The Opus outer review, and the one thing it caught that five inner rounds did not

The outer review did what the inner loop structurally could not: it **verified the
tool's core claim against physical reality** rather than against the tool. It
opened `form-kits/f1040/form.pdf`, located widget `f1_68[0]` at
`Rect(252, 654, 323.25, 666)`, found the printed token `"6a"` immediately to its
left on the same row with the row text "6a Social security benefits", and
confirmed that the oracle's report -- *`fld_9` says line 9 but its widget is
printed on line 6a* -- is factually true. It also verified the negative control
(`f1_73[0]` really is the line-9 widget the correction test rebinds to).

That is the check that matters most for a tool like this, and no amount of
self-consistent unit testing substitutes for it: a detector that reports
confidently and wrongly is worse than no detector. It then found the gutter rule
did not match its own docstring (above) -- a mismatch five rounds of inner review
had read past, because every one of them checked the code against my description
of the rule instead of against the PDF.

**Pass 2 found the same class of error a third time, in a docstring I had just
written.** The "KNOWN BLIND SPOTS" note claimed option-level claims "are not
checked ... this reads only a field's own `pdf_field_name`". But `_iter_fields`
yields ANY dict with a string `id` at any depth, so an option carrying an `id` was
yielded as a field in its own right and its LABEL read as a stated line. An option
labelled `"1 Yes"` on a correctly bound widget printed on row 6a produced a
confident FALSE finding -- the "1" is list-item text, not a line number. Dormant
only because no shipped or fresh schema currently gives options ids, while f1040
already ships labels that parse as markers (`"1 Rollover"`, `"2 QCD"`,
`"1 Line 3a"`). The exclusion the sibling overlay already had (by object identity)
is now enforced in `_iter_fields` itself, so the documented contract is true by
construction rather than by accident of the current data.

Three separate reviews, three instances of one failure: **a comment asserting a
property nobody had executed.** The tests that "covered" each one passed
throughout, because they tested the same belief the comment stated. The cheap
prevention is to make the claim executable -- assert the marker set, inject the
option, diff the two implementations -- rather than to write it more carefully.

## Verification

- 48 tests across the two tools plus the eval-sweep pins.
- Full suite: 2298 passed, 2 skipped (both `tests/` and `backend/tests/` roots;
  `closeout_prep.py` runs only the latter). The count is lower than this branch's
  earlier 2339 because `origin/dev` deleted `tests/test_harness_ledger.py`
  (52 tests, bd `polyglot-pdf-40r4`); 2339 - 52 + 11 new = 2298.
- The oracle's f1040 findings and the fresh-extraction count (5) are unchanged by
  the v3 gutter rule -- 20 findings / 52 checked on the shipped kit, exactly the
  pre-fix baseline, with the legend numerals now rejected.
- The overlay's multiclaim verdict was checked against **live `lint_schema`** on
  five shapes (two different fields; two options of one field; an option valued
  `"field"`; groups-of-one; a normal two-widget choice) -- agreement on all five.
- Real-kit regression after all four rounds: f1040 `rc=1` (20 findings), w7
  `rc=3` (abstains -- 10 markers found but no checkable pair), and **0
  multiclaimed** on w7, f1040 and i-90. The no-false-positive evidence rests on
  **w7 and f1040**, whose claims resolve fully; the i-90 row exercises only ~22%
  of that form (43 of 189 claims resolve -- see the limitation below), so it
  corroborates rather than confirms.
- The strongest equivalence evidence is not the real kits but an **exhaustive
  sweep**: 1560 synthetic shapes (1-2 fields x field-level claim in
  {none, W1, W2} x 0-2 options x every option-claim combination) compared against
  live `lint_schema`, **zero divergences** in the multiclaimed widget set. Where
  the overlay differs at all it OVER-detects relative to lint -- it walks
  `parts`/`sections`/nested `fields` that lint's flat loop never sees (the
  already-filed lint gap bd `polyglot-pdf-hj6w`), so it errs toward showing a
  reviewer more, never less.
- No shipped kit was modified (`git diff --name-only origin/dev...HEAD --
  form-kits/` is empty); bd `polyglot-pdf-3ave` stays open for the f1040 data
  fix.

## Known limitation found while verifying

On i-90 the CLI overlay reports 152 widgets "unclaimed" that are in fact claimed:
that kit stores SHORT widget names (`P1_Line10_CityTownOfBirth[0]`) while the PDF's
real widgets are fully qualified (`form1[0].#pageSet[0].Page1[0]...`). This tool
matches on the exact string, whereas every other consumer in the repo resolves
exact-or-dot-suffix (`schema_lint._match_dump_names`,
`pdf_fill_routes.find_widget`, `schema_repair._check_widgets_exist`), so 146 of
189 claims miss.

Pre-existing name-resolution behaviour, not a regression from this work. Filed as
bd **`polyglot-pdf-wjxs`**, which also records the sharper consequence found in
round 5: two claimants written in DIFFERENT name styles land in different buckets,
so a genuine multiclaim would report `multiclaimed: 0`. No live defect is hidden on
shipped data today -- after correct resolution i-90 has exactly one repeatedly
claimed widget, `P7_checkbox7Extend[0]`, and it is the benign groups-of-one pair
lint also passes -- but the blind spot is real for future kits.

The editor-side overlay (bd `polyglot-pdf-w70y`) is immune to this whole class,
since it keys on `pdf_position` rects rather than widget names.
