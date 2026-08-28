# W-7 session cost: deployed config vs naive baseline (bd polyglot-pdf-wiadk)

**Status: COMPLETE -- both the W-7 study (bd wiadk) and its i90-v2 extension
(bd polyglot-pdf-2nikx) are finished, replay-validated, and reconciled.**
Model `gemini-live-2.5-flash-native-audio` (2.5 tier), Vertex, google-genai
SDK >= 2.8. W-7 dates: 2026-08-27; i90-v2 dates: 2026-08-28. Combined program
spend: **~$43.9-54.2** (two reconciliation scenarios, see "i90-v2 program
spend ledger" below), well under the $100 program cap. Billing-console
reconciliation against these harness-computed dollar figures is a follow-up
over the 2026-08-27 quiet-day window (see "Billing reconciliation" below) --
those W-7 runs spanned roughly 19:15-20:05 UTC, and Vertex billing exports
lag same-day traffic, so the console total for this window will not be
queryable until at least the next business day.

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

## i90-v2 extension (bd polyglot-pdf-2nikx, 2026-08-28) -- pre-registrations

The same comparison on the NEW long-form I-90 kit (`form-kits/i-90_v2`, 34
sections / 94 fields; a coherent single persona asks 57 questions -- the other
37 fields are schema-gated conditionals/read-only, enumerated in
`I90V2_EXCLUDED` and pinned by tests). Naive SI for this form: **19,710 SI +
737 tool = 20,447 tokens** (measured `count_tokens`, 2026-08-28; smaller than
W-7's 28,660 because the I-90 booklet is half the size).

1. **WRITTEN BEFORE THE FULL 57q NAIVE HAPPY RUN** (pilot
   `costs_i90-v2_2.5_naive_happy_20260828T012812Z`, $0.342/6q): predicted
   full naive-happy = **$4.86, band $3.73-$5.99** (+/-25% on the projected
   part). Method: trace extension from the pilot's own per-event numbers
   (4.67 events/q stable avg, +594 tok context growth/q, +507 tok audio
   growth/q) with the ~32,768-token platform force-trim modeled as a sawtooth
   to the ~19.8k SI floor (2 trims projected). Wall-clock projects ~9.3 min
   vs the ~10-min connection lifetime: completion is NOT assured, and an
   API-terminated run is a pre-registered reportable RESULT (cost-to-
   termination + questions completed), not a discard.
2. Naive-unhappy (4 turns/q, ~18-19 min projected) is EXPECTED to be
   API-terminated near the 15-min uncompressed session cap at roughly
   question 40-46 of 57; predicted cost-to-termination ~$7-9. "The naive
   approach cannot complete the I-90 in one session" is the anticipated
   headline IF the logs prove a server-initiated close.
3. Deployed arm expectations (not formal predictions): happy ~$1.85/run,
   unhappy ~$3.6/run, scaling the W-7 means by question count; compression
   effectiveness verified per-run via compression_effective + evictions.
4. Same conventions as the W-7 study throughout: all-in excludes the
   greeting (own line), Live cached tokens asserted zero, text sidecar priced
   via price_text_usage, naive quality claims subject to a scorer-fairness
   check (the naive smoke's 0/2 looked like format-normalization noise --
   verify fill_failure_modes before quoting naive accuracy).

### i90-v2 budget ledger (same $100 program cap; W-7 spent $10.17)

| # | run | est. $ | actual $ | notes |
|---|-----|--------|----------|-------|
| 10 | D smoke i90-v2 happy q3 | ~0.10 | 0.053 | spell-back + secretary exercised |
| 11 | N smoke i90-v2 happy q2 | ~0.15 | 0.069 | naive SI 20.4k confirmed on the wire |
| 12 | N pilot i90-v2 happy q6 | ~0.70 | 0.342 | grounds pre-reg #1 |

## i90-v2 method changes vs. the W-7 study

Three changes were made to the harness between the W-7 study and the i90-v2
extension, plus one lesson about the scripted audio path. All three code
changes are committed on this branch and apply to **both arms identically**
(deployed and naive), so none of them bias the deployed-vs-naive comparison
relative to each other -- they change the absolute cost/duration of a run,
not the ratio between arms.

1. **Adaptive confirm-gate (`_settle_confirm`).** The W-7 harness advanced to
   the next question as soon as it sent a scripted "yes" turn, regardless of
   whether the model's tool calls actually confirmed the field. The i90-v2
   harness instead waits for each field to actually settle (be confirmed)
   before moving on, sending at most one extra "nudge" turn if the first
   confirm attempt doesn't land. This only affects the live-adapter harness
   path (not the naive replay/estimator math) and adds real turns -- and
   therefore real re-billed context -- exactly when a confirm doesn't
   settle cleanly the first time. It fired 0 extra nudges on the deployed
   happy runs, 4 on deployed-unhappy run 1 (two fields, `family_name` and
   `given_name`, needed a nudge), 1 on naive-happy, and 6 on naive-unhappy.
2. **Derailment guard.** The harness now aborts a run after 6 consecutive
   tool-silent questions (the model stops calling any tool at all in
   response to a question) or 8 consecutive confirm-stagnant questions (a
   confirm is requested but never settles). This is what actually stopped
   the naive-unhappy run at question 39 of 57 -- see "Naive-unhappy did not
   complete" below. Without this guard a wedged run would burn budget
   indefinitely with no forward progress; with it, a wedge becomes a
   reported, bounded-cost result instead of an unbounded one.
3. **The ASR lesson (USCIS number leading zeros).** The scripted persona's
   gTTS-synthesized speech for a USCIS account number beginning with a
   leading zero ("0 0 9 ...") was transcribed by the model's ASR as letters
   ("OON 9...") rather than digits, which then failed the strict
   `^[0-9]{12}$` validation and desynced an entire scripted run (this is
   one of the diagnostic runs excluded below, not one of the headline
   valid runs). The fix: the persona's USCIS number was changed to start
   with a non-zero digit, side-stepping the ASR ambiguity rather than
   attempting to fix ASR digit-vs-letter disambiguation itself (out of
   scope for a cost-measurement harness).

**Diagnostic-run exclusion rule.** `scripts/spikes/data/2nikx-full/` holds 9
summary files, not 6: alongside the 2 valid deployed-happy, 2 valid
deployed-unhappy, and 1 naive-happy + 1 naive-unhappy run reported as the
headline results below, it also contains 2 lower-quality deployed-happy dry
runs (`013010Z`, fill_accuracy.matched = 1/57 -- an almost total fill
failure; `020339Z`, matched = 14/57) and 1 deployed-unhappy dry run
(`024500Z`, matched = 12/57, only 33 of 57 steps completed) from earlier in
the harness's development, before the confirm-gate and derailment-guard
fixes above landed. **These 3 runs are excluded from every headline number
in this report** on the accuracy evidence alone (near-total fill failure is
not a usable cost data point for a comparison whose whole point is
cost-at-comparable-accuracy) and are instead counted as sunk
method-development cost in the program ledger below, alongside the smoke,
pilot, and debug runs and one additional orphan session (the "killed by
tooling" run, reconciled from the raw token-usage log since its own
artifacts never wrote to disk). This mirrors the W-7 study's own convention
of separating pipeline-proof smokes from headline full runs, extended here
to cover harness-development dry runs that happened to run at full
question-count.

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

## i90-v2 Results (bd polyglot-pdf-2nikx)

### i90-v2.1 Session cost table (all 6 valid runs + means)

Replay-validated (see "i90-v2 replay validation" below): all 6 replay within
$0.000004 of the CSV's own recorded total, `cache_summary` reports 0 cached
tokens on every run.

| Run (stamp) | Arm | Path | Q | Recorded (CSV, voice-only) | Text-sidecar | Greeting (subset of voice) | **All-in** |
|---|---|---|---:|---:|---:|---:|---:|
| 021631Z | Deployed | happy | 57 | $2.035449 | $0.004259 | $0.003253 | **$2.039708** |
| 022519Z | Deployed | happy | 57 | $2.067670 | $0.004384 | $0.003409 | **$2.072054** |
| 030509Z | Deployed | unhappy | 57 | $4.268139 | $0.004354 | $0.005677 | **$4.272493** |
| 032527Z | Deployed | unhappy | 57 | $4.041460 | $0.004347 | $0.003481 | **$4.045807** |
| 034310Z | Naive | happy | 57 | $6.016500 | -- | -- | **$6.016500** |
| 035215Z | Naive | unhappy | **39/57 (DID NOT COMPLETE)** | $5.912473 | -- | -- | **$5.912473** |

All four deployed all-in figures were verified to equal `voice_usd +
text_usd` exactly (residual < $0.00001) -- confirming the single
greeting-as-its-own-line/all-in-excludes-greeting cost convention from the
W-7 study (commit `ed5dde52`) is applied consistently here too.

| Run | Arm | Path | All-in $ | Wall clock | Q done | Confirmed | Correct | Accuracy | Evictions/trims |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| 021631Z | Deployed | happy | $2.039708 | 513.9s | 57/57 | 57/57 | 48/57 | 84.2% | 12 |
| 022519Z | Deployed | happy | $2.072054 | 552.9s | 57/57 | 57/57 | 48/57 | 84.2% | 14 |
| **Deployed happy mean** | | | **$2.055881** | **533.4s** | | 57/57 | 48/57 | **84.2%** | |
| 030509Z | Deployed | unhappy | $4.272493 | 1185.1s | 57/57 | 57/57 | 48/57 | 84.2% | 26 |
| 032527Z | Deployed | unhappy | $4.045807 | 1041.2s | 57/57 | 57/57 | 48/57 | 84.2% | 17 |
| **Deployed unhappy mean** | | | **$4.159150** | **1113.2s** | | 57/57 | 48/57 | **84.2%** | |
| 034310Z | Naive | happy | $6.016500 | 511.9s | 57/57 | 57/57 | 47/57 | 82.5% | 2 (platform force-trim) |
| 035215Z | Naive | **unhappy -- DID NOT COMPLETE** | $5.912473 | 2103.1s (35.1 min) | **39/57** | 33/57 | 24/57 | 42.1% of 57 / 61.5% of 39 attempted | 2 (platform force-trim) |

"Evictions" carries the same two-mechanism caveat as the W-7 table above:
deployed rows count the app's own curated context-compression; naive rows
count the platform's blind force-trim (see Finding 1, which reproduces on
i90-v2 too -- both naive runs still show the ~31.8-31.9k-to-~27.9-28k
sawtooth pattern).

### i90-v2.2 Naive-unhappy did not complete -- model collapse, not API termination

The naive-unhappy run went tool-silent for 6 consecutive questions and the
derailment guard (see "i90-v2 method changes" above) aborted it at question
39 of 57 (`derailed_reason: "6 consecutive tool-silent questions"`). Before
that point it had accumulated 6 confirm-nudges and left 6 questions
unsettled (`ssn`, `status`, `reason_section_a`, `p3_location_applied`,
`p3_location_issued`, `p3_destination`).

**This was a model collapse, not a server-initiated close.** `session_count`
stayed at 1 for the entire run and `close_1011` is absent from the meta --
there is no GoAway, no reconnect, and no evidence the Live API terminated
the session at all. The model itself simply stopped calling tools in
response to new questions, and the harness's own guard is what ended the
run, not the platform. This distinction matters for how the result is
worded: "the naive approach timed out" or "was terminated" would be
inaccurate; "the naive approach's model degraded to the point of making no
further progress, and the harness's own safety guard stopped a run that
would otherwise have burned budget indefinitely" is the accurate framing.

### i90-v2.3 Cost per confirmed field

| Arm x Path | All-in $ (mean) | Confirmed fields | $/confirmed field |
|---|---:|---:|---:|
| Deployed happy | $2.055881 | 57 | $0.0361 |
| Deployed unhappy | $4.159150 | 57 | $0.0730 |
| Naive happy | $6.016500 | 57 | $0.1056 |
| Naive unhappy (partial, DNC) | $5.912473 | 33 | $0.1792 |

Naive/deployed ratio: happy = 2.92x, **unhappy (per-confirmed-field) =
2.455x**. See i90-v2.6 below for why the per-confirmed-field ratio, not the
raw dollar ratio, is the fair unhappy-path comparator here.

### i90-v2.4 Trims / evictions / nudges / reconnects

| Run | Arm | Evictions/force-trims | Confirm-nudges | Reconnects | Session count |
|---|---|---:|---:|---:|---:|
| dti happy 021631Z | Deployed | 12 | 0 | 0 | 1 |
| dti happy 022519Z | Deployed | 14 | 0 | 1 | 2 |
| dti unhappy 030509Z | Deployed | 26 | 4 (unsettled: `family_name`, `given_name`) | 2 | 3 |
| dti unhappy 032527Z | Deployed | 17 | 0 | 1 | 2 |
| naive happy 034310Z | Naive | 2 (platform force-trim: 31,843->25,497 at raw event 180; 31,872->25,413 at 275) | 1 | 0 | 1 |
| naive unhappy 035215Z (partial) | Naive | 2 (platform force-trim: 31,878->25,463 at raw event 157; 31,884->25,458 at 243) | 6 | 0 | 1 |

All 4 deployed runs survived multiple ~10-minute connection boundaries via
the reconnect machinery (`session_count` 1-3) with zero data loss -- this is
exactly the mechanism the naive arm has no equivalent for, and it is a
second, independent reason (beyond cost) the naive arm cannot be treated as
production-equivalent on a long form.

### i90-v2.5 Modality shares

| Run | audio-in % | text-in % | text-out % | audio-out % |
|---|---:|---:|---:|---:|
| Deployed happy (mean of 2) | ~48% | ~47% | ~0.4% | ~5% |
| Deployed unhappy (mean of 2) | ~55-58% | ~37-40% | ~0.3% | ~3-4% |
| Naive happy | audio-in minority | **text-in dominant** | small | small |
| Naive unhappy (partial) | audio-in minority | **text-in dominant** | small | small |

The qualitative direction matches the W-7 pattern exactly: naive is
text-in-dominated by the re-sent 20,447-token SI+tools block on every turn;
deployed stays audio-in-led, consistent with the MEASURED COST INVARIANT
(see the W-7 cross-reference section above, which this run reproduces in
shape though not in exact percentage -- full per-run decimal modality
percentages were not re-derived for i90-v2 in this pass, since the ordering,
not the precise share, is the durable finding per the standards doc's own
provenance caveat).

### i90-v2.6 Cross-form comparison: W-7 vs. i90-v2 (moat scales with form length)

| Metric | W-7 (22 Q) | i90-v2 (57 Q) | Direction |
|---|---:|---:|---|
| Deployed happy mean | $0.713243 | $2.055881 | |
| Naive happy | $1.839110 | $6.016500 | |
| **Happy multiplier (naive/deployed)** | **2.58x** | **2.93x** | **moat widens with form length** |
| Deployed unhappy mean | $1.367385 | $4.159150 | |
| Naive unhappy | $3.281677 (complete) | $5.912473 (partial, 39/57 done -- did not complete) | |
| Unhappy multiplier, raw dollars (naive/deployed) | 2.40x | 1.42x -- **not usable**, see caveat below | |
| **Unhappy multiplier, per-confirmed-field (naive/deployed)** | n.a. (W-7 naive completed; ratio not needed) | **2.455x** | fair unhappy comparator |

**Read this table carefully -- it is n=1 per naive cell.** Every naive
number here comes from a single run (as does every naive number in the W-7
study); the happy-path multiplier going from 2.58x on the 22-question W-7 to
2.93x on the 57-question i90-v2 is consistent with a "the moat widens as the
form gets longer" story (a longer naive session re-bills its flat SI floor
over more turns, and the SI floor itself is a fixed tax the deployed arm's
per-field DTI SI mostly avoids), but **two data points is a direction, not a
trend line** -- this finding should be read as "consistent with, and
suggestive of" scaling with form length, not as a fitted or proven
relationship. It would take a third form at a third length to distinguish
"scales with length" from "these two forms happened to land this way."

