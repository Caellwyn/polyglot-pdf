---
date: 2026-07-10
bead: polyglot-pdf-6cfu.1
title: "Deterministic division derivation prototype: derived-vs-current report for all 5 forms (go/no-go checkpoint)"
tags: [extractor, conventions]
---

## Trigger

Sprint 10 (epic `polyglot-pdf-6cfu`, plan
`docs/sprint_10_deterministic-divisions_plan.md`): form sections are cut by
the extraction LLM with no splitting policy, which makes boundaries arbitrary
and human-intervention-heavy. The maintainer wants deterministic divisions
aligned with the form's own printed sections. Bead 6cfu.1 is the go/no-go
prototype: `scripts/authoring/derive_sections.py` plus this derived-vs-current
comparison over all 5 checked-in forms.

## What shipped

- `scripts/authoring/derive_sections.py` -- standalone deterministic division
  derivation. Strategy ladder, auto-selected per form from widget names:
  1. **name-convention** (USCIS): `P{N}_Line{item}_...` names give part
     membership + item ordering with no geometry; printed bold-italic
     sub-headings (column-aware, part-heading barrier) subdivide.
  2. **printed-heading** (IRS): per-page text-style census; bold left-margin
     lines 1-8pt over body size are headings (adjacent same-style lines
     merged at <= 1.3x line height); fields belong to the nearest heading
     above on their page.
  3. **page-fallback**: page = section.
  Common rules: sections never span pages ("(continued)"); cap 20 fields with
  sub-splits at line-item/row family boundaries ("X (1 of 3)"); labels from
  the form's printed text, ASCII-normalized; 1-based page numbers.
- Sprint plan doc `docs/sprint_10_deterministic-divisions_plan.md` + INDEX row;
  epic `polyglot-pdf-6cfu` with beads .1-.6 wired exploration -> implementation
  -> testing -> retrofit.

## Results (summary)

| form | strategy | derived | current kit | max section size | determinism |
|------|----------|---------|-------------|------------------|-------------|
| f1040 | printed-heading | 2 parts / 17 sections | 12 / 15 | 20 | byte-identical |
| i-90 | name-convention | 9 parts / 32 sections | 8 / 16 | 12 | byte-identical |
| w7 | printed-heading | 1 part / 9 sections | 3 / 9 | 20 | byte-identical |
| w7-2 | printed-heading | 1 part / 9 sections | 7 / 13 | 20 | byte-identical |
| w9-heldout | printed-heading | 1 part / 2 sections | (no schema) | 18 | byte-identical |

