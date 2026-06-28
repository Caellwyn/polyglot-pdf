---
date: 2026-06-28
bead: polyglot-pdf-08zv
title: "G1c: tune the contradiction checker -- tuned per-section prompt + voice model for end-of-form (3.5-flash dropped)"
tags: [performance, testing, postmortem]
---

## Trigger

G1b (0zp3) settled the out-of-band contradiction checker's model choice but left
two residual levers, and G1d (wf3q) gave it a CLEAN, validated corpus so precision
is finally trustworthy. 08zv tunes the two levers on the clean corpus: per-section
PRECISION (the cheap model over-flags) and end-of-form LATENCY (the 132-field sweep
is slow). The bead's starting assumptions -- "use 3.5-flash for the end-of-form
accuracy tier" and "cache the SI to cut latency" -- both turned out to be wrong on
the clean corpus.

## What shipped

A measurement harness + a findings recommendation (this is a measurement bead, no
production wiring):

- **`backend/scripts/probe_g1c_tuning.py`** -- two levers over the clean corpus
  (`g1b_corpus`, `corpus_fp`-stamped) scored by `g1b_scoring`:
  - PRECISION: a `PROMPT_TUNED` (anti-hedging rule + few-shot examples for the
    foreign / territory / dual-address FP buckets) vs the G1b baseline prompt, on
    2.5-flash-lite.
  - LATENCY: 3.5-flash @132 baseline vs payload-trim, plus a cache-feasibility
    token check.
- **`backend/scripts/g1c_aggregate.py`** -- pools repeated precision runs (sum
  tp/fn/fp/tn) so cheap-model per-call noise averages out.
- **`scripts/spikes/g1c_tuning_findings.md`** -- the recommendation + measured
  deltas (exit criterion 3).
- Run data: precision x3 (`g1c_precision_*`), latency x1 (`g1c_latency_*`), and the
  voice-model clean run (`g1b_bakeoff_20260628T092129`).

### The findings (two premises overturned)

**Per-section tier -- prompt win (exit criterion 2).** Pooled over 3 runs on
2.5-flash-lite, `PROMPT_TUNED` cuts false positives ~7x with recall held:
precision 0.77->0.96 at section size (20), 0.89->0.97 at page size (40). The lite
model's FPs concentrated exactly in the three coherent-but-unusual buckets the
clean corpus exposed (foreign addresses, US territories, dual addresses); the
anti-hedging + few-shot prompt fixes them.

**End-of-form tier -- 3.5-flash DROPPED, voice model wins (exit criteria 1+3).**
Re-measuring on the clean corpus overturned two G1b premises:
1. "Cheap models miss far-apart cross-section contradictions -> need 3.5-flash" was
   a CONTAMINATED-CORPUS ARTIFACT. On the clean corpus, 2.5-flash gets recall 1.000
   on every class (cross_date 3/3, duration_year 3/3) at 5x lower cost than
   3.5-flash, and the native-audio VOICE model gets recall 0.963 / precision 1.000.
2. CACHING is inapplicable: caching only helps content that REPEATS byte-identically
   across calls, and the only such content is the 324-token SI+rules prefix (the
   form payload is unique per applicant). 324 is below both cache minimums
   (3.5-flash 4096, 2.5-flash 2048), so the prefix can't cache on either model.
   (The FULL prompt is ~2908 tokens, which does exceed the 2.5-flash 2048 minimum --
   but that is irrelevant, since the full prompt never repeats.) Payload-trim is a
   net loss (precision 0.90->0.79; the model needs field names for meaning).

The end-of-form winner is the **native-audio voice model** (maintainer steer: it is
cheaper than 3.5-flash and already connected): recall 0.96, precision 1.00,
**p50 7.4s / p90 9.3s @132** -- ~3x faster than 2.5-flash (p50 23s), cheaper than
3.5-flash, zero new model dependency.

### CRITICAL production constraint -- fresh session, never the connected one

The end-of-form voice check MUST run on a brand-new, isolated Live session carrying
ONLY the checker SI + form payload, NOT the user's connected form-fill session.
Reusing the connected session would re-bill the ENTIRE conversation history (every
prior voice turn) as input on the check call. The probe measured it correctly --
`_run_live` opens a fresh `client.aio.live.connect` per call with
`system_instruction=_LIVE_SI` and the payload as the sole turn, cost basis
`count_tokens([_LIVE_SI, payload])` only -- and the measured cost/latency is only
valid under a fresh session. Recorded in the findings doc + on the bead for the
production-wiring beads (jnjj.16/jnjj.17).

## Recommendation

- Per-section checker: 2.5-flash-lite + `PROMPT_TUNED`.
- End-of-form checker: the native-audio voice model via a `report_conflicts` tool
  call on a FRESH ephemeral Live session.
- Drop 3.5-flash; do not pursue caching or payload trimming.

## Doc freshness

This bead's surface is the bake-off spike harness (`backend/scripts/g1c_*.py`,
`g1b_*.py`) + `scripts/spikes/`. No tier-1/tier-2 doc has a `**Tracks:**` glob over
those paths, so there is no surface doc to bump. The new findings doc
(`g1c_tuning_findings.md`) is the spike record, alongside the existing
`g1b_bakeoff_findings.md`.

The closeout doc-freshness check flagged ~20 STALE tier-2 docs, but every one
tracks runtime code from the secretary/DTI commits that merged into dev on
2026-06-27 (`backend/routes/`, `backend/adapters/`, `backend/config.py`,
`backend/services/`, `frontend/`) -- NOT files this branch touched. They were stale
before this work; left as-is per the doc-maintenance rule (only bump a stale doc
whose tracked files THIS branch changed).

Beads housekeeping flagged 1 orphan + 4 stale `in_progress`. The orphan
(`polyglot-pdf-jnjj.45`, the secretary) merged but was not closed -- it is the
maintainer's bead, surfaced to them rather than closed as part of this unrelated
closeout. The 4 stale beads (`hrn`, `jf6w`, `ue5s`, `jnjj.46`) are not this PR's
and are left untouched.

## Telemetry gap

`harness_ledger.py` could not locate the session transcript JSONL (the session
switched worktrees mid-run via EnterWorktree, so the sanitized-cwd lookup points at
the new worktree path while the transcript lives under the original session dir --
the known `--transcript after EnterWorktree` issue). Telemetry is warn-only, so the
row was skipped rather than blocking the closeout; noted here for the record.

## Files touched

- `backend/scripts/probe_g1c_tuning.py` (new) -- precision + latency levers.
- `backend/scripts/g1c_aggregate.py` (new) -- pooled run aggregator.
- `scripts/spikes/g1c_tuning_findings.md` (new) -- recommendation + measured deltas.
- `scripts/spikes/data/g1c_precision_*.{csv,meta.json}` x3 (new) -- precision runs.
- `scripts/spikes/data/g1c_latency_20260627T194907.{csv,meta.json}` (new) -- 3.5-flash
  latency + cache-feasibility run (kept as the evidence 3.5-flash is dropped).
- `scripts/spikes/data/g1b_bakeoff_20260628T092129.{csv,meta.json}` (new) -- the
  voice-model clean-corpus run.