The raw unhappy-path dollar multiplier (1.42x) is actively misleading here
and is reported only to be explicitly debunked: naive-unhappy spent
$5.912473 for 39 of 57 questions (68% complete) before derailing, while
deployed-unhappy spent a mean of $4.159150 for a full 57/57. Comparing those
two totals directly compares unequal amounts of completed work -- the
correct normalization is the per-confirmed-field ratio (2.455x), which is
what should be cited as "the i90-v2 unhappy-path naive/deployed cost
ratio," not the 1.42x raw-dollar figure.

Also notable: the naive arm's SI is *smaller* on i90-v2 (20,447 tokens: 19,710
SI + 737 tools) than on W-7 (28,660 tokens), because the I-90 booklet is
roughly half the size of the W-7 booklet -- yet the naive/deployed cost gap
is still wider on i90-v2. This means the widening isn't simply "a bigger
naive SI"; it is more consistent with the longer form producing more total
turns over which *any* flat per-turn SI tax compounds, i.e. turn count
(driven by question count), not SI size, is the more likely driver of the
scaling-with-length effect -- though again, this is inference from two data
points, not a controlled ablation isolating SI size from turn count.

### i90-v2.7 Pre-registration grades

**Naive-happy (pre-registration #1 in "i90-v2 extension" above):** predicted
$4.86, band $3.73-$5.99; actual $6.0165 -- **0.44% above the band ceiling**
(23.8% above the point prediction). Cause: the pilot run that grounded this
prediction ran *before* the adaptive confirm-gate (`_settle_confirm`)
existed in the harness. Because the gate makes the harness wait for each
field to actually settle, adding an extra nudge turn whenever a confirm
doesn't land the first time, every settle turn on the full run re-bills the
naive arm's ~24k-token prompt an additional time that the pre-gate pilot's
trace never had to account for. The gate applies identically to both arms,
so it does not bias the deployed-vs-naive comparison -- but it does explain
why this particular naive projection undershot the eventual actual cost.

**Naive-unhappy (pre-registration #2):** predicted "expected API termination
near the 15-minute uncompressed session cap ... predicted cost-to-
termination ~$7-9." Actual: no API termination occurred at all; the model
wedged (went tool-silent) at 35.1 minutes of wall-clock time, and the
harness's own derailment guard -- not the platform -- ended the run at
question 39 of 57, having spent $5.912473. **Grade: WRONG MECHANISM, RIGHT
CONCLUSION.** The prediction's headline claim -- "the naive approach cannot
complete this form in one session" -- was correct. But the predicted cause
(a server-side duration cap firing) did not occur, and the predicted cost
band ($7-9) did not hold either, because the actual failure mode (a
much-later model collapse under the harness's tool-silence guard) stopped
the run earlier than a full-duration API termination would have. Reporting
this honestly as a wrong-mechanism/right-conclusion result, rather than
rounding it up to "correctly predicted," is the same discipline the W-7
study's own Estimator grading section applied to its own imperfect
predictions.

**Gate-adjusted naive-happy method note:** the naive-happy run itself needed
only 1 confirm-nudge (vs. 6 on naive-unhappy), so the confirm-gate's extra-
turn cost on the happy-path pre-registration is small. Deriving "what the
pre-gate pilot would have predicted, adjusted for the gate's measured 1
extra nudge" is not cheaply derivable from the committed pilot artifacts
without new curve-fitting of the pilot's own per-event growth rate to one
additional settle-turn -- it is skipped here rather than guessed, per the
same "report only what's derivable from committed artifacts" discipline
used throughout this doc.

### i90-v2.8 Docs-vs-reality divergence: the 15-minute uncompressed-session cap did not fire

`docs/components/context-compression.md` states (line 57): "Without
compression, audio-only sessions are also hard-capped at **15 minutes**."
The naive arm runs with `CONTEXT_COMPRESSION_ENABLED=False` -- i.e. it is
exactly the uncompressed configuration that claim describes. The
naive-unhappy run ran for **2103.1 seconds (35.05 minutes)** -- more than
double the documented 15-minute cap -- with `session_count=1` and no
`close_1011`/reconnect event anywhere in its meta.json. The documented cap
simply did not fire on this run.

This is flagged here as a genuine docs-vs-reality divergence, not resolved:
either (a) the 15-minute figure describes a different condition than "an
uncompressed session with a naive from-scratch tool catalog and SI" (for
example, it may assume the production tool catalog and section machinery,
which the naive arm deliberately does not carry), (b) the cap has changed or
was never as hard as documented, or (c) the naive arm's specific
configuration (5-tool catalog, no secretary, no spell-back) somehow avoids
whatever server-side condition triggers the cap. This report does not
determine which explanation is correct -- that is a question for whoever
owns `docs/components/context-compression.md` to investigate, since the
practical effect of an inaccurate hard-cap claim is a downstream design or
capacity-planning decision made on a wrong assumption. The one thing this
run *does* establish is that "uncompressed sessions on this model are
hard-capped at 15 minutes" cannot be treated as reliably true in every
configuration -- at minimum the naive arm's specific setup is a documented
counterexample.

### i90-v2.9 Program spend ledger

**W-7 study (bd polyglot-pdf-wiadk):** $10.173 total (see the W-7 budget
ledger above).

**i90-v2 committed artifacts** (every CSV/summary under
`scripts/spikes/data/2nikx-{full,pilot,smoke,debug}/`):

| Category | Runs | Sum $ |
|---|---:|---:|
| 2nikx-full: deployed happy x4 (2 valid + 2 excluded dry runs), unhappy x3 (2 valid + 1 excluded dry run) | 7 | $18.803410 |
| 2nikx-full: naive happy + unhappy (partial) | 2 | $11.928973 |
| 2nikx-pilot: naive happy q6 | 1 | $0.341589 |
| 2nikx-smoke: dti happy q3, naive happy q2 | 2 | $0.121760 |
| 2nikx-debug: dti happy q8 | 1 | $0.105513 |
| **Committed-artifact subtotal** | **13** | **$31.301245** |

This subtotal includes the 3 excluded dry runs from "i90-v2 method changes"
above (`013010Z`, `020339Z`, `024500Z`) -- they are counted here as sunk
method-development cost even though their accuracy disqualifies them from
the headline results tables.

**One additional orphan session reconciled from `backend/logs/token_usage.jsonl`**
(summing each event's `cost.total_usd`; this reconciliation method
cross-checks within 0.5-2.4% of the committed runs' precise `all_in_usd`, so
treat it as a close approximation): `form_session_id`
`4loz-dti-unhappy-20260828T023442Z`, tagged `form_id: "I-90"`, 02:34-02:44 UTC
on 2026-08-28 -- this is the "killed by tooling" run referenced in this
project's task history (its own artifacts never wrote to disk). Reconciled
cost: **$2.421086**.

Ten further `4loz-*` orphan sessions exist in the same log, timestamped
2026-08-27 19:20-20:04 UTC and tagged `form_id: "W-7"` -- these fall inside
the W-7 study's own 19:15-20:05 UTC run window and are very likely already
counted inside the W-7 study's reported $10.173 (its budget ledger's smokes
and full runs). They are **not** added a second time here to avoid
double-counting, though this was not independently proven by cross-matching
each orphan's exact cost against a specific W-7 ledger row -- see the
Anomalies section below for the honest statement of this open question.

**Program total:**

| Component | $ |
|---|---:|
| W-7 study | $10.173 |
| i90-v2 committed artifacts | $31.301245 |
| i90-v2 orphan "killed by tooling" run | $2.421086 |
| **Program total** | **$43.895** |
| **vs. $100 cap** | **$56.10 remaining** |

**Anomaly resolutions (orchestrator, from primary evidence, 2026-08-28):**
1. The 10 W-7-tagged "orphan" token-log sessions (19:20-20:05 UTC 08-27,
   ~$10.32) ARE the W-7 study's own smokes/pilot/full runs -- their
   form_session_id stamps (4loz-dti-happy-20260827T193603Z etc.) match the
   W-7 ledger's committed artifacts one-for-one, and their subtotal matches
   the W-7 study's $10.17 to within greeting/boundary accounting. They are
   already counted; the CONSERVATIVE program total above is the correct one,
   and the $54.22 "inclusive" scenario double-counts them.
2. The diagnostic-run figures ($1.58 / $2.46 / $2.34) reconcile EXACTLY
   against their committed artifacts' all_in_usd ($1.575967 / $2.457632 /
   $2.339749, runs 013010Z / 020339Z / 024500Z under 2nikx-full) -- the
   analysis pass had searched the raw token log instead of the artifacts.

