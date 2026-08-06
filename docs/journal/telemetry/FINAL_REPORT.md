# Harness A/B experiment -- FINAL report

**Bead:** polyglot-pdf-hrn.17 (parent epic polyglot-pdf-hrn, "Harness tuning").
**Plan of record:** [`docs/sprint_1_harness-tuning_plan.md`](../../archive/sprint_1_harness-tuning_plan.md)
(section "A/B testing strategy").
**Data:** all rows in `docs/journal/telemetry/*.json` plus the legacy
`docs/journal/harness_ledger.jsonl`, deduped by `(session_id, recorded_at)`.
Snapshot taken 2026-07-04 (199 rows total).

This is the report the per-closeout directive has been asking for since 2026-07-02
("Combined arm done (arm_BC > 10) -- write the FINAL report"). Writing it also
flips the directive off (see "Closing the experiment" below).

---

## TL;DR -- what to keep

| Change | Verdict | Why |
|--------|---------|-----|
| **#1 telemetry ledger** (`harness_ledger.py`) | **KEEP** | It is the measurement substrate; already load-bearing in closeout. Not an arm. |
| **B -- fresh-eyes model tiering** (Haiku on small diffs) | **KEEP (already default)** | 0 errors shipped, 0 Haiku self-escalations in-sample; no downside observed. Under-powered as an isolated arm, but the failure mode it guards (a cheap model missing a real bug) never fired. |
| **C -- bounded review loop** (defer nits, ambiguous=blocker) | **KEEP (already default)** (see caveat) | 0 errors shipped; deferred-nit convention worked (10 nits deferred across the sample, none later re-classified as blockers). **Caveat:** C-alone recorded no counters (see "under-powered" below) -- this KEEP rides on the BC result, not C's own data. |
| **BC combined (B+C together)** | **ADOPT as the standing default** | Lowest maintainer-touchpoint rate of any arm (0.33 vs baseline 0.98), 0 errors shipped. This is effectively how closeout already runs. |

**Bottom line:** B and C are both retained and are already the de-facto default;
the combined BC configuration is adopted as the standing harness. **No arm shipped
a single regression** (errors_shipped summed to 0 across all 138 production rows
that recorded the counter), so the adoption rule's guardrail ("adopt whatever beats
A without a worse error rate") is satisfied trivially -- the decision comes down to
cost/speed/touchpoints, where BC wins on touchpoints and ties on error rate.

---

## The honest caveat up front: this experiment is under-powered on cost

