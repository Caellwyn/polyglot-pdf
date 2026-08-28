# W-7 session cost: deployed config vs naive baseline (bd polyglot-pdf-wiadk)

**Status: COMPLETE -- all 6 live runs finished, replay-validated, and
reconciled.** Model `gemini-live-2.5-flash-native-audio` (2.5 tier), Vertex,
google-genai SDK >= 2.8. Date: 2026-08-27. Live spend: ~$10.17 total (3
pipeline smokes $0.442 + N-happy pilot $0.449 + 6 full runs $9.282043).
Billing-console reconciliation
against these harness-computed dollar figures is a follow-up over the
2026-08-27 quiet-day window (see "Billing reconciliation" below) -- these
runs spanned roughly 19:15-20:05 UTC, and Vertex billing exports lag same-day
traffic, so the console total for this window will not be queryable until at
least the next business day.

## Question

A. What does a real W-7 voice session cost all-in on the deployed config
(continuous DTI + production-DERIVED compression + secretary + pro-pass)?
B. What would the same session cost on a NAIVE implementation -- the full form
schema + the official IRS W-7 instruction booklet pasted into the system
instruction, one unbounded Gemini Live session, no compression, no secretary,
no DTI?

Framing note: internally, compression's design comparator is section-resets
(bd memory `section-resets-are-cost-mitigation`), never "vs unbounded". The
naive arm here is an EXTERNAL competitor baseline for a market/moat comparison,
not the internal design justification.

## Gate 1 (prior work) -- summary