Exit criteria: all met. (1) Reports for all 5 forms below, including the i-90
two-column page-2 case: `Reason for Application` fields land in Part 2 via
their `P2_` name prefixes with `Line` ordering, no geometry involved. (2)
f1040/w7 boundaries + labels match the printed left-margin headings (Filing
Status / Digital Assets / Dependents / Income / Tax and Credits / ...; Name /
Applicant's Mailing Address / Birth Information / ...). (3) `--check` double
runs are byte-identical on every form.

## Key findings beyond the exit criteria

1. **The w7/w7-2 kits have a shipped field-to-widget mapping bug** (filed as
   its own P1 bead): the kit's `name_1a_first` points at widget `f1_06`,
   which is actually the treaty-article input; the shift cascades
   (`mailing_street` -> `f1_12` = the 1b Last name box; `mailing_city` ->
   `f1_13` = the street line). Verified against the AcroForm dump rects and a
   render of the printed page. Consequence: W-7 PDF filling writes values one
   box off through that region today. The "drawn from" bleeds in the w7
   tables below are artifacts of THIS kit bug -- the derived geometric
   assignment matches the printed form.
2. **i-90 has 18 fields with no `pdf_field_name` in the kit** (extraction
   gaps); they file per page under "Other items". A derivation-era extraction
   (bead 6cfu.2) should reduce these to zero by starting from the dump.
3. **f1040 has 4 fields with no `pdf_position`** (`fld_1a..fld_1d`) --
   pre-existing kit gaps, listed as unassigned.
4. i-90 page 7 produces two adjacent sections both labeled "Your Full Name"
   (the re-entry name block is `P1_`-named while its neighbors are `P8_`);
   cosmetic, resolvable in bead 6cfu.2 (e.g. suffix the part).
5. IRS margin headings are vertically centered on their blocks, so a pure
   y-threshold can mis-assign a boundary row in theory; margin-strip rule
   segments (PyMuPDF `get_drawings`) exactly delimit the blocks (verified on
   w7: rules at y 276/324/372/420/444/612/696 = the heading tops) and are the
   bead-2 refinement path if boundary precision needs tightening.

## Per-form derived-vs-current tables

The "drawn from" column shows which CURRENT kit sections each derived
section's fields come from (counts in parentheses). Current-kit labels are
the old LLM-cut sections -- not ground truth (see w7 finding above).

## f1040

- strategy: **printed-heading**
- derived: 2 parts / 17 sections; current kit: 12 parts / 15 sections
- section headings detected: p1 'Filing Status'; p1 'Digital Assets'; p1 'Dependents'; p1 'Income'; p2 'Tax and Credits'; p2 'Payments and Refundable Credits'; p2 'Refund'; p2 'Amount You Owe'; p2 'Third Party Designee'; p2 'Sign Here'; p2 'Paid Preparer Use Only'
- NOTE: 4 fields have no pdf_position (listed in the report)
- NOTE: 'Page 1 (top)' (27 fields) cap-split into 2
- NOTE: 'Dependents' (42 fields) cap-split into 3
- NOTE: 'Income' (30 fields) cap-split into 2
- NOTE: 'Tax and Credits' (25 fields) cap-split into 2

| # | derived section | page | fields | drawn from (current kit sections) |
|---|-----------------|------|--------|-----------------------------------|
| 1 | Page 1 (top) (1 of 2) | 1 | 19 | Tax Year and Filing Indicators (10), Taxpayer and Spouse Names and SSNs (6), Address (3) |
| 2 | Page 1 (top) (2 of 2) | 1 | 8 | Address (6), Presidential Election Campaign (2) |
| 3 | Filing Status | 1 | 5 | Filing Status (5) |
| 4 | Digital Assets | 1 | 1 | Digital Assets (1) |
| 5 | Dependents (1 of 3) | 1 | 20 | Dependents (20) |
| 6 | Dependents (2 of 3) | 1 | 13 | Dependents (13) |
| 7 | Dependents (3 of 3) | 1 | 9 | Dependents (9) |
| 8 | Income (1 of 2) | 1 | 20 | Income (20) |
| 9 | Income (2 of 2) | 1 | 10 | Income (10) |
| 10 | Tax and Credits (1 of 2) | 2 | 20 | Tax and Credits (20) |
| 11 | Tax and Credits (2 of 2) | 2 | 5 | Tax and Credits (5) |
| 12 | Payments and Refundable Credits | 2 | 16 | Payments and Refundable Credits (16) |
| 13 | Refund | 2 | 7 | Refund (7) |
| 14 | Amount You Owe | 2 | 2 | Amount You Owe (2) |
| 15 | Third Party Designee | 2 | 4 | Third Party Designee (4) |
| 16 | Sign Here | 2 | 6 | Sign Here (6) |
| 17 | Paid Preparer Use Only | 2 | 7 | Paid Preparer Use Only (7) |

Unassigned (no pdf_position): fld_1a, fld_1b, fld_1c, fld_1d
## i-90

- strategy: **name-convention**
- derived: 9 parts / 32 sections; current kit: 8 parts / 16 sections
- part headings detected: p1 'Part 1.  Information About You'; p2 'Part 1.  Information About You (continued)'; p2 'Part 2.  Application Type'; p3 'Part 2.  Application Type (continued)'; p3 'Part 3.  Processing Information'; p3 'Part 4.  Accommodations for Individuals with'; p4 'Part 4.  Accommodations for Individuals with Disabilities and/or Impairments (continued)'; p4 'Part 5.  Applicant's Statement, Contact Information, Certification, and Signature'; p5 'Part 6.  Interpreter's Contact Information, Certification, and Signature'; p5 'Part 7.  Contact Information, Declaration, and'; p6 'Part 7.  Contact Information, Declaration, and Signature of the Person Preparing this Application, if Other Than the Applicant'; p7 'Part 8.  Additional Information'
- section headings detected: p1 'Mailing Address'; p1 'Your Full Name'; p1 'Physical Address'; p2 'Reason for Application (Select only one box)'; p2 'Additional Information'; p3 'Biographic Information'; p4 'Applicant's Contact Information'; p4 'Applicant's Certification'; p4 'Applicant's Statement'; p4 'Applicant's Signature'; p5 'Interpreter's Signature'; p5 'Interpreter's Full Name'; p5 'Preparer's Full Name'; p5 'Interpreter's Mailing Address'; p5 'Preparer's Mailing Address'; p5 'Interpreter's Contact Information'; p5 'Preparer's Contact Information'; p5 'Interpreter's Certification'; p6 'Preparer's Statement'; p6 'Preparer's Certification'; p6 'Preparer's Signature'; p7 'Your Full Name'
- NOTE: 18 fields filed per page under 'Other items' (18 have no pdf_field_name in the kit, 0 do not match the USCIS pattern)

| # | derived section | page | fields | drawn from (current kit sections) |
|---|-----------------|------|--------|-----------------------------------|
| 1 | Part 1.  Information About You | 1 | 2 | Part 1.1 - Information About You: Numbers and Names (2) |
| 2 | Your Full Name | 1 | 6 | Part 1.1 - Information About You: Numbers and Names (6) |
| 3 | Mailing Address | 1 | 9 | Part 1.2 Mailing Address (9) |
| 4 | Physical Address | 1 | 8 | Part 1.3 Physical Mailing Address (8) |
| 5 | Other items (page 1) | 1 | 3 | Part 1.1 - Information About You: Numbers and Names (1), Part 1.3 Physical Mailing Address (1), Part 1.2 Mailing Address (1) |
| 6 | Additional Information | 2 | 8 | Part 1.4 Additional Information (8) |
| 7 | Reason for Application (Select only one box) | 2 | 1 | Part 2 - Application Type (1) |
| 8 | Other items (page 2) | 2 | 3 | Part 2 - Application Type (2), Part 1.4 Additional Information (1) |
| 9 | Part 3.  Processing Information | 3 | 4 | Part 3 - Processing Information (4) |
| 10 | Biographic Information | 3 | 5 | Part 3 - Processing Information (5) |
| 11 | Part 4.  Accommodations for Individuals with Disabilities and/or Impairments | 3 | 2 | Part 4 - Accommodations for Individuals with Disabilities and/or Impairments (2) |
| 12 | Other items (page 3) | 3 | 8 | Part 3 - Biographic Information (4), Part 3 - Processing Information (2), Part 2 - Application Type (1), Part 4 - Accommodations for Individuals with Disabilities and/or Impairments (1) |
| 13 | Part 4.  Accommodations for Individuals with Disabilities and/or Impairments (continued) | 4 | 4 | Part 4 - Accommodations for Individuals with Disabilities and/or Impairments (4) |
| 14 | Applicant's Statement | 4 | 2 | Part 5 - Applicant's Statement, Contact Information, Certification, and Signature (2) |
| 15 | Applicant's Contact Information | 4 | 3 | Part 5 - Applicant's Statement, Contact Information, Certification, and Signature (3) |
| 16 | Applicant's Signature | 4 | 2 | Part 5 - Applicant's Statement, Contact Information, Certification, and Signature (2) |
| 17 | Other items (page 4) | 4 | 1 | Part 5 - Applicant's Statement, Contact Information, Certification, and Signature (1) |
| 18 | Interpreter's Full Name | 5 | 3 | Part 6.1 Interpreter's Name and Business (3) |
| 19 | Interpreter's Mailing Address | 5 | 8 | Part 6.2 Interpreter's Address (8) |
| 20 | Interpreter's Contact Information | 5 | 3 | Part 6.3 Interpreter's Phone Number, Signature and Language (3) |
| 21 | Interpreter's Signature | 5 | 2 | Part 6.3 Interpreter's Phone Number, Signature and Language (2) |
| 22 | Interpreter's Certification | 5 | 1 | Part 6.3 Interpreter's Phone Number, Signature and Language (1) |
| 23 | Preparer's Full Name | 5 | 3 | Part 7.1 Preparer's Name and Business (3) |
| 24 | Preparer's Mailing Address | 5 | 8 | Part 7.2 Preparer's Address (8) |
| 25 | Preparer's Contact Information | 5 | 3 | Part 7.3 Preparer's Phone, Representation, and Signature (3) |
| 26 | Other items (page 5) | 5 | 2 | Part 6.2 Interpreter's Address (1), Part 7.2 Preparer's Address (1) |
| 27 | Preparer's Statement | 6 | 1 | Part 7.3 Preparer's Phone, Representation, and Signature (1) |
| 28 | Preparer's Signature | 6 | 2 | Part 7.3 Preparer's Phone, Representation, and Signature (2) |
| 29 | Other items (page 6) | 6 | 1 | Part 7.3 Preparer's Phone, Representation, and Signature (1) |
| 30 | Your Full Name | 7 | 4 | Part 8.1 - Additional Information Part A (4) |
| 31 | Your Full Name | 7 | 8 | Part 8.1 - Additional Information Part A (4), Part 8.2 Additional Information Part B (4) |
| 32 | Part 8.  Additional Information | 7 | 12 | Part 8.2 Additional Information Part B (8), Part 8.1 - Additional Information Part A (4) |
## w7

- strategy: **printed-heading**
- derived: 1 parts / 9 sections; current kit: 3 parts / 9 sections
- section headings detected: p1 'Name'; p1 'Applicant's Mailing Address'; p1 'Foreign (non-U.S.) Address'; p1 'Birth Information'; p1 'Other Information'; p1 'Sign Here'; p1 'Acceptance Agent's Use ONLY'
- NOTE: 'Other Information' (22 fields) cap-split into 2

| # | derived section | page | fields | drawn from (current kit sections) |
|---|-----------------|------|--------|-----------------------------------|
| 1 | Page 1 (top) | 1 | 15 | Reason you're submitting Form W-7 (13), Application type (check one box) (1), Name (1) |
| 2 | Name | 1 | 6 | Name (5), Applicant's Mailing Address (1) |
| 3 | Applicant's Mailing Address | 1 | 2 | Foreign (non-U.S.) Address (1), Applicant's Mailing Address (1) |
| 4 | Foreign (non-U.S.) Address | 1 | 2 | Birth Information (1), Foreign (non-U.S.) Address (1) |
| 5 | Birth Information | 1 | 4 | Birth Information (3), Other Information (1) |
| 6 | Other Information (1 of 2) | 1 | 20 | Other Information (20) |
| 7 | Other Information (2 of 2) | 1 | 2 | Other Information (2) |
| 8 | Sign Here | 1 | 3 | Sign Here (3) |
| 9 | Acceptance Agent's Use ONLY | 1 | 7 | Acceptance Agent's Use ONLY (5), Sign Here (2) |
## w7-2

- strategy: **printed-heading**
- derived: 1 parts / 9 sections; current kit: 7 parts / 13 sections
- section headings detected: p1 'Name'; p1 'Applicant's Mailing Address'; p1 'Foreign (non-U.S.) Address'; p1 'Birth Information'; p1 'Other Information'; p1 'Sign Here'; p1 'Acceptance Agent's Use ONLY'
- NOTE: 'Other Information' (22 fields) cap-split into 2

| # | derived section | page | fields | drawn from (current kit sections) |
|---|-----------------|------|--------|-----------------------------------|
| 1 | Page 1 (top) | 1 | 15 | Reason you're submitting Form W-7 (11), Additional information for a and f (2), Application type (check one box) (1), Name (1) |
| 2 | Name | 1 | 6 | Name (5), Applicant's Mailing Address (1) |
| 3 | Applicant's Mailing Address | 1 | 2 | Foreign (non-U.S.) Address (1), Applicant's Mailing Address (1) |
| 4 | Foreign (non-U.S.) Address | 1 | 2 | Birth Information (1), Foreign (non-U.S.) Address (1) |
| 5 | Birth Information | 1 | 4 | Birth Information (3), Other Information (1) |
| 6 | Other Information (1 of 2) | 1 | 20 | Previously received ITIN or IRSN (10), Identification document(s) submitted (7), Other Information (2), College/university or company information (1) |
| 7 | Other Information (2 of 2) | 1 | 2 | College/university or company information (2) |
| 8 | Sign Here | 1 | 3 | Sign Here (3) |
| 9 | Acceptance Agent's Use ONLY | 1 | 7 | Acceptance Agent's Use ONLY (5), Sign Here (2) |
## w9-heldout

- strategy: **printed-heading**
- derived: 1 parts / 2 sections; current kit: 0 parts / 0 sections
- section headings detected: p1 'Part I'; p1 'Part II'; p1 'Sign Here'; p1 'General Instructions'; p1 'What's New'; p3 'What Is FATCA Reporting?'; p3 'Updating Your Information'; p3 'Penalties'; p3 'Specific Instructions'; p3 'Line 1'; p5 'Part II. Certification'; p5 'What Name and Number To Give the Requester'

| # | derived section | page | fields | drawn from (current kit sections) |
|---|-----------------|------|--------|-----------------------------------|
| 1 | Page 1 (top) | 1 | 18 | - (18) |
| 2 | Part I | 1 | 5 | - (5) |