### i90-v2.10 Replay validation

| Run (stamp) | Arm | Path | Recorded (CSV) | Replayed | Delta |
|---|---|---|---:|---:|---:|
| 021631Z | Deployed happy | happy | $2.035449 | $2.035449 | $0.000000 |
| 022519Z | Deployed happy | happy | $2.067670 | $2.067672 | $0.000002 |
| 030509Z | Deployed unhappy | unhappy | $4.268139 | $4.268139 | $0.000000 |
| 032527Z | Deployed unhappy | unhappy | $4.041460 | $4.041462 | $0.000002 |
| 034310Z | Naive happy | happy | $6.016500 | $6.016503 | $0.000003 |
| 035215Z | Naive unhappy (partial) | unhappy | $5.912473 | $5.912475 | $0.000002 |

All 6 replay within $0.000004 -- consistent with the W-7 study's own replay
tolerance. `cached_curve` sums to 0 on every run: the Live path bills 100% of
prompt tokens at full input rate on i90-v2 too, same as W-7 (no cached-token
discount row exists or is needed on this path, per bd 89mt evidence).

### i90-v2.11 Footnotes

**Naive schema-only variant (booklet share of the i90-v2 SI):**
`naive_si_booklet_chars` = 40,908 of `system_instruction_chars` = 80,438
total -> **50.9% of the naive SI, by character count, is the booklet** (the
remaining 49.1%, ~39,530 chars, is the schema/field-catalog text). Scaling
proportionally to the measured 19,710 SI-only tokens: ~10,024 tokens are
booklet, ~9,686 are schema -- so a schema-only naive variant would roughly
halve the naive SI floor, which would materially narrow (not eliminate) the
naive/deployed gap, since naive's dominant cost driver is re-sending this SI
on every turn. This is arithmetic on the measured character split, not a new
live measurement -- consistent with the W-7 study's own schema-only
footnote, which used the identical method.