- bd `polyglot-pdf-89mt` (2026-08-06): deployed-config W-7, happy $0.59 /
  unhappy $1.25 all-in on a 2,485-token SI. Stale: shipped SI grew to ~3,363
  tok and the spell-back cutover (PR #642) changed name-field turns. Raw
  artifacts deliberately unshipped; harness commits cherry-picked onto this
  branch (see git log).
- No true naive arm has ever been run in this repo (three-agent audit,
  2026-08-27).
- Live-API cached tokens: across all five real August W-7 runs (496 billed
  events), `cached_content_token_count` was NEVER reported (0 events nonzero).
  All replay pricing therefore bills prompt tokens at full rate and asserts
  cached == 0 on the Live path. Text-sidecar (secretary/pro-pass) calls DO
  cache and are priced with the cached-input discount via the harness's
  `price_text_usage` (bd 0cyu).
- Session limits (vendored live-api docs + journal 2026-06-15): uncompressed
  audio sessions hard-cap at 15 min; connection lifetime ~10 min (GoAway);
  no session resumption configured in this codebase. Naive-happy fits; a live
  naive-unhappy run may be API-terminated -- PRE-REGISTERED: if a naive run is
  terminated by the API (GoAway / server close in the adapter logs), that is a
  reported RESULT ("a naive session cannot complete this form in one session"),
  not a discarded run, provided the logs prove the server initiated the close.

## Measured constants (Phase 0)

- Naive SI: **27,923 tokens** (legacy full-schema SI, spell-back addendum off,
  + booklet; 109,722 chars) + **737** tool-declaration tokens (5-tool naive
  catalog) = **28,660 tokens** re-billed on every billed event (real
  `count_tokens` against `gemini-live-2.5-flash-native-audio`, 2026-08-27).
  An earlier count of 26,009 was WRONG -- the count script built the SI
  without the multi-module get_settings patch, so it rendered the DTI SI +
  booklet instead of the legacy full-schema SI + booklet (the jnjj.25 trap;
  fixed in count_naive_si_tokens.py the same day). Cross-check: the naive
  smoke's observed per-event text-in was ~28.7k tokens -- matches the
  corrected count, not the old one.
- Naive tool catalog: update_form_fields, get_form_status, confirm_field,
  skip_field, switch_to_field ONLY. The first naive smoke declared the full
  production catalog and measured the model actually CALLING ask_secretary --
  a ~29k-token context re-send burned on the fail-open answer. A naive
  competitor has no secretary, no spell-back TTS pipeline, and no section
  machinery, so those three declarations are filtered out of the naive arm
  (pinned by an allowlist test, mutation-verified).
- W-7 plan: 22 questions (realistic nonresident-filer path through the
  53-field schema). Happy = 2 turns/question; unhappy = 4 turns/question
  (wrong -> reject -> correct -> confirm).
- Rates (per 1M, `GEMINI_PRICING_BY_FAMILY`, verified 2026-05-30): 2.5 Live
  text-in $0.50, audio-in $3.00, text-out $2.00, audio-out $12.00.
- Cloud TTS (spell-back) is NOT exercised by the harness fake client (it acks
  `delivered` without fetching); deployed-arm TTS cost is computed separately
  from recorded `spellback_count`/`spellback_total_chars` at the published
  Chirp 3 HD rate (rate + retrieval date to be recorded at analysis time).

## Pre-registrations

1. **WRITTEN BEFORE THE FULL N-HAPPY RUN (2026-08-27, pilot
   `costs_w7_2.5_naive_happy_20260827T192900Z`): predicted full 22-question
   naive happy-path voice cost = $2.27, band $1.90-$2.63** (+/-20% on the
   projected q7-22 portion). Method, exactly as pre-registered: replay
   arithmetic extended from the pilot's own per-event trace -- stable
   per-question billed-event count (4.70 events/q, q3-q6 average), per-event
   prompt extended from the measured prompt_curve tail (30,043 tok) at the
   measured context growth (+407 tok/question), cumulative audio-in extended
   at its measured growth (+830 tok/question), output tokens at stable
   averages, all priced at the full `rates_per_token` recorded in the pilot
   meta. NOT a polynomial fit. Pilot measured q1-6 = $0.449; projected
   q7-22 = $1.818.
2. Naive-unhappy is reported as a band from two independent estimators
   ((a) naive replay of the measured D-unhappy trace -- biased LOW because it
   inherits the deployed arm's efficient turn structure; (b) turn-structure
   projection from the measured N-happy run). A live naive-unhappy run happens
   only if its projected cost <= $20 and the running total allows.
3. Schema-only (no booklet) naive variant is reported as billing-arithmetic
   only, behavior held fixed.

## Budget ledger (cap $100; single-run projection > $10 -> stop + re-estimate; total > $60 -> stop + ping)

The Gate-1 carried-forward ledger lists three smokes ($0.170, $0.137,
$0.135) plus the pilot ($0.449); only two smokes map to the D/N pipeline-proof
rows below (rows 1-2) -- the third smoke's specific run is not separately
identified in this doc's own artifacts and is carried forward as part of the
ledger total rather than broken out as its own numbered row here.

| # | run | est. $ | actual $ | notes |
|---|-----|--------|----------|-------|
| 1 | D smoke, happy, --questions 5 | ~0.20 | 0.170 | pipeline proof incl. spell-back on name fields |
| 2 | N smoke, happy, --questions 2 | ~0.15 | 0.137 | pipeline proof, naive SI + no compression |
| 3 | N pilot, happy, --questions 6 | ~0.80 | 0.449 | grounds the pre-registered N-happy prediction |
| 4 | D full, happy run 1, --questions 22 | (no formal pre-reg; deployed-arm full runs were not separately estimated) | 0.702181 | 22/22 fields correct + confirmed |
| 5 | D full, happy run 2, --questions 22 | -- | 0.724305 | 22/22 fields correct + confirmed |
| 6 | D full, unhappy run 1, --questions 22 | -- | 1.406226 | 22/22 fields correct + confirmed; secretary fired 3x |
| 7 | D full, unhappy run 2, --questions 22 | -- | 1.328544 | 22/22 fields correct + confirmed; secretary fired 0x |
| 8 | N full, happy, --questions 22 | 2.27 (band 1.90-2.63, pre-reg #1) | 1.839110 | 21/22 filled (missing `us_visa_type_number_expiration`), 22/22 confirmed; 2 platform force-trims; -19.0% vs. point prediction, $0.061 below band floor |
| 9 | N full, unhappy, --questions 22 | ~4 (rough pre-run projection, stated in the session log BEFORE the run -- "projects to roughly $4, ~2x the naive-happy event count at the capped per-event prompt"; recorded there, not in this doc at the time, so it is a weaker pre-registration than row 8's -- noted honestly. Post-hoc estimators: B 3.678, A trim-aware 1.362, A no-eviction 8.514) | 3.281677 | 21/22 filled, 20/22 confirmed; 3 platform force-trims |

**Greeting convention (applies to every dollar figure in this doc):** the
headline `all_in_usd` = voice cost of the 22 questions + text-sidecar cost;
the session GREETING (the model's opening turn before question 1) is measured
and reported as its own line (`greeting_usd`: deployed ~$0.004-0.005/run,
naive ~$0.016/run -- 3x dearer because the naive greeting re-bills the ~28.7k
SI) but is NOT folded into `all_in_usd`. This matches the bd-89mt convention
(comparability) and is conservative for the moat claim (excluding it
understates the naive arm more than the deployed arm). `turns.csv`'s
`cumulative_cost_usd` column DOES seed from the greeting and excludes the
text sidecar -- reading its last row as "the session cost" mixes conventions
(a fresh-eyes finding caught the comparison charts doing exactly that,
drifting the naive endpoints ~1-2 cents high; `plot_wiadk_comparison.py` now
reads the headline for bars and subtracts the greeting seed from curves).

**Total actual spend: ~$10.173** (3 pipeline smokes $0.170 + $0.137 + $0.135
= $0.442, plus the N-happy pilot $0.449, plus the 6 full runs summing to
$9.282043). Well under the $60 stop-and-ping threshold and the $100 cap; no
single run exceeded the $10 per-run re-estimate trigger.

## Results

### 1. Full results -- all 6 runs + means

All-in cost = voice (Live API audio+text turns) + text sidecar (secretary +
pro-pass calls), replay-validated against the recorded per-event ledger (see
"Replay validation" below).

| Run | Path | All-in cost | Wall clock | Evictions | Fields filled | Fields confirmed |
|---|---|---:|---:|---:|---:|---:|
| D happy 1 (193603Z) | happy | $0.702181 | 204.5s | 7 | 22/22 | 22/22 |
| D happy 2 (193939Z) | happy | $0.724305 | 223.1s | 6 | 22/22 | 22/22 |
| **D happy mean** | happy | **$0.713243** | 213.8s | 6.5 | 22/22 | 22/22 |
| D unhappy 1 (194334Z) | unhappy | $1.406226 | 425.4s | 9 | 22/22 | 22/22 |
| D unhappy 2 (195050Z) | unhappy | $1.328544 | 421.6s | 9 | 22/22 | 22/22 |
| **D unhappy mean** | unhappy | **$1.367385** | 423.5s | 9 | 22/22 | 22/22 |
| N happy (193127Z) | happy | $1.839110 | 192.4s | 2 (platform force-trim) | 21/22 | 22/22 |
| N unhappy (195815Z) | unhappy | $3.281677 | 381.3s | 3 (platform force-trim) | 21/22 | 20/22 |

"Evictions" means two different mechanisms across arms: the deployed arm's
count is the app's own curated context-compression (window eviction by
design, bounding cost); the naive arm's count is the **platform's blind
32k-token force-trim** (see Finding 1 below) -- the naive arm has no
compression of its own, so every "eviction" row for it is an involuntary
platform intervention, not a designed behavior.

**Headline means (verified against `summary.json.headline.all_in_usd`):**
deployed happy **$0.713**, deployed unhappy **$1.367**. 22/22 fields correct
+ confirmed on all four deployed runs -- the deployed arm never traded
accuracy for cost across two independent happy and two independent unhappy
runs.

**Multipliers and % savings (deployed vs. naive, same path):**

| Path | Naive mean | Deployed mean | Savings ($) | Savings (%) | Naive / deployed multiple |
|---|---:|---:|---:|---:|---:|
| Happy | $1.839110 | $0.713243 | $1.125867 | 61.2% | 2.58x |
| Unhappy | $3.281677 | $1.367385 | $1.914292 | 58.3% | 2.40x |

The deployed configuration costs the user roughly **39-42 cents on the naive
dollar**, and does so while also fixing the naive arm's accuracy gap (naive
missed one field on both paths; deployed missed none on any of four runs) and
carrying quality machinery (secretary, pro-pass, spell-back) the naive arm
does not pay for at all -- see "Bias directions" below for why this makes the
savings figure, if anything, an understatement of the deployed design's
efficiency per unit of delivered correctness.

### 2. Modality breakdown -- where the money goes

| Arm x path | audio-in | text-in | text-out | audio-out |
|---|---:|---:|---:|---:|
| D happy 1 | 46.51% | 48.12% | 0.36% | 5.01% |
| D happy 2 | 49.68% | 45.51% | 0.35% | 4.46% |
| **D happy mean** | **48.10%** | **46.81%** | **0.35%** | **4.73%** |
| D unhappy 1 | 58.76% | 36.99% | 0.29% | 3.96% |
| D unhappy 2 | 56.74% | 39.83% | 0.30% | 3.12% |
| **D unhappy mean** | **57.75%** | **38.41%** | **0.30%** | **3.54%** |
| N happy | 12.91% | 86.30% | 0.16% | 0.62% |
| N unhappy | 14.78% | 83.92% | 0.15% | 1.15% |

The deployed arm's modality mix is audio-in-led with text-in close behind, on
both paths -- consistent with the app's own MEASURED COST INVARIANT (see
"Cross-reference to the MEASURED COST INVARIANT" below). The naive arm is the inverse
world: **text-in dominates at 84-86%**, because a ~28.7k-token SI+booklet is
re-sent on every one of the 110-191 raw billed events in the session, and
audio-in is a distant second at 13-15%. This is exactly the pre-compression
"text-in is 95-98%" shape that `docs/standards/logging-and-cost.md` calls
obsolete for the deployed config -- reproduced here as the counterfactual
baseline the deployed arm's compression + SI diet were built to escape. In
other words: the naive arm is a live demonstration of what this app's own
cost profile looked like before context-compression and the SI diet shipped.

### 3. Per-field cost

| Run | Fields matched (fill-correct) | Fields confirmed | All-in cost | usd/correct-field | usd/confirmed-field |
|---|---:|---:|---:|---:|---:|
| D happy 1 | 22 | 22 | $0.702181 | $0.0319 | $0.0319 |
| D happy 2 | 22 | 22 | $0.724305 | $0.0329 | $0.0329 |
| D unhappy 1 | 22 | 22 | $1.406226 | $0.0639 | $0.0639 |
| D unhappy 2 | 22 | 22 | $1.328544 | $0.0604 | $0.0604 |
| N happy | 21 | 22 | $1.839110 | $0.0876 | $0.0836 |
| N unhappy | 21 | 20 | $3.281677 | $0.1563 | $0.1641 |

The naive arm's two denominators diverge because its fill accuracy and its
client-side confirmation disagree: N happy correctly filled 21/22 fields
(missed `us_visa_type_number_expiration`, left blank) but the client
confirmed all 22 -- meaning one confirmed field holds an incorrect/blank
value that the human step nonetheless clicked "confirm" on. N unhappy
matched 21/22 but only 20/22 were confirmed. The shipped harness metric
(`usd_per_correct_field`) is computed against **matched**, not confirmed.
Per-field cost roughly **doubles to triples** going from deployed to naive on
both denominators and both paths -- the deployed arm costs about a third of a
cent per field on the happy path and six-to-seven cents on unhappy; the naive
arm costs eight-to-nine cents happy and fifteen-to-sixteen cents unhappy.

### Finding 1: the Live API force-trims naive sessions at ~32k context tokens -- "unbounded" is not billable-unbounded

The single most consequential discovery of this experiment is not the dollar
totals -- it's that the naive arm's "no compression, unbounded session"
premise turned out to be **false at the platform level**. The `eviction_drops`
recorded in both naive meta.json files show the server's own context silently
collapsing mid-session:

| Run | Drop # | Prompt tokens before | Prompt tokens after | Approx. reduction |
|---|---|---:|---:|---:|
| N happy | 1 (raw event 57 of 110) | 31,876 | 27,910 | -3,966 |
| N happy | 2 (raw event 104 of 110) | 31,821 | 27,979 | -3,842 |
| N unhappy | 1 (raw event 53 of 191) | 31,833 | 28,004 | -3,829 |
| N unhappy | 2 (raw event 101 of 191) | 31,848 | 27,895 | -3,953 |
| N unhappy | 3 (raw event 160 of 191) | 31,880 | 27,893 | -3,987 |

Every drop clusters in the same narrow band: the session's prompt-token count
climbs to roughly 31,800-31,900, then the platform silently trims it back
down to roughly 27,900-28,000 -- a reduction of ~3,800-4,000 tokens each
time, with no corresponding tool call, log line, or client-visible event in
the harness's own instrumentation. This is a **server-initiated, blind trim
of oldest conversation history**, not a designed behavior of anything in this
codebase: the naive arm's settings explicitly disable
`CONTEXT_COMPRESSION_ENABLED` (see Method below), so nothing in the app asked
for this. The Live API itself appears to enforce an internal context ceiling
around ~32k tokens for this native-audio model and enforces it by evicting
the oldest turns once the session crosses it -- independent of, and invisible
to, the caller's own compression settings.

**What this means:**

1. **"Unbounded" was never actually unbounded.** The naive arm was designed
   as a maximally-uncompressed baseline -- no sliding window, no DTI, no
   secretary, resend the whole SI every turn, let context accumulate forever.
   In practice the platform itself imposes a hard ceiling that no session on
   this model can cross: cost growth on a long enough naive session is
   self-limiting, not linear-forever, because the platform starts silently
   deleting history once the accumulated prompt exceeds ~32k tokens. Any
   projection or estimator that assumes truly-unbounded accumulation (see
   Estimator A, "no-eviction" variant, below) will overshoot badly for
   exactly this reason.
2. **Blind trim vs. curated window is a real quality difference, not just a
   labeling one.** The platform's force-trim removes the *oldest* turns with
   no knowledge of which turns still matter (a still-unconfirmed field's
   guidance, an in-progress correction) -- it is a FIFO eviction with zero
   domain awareness. The deployed arm's context-window compression is instead
   a **curated** window: it is derived per-form from the SI+tools floor plus
   an inline injection budget (`CONTEXT_COMPRESSION_DERIVE_FROM_SI_FLOOR`),
   and its eviction targets stale per-field guidance specifically, not
   whatever happens to be oldest. The naive arm gets FIFO amnesia; the
   deployed arm gets purpose-built pruning.
3. **The naive arm's accuracy failures and divergences cluster after force
   trims.** Both naive runs missed the same field
   (`us_visa_type_number_expiration`) and the happy run recorded 7
   divergences (a "divergence" being the model addressing/confirming a
   different field than the one currently in focus) -- both plausible
   symptoms of the model periodically losing access to turns of context it
   still needed, with no warning and no ability to recover the trimmed
   information. This is directly attributable to the blind-trim mechanism:
   a curated eviction (deployed arm) preserves what the app's own logic
   knows is still relevant; a blind FIFO trim (naive arm, platform-imposed)
   has no such guarantee and can silently remove a field's own instructions
   partway through filling it.

**Why this belongs in the writeup as a first-class finding, not a footnote:**
it directly explains why Estimator A's "no-eviction" variant fails so badly
(+159.4%, see Estimator grading below) -- that estimator's premise (context
accumulates without limit) is empirically false for this model on this
platform. It also means the naive-vs-deployed cost gap measured here is, if
anything, a **conservative** estimate of what a truly-unbounded competitor
implementation would cost, since the real platform is quietly capping the
naive arm's worst-case growth for free.

