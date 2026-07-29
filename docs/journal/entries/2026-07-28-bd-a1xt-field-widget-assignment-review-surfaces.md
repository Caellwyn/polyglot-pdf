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

Multiclaim ownership is keyed on the owning FIELD, mirroring `schema_lint`'s
`_check_dump_claims`, so the two shapes that lint declares benign stay unflagged:
field-level plus a single option of the SAME field (the groups-of-one
convention), and an option dict carrying its own `id` (which the walker would
otherwise count as a second owner).

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
- **A gutter marker must sit in a RECURRING COLUMN, not merely near the widget.**
  The first version used proximity alone and read f1040's "1 Rollover 2 QCD 3"
  checkbox legend as "line 3" -- three false positives. Real markers share a
  right edge and repeat down the page. Pinned by a regression test, since
  proximity-only is the obvious way to reimplement this wrong.
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

## Two rounds of pre-PR review, and what they caught

The fresh-eyes loop found real bugs in this diff twice, both times in the
detection machinery itself:

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

The lesson worth keeping: a detector's false-positive behavior needs the same
adversarial scrutiny as its true positives, and "mirrors an existing rule" is a
claim to verify against that rule's carve-outs, not an assertion to make in a
comment.

## Verification

- 34 tests (20 oracle, 14 overlay).
- Full suite: 2333 passed, 2 skipped (both `tests/` and `backend/tests/` roots;
  `closeout_prep.py` runs only the latter).
- Real-kit regression after the fixes: f1040 `rc=1` (20 findings), w7 `rc=3`
  (abstains, 10 markers found but no checkable pair), and **0 multiclaimed** on
  both shipped kits -- confirming the round-2 false positive is gone.
- No shipped kit was modified (`git diff --name-only origin/dev...HEAD --
  form-kits/` is empty); bd `polyglot-pdf-3ave` stays open for the f1040 data
  fix.
