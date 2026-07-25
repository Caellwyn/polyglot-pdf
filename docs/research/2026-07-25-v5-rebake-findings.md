# V5 re-bake + audit findings (bd polyglot-pdf-hif1, epic polyglot-pdf-sekc)

*2026-07-25. The one maintainer-ask spend of the translation-quality-gate
epic: both shipped kits (i-90 + w7) re-baked from scratch through the full
context + glossary + temp-0 forward pass and the verify/rectify loop, so the
shipped translation set is born verified. Rollback tag:
`pre-v5-rebake-2026-07-25`.*

**Purpose lens (maintainer 2026-07-25): every one of these strings is
MODEL-FACING** -- it steers the voice model's spoken-language consistency
(field names, option labels, section titles in the session language). There
is no user-facing display translation; a flag below means "the voice model
might say something off", never "the user sees a wrong form".

## Headline numbers

- Scope: 2 kits x 17 languages = 34 kit-languages; 274 (i-90) + 80 (w7)
  strings verified per language; ~6,000 baked translations total.
- **Actual spend: $4.25** (287 pro calls $4.20 + 92 flash-lite calls $0.05)
  -- inside the approved ~$4-5 worst-case ask.
- Zero failed languages; both kits written in one pass.
- **Deterministic lint sweep over the re-baked kits: 0 findings** (DNT
  intact, ASCII digits, format masks, expected scripts, glossary pins --
  `backend/services/translation_lint.py`, exit 0). Epic criterion 2's
  script check.
- Full backend + scripts test suites green against the re-baked kits.
- Flags: **346 total** -- 257 drift-rectified (the loop caught and fixed
  them in-pass), 2 mechanical-rectified, **73 unresolved** + **14
  ambiguous-source** = the 87-entry human-review worklist below.
- Full flag details (messages + rectify traces): committed artifacts
  [`v5-rebake/i-90-flags.json`](v5-rebake/i-90-flags.json) +
  [`v5-rebake/w7-flags.json`](v5-rebake/w7-flags.json).

## Per-language flag counts (both kits, low-resource first)

| language | rectified | mechanical | unresolved | ambiguous |
|---|---|---|---|---|
| urdu | 3 | 0 | 3 | 0 |
| tagalog | 25 | 0 | 3 | 0 |
| afrikaans | 3 | 0 | 4 | 0 |
| persian | 16 | 0 | 2 | 0 |
| hindi | 5 | 0 | 4 | 5 |
| swedish | 13 | 0 | 10 | 2 |
| ukrainian | 16 | 0 | 12 | 0 |
| korean | 13 | 0 | 1 | 0 |
| arabic | 14 | 2 | 6 | 0 |
| dutch | 5 | 0 | 3 | 0 |
| italian | 12 | 0 | 2 | 0 |
| portuguese | 19 | 0 | 0 | 1 |
| russian | 14 | 0 | 9 | 0 |
| german | 6 | 0 | 6 | 0 |
| french | 15 | 0 | 4 | 2 |
| chinese | 30 | 0 | 0 | 0 |
| spanish | 48 | 0 | 4 | 4 |

Low-resource languages do NOT show elevated unresolved rates -- the worst
worklists are ukrainian (12), swedish (10), and russian (9), all driven by
the systemic clusters below, not by language quality.

## The worklist clusters (what a human reviewer should actually look at)

The 87 worklist entries collapse into a handful of repeated causes:

1. **The w7 "IRSN" false-flag cluster (~24 entries across 8 languages: ur,
   tl, af, hi, ar, nl, de, fr).** The judge repeatedly flagged the three
   `irsn_partN` field names claiming "IRSN should be IRS (never-translate
   list)" -- but the SOURCE says IRSN (Internal Revenue Service Number),
   which is correct and simply is not on the do-not-translate list. The
   rectify loop then flip-flopped (IRSN -> IRS -> IRSN) and correctly kept
   the ORIGINAL under the judge-origin keep rule. **The baked strings are
   right; the flags are judge noise.** Fix: add IRSN to the glossary DNT
   list so the judge stops relitigating it (follow-up bead filed).
2. **The "suite" option (ru + uk, 8 entries).** The judge argued
   transliteration vs. translation for an address-unit type. Kept originals
   are reasonable renderings; low priority.
3. **The Part-7 attorney-attestation texts (most of the 14 ambiguous
   flags, across es/fr/hi/pt/sv).** The source itself is the awkward
   template "...my representation ... extends / does not extend beyond the
   preparation of this application" -- the translator (correctly)
   self-flags it as under-determined. This is a SOURCE quality issue; the
   fix, if any, is clarifying the English label, not the translations.
4. **Name-part field names (first/middle/prior-name variants) in
   sv/uk/ru/ko/it.** Judge quibbles over literal vs. natural renderings of
   short name-part labels; kept originals read fine (confirmed by the
   cross-family audit below, which accepted nearly all of them).

## Cross-family judge audit (Claude second opinion -- once, spike-only)

Per the epic plan, an independent Claude (Sonnet) judge re-reviewed the
ENTIRE final baked set (all ~6,000 pairs, per language, glossary in hand,
zero new API keys -- agent harness only) as a cross-family check on the
Gemini-judged pipeline:

- Claude flagged **7** strings; Gemini's final worklist has **81 distinct
  (language, kit, source-string) triples** (the 87 worklist ENTRIES dedupe
  to 81 because fan-out records one source at several kit paths); overlap
  **1** (a French option that both families flagged). Full methodology,
  per-flag detail, and the cost derivation are committed in
  [`v5-rebake/cross-family-comparison.md`](v5-rebake/cross-family-comparison.md).
- **Claude accepted 80 of Gemini's 81 kept-original worklist strings** --
  strong evidence the keep rules are safe and that most of the unresolved
  worklist is judge over-flagging, not real drift (consistent with cluster
  1 above being noise).
- **Claude-only catches (6) -- real drift the Gemini pipeline cleared:**
  - afrikaans (w7, x3): "Middle name" baked as "Tweede naam" ("second
    name") -- ambiguous next to first/last name; the same form set uses the
    correct "middelnaam" elsewhere.
  - swedish (i-90, x2): "Hispanic or Latino" baked as "Spansktalande..."
    ("Spanish-SPEAKING") -- an ethnicity category rendered as a
    language-ability category.
  - portuguese (i-90): hair color "Sandy" baked as "Loiro-escuro" ("dark
    blond") -- shifts the option into a different color category.
- Takeaway for the epic: the two judge families have nearly disjoint
  false-positive profiles, and the cross-family pass surfaced a small
  number of true misses at zero marginal API cost. Worth repeating at the
  next full re-bake (but not per-bake -- the 6 misses out of ~6,000 confirm
  the in-family loop carries the load).
- The 6 confirmed corrections are filed as a follow-up content-fix bead
  (below) rather than hand-patched here -- shipping decisions on flags stay
  human, and content edits should re-enter the verified pipeline.

## Full worklist (unresolved + ambiguous, low-resource first)

Message texts and full rectify traces are in the committed artifacts; this
is the location index. `U` = drift-unresolved (original kept), `A` =
ambiguous-source.

- **urdu (3):** U w7 irsn_part1/2/3 spoken names (cluster 1).
- **tagalog (3):** U w7 irsn_part1/2/3 spoken names (cluster 1).
- **afrikaans (4):** U w7 previously_received_itin; irsn_part1/2/3
  (cluster 1).
- **persian (2):** U i-90 p2_checkbox2[5] DHS option label; p3_hair_color
  option `sandy`.
- **hindi (9):** A i-90 p7_checkbox7 spoken name + 2 option labels,
  p7_checkbox7extend, p1_line6a_incareofname (clusters 3); U i-90
  p5_line2_nameofrepresentative; U w7 irsn_part1/2/3 (cluster 1).
- **swedish (12):** A i-90 p7_checkbox7 + p7_checkbox7extend (cluster 3);
  U i-90 p1_line5a/5b/5c name parts (cluster 4), p7_line3a_streetnumbername,
  p8 partnumber fields x5; U w7 previously_received_itin.
- **ukrainian (12):** U i-90 unit-type `suite` option labels x4 + spoken
  names x4 (cluster 2), p7_checkbox7 spoken name; U w7
  prior_name_first/middle/last (cluster 4).
- **korean (1):** U w7 prior_name_first (cluster 4).
- **arabic (6):** U i-90 p2_checkbox2[5] DHS option,
  p3_line3a1_cityandstate, p4_line1a_accomodationrequested; U w7
  irsn_part1/2/3 (cluster 1).
- **dutch (3):** U w7 irsn_part1/2/3 (cluster 1).
- **italian (2):** U w7 name_1b_first, prior_name_first (cluster 4).
- **portuguese (1):** A i-90 p7_checkbox7 spoken name (cluster 3).
- **russian (9):** U i-90 unit-type `suite` labels x4 + spoken names x4
  (cluster 2); U w7 prior_name_first (cluster 4).
- **german (6):** U i-90 p3_checkbox5[1], p6_line3e_zipcode; U w7
  previously_received_itin, irsn_part1/2/3 (cluster 1).
- **french (6):** A i-90 p7_checkbox7, p1_line6a_incareofname (cluster 3);
  U i-90 p2_checkbox2[5] DHS option (the one BOTH judge families flagged);
  U w7 irsn_part1/2/3 (cluster 1).
- **spanish (8):** A i-90 p7_checkbox7 spoken name + 2 option labels +
  p7_checkbox7extend (cluster 3); U w7 previously_received_itin + 3 more
  (see artifact).

## Observations under the model-facing lens

- The 257 in-pass rectifications are the gate doing its job: drift is
  caught and fixed before anything ships, and what ships flagged is a
  review queue, not a defect list.
- The i-90 US state option set baked Latin-identical in every language
  (as expected); no state name was flagged by either judge family. The
  identity_sets bead (`polyglot-pdf-mysi`) remains the right cost/bloat fix
  and V5 saw no evidence transliteration is needed for voice consistency --
  the behavioral question stays open for live-session evidence.
- The near-duplicate i-90 source options ("...because of Department of
  Homeland Security" vs "...because of DHS error") confused translators and
  BOTH judge families in several languages -- a source-side quirk of the
  official form's own option list.

## Follow-ups filed

- Content fixes for the 6 cross-family-confirmed drifts, through the
  pipeline (bead filed at closeout; see the epic).
- Glossary: add IRSN to the do-not-translate list to retire cluster 1's
  judge noise (same bead).