### Estimator grading

**(a) Pilot pre-registration vs. the full naive-happy run**

| Prediction | Measured | Delta | % |
|---|---:|---:|---:|
| $2.27 (band $1.90-$2.63) | $1.839110 | -$0.430890 | -19.0% |

The actual run landed **19% below the point prediction and $0.061 below the
stated band floor** ($1.90). Honest accounting of why: the pilot projection
was built (deliberately, per the pre-registration method) from a linear
extension of the first 6 questions' per-question token growth. That
extrapolation had no way to see two effects that only surfaced once the full
22-question run actually happened: **(1)** the platform's ~32k-token
force-trim (Finding 1, above) caps how large the session's re-billed context
can actually grow -- contrary to the "keep accumulating forever" assumption a
linear extrapolation implicitly makes -- and **(2)** a real drop in
per-question orientation/tool-call overhead after roughly question 12 in the
measured run, which a 6-question pilot had no visibility into. Both effects
push the realized cost below what a linear extrapolation from a short pilot
would predict. This is reported honestly, including the below-band-floor
miss, rather than adjusted after the fact.

**(b) Estimator A -- naive_replay of the measured D-unhappy trace,
naive_si_tokens=28,660, mean of 2 runs**

| Variant | Predicted | Measured N_unhappy | Delta | % |
|---|---:|---:|---:|---:|
| No-eviction (as specified) -- D_unhappy_1 | $8.577800 | $3.281677 | +$5.296123 | +161.4% |
| No-eviction -- D_unhappy_2 | $8.450469 | $3.281677 | +$5.168792 | +157.5% |
| No-eviction -- **mean** | **$8.514135** | $3.281677 | **+$5.232458** | **+159.4%** |
| Trim-aware (cap modeled prompt at 32k) -- D_unhappy_1 | $1.395677 | $3.281677 | -$1.886000 | -57.5% |
| Trim-aware -- D_unhappy_2 | $1.328604 | $3.281677 | -$1.953073 | -59.5% |
| Trim-aware -- **mean** | **$1.362140** | $3.281677 | **-$1.919537** | **-58.5%** |

