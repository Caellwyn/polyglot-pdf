---
date: 2026-07-23
bead: polyglot-pdf-tupu.4
title: "test(i18n): Epic B verification sweep -- 12 runs, zero spoken-name secretary queries, zero English field-name readouts"
tags: [harness, testing]
---

## Trigger

Epic polyglot-pdf-tupu's final bead: the n>=3-per-language behavioral sweep
the epic rubric requires, run at the tupu.2 PR head (#466) against the
2026-07-22 baselines.

## What shipped

- 12 committed run sets (es/zh/hi/fr x3, stamps 20260723T043827Z..050312Z,
  ~$7.9) + the findings-doc sweep section scoring the epic rubric.
- Headline: ZERO spoken-name secretary queries in 12/12 runs (baseline: fr
  asked on 14/14 questions); zero raw-English field-name readouts; greetings
  and guidance fully in-language; hi 42/42 fills. Residuals recorded: one
  3-word English filler in one hi run; one zh mid-run STALL (6/14 -- NOT the
  wrong-field desync; zero wrong-field fills in all 3 zh runs) -- the
  stall/desync family stays with bd 66ek.1 (r5m7).

## Lessons

- The mechanism-tied rubric criterion (zero NAME queries, volume as a
  diagnostic) paid off exactly as designed: one es run had 14 secretary
  calls, all recall/status -- attributable at a glance instead of
  contaminating the epic's verdict.

## Doc freshness

Findings doc extended (the experiment record). No tier-1/2 docs track the
data files; pre-existing stale set unchanged (recorded in the prior sprint-13
entries).

## Files touched

- scripts/spikes/multilingual_ux_findings.md (sweep section)
- scripts/spikes/data/costs_i90-full_2.5_dti_cont_happy_20260723T0[45]* (12
  run sets) + this entry