The plan's design was: baseline A (>15 rows) -> independent B and C arms (each >10)
-> combined BC (>10). **That sequence was not followed cleanly.** What the ledger
actually holds (production rows only -- `audit`-category measurement work is never
charged to an arm, per the plan's fairness rule):

| Arm | production rows | rows with a USD cost block |
|-----|-----------------|----------------------------|
| A (baseline) | 127 | 22 |
| B (tiering only) | 3 | 0 |
| C (bounded loop only) | 7 | 0 |
| BC (combined) | 18 | 6 |

Two structural problems the reader must keep in mind:

1. **B and C never reached their `>10` independent thresholds.** B has 3 rows, C
   has 7. The experiment jumped from baseline straight to the combined arm. So the
   "is B alone worth it / is C alone worth it" question **cannot be answered from
   this data** -- only "is B+C together worth it vs baseline." C in particular
   recorded **no** babysitting counters at all (all null), so C-alone has literally
   no comparable signal.
2. **USD cost was added to the row schema late** (bd polyglot-pdf-cb6i), so only
   recent rows carry `cost_usd`. Cost means are computed over 22/127 (A) and 6/18
   (BC) rows -- a thin, recency-biased slice, **not** a representative cost
   comparison. Treat every dollar figure below as directional, not decisive.

Given both, the defensible recommendation leans on the metrics that have real n
(maintainer touchpoints, review rounds, errors shipped) and treats cost as
supporting colour only.

---

## Per-arm numbers

Metrics are per-PR means; `n=` is how many rows carried that field. All figures are
**production** rows only.

### Baseline A (n=127)
- Maintainer touchpoints: **0.98** (n=120)
- Review rounds: 0.94 (n=114)
- Deferred nits: 0.06 (n=114)
- Haiku self-escalations: 0.00 (n=114)
- **Errors shipped: 0.00 (n=113)**
- Cost/PR: mean $114.22, median $77.71 (n=22 only -- thin)

### Arm B -- fresh-eyes tiering only (n=3)
- Review rounds: 0.33 -- Touchpoints: 0.00 -- Errors: 0.00 (n=3)
- No cost block on any B row. Sample far too small to rank; recorded for completeness.

### Arm C -- bounded loop only (n=7)
- **No counters recorded on any C row** (all null) and no cost block. C-alone yields
  no usable signal; it is retained on the strength of the BC result, not its own.

### Arm BC -- combined (n=18)
- Maintainer touchpoints: **0.33** (n=15) -- roughly one third of baseline
- Review rounds: 1.67 (n=15) -- higher than A, discussed below
- Deferred nits: 0.00 (n=15)
- Haiku self-escalations: 0.00 (n=15)
- **Errors shipped: 0.00 (n=15)**
- Cost/PR: mean $496.82, median $576.44 (n=6) -- **heavily distorted, see below**

---

## The #282-#284 cost distortion (flagged, per the bead)

The bead explicitly warned that several BC rows were recorded in sessions where
Codex was quota-exhausted and the **Opus-4.8 fallback reviewer** ran instead, and
that those rows should be flagged rather than treated as typical BC costs. Those are
PRs **#282 / #283 / #284** (2026-07-02), which map to beads **92qe.3 / 92qe.4 /
92qe.5**.

Of the 6 BC rows that carry a cost block, **3 are these flagged rows** -- and they
are the three most expensive:

| BC row (recorded_at) | bead | cost | fallback reviewer? |
|----------------------|------|------|--------------------|
| 2026-07-02T04:56Z | 92qe.1 | $162 | no |
| 2026-07-02T05:49Z | 92qe.2 | $444 | no |
| 2026-07-02T07:10Z | **92qe.3 (PR #282)** | **$708** | Codex-exhausted window |
| 2026-07-02T07:50Z | **92qe.4 (PR #283)** | **$812** | Opus-4.8 reviewer ran |
| 2026-07-02T08:14Z | **92qe.5 (PR #284)** | **$851** | Opus-4.8 reviewer ran |
| 2026-07-02T21:52Z | fyq4 | $2 | no |

- BC cost **including** the flagged rows: mean $497, median $576.
- BC cost **excluding** the flagged rows (3 clean costed rows): **mean $203, median
  $162.**

So more than half the "BC is expensive" signal is the fallback reviewer, not the BC
harness. **Do not read BC as a ~$500/PR arm** -- its clean costed rows sit near $200,
and even that is 3 heavy feature-work PRs (the 92qe hosted-extraction epic), not a
like-for-like basket against baseline A's mix. The elevated BC **review-rounds**
number (1.67) is partly the same story: the fallback-reviewer sessions ran extra
rounds. This is a measurement artifact of a reviewer outage, not a property of the
B+C harness changes.

---

## Adoption decision (against the plan's rule)

The plan's adoption rule: *adopt either/both of B/C that beat A on
cost/speed/touchpoints **without** a worse error-shipped rate; the combined arm
validates B+C > A.*

- **Error-shipped rate:** 0 everywhere. No arm regresses the guardrail. (This is the
  gate, and every arm passes it.)
- **Maintainer touchpoints:** BC 0.33 vs A 0.98 -- BC clearly wins the metric that
  most directly reflects "did this save the maintainer's attention," which is the
  epic's actual objective ("stop burning tokens and maintainer attention").
- **Cost:** inconclusive by construction (thin, confounded). Not used to decide.
- **B-alone / C-alone:** cannot be isolated (thresholds unmet). Adopted on the BC
  result plus the absence of any observed downside.

**Decision: keep B and C; adopt BC as the standing default.** In practice closeout
already runs this way (Haiku-tiered fresh-eyes + bounded review loop), so adoption
is a ratification of current behaviour, not a change. The experiment's value was
confirming that behaviour ships **zero** regressions while cutting maintainer
touchpoints ~3x against the pre-experiment baseline.

---

## What the experiment did NOT establish (honest limits)

- **No clean B-vs-C separation.** We know B+C together is safe and low-touch; we do
  **not** know the marginal contribution of each. If that ever matters, it needs a
  fresh run that actually holds each arm to its `>10` threshold.
- **No trustworthy cost curve.** The cost block arrived late and the richest BC
  sample coincided with a reviewer outage. Cost claims here are directional only.
- **Guardrail = 0 is partly a low-stakes-sample property.** This is pre-production
  work; "0 errors shipped" reflects both good harness behaviour and the fact that
  these were mostly harness/doc/small-feature PRs. It is evidence, not proof, that
  the cheap-model tiering never misses a real bug.

These limits are why the recommendation is "ratify current behaviour," not "we
proved BC is cheaper."

---

## Closing the experiment

The per-closeout directive (`harness_ledger.py --print-directive`) fires
"Combined arm done -- write the FINAL report" whenever `arm_BC > 10`. Since the
counter is **derived by counting rows** (and rows are never deleted), that condition
stays true forever -- the directive would nag on every future closeout.

To stop it without corrupting the row-derived counter, this report drops a committed
sentinel, **`docs/journal/telemetry/REPORT_DONE`**, that names this file.
`phase_directive()` checks for that sentinel first and, when present, returns a
terminal "experiment closed" directive instead of the write-the-report nag. The
arm counts remain fully re-derivable from the rows; only the *directive* is
short-circuited. To re-open the experiment (e.g. a clean B-vs-C rerun), delete the
sentinel.