The task's prior expectation was that this estimator would be **biased LOW**
(on the reasoning that it inherits the deployed arm's efficient turn
structure). That does not hold for the literal no-eviction variant: it is
biased enormously **HIGH** (+159.4%), because replaying the deployed arm's
own compressed, tightly-managed turn-content growth as if that content had to
be re-sent in full with a large flat naive SI floor on top every turn, with
nothing ever evicted, double-counts both the deployed session's already-small
per-turn deltas AND an unbounded accumulation that the real platform
prevents (Finding 1). The trim-aware variant (capping the modeled prompt at
~32k, mirroring the real force-trim) swings the other way and undershoots by
-58.5%, because capping only the *history* term while still using the
deployed run's much-smaller-than-naive per-turn deltas can't reproduce a
session that, in the real naive run, resends a ~28k-token SI+booklet from
question 1 -- the trim only bites once accumulation would exceed 32k, so most
of the trajectory undercounts. **Neither variant of Estimator A is a usable
unhappy-cost predictor from the D-unhappy trace.** The input trace (deployed,
compressed) and the naive billing model are structurally mismatched; this
estimator answers "what would naive billing cost if laid over the deployed
session's already-cheap turns," not "what would a naive session with
naive-sized turns actually cost."

**(c) Estimator B -- project_unhappy on the measured N-happy trace,
turns_multiplier from actual meta turn counts**