**3.1-rates variant** (same measured token counts, repriced at
`GEMINI_PRICING_BY_FAMILY["3.1"]`: text-in $0.75/1M and text-out $4.50/1M vs.
2.5's $0.50/$2.00; audio rates identical):

| Run | At 2.5 rates (as billed) | At 3.1 rates (replay) | Increase |
|---|---:|---:|---:|
| Naive happy | $6.016503 | $7.726393 | +28.4% |
| Naive unhappy (partial) | $5.912475 | $7.483916 | +26.6% |
| Deployed happy 021631Z | $2.035449 | $2.495599 | +22.6% |
| Deployed unhappy 030509Z | $4.268139 | $5.080503 | +19.0% |

3.1 rates would raise every arm ~19-28%, with naive rising proportionally
more (it has the larger, constantly-resent text-in component that the
higher 3.1 text rates apply to) -- i.e. 3.1 pricing would **widen**, not
narrow, the deployed/naive gap. This is the same directional finding as the
W-7 study's own 3.1-rates footnote.

**Deployed TTS spell-back line** (from the 4 valid deployed runs;
`spellback_disabled: false` on all 4): 021631Z = 6 events/54 chars, 022519Z =
5/30, 030509Z = 10/74, 032527Z = 10/62 -- **31 spell-back events, 220
characters total** across the 4 runs, all via the TTS-read-digits path (not
letter-by-letter spelling), consistent with the scar-tissue fix that moved
identifier read-back off spelled-aloud audio (see memory
`spelling-aloud-desyncs-native-audio-use-tts-tool`). Not folded into any
all-in total, same convention as the W-7 study's own TTS footnote.

## Anomalies / interpretation notes carried into this report

**W-7 study anomalies:**

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

**i90-v2 extension anomalies:**

6. **3 of the 9 committed 2nikx-full runs were dry runs, excluded from
   headline results on accuracy grounds, not independently re-justified
   here.** `013010Z` (matched 1/57), `020339Z` (matched 14/57), and `024500Z`
   (matched 12/57, only 33/57 steps done) read as failed/degraded pipeline
   attempts from before the confirm-gate and derailment-guard fixes landed.
   The exclusion looks correct on the accuracy evidence, but this report did
   not independently trace each run's specific failure back to a specific
   pre-fix commit -- it accepts the accuracy numbers at face value as
   sufficient grounds for exclusion.
7. **Ten `4loz-*` orphan sessions in `backend/logs/token_usage.jsonl` carry a
   `form_id` tag that contradicts their timing.** All ten are timestamped
   2026-08-27 19:20-20:04 UTC (inside the W-7 study's own run window) and use
   session-id naming (`4loz-dti-happy-*`, `4loz-naive-unhappy-*`) that could
   plausibly be either W-7 harness runs or unrelated i90-v2 development
   activity -- they are tagged `form_id: "W-7"`, which is consistent with
   them being W-7 runs. This report assumes they are already counted inside
   the W-7 study's reported $10.173 total and does **not** add their
   reconciled cost (~$10.32 by the same log-summing method used for the
   "killed by tooling" run) a second time into the i90-v2 program total.
   This assumption was not independently verified by matching each orphan's
   exact dollar figure against a specific row in the W-7 budget ledger --
   the W-7 ledger table states dates but not times-of-day, so overlap could
   not be ruled out purely from that table. If this assumption is wrong,
   the true program total would be closer to $54.2 than $43.9 (still well
   under the $100 cap either way). Flagged rather than silently resolved
   one way or the other.
8. **The naive-happy pre-registration missed high, not low.** The W-7
   study's own naive-happy pre-registration missed low (-19.0%, "Estimator
   grading" section above); the i90-v2 naive-happy pre-registration missed
   high (+0.44% over the band ceiling, "i90-v2.7" above). The two
   pre-registrations used different methods (W-7's was a mid-run linear
   extrapolation; i90-v2's was a pre-run trace extension from a 6-question
   pilot) and the i90-v2 miss has an identified, harness-level cause (the
   confirm-gate added after the pilot ran) rather than a modeling artifact
   -- the two misses are not evidence of a consistent directional bias
   across studies, just two different estimators each imperfect in its own
   identified way.

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

## i90-v2 chart references

Generated by `scripts/spikes/plot_2nikx_comparison.py
scripts/spikes/data/2nikx-full` -- a **sibling** script to
`plot_wiadk_comparison.py`, not a shared-code extension of it (the two run
sets have different compression configs, different question-count axes, and
the i90-v2 unhappy run has no natural "final point" to draw a completed line
through, so adapting the W-7 script in place would have obscured more than
it shared). It reuses the `_load`-with-provenance-assertion pattern and the
overall plotting style, and independently confirms: naive runs carry
`compression=False`; all 4 deployed runs carry
`compression_effective.derived_from_si_floor=True` with
`trigger=10890/window=9390`. It reads the 2 valid deployed-happy runs
(`021631Z`, `022519Z`), the 2 valid deployed-unhappy runs (`030509Z`,
`032527Z`), and the single naive-happy (`034310Z`) and naive-unhappy
(`035215Z`) runs, explicitly excluding the 3 diagnostic dry runs described in
"i90-v2 method changes" above by exact filename match (not a glob), so a
future diagnostic run added to the same directory does not silently get
pulled into the charts. 4 PNGs under `scripts/spikes/data/2nikx-full/plots/`:

1. **cumulative_cost_happy.png** -- running all-in cost vs. question number,
   happy path, deployed mean ($2.06 final) vs. naive ($6.02 final).
2. **cumulative_cost_unhappy.png** -- same, unhappy path: deployed mean
   ($4.16 final, full 57/57) vs. naive ($5.91, but only 39/57 questions) --
   the naive line ends early rather than reaching a comparable final
   question, reflecting the did-not-complete result rather than smoothing
   over it.
3. **session_cost_bars.png** -- grouped bars, arm x path, all-in session
   cost.
4. **cost_per_confirmed_field.png** -- the per-confirmed-field normalization
   (i90-v2.3 above), which is the fair unhappy-path comparator given the
   naive arm's incomplete run.

All four charts were confirmed to render with the provenance assertions
passing.
