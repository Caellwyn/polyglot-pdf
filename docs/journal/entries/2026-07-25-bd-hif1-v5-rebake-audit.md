---
date: 2026-07-25
bead: polyglot-pdf-hif1
title: "V5: full re-bake + audit through the pipeline (i-90 + w7 x 17 languages)"
tags: [extractor, testing]
---

## Trigger

The one maintainer-ask spend of the translation-quality-gate epic
(`polyglot-pdf-sekc`, plan V5 section): regenerate both shipped kits'
translations through the upgraded pipeline (context-carrying forward pass +
glossary + temp 0 + the verify/rectify loop) so the shipped set is born
verified, and deliver the per-language flag worklist + findings. Spend
pre-authorized by the maintainer at session start ("you have the go ahead
for V5"); scope was previously narrowed to the 2 shipped kits (i-90 + w7,
maintainer 2026-07-25).

## What shipped

- Rollback tag `pre-v5-rebake-2026-07-25` (pushed), then a `--force` re-bake
  of i-90 + w7 across all 17 non-English languages via
  `translate_option_labels.py` with `--flags-out` artifacts. Zero failed
  languages. **Actual spend $4.26** (287 pro + 92 flash-lite calls) vs the
  ~$4-5 approved worst case.
- The deterministic lint sweep over the re-baked kits: **0 findings**
  (`backend/services/translation_lint.py`, script-checked -- epic criterion
  2). Full backend + scripts suites green against the re-baked kits.
- Deliverables: `docs/research/2026-07-25-v5-rebake-findings.md` (headline
  numbers, per-language table, the 87-entry unresolved+ambiguous worklist
  low-resource-first, cluster analysis, model-facing observations) + the
  two committed flag artifacts under `docs/research/v5-rebake/`.
- The V4 surfacing shipped one PR earlier, so the re-bake's flags also ride
  each kit's `_bakeoff.authoring.option_translation`... note: the CLI bake
  does NOT persist provenance (by design -- V4 scoped provenance to
  extraction + editor route); the committed artifacts + findings doc are
  the CLI-path record.
- Cross-family judge audit (once, spike-only, per plan): 17 Claude (Sonnet)
  subagents re-judged the ENTIRE final baked set (~6,000 pairs) with the
  glossary -- zero new API keys, agent harness only. Result: 7 Claude
  flags vs Gemini's 81-string worklist, overlap 1; Claude accepted 80/81
  of the kept originals (keep rules validated); 6 Claude-only real drifts
  (afrikaans "middle name" as "second name" x3, swedish "Hispanic" as
  "Spanish-speaking" x2, portuguese "Sandy" hair as "dark blond") filed as
  a follow-up content-fix bead together with pinning IRSN as
  do-not-translate (the w7 IRSN judge-noise cluster, ~24 false flags
  across 8 languages).
- Fresh-eyes triage: (filled at closeout -- see PR.)

## Lessons

- **Cross-family judging has a nearly disjoint false-positive profile.**
  The in-family judge (Gemini judging Gemini) over-flags short label
  quibbles and DNT-substring lookalikes (IRSN vs IRS) but cleared six real
  category errors; the out-of-family judge caught exactly those six and
  none of the noise. One cross-family sweep per full re-bake is cheap
  (agent harness, no API keys) and worth repeating; per-bake it is not
  needed -- 6 misses in ~6,000 strings confirms the in-family loop carries
  the load.
- **DNT lists need the acronym's SUPERSTRINGS considered.** "IRSN contains
  IRS" produced the single largest worklist cluster -- pure judge noise
  that burned rectify credits in 8 languages. When pinning short acronyms,
  check the kit for longer tokens that embed them.
- A ~48k-line non-English kit diff is unreviewable line-by-line, as the
  plan predicted -- the flag list + lint sweep + cross-family audit ARE the
  review; the PR body should say so plainly.

## Doc freshness

- New: `docs/research/2026-07-25-v5-rebake-findings.md` + artifacts.
- No tier-1/tier-2 doc tracks `form-kits/` content; the sprint plan doc was
  already updated (V4's rider). Reviewed and left as-is.

## Files touched

- `form-kits/i-90/schema.json` -- full 17-language re-bake (verified)
- `form-kits/w7/schema.json` -- full 17-language re-bake (verified)
- `docs/research/v5-rebake/i-90-flags.json` -- flag artifact (full messages + traces)
- `docs/research/v5-rebake/w7-flags.json` -- flag artifact
- `docs/research/2026-07-25-v5-rebake-findings.md` -- findings + worklist