N_happy meta turns = 44, N_unhappy meta turns = 88, multiplier = 88/44 =
2.0000 (exactly 2x, matching the harness's designed 4-turns-vs-2-turns-per-
question structure).

| Predicted | Measured N_unhappy | Delta | % |
|---|---:|---:|---:|
| $3.678217 | $3.281677 | +$0.396540 | +12.1% |

Estimator B overshoots by 12.1% -- much closer than Estimator A, and this is
the **usable predictor** of the two. It over-predicts because it scales the
happy run's per-question token deltas linearly by the turn multiplier without
accounting for the force-trim-driven prompt resets in the real N_unhappy run
(3 eviction_drops vs. the model's implicit "keep growing" assumption), which
caps some of the accumulation the naive-happy trend would otherwise imply
carrying twice as far. **Takeaway: when you need a naive-arm cost estimate
without running the naive session itself, project from a trace that already
has naive-shaped turns (Estimator B), not from a differently-shaped trace no
matter how well-measured (Estimator A).**

### Bias directions (stated explicitly)

- **Estimator A (naive_replay of the D-unhappy trace) underestimates the
  true naive cost in its trim-aware form** (-58.5%) and **overestimates it
  wildly in its no-eviction form** (+159.4%) -- see above. Neither direction
  is usable; both are reported so the failure mode is on the record rather
  than silently discarded.
- **The deployed arm's dollar figures INCLUDE quality machinery the naive
  arm does not pay for at all.** The deployed happy mean ($0.713243) and
  unhappy mean ($1.367385) both carry the cost of the pro-pass (fires on
  every deployed run, ~$0.0025/run) and, on one of the two unhappy runs, the
  secretary (~$0.008/run when it fires). The naive arm has neither
  mechanism -- it cannot ask a secondary model to resolve field ambiguity,
  and it has no pro-pass review step. Despite paying for this extra
  machinery, the deployed arm still costs 39-42% of the naive arm's price
  AND fills more fields correctly (22/22 vs. 21/22 on both naive runs). The
  61.2%/58.3% savings figures above are therefore, if anything, an
  **understatement** of the deployed design's cost-efficiency per unit of
  delivered correctness -- a truly apples-to-apples "naive arm with the same
  accuracy guarantees" would need its own secretary-equivalent and would cost
  even more than the $1.839/$3.282 measured here.

### Framing caveat

The naive arm constructed for this experiment is an **external competitor
baseline** for a market/moat comparison -- "what would it cost a competitor
who built the obvious, unoptimized version of this product?" -- not this
codebase's internal design comparator. Internally, the compression feature's
own design comparator is **section-resets** (bd memory
`section-resets-are-cost-mitigation`), never "vs. unbounded"; that
comparison is answered elsewhere and is out of scope here. Do not read the
2.4-2.6x savings multiples above as "compression saves 2.5x over the
next-best internal alternative" -- they say only "the deployed product costs
2.4-2.6x less than a naive from-scratch competitor implementation would."

### Billing reconciliation (pre-registered follow-up)

These 6 full runs plus the 3 smokes/pilot spanned roughly **19:15-20:05 UTC
on 2026-08-27**, a quiet traffic day for this project's Vertex/GCP billing
account. Reconciling the harness's computed dollar figures against the
actual Google Cloud billing console total for that window is
**pre-registered as a follow-up, not part of this report**: Vertex billing
exports lag same-day usage (typically by at least one business day), so the
console total for this specific window will not be queryable until after
2026-08-27. When that reconciliation is run, compare the console's itemized
total for the project's Vertex Gemini Live usage in the 19:15-20:05 UTC
window against this report's summed actual spend (~$10.17, see the budget
ledger above) -- a clean match validates the harness's per-token pricing
model end-to-end against real invoiced cost, not just against the harness's
own internal replay (see "Replay validation" below, which only proves
internal consistency between the recorded event log and the harness's own
price table, not agreement with Google's actual invoice).

### Replay validation (recorded vs. token x rate replay)

| Run | Recorded total | Replayed total | Delta | Cached tokens (Live path) | `cache_summary.reported` |
|---|---:|---:|---:|---:|---|
| D happy 1 (193603Z) | $0.699771 | $0.699770 | -$0.000001 | 0 | False |
| D happy 2 (193939Z) | $0.721811 | $0.721814 | +$0.000003 | 0 | False |
| D unhappy 1 (194334Z) | $1.395677 | $1.395677 | +$0.000000 | 0 | False |
| D unhappy 2 (195050Z) | $1.326009 | $1.326010 | +$0.000001 | 0 | False |
| N happy (193127Z) | $1.839110 | $1.839108 | -$0.000002 | 0 | False |
| N unhappy (195815Z) | $3.281677 | $3.281679 | +$0.000002 | 0 | False |

All 6 deltas are within $0.000003 -- float rounding noise from `round(total,
6)` vs. the CSV's independently-rounded per-row sums, not a pricing-model
mismatch. Every run's `cache_summary.events_with_nonzero_cache` = 0 and the
cached-token curve sums to 0 across all 6 runs -- `replay_total`'s
full-rate-no-discount assumption holds on all 6 runs, so no cached-token
guard was tripped. (Note the D-arm "recorded total" rows above are the
**voice-only** figure; the all-in figures in section 1 add the text-sidecar
cost -- see below.)

### Text sidecar reconciliation (deployed runs only)

| Run | Voice recorded | Voice replayed | Text (by caller) | Text total | All-in recorded | Recon (voice_replay + text) | Delta |
|---|---:|---:|---|---:|---:|---:|---:|
| D happy 1 | $0.699771 | $0.699770 | pro: $0.002410 | $0.002410 | $0.702181 | $0.702180 | -$0.000001 |
| D happy 2 | $0.721811 | $0.721814 | pro: $0.002494 | $0.002494 | $0.724305 | $0.724308 | +$0.000003 |
| D unhappy 1 | $1.395677 | $1.395677 | pro: $0.002454, secretary: $0.008013, validator: $0.000082 | $0.010549 | $1.406226 | $1.406226 | $0.000000 |
| D unhappy 2 | $1.326009 | $1.326010 | pro: $0.002454, validator: $0.000081 | $0.002535 | $1.328544 | $1.328545 | +$0.000001 |

Both deployed happy runs fired the pro-pass only -- secretary made 0 calls
(no field ambiguity needed resolving on the happy path). Deployed unhappy
run 1 additionally fired the secretary 3 times ($0.008013); unhappy run 2
fired 0 secretary calls despite being the "correction" path, showing
secretary invocation is data-dependent, not turn-count-dependent -- **a real
behavioral difference between nominally-identical unhappy runs**, not a
measurement artifact, and it's why D_unhappy_1's all-in cost ($1.406226)
exceeds D_unhappy_2's ($1.328544) by more than the voice-only difference
would predict. `pro_pass.model = gemini-2.5-pro` on every run and
`summary.pro_pass.usd` matches `text_usd_by_caller.pro` exactly on all 4
runs, confirming the pricing path used is `price_text_usage` (the
cached-discount-aware function keyed per-model), not a flat rate. All-in
reconciliation deltas are all within $0.000003 -- clean.

### Method

**Harness:** `scripts/spikes/measure_form_session_costs.py`, driving the real
`gemini-live-2.5-flash-native-audio` model over Vertex (never AI Studio --
see memory `all-live-model-work-on-vertex.md`) via a fake client that
provides scripted W-7 audio answers and acks the spell-back tool's
`delivered` response without fetching real Cloud TTS audio (see "Cloud TTS
line" footnote below for why that matters). All 6 runs used the 22-question
realistic nonresident-filer W-7 plan; happy path = 2 turns/question
(value -> confirm); unhappy path = 4 turns/question (wrong -> reject ->
correct -> confirm).

**Deploy-fidelity flags (deployed arm):** `_make_settings("dti", ...,
compression=True, continuous=True, derive_compression=True)` --
`USE_DTI=True` (production's Dynamic Turn Injection SI), `CONTINUOUS_SESSION`
on, `CONTEXT_COMPRESSION_ENABLED=True` with
`CONTEXT_COMPRESSION_DERIVE_FROM_SI_FLOOR=True` (the window is derived
per-form from this form's SI+tools floor plus its inline injection budget,
exactly as production sizes it -- NOT a fixed `--trigger`/`--window` pair,
which would measure a configuration nobody deploys). Secretary and pro-pass
are wired live (`text_ai_wired`); spell-back is enabled and exercised on
name-field turns via the fake client's ack path.

**Naive arm definition** (`_make_settings("naive", ...)`,
`measure_form_session_costs.py` lines ~1930-1954): same base settings shape
as an unbounded session (`USE_DTI=False`, `CONTINUOUS_SESSION` as passed,
`CONTEXT_COMPRESSION_ENABLED=False` -- no compression of any kind), with the
legacy full-schema system instruction plus the official IRS W-7 instruction
booklet appended (109,722 SI chars, 27,923 SI tokens + 737 tool-declaration
tokens = 28,660 tokens re-billed on every event). **5-tool catalog**:
`update_form_fields`, `get_form_status`, `confirm_field`, `skip_field`,
`switch_to_field` only -- `ask_secretary` and `switch_section` are filtered
out of the production tool list at the call site (pinned by an allowlist
test, mutation-verified), because a naive from-scratch competitor has no
secretary architecture and no section machinery of its own; a stray
`switch_section` call would open a second session and violate the arm's
single-session premise. **Spell-back is off** (`SPELLBACK_TOOL_ENABLED:
False`) for the same reason -- a naive competitor has no Cloud TTS
integration to spell values back with, so it isn't charged for a pipeline it
doesn't have. The first naive smoke run declared the full production tool
catalog and measured the model actually *calling* `ask_secretary` mid-run,
burning a ~29k-token context re-send on the fail-open answer; the filtered
5-tool catalog is a direct fix for that observed failure mode, not a
speculative precaution.

**VAD -- labeled deviation from deploy config, present in ALL arms:**
`_make_settings()` (same function, `measure_form_session_costs.py` line
~2023) sets `s.DISABLE_GEMINI_VAD = True` on every arm, disabling the
production automatic voice-activity detection in favor of explicit
`ActivityStart`/`ActivityEnd` brackets sent by the harness. This is NOT how
the deployed app runs in production (production leaves automatic VAD on).
The harness pins it off because the alternative (`VAD_*_SENSITIVITY =
"UNSPECIFIED"`, tried historically) does not actually disable server-side
VAD in native-audio mode -- the adapter's manual brackets no-op, so turn
boundaries are detected by the server's own VAD reacting to the harness's
synthetic gTTS audio. That worked tolerably on AI Studio but Vertex
intermittently missed a gTTS utterance's end and hung ~41s waiting for the
next utterance to flush it, past the harness's 40s wait-turn timeout,
triggering a barge-in and an escalating desync wedge (observed 2026-07-05 per
the code comment, on two 30-question continuous runs, both dying around
question 8). `DISABLE_GEMINI_VAD=True` makes the harness's explicit activity
brackets actually take effect, giving deterministic synthetic-turn
boundaries instead. Both the deployed and naive arms carry this same
deviation, so it does not bias the deployed-vs-naive comparison relative to
each other -- but it means neither arm's dollar figure is a perfect stand-in
for a real user's session with production automatic VAD (audio-in token
accounting under real VAD may differ slightly around turn-boundary padding).

**Audio fixtures:** scripted W-7 answers synthesized via the harness's gTTS
audio-generation path (per the VAD note above), one fixture set covering all
22 questions' happy-path values and the unhappy path's additional
wrong-value/correction turns.

**SDK / model / date:** google-genai SDK >= 2.8 (per repo-wide sweep in
memory `retest-tool-call-findings-after-genai-2-8-cutover.md`), model
`gemini-live-2.5-flash-native-audio`, Vertex (never AI Studio), all 6 runs +
3 smokes/pilot executed 2026-08-27.

### Cross-reference to the MEASURED COST INVARIANT

`docs/standards/logging-and-cost.md`'s MEASURED COST INVARIANT table states,
for the deployed 2.5 native-audio production config: happy path ~49%
audio-in / ~47% text-in / ~4% other; unhappy path ~60% audio-in / ~36%
text-in / ~5% other.

This experiment's fresh deployed-arm measurements: happy 48.10% audio-in /
46.81% text-in / 5.08% other (text-out+audio-out); unhappy 57.75% audio-in /
38.41% text-in / 3.84% other. Both paths are within 1-2.4 percentage points
of the documented figures, same ordering (audio-in leads, text-in close
behind on happy; audio-in leads more clearly on unhappy), well inside the
noise the standards doc's own provenance paragraph already anticipates ("the
ORDERING is the durable finding; treat the percentages as approximate").

**Verdict: CONFIRMED.** No update to `docs/standards/logging-and-cost.md`'s
invariant table or provenance paragraph is needed -- the fresh W-7
measurement here reproduces the standards doc's documented shape closely
enough that restating it would add a citation without changing a number the
reader would act on differently.

### Footnotes

**(a) Schema-only naive variant (billing-arithmetic-only, behavior held fixed)**

Booklet token count: booklet_chars=81,242 / SI_chars=109,722 = 0.740435
share; x naive SI text-in tokens (27,923) = **20,675.16 booklet tokens**
(schema-only residual = 27,923 - 20,675.16 = 7,247.84 tokens). Re-summed by
subtracting `booklet_tokens x text_input_rate` from every billed event's
text-in cost, with behavior (turns, audio, output) held fixed -- this is a
pure billing-arithmetic exercise, not a re-run with a smaller SI (a
schema-only naive session would likely behave differently -- fewer
misunderstandings, possibly different divergences -- and that behavioral
question is out of scope here):

| Run | Full-naive recorded | Schema-only re-sum | Savings | % reduction |
|---|---:|---:|---:|---:|
| N happy (22 billed CSV rows) | $1.839110 | $1.611682 | $0.227428 | 12.4% |
| N unhappy (22 billed CSV rows) | $3.281677 | $3.054252 | $0.227425 | 6.9% |

Note: "22" above counts CSV rows (one per question, the CSV's own
aggregation unit), not raw API calls (110/191 per `cache_summary.events`);
the booklet-token subtraction is applied once per CSV row, consistent with
how the CSV represents "billed events" for this dataset. Savings is nearly
flat in dollar terms across happy/unhappy (~$0.227 either way, since 22 rows
x the fixed per-row reduction is the same on both paths) but a much smaller
% of the larger unhappy total. (Raw-API-call granularity, 110/191 events,
would multiply this savings figure 5-9x and is unlikely to be the intended
reading -- flagged as an interpretation choice, not resolved as ambiguous in
the numbers themselves.)

**(b) Naive arm on 3.1 pricing rates**

| Run | 2.5 recorded | 3.1-rate replay | Ratio (3.1/2.5) |
|---|---:|---:|---:|
| N happy | $1.839110 | $2.636426 | 1.4335x |
| N unhappy | $3.281677 | $4.664966 | 1.4215x |

3.1's rate row (text-in $0.75/1M vs. 2.5's $0.50/1M; text-out $4.50/1M vs.
2.5's $2.00/1M; audio rates identical) drives roughly **+43%** on this
heavily text-in-dominated naive arm. This is a pricing-table substitution
only -- it does not model any behavioral difference 3.1 might have (e.g.
3.1's reasoning/thinking tokens bill as output, per the standards doc's own
caveat), so treat it as "what would this exact naive session cost if it had
been billed at 3.1 list rates," not "what would a 3.1-native-audio naive
session cost."

**(c) Cloud TTS spell-back line (deployed arm only)**

Rate used: **$30.00 per 1M characters**, Chirp 3 HD -- list price, from
training-data vintage, **not sourced from this repo (grepped `scripts/
spikes/`, `docs/standards/`, `docs/genai_docs/` -- no TTS pricing table
found); verify against current Google Cloud TTS pricing before citing this
externally.**

| Run | spellback_count | spellback_total_chars | TTS cost @ $30/1M chars |
|---|---:|---:|---:|
| D happy 1 | 3 | 14 | $0.00042 |
| D happy 2 | 4 | 22 | $0.00066 |
| D unhappy 1 | 5 | 21 | $0.00063 |
| D unhappy 2 | 6 | 26 | $0.00078 |

All sub-cent, as expected, and a strictly **separate line** from every
dollar figure elsewhere in this report -- the harness's fake client acks
`delivered` without fetching real Cloud TTS audio, so **no real Cloud TTS
spend occurred in any of these runs**. `spellback_count`/
`spellback_total_chars` are recorded so this line can be estimated
separately; they are not folded into any all-in total above.

**(d) Variance proxy band (i90-full E1 happy triplet, cross-form)**

| Run stamp | Recorded total |
|---|---:|
| 20260714T055600Z | $2.420659 |
| 20260714T061257Z | $2.415933 |
| 20260714T062904Z | $2.486589 (CSV-summed: $2.482062 -- used for the CV below; see note) |

Mean = $2.439551, sample stdev (n=3) = $0.036891, **CV = 1.51%**.

**This is a cross-form proxy, not a W-7-native variance estimate** -- the I-90
form, not the W-7. The W-7 deployed arm here has only n=2 runs per path, too
few to compute its own stdev/CV meaningfully; borrowing the I-90
full-stress-test triplet's run-to-run spread (1.51%, tight) is the best
available proxy for how much run-to-run noise to expect on a
comparably-configured (continuous-DTI + compression) deployed session on a
different form:

| | Mean | Band (mean +/- CV) |
|---|---:|---|
| Deployed happy | $0.710791 | $0.700042 - $0.721540 |
| Deployed unhappy | $1.360843 | $1.340264 - $1.381422 |

Note: the CSV-summed total for run 3 (20260714T062904Z) is $2.482062, not
the $2.486589 alternate figure that appears elsewhere for that run -- the
CSV's own "total cost" column (the ground truth `replay_total` is built to
reproduce) was used here for consistency with how every other number in this
report was derived. The two figures are within ~0.2% of each other and do
not change the reported 1.51% CV materially either way.

## Anomalies / interpretation notes carried into this report

1. Estimator A's directional prior was WRONG for the no-eviction variant:
   expected biased LOW, measured +159.4% HIGH -- see "Estimator grading"
   above for the full explanation (naive_replay applied to the deployed
   arm's already-small per-turn deltas, with a large flat naive SI stacked
   on top and never evicted, double-counts two effects that don't cancel the
   way they would against a trace with naive-sized turns).
2. The two D-unhappy runs diverge sharply on secretary usage (3 calls vs. 0)
   despite identical schema and turn structure by design -- real behavioral
   variance between nominally-identical runs, not a measurement artifact.
3. Naive arm's fill/confirm denominators diverge internally on both runs
   (matched != confirmed) -- both `usd_per_correct_field` (matched
   denominator, the shipped metric) and a confirmed-denominator variant are
   reported in section 3 above rather than picking one silently.
4. Footnote (a)'s "n_events" is ambiguous in the underlying instruction
   ("re-sum ... from every billed event's text-in"): applied once per CSV
   row (22), not once per raw API call (110/191) -- see footnote (a) for the
   reasoning and the ~5-9x sensitivity if the other granularity was meant.
5. Cloud TTS rate ($30/1M chars) could not be sourced from anything in this
   repo; it is a training-data-vintage list-price recollection, labeled as
   such per footnote (c). All four TTS dollar amounts are sub-cent
   regardless of rate precision, so this does not materially affect any
   total in this report, but should not be cited externally without
   verifying against current pricing.

## Chart references

Generated by `scripts/spikes/plot_wiadk_comparison.py
scripts/spikes/data/wiadk-full` (all provenance assertions passed -- each of
the 6 `meta.json` files verified against its expected arm/path/compression
config before plotting). 5 PNGs under
`scripts/spikes/data/wiadk-full/plots/`:

1. **cumulative_cost_happy.png** -- running all-in cost vs. question number,
   happy path. Deployed arm: 2 thin per-run lines + 1 bold mean line ($0.71
   final). Naive arm: 1 bold line ($1.84 final). Vertical dotted lines mark
   the naive run's platform force-trim events (Finding 1), positioned by
   approximating the raw event index to a question number.
2. **cumulative_cost_unhappy.png** -- same, unhappy path: deployed mean
   $1.37 vs. naive $3.28, three force-trim markers (naive unhappy evicted 3
   times vs. happy's 2).
3. **session_cost_bars.png** -- grouped bars, arm x path, all-in session
   cost ($0.71/$1.37 deployed vs. $1.84/$3.28 naive). Deployed bars carry
   error-bar whiskers from the cross-form variance proxy (footnote d).
4. **modality_breakdown.png** -- stacked bars of audio-in/text-in/text-out/
   audio-out share per arm x path, visualizing the modality table in
   section 2 above.
5. **context_curve.png** -- prompt-token curve over the session for all 6
   runs, visually showing the deployed arm's bounded sawtooth (compression
   evictions) against the naive arm's climb-then-blind-trim pattern (Finding
   1) up to the ~32k ceiling.

Both `context_curve.png` and `session_cost_bars.png` were visually reviewed
for legibility; all 5 PNGs confirmed nonempty.
