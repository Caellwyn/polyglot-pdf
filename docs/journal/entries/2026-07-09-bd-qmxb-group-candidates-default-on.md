---
date: 2026-07-09
bead: polyglot-pdf-qmxb
title: "Group-candidates default-ON + deterministic family-completion safety net"
tags: [extraction, authoring, harness]
---

## Trigger

The "fix the system, not the individual form" follow-up to bd 0nxh (i-90 Part-2
Q3 shipped with only 1 of its 5 P2_checkbox3 select-one checkbox widgets modeled).
Root cause (per the 3fz7/0nxh investigation): the extractor's LLM pass
stochastically DROPS option-widgets when consolidating a "select one/all of N
checkboxes" question, and no deterministic pass recovers the GROUP -- backfill
(w0eq) adds dropped widgets as loose booleans, and the widget-type retype was
built then removed (w0eq) because type can't distinguish single- from
multi-select. Bead 1 of a small epic (qmxb -> ox6y measure -> aw1u paid verify).

## What shipped

Two changes in `scripts/authoring/extract_form.py`, both reusing existing,
closed machinery -- no new heuristics:

1. **group-candidates default-ON** (the deferred P5.3 switch-on). `extract()` and
   the CLI now default `group_candidates=True` (with a `--no-group-candidates`
   opt-out); the low-level `arm_llm_native.build_prompt`/`run` keep their neutral
   `False` default. The h76m.12 ablation already proved this is the fix: ON, the
   LLM ADOPTS the mined family as ONE field with every option correctly
   widget-mapped; OFF, it SPLITS into unmappable checkboxes. It was left OFF only
   "until P5.2 repair lands" -- repair (h76m.13, CLOSED) now owns the ON-arm's
   repairable vocabulary defects (duplicate on-value slugs -> label-minted slugs;
   invented `or` -> any_of). Held-out w9 was identical across arms (no regression).

2. **`_complete_grouped_families` safety net** (step 3c2, BEFORE the 3d backfill).
   The hint reduces but cannot eliminate stochastic drops, so this deterministic
   pass backstops it: for each family from `find_group_candidates(dump)`, if
   EXACTLY ONE field owns it (claims >=1 member via an option AND 0 < claimed <
   all), the missing members are appended as options of THAT SAME field. It NEVER
   changes the field's type -- single-vs-multi is the LLM's semantic call, already
   made; we only complete the option set, so the removed-retype trap is not
   re-opened. Every ambiguous case SKIPS (family split across fields; 0 claimed
   false-positive; already complete), and the 3d backfill still guarantees no
   widget silently vanishes. Provenance records `group_completion`.

## Verification (offline, no paid tokens)

- Tier 1 (`tests/test_extract_form_group_completion.py`, synthetic dump): the
  0nxh shape (1 of 5 modeled) completes to all 5 as options of the same field,
  type unchanged (radio AND checkbox_group cases); the 3 skip negatives; no-dump
  no-op.
- Tier 2 (real i-90 dump, no LLM): `find_group_candidates` surfaces the
  P2_checkbox3[0..4] + P2_checkbox2[0..11] families, and the completer recovers
  all 5 P2_checkbox3 from a simulated 1-of-5 drop -- the exact 0nxh bug, now
  auto-fixed.
- Full backend + tools suite: 1749 passed.

Deferred to the follow-up beads: adding i-90 to `eval_extraction._FORMS` to
MEASURE coverage (ox6y), and ONE paid Vertex re-extraction end-to-end (aw1u).

## Doc freshness

No tier-2 doc tracks scripts/authoring or scripts/bakeoff; this entry is the
record. The stale default-OFF comments in extract_form.py were refreshed.
